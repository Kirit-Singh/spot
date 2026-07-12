"""THE SELF-HASHED REPORT: a producer's arithmetic is not a proof of its arithmetic.

The replay report is written by the producer, hashed by the producer, and pinned by a
manifest the same producer wrote. Every field in it is a CLAIM. So a report can be
perfectly well-formed, correctly pinned, byte-identical to its hash — and still say
"33,983 scopes determined, 33,977 proven complete, 0 incomplete", which does not add
up, and which means six released scopes were never examined at all.

Nothing in the pinned artifact stops that. The only defence is to check the report's own
counters against each other AND against the independently derived universe, and to
require that the report say WHICH RULE produced them: a "complete" computed under some
other rule is not this gate's "complete", and a report naming no rule has answered an
unknown question.

Each attack below is an HONEST-PRODUCER forgery: the tampered report is re-pinned so its
hash matches its bytes. A refusal therefore has to come from the arithmetic or from the
rule id — never from a hash mismatch, which would prove nothing about either.
"""
from __future__ import annotations

import copy
import os

import pytest
from direct import replay
from direct.manifest import ManifestError
from direct.run_screen import build_screen
from fixtures_direct import TARGET_GENES
from fixtures_spec import TargetSpec
from test_source_replay import run_and_verify, verify

RULE_IDS = ("replay_rule_id", "completeness_rule_id")


def _forge(**over):
    """Rewrite the pinned report's fields, keeping it internally hash-consistent."""
    def _fn(report: dict) -> dict:
        out = copy.deepcopy(report)
        out.update(over)
        return out
    return _fn


# --------------------------------------------------------------------------- #
# 1. THE RULE IDS. A verdict is only interpretable under the rule that made it.
# --------------------------------------------------------------------------- #
def test_the_v2_report_stamps_both_rule_ids():
    from direct import manifest_schema as MS
    assert replay.REPLAY_RULE_ID == MS.REPLAY_RULE_ID
    assert replay.COMPLETENESS_RULE_ID == MS.COMPLETENESS_RULE_ID
    # ...and both are REQUIRED of any report the lane will accept
    for key in RULE_IDS:
        assert key in MS.REPLAY_COMPLETENESS_KEYS


@pytest.mark.parametrize("key", RULE_IDS)
def test_a_report_that_names_no_rule_is_refused(synthetic_run, key):
    """Silence is not assent: a report with no rule id answered an unknown question."""
    def drop(report):
        out = copy.deepcopy(report)
        out.pop(key)
        return out

    with pytest.raises(ManifestError, match="completeness field"):
        build_screen(synthetic_run(source_replay_fn=drop))


@pytest.mark.parametrize("key", RULE_IDS)
def test_a_report_computed_under_a_DIFFERENT_rule_is_refused(synthetic_run, key):
    """A v1 'complete' is not a v2 'complete', however honestly it is pinned."""
    forged = _forge(**{key: "spot.stage02.direct.replay_rule.v1"})
    with pytest.raises(ManifestError, match="rule_id"):
        build_screen(synthetic_run(source_replay_fn=forged))


@pytest.mark.parametrize("key", RULE_IDS)
def test_the_standalone_verifier_also_demands_the_exact_rule_ids(synthetic_run, key):
    """The generator and the verifier must refuse it INDEPENDENTLY."""
    from direct import verify_source as VS
    assert VS.REPLAY_RULE_ID == replay.REPLAY_RULE_ID
    assert VS.COMPLETENESS_RULE_ID == replay.COMPLETENESS_RULE_ID
    assert key in VS.COMPLETENESS_KEYS


# --------------------------------------------------------------------------- #
# 2. THE ARITHMETIC. Each identity is a distinct way to count a scope as proven
#    without ever having examined it.
# --------------------------------------------------------------------------- #
def test_complete_must_equal_determined(synthetic_run):
    """Six determined scopes quietly unproven, and the verdict still says 'complete'."""
    def forge(report):
        out = copy.deepcopy(report)
        out["n_scopes_complete"] = out["n_scopes_determined"] - 1
        return out

    with pytest.raises(ManifestError, match="proven complete"):
        build_screen(synthetic_run(source_replay_fn=forge))


def test_complete_plus_incomplete_must_equal_determined(synthetic_run):
    """A determined scope that is NEITHER complete nor incomplete was never examined."""
    def forge(report):
        out = copy.deepcopy(report)
        out["n_scopes_determined"] = out["n_scopes_determined"] + 2
        out["n_scopes_named"] = out["n_scopes_named"] + 2
        return out

    with pytest.raises(ManifestError):
        build_screen(synthetic_run(source_replay_fn=forge))


def test_named_must_equal_determined_plus_ambiguous(synthetic_run):
    """The report has to agree with its own total before anyone believes a part of it."""
    def forge(report):
        out = copy.deepcopy(report)
        out["n_scopes_named"] = out["n_scopes_named"] + 5
        return out

    with pytest.raises(ManifestError, match="n_scopes_named"):
        build_screen(synthetic_run(source_replay_fn=forge))


def test_a_report_that_looked_at_fewer_scopes_than_the_manifest_holds_is_refused(
        synthetic_run):
    """A scope the report never looked at cannot be reported complete."""
    def forge(report):
        out = copy.deepcopy(report)
        out["n_scopes_determined"] -= 1
        out["n_scopes_complete"] -= 1
        out["n_scopes_named"] -= 1
        return out

    with pytest.raises(ManifestError):
        build_screen(synthetic_run(source_replay_fn=forge))


# --------------------------------------------------------------------------- #
# 2b. THE RELABELLING. Every total balances, and six scopes stop being proven.
#
# This is the attack the totals CANNOT see, and it is the cheapest one available: do not
# change a single sum — just move scopes from the determined column to the ambiguous one.
#
#   named            == determined + ambiguous     still true (0 + 2 == 2)
#   complete         == determined                 still true (0 == 0)
#   complete + incomplete == determined            still true (0 + 0 == 0)
#   determined + ambiguous == manifest scopes      still true (0 + 2 == 2)
#   determined + ambiguous == released universe    still true
#   n_records / n_replayed / offset_proven / hashes      all untouched
#
# Every identity the runtime checked held. And a scope that DOES carry evidence — that
# has a determined row, a guide, a citation and a source record — was quietly excused
# from ever having to be proven COMPLETE, because only determined scopes are. The
# report is now describing a manifest that does not exist.
#
# The only thing that can see it is the split itself, derived from the CURRENT rows.
# --------------------------------------------------------------------------- #
def _relabel_determined_as_ambiguous(report):
    """Move every determined scope into the ambiguous column. Preserve every total."""
    out = copy.deepcopy(report)
    determined = out["n_scopes_determined"]
    out["n_scopes_determined"] = 0
    out["n_scopes_ambiguous"] = out["n_scopes_ambiguous"] + determined
    out["n_scopes_complete"] = 0
    out["n_scopes_incomplete"] = 0
    return out


def _one_determined_one_ambiguous():
    """The minimal manifest that can be relabelled: one of each."""
    return [
        TargetSpec(TARGET_GENES[0], ["g-D-1"], 1.0, a_effect=-1.0,
                   manifest_main=["g-D-1"]),
        TargetSpec(TARGET_GENES[1], ["g-A-1"], 1.0, a_effect=-1.0,
                   ambiguous_estimates=("main",)),
    ]


def test_the_honest_report_over_this_manifest_really_is_one_and_one(synthetic_run):
    """Pin the baseline the attack perverts, so the attack cannot be vacuous."""
    seen = {}

    def capture(report):
        seen.update(report)
        return report

    build_screen(synthetic_run(specs=_one_determined_one_ambiguous(),
                               source_replay_fn=capture))
    assert seen["n_scopes_determined"] == 1
    assert seen["n_scopes_ambiguous"] == 1
    assert seen["n_scopes_named"] == 2
    assert seen["n_scopes_complete"] == 1
    assert seen["n_scopes_incomplete"] == 0


def test_the_RUNTIME_refuses_a_report_that_RELABELS_a_determined_scope(synthetic_run):
    """The named split check must fire — NOT a hash mismatch, and not a total."""
    honest = {}

    def forge(report):
        honest.update(copy.deepcopy(report))
        return _relabel_determined_as_ambiguous(report)

    with pytest.raises(ManifestError, match="determined scope") as exc:
        build_screen(synthetic_run(specs=_one_determined_one_ambiguous(),
                                   source_replay_fn=forge))

    # It was refused BY THE SPLIT, and the message says so.
    assert "relabels a determined scope as ambiguous" in str(exc.value)

    # ...and every identity the old code checked still balanced perfectly. This is what
    # makes the attack an attack: nothing else in the report was wrong.
    forged = _relabel_determined_as_ambiguous(honest)
    assert forged["n_scopes_named"] == (forged["n_scopes_determined"]
                                        + forged["n_scopes_ambiguous"])
    assert forged["n_scopes_complete"] == forged["n_scopes_determined"]
    assert (forged["n_scopes_complete"] + forged["n_scopes_incomplete"]
            == forged["n_scopes_determined"])
    assert (forged["n_scopes_determined"] + forged["n_scopes_ambiguous"]
            == honest["n_scopes_determined"] + honest["n_scopes_ambiguous"])
    for untouched in ("n_records", "n_replayed", "n_records_offset_proven",
                      "source_sha256", "source_record_table_sha256",
                      "completeness_verdict", "verdict"):
        assert forged[untouched] == honest[untouched]


def test_the_runtime_refuses_the_relabelling_at_FULL_manifest_scale_too(synthetic_run):
    """Not an artefact of a two-row manifest: the default bundle relabels the same way."""
    with pytest.raises(ManifestError, match="determined scope"):
        build_screen(synthetic_run(
            source_replay_fn=_relabel_determined_as_ambiguous))


def test_the_runtime_refuses_an_inflated_AMBIGUOUS_count(synthetic_run):
    """The other half of the split. Claiming ambiguity you do not have is also a lie."""
    def forge(report):
        out = copy.deepcopy(report)
        out["n_scopes_ambiguous"] += 1
        out["n_scopes_determined"] -= 1
        out["n_scopes_complete"] -= 1
        return out

    with pytest.raises(ManifestError, match="determined scope"):
        build_screen(synthetic_run(source_replay_fn=forge))


def test_the_runtime_and_the_standalone_verifier_AGREE_about_the_split(synthetic_run):
    """Parity: the same relabelling dies on both sides, by the same rule."""
    with pytest.raises(ManifestError, match="determined scope"):
        build_screen(synthetic_run(
            source_replay_fn=_relabel_determined_as_ambiguous))

    # the standalone rule, driven directly (a perfect hash, wrong numbers)
    relabelled = _relabel_determined_as_ambiguous(HONEST)
    assert _verifier_failures(relabelled)


# --------------------------------------------------------------------------- #
# 2c. THE SUMMARY VERDICT must be DERIVED from the fields, not asserted beside them.
#
# Every check in the lane interrogates a specific counter. A forger who reseals a report
# can leave every one of them honest and forge — or simply DELETE — the one-word summary
# that consumers actually branch on. Nothing compared the headline to the body, so the
# summary was a free-standing claim.
#
# The derivation is now required as an EQUIVALENCE in both directions:
#
#     complete  <->  no incomplete scope, no non-targeting citation, no downgrade,
#                    no overclaim, every offset proof confirmed
#     replayed  <->  no failed record AND complete
# --------------------------------------------------------------------------- #
SUMMARY_CHECK = "was not computed from them"
VERDICT_CHECK = "not redeemed by honest fields underneath it"


def test_an_OMITTED_top_level_verdict_is_refused(synthetic_run):
    """Absence is not assent. Every field underneath is honest."""
    def forge(report):
        out = copy.deepcopy(report)
        out.pop("verdict")
        return out

    with pytest.raises(ManifestError, match=VERDICT_CHECK):
        build_screen(synthetic_run(source_replay_fn=forge))


def test_an_OMITTED_completeness_verdict_is_refused(synthetic_run):
    def forge(report):
        out = copy.deepcopy(report)
        out.pop("completeness_verdict")
        return out

    with pytest.raises(ManifestError):
        build_screen(synthetic_run(source_replay_fn=forge))


@pytest.mark.parametrize("forged", ["refused", "REPLAYED", "ok", "", "partial"])
def test_a_WRONG_top_level_verdict_is_refused_by_summary_consistency(synthetic_run,
                                                                     forged):
    """The body says replayed. The headline says otherwise. They must agree."""
    with pytest.raises(ManifestError, match=VERDICT_CHECK):
        build_screen(synthetic_run(source_replay_fn=_forge(verdict=forged)))


def test_a_WRONG_completeness_verdict_is_refused_by_summary_consistency(synthetic_run):
    with pytest.raises(ManifestError, match=SUMMARY_CHECK):
        build_screen(synthetic_run(
            source_replay_fn=_forge(completeness_verdict="incomplete")))


def test_a_report_claiming_COMPLETE_over_failing_fields_is_refused(synthetic_run):
    """The other direction: the headline lies UPWARD.

    A specific counter catches this first, which is correct — the specific cause is the
    better diagnosis. What the summary rule adds is that there is no way to satisfy the
    counters and the headline independently: they are the same statement.
    """
    def forge(report):
        out = copy.deepcopy(report)
        out["n_scopes_incomplete"] = 1          # the body now says NOT complete...
        out["completeness_verdict"] = "complete"   # ...and the headline still says it is
        return out

    with pytest.raises(ManifestError, match="INCOMPLETE"):
        build_screen(synthetic_run(source_replay_fn=forge))


def test_the_summary_rule_ACCEPTS_the_honest_report(synthetic_run):
    """An equivalence that refuses everything is not an equivalence."""
    result = build_screen(synthetic_run())
    assert result["run_id"]


# --------------------------------------------------------------------------- #
# 3. THE STANDALONE VERIFIER refuses the same arithmetic, INDEPENDENTLY.
#
# These drive the verifier's rule DIRECTLY rather than by rewriting the pinned report
# on disk, and the distinction is not pedantry. Editing the report changes its bytes,
# so the verifier stops at "replay report present with bytes matching its pin" — a HASH
# failure. A test that forged the file and asserted a non-zero exit would pass without
# the arithmetic check existing at all, and would keep passing if it were deleted. What
# has to be proven here is that the verifier refuses a report whose hash is PERFECT and
# whose numbers do not add up, so the report is handed to the rule directly.
# --------------------------------------------------------------------------- #
HONEST = {"n_scopes_determined": 33977, "n_scopes_ambiguous": 6,
          "n_scopes_named": 33983, "n_scopes_complete": 33977,
          "n_scopes_incomplete": 0}
COVERAGE = {"n_released": 33983, "n_determined": 33977, "n_ambiguous": 6}


def _verifier_failures(report, coverage=COVERAGE):
    from direct import verify_source as VS
    from direct.verify_run import Report
    rep = Report()
    VS.check_scope_arithmetic(report, coverage, rep)
    return [name for name, _detail in rep.failures]


def test_the_verifier_accepts_arithmetic_that_actually_adds_up():
    """A guard that never passes is as useless as one that never fails."""
    assert _verifier_failures(HONEST) == []


def test_the_verifier_refuses_an_internally_inconsistent_report():
    """determined=33983, complete=33977, incomplete=0 — six scopes never examined."""
    forged = dict(HONEST, n_scopes_complete=33977 - 6, n_scopes_incomplete=0)
    assert _verifier_failures(forged)


def test_the_verifier_refuses_a_report_that_relabels_determined_as_ambiguous():
    """The TOTAL still matches the release. Six scopes have simply stopped proving.

    This is why matching only determined+ambiguous against n_released is not enough:
    that sum is preserved by construction here, and yet the report has proven strictly
    less than the manifest claims. Only comparing the two counts SEPARATELY sees it.
    """
    forged = dict(HONEST, n_scopes_determined=33971, n_scopes_ambiguous=12,
                  n_scopes_complete=33971)
    assert sum(forged[k] for k in ("n_scopes_determined",
                                   "n_scopes_ambiguous")) == COVERAGE["n_released"]
    assert _verifier_failures(forged)


def test_the_verifier_refuses_a_report_whose_counters_are_missing_or_junk():
    """A missing operand must not silently become a sentinel that a comparison passes."""
    for key in ("n_scopes_determined", "n_scopes_complete", "n_scopes_named"):
        forged = {k: v for k, v in HONEST.items() if k != key}
        assert _verifier_failures(forged)


def test_the_verifier_refuses_a_report_describing_a_DIFFERENT_universe():
    """The report is about the release the run actually projected, or it is about
    nothing."""
    assert _verifier_failures(HONEST, {"n_released": 33982, "n_determined": 33976,
                                       "n_ambiguous": 6})


# --------------------------------------------------------------------------- #
# 4. ...and the pinned-bytes check is still there underneath it all.
# --------------------------------------------------------------------------- #
def test_editing_the_pinned_report_on_disk_is_caught_by_its_hash(synthetic_run):
    """Belt and braces: the arithmetic gate does not replace the pin, it backs it up."""
    import json

    from fixtures_evidence import REPLAY_REPORT_NAME

    args = run_and_verify(synthetic_run())
    assert verify(args, strict=False) == 0

    path = os.path.join(os.path.dirname(args.selection), REPLAY_REPORT_NAME)
    with open(path) as fh:
        report = json.load(fh)
    report["n_scopes_complete"] = report["n_scopes_determined"] - 1
    with open(path, "w") as fh:
        json.dump(report, fh, indent=2, sort_keys=True)

    assert verify(args, strict=False) == 1
