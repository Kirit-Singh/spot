"""THE DOWNGRADE: deleting evidence by relabelling it unknown.

The lane checked contributor COMPLETENESS — that a determined scope names every guide
the source kept for it — and then took ``evidence_state`` itself entirely on trust. A
scope labelled ``ambiguous`` was examined by nothing, anywhere: not by the runtime
replay, not by the strict verifier, not by the schema. "The identity is unknown" was
treated as a confession no source could contradict.

The source contradicts it constantly, and the forgery is free:

    take one determined scope. Collapse its rows to a single ambiguous row citing
    nothing. Let the HONEST producer regenerate the record table and the replay report
    from those rows.

Every count now balances by construction — determined-1, ambiguous+1, named unchanged,
complete==determined, records==offsets_proven — and every hash is correct, because the
producer computed them. The manifest and the report agree perfectly. Nothing is
inconsistent with anything.

And the raw source is still holding that scope's two kept targeting guides.

The victim loses its mask, its score and its rank; the screen ships one fewer ranked
target and nobody can tell. The independent audit built exactly this, and the standalone
verifier exited 0 with 31/31 checks green.

THE RULE
--------
The manifest does not get to classify its own evidence. The SOURCE classifies it:

    provable(scope) = { g : the source kept a row for this (target, condition)
                            whose guide_type is TARGETING }

    non-empty -> DETERMINABLE. ``determined`` is mandatory.
    empty     -> genuinely non-determinable. ``ambiguous`` is the only honest label.

WHERE THE AUTHORITY LIVES
-------------------------
A fully resealed downgrade is invisible to every document the producer wrote, and that
includes the pinned replay report — a forger who has the old code simply emits
``n_scopes_downgraded: 0``. So a report-reading check cannot catch this, and the tests
below prove it: the non-strict verifier passes the forged run.

Only re-derivation from the RAW SOURCE catches it. That is why strict replay is the
release gate and why production / research_only may not skip it.
"""
from __future__ import annotations

import contextlib
import io
import os

import pandas as pd
import pytest
from direct import config, replay
from direct.manifest import ManifestError
from direct.run_screen import build_screen
from fixtures_direct import TARGET_GENES, default_specs
from test_source_replay import verify

VICTIM = TARGET_GENES[0]

DOWNGRADE_CHECK = ("STRICT: no scope the SOURCE can determine is labelled ambiguous")
OVERCLAIM_CHECK = ("STRICT: no scope the SOURCE cannot determine is labelled "
                   "determined")


# --------------------------------------------------------------------------- #
# The forger is the PRE-FIX PRODUCER ITSELF.
#
# Not a hand-edited file: the actual code that shipped before this fix, which believed
# ``evidence_state`` and reported the manifest's own split back as though the source had
# confirmed it. Everything it emits is internally perfect, because an honest program
# built it. That is the whole point — the run under test is not malformed in any way a
# consistency check can reach.
# --------------------------------------------------------------------------- #
def _manifest_trusting_classify(rows, provable):
    """Believe the labels; report zero downgrades. The old behaviour, exactly."""
    labelled: dict[tuple, str] = {}
    for row in rows:
        if not replay._is_pooled(row):
            continue
        scope = (str(row.get("target_id")), str(row.get("condition")))
        if str(row.get("evidence_state")) == "determined" \
                and not replay._excluded(row) \
                and not replay._is_null(row.get("guide_id")):
            labelled[scope] = "determined"
        else:
            labelled.setdefault(scope, "ambiguous")
    n_det = sum(1 for v in labelled.values() if v == "determined")
    return {"n_scopes_source_determinable": n_det,
            "n_scopes_source_non_determinable": len(labelled) - n_det,
            "n_scopes_downgraded": 0, "n_scopes_overclaimed": 0, "failures": []}


@pytest.fixture
def blind_producer(monkeypatch):
    """Run the generator as it was before the source classified anything."""
    monkeypatch.setattr(replay, "classify_scopes", _manifest_trusting_classify)


def downgrade(target=VICTIM):
    """Collapse a determined scope to ONE ambiguous row that cites nothing."""
    def attack(rows):
        out, seen = [], False
        for r in rows:
            if r["target_id"] != target:
                out.append(r)
                continue
            if r["evidence_state"] != "determined" or seen:
                continue
            seen = True
            out.append({k: v for k, v in r.items()
                        if k not in ("identity_method", "source_id",
                                     "source_sha256")}
                       | {"evidence_state": "ambiguous", "guide_id": None,
                          "source_record_id": None})
        return out
    return attack


def failed_checks(args, strict: bool):
    from direct.verify_run import Report, reconstruct
    rep = Report()
    with contextlib.redirect_stdout(io.StringIO()):
        reconstruct(args.out_dir, os.path.dirname(args.selection), rep, strict=strict)
    return [name for name, _detail in rep.failures]


# --------------------------------------------------------------------------- #
# 1. THE ATTACK HAS SCIENTIFIC BITE. Prove the victim really loses its rank.
# --------------------------------------------------------------------------- #
def test_the_resealed_downgrade_really_does_delete_the_victims_rank(synthetic_run,
                                                                    blind_producer):
    """Before proving it is caught, prove it is worth catching."""
    honest = build_screen(synthetic_run())
    forged = build_screen(synthetic_run(manifest_rows_fn=downgrade()))

    h = pd.read_parquet(os.path.join(honest["out_dir"], "screen.parquet")) \
        .set_index("target_id")
    f = pd.read_parquet(os.path.join(forged["out_dir"], "screen.parquet")) \
        .set_index("target_id")

    # the victim was fully evaluable, and is now excluded with no rank in either arm
    assert bool(h.loc[VICTIM, "A_evaluable"]) is True
    assert bool(f.loc[VICTIM, "A_evaluable"]) is False
    for arm in config.ARMS:
        col = config.ARM_RANK_COLUMN[arm]
        assert pd.notna(h.loc[VICTIM, col])
        assert pd.isna(f.loc[VICTIM, col])
        # ...and the published screen ships one fewer ranked target
        assert int(f[col].notna().sum()) == int(h[col].notna().sum()) - 1

    # the contributor evidence for the victim is simply gone
    hc = pd.read_parquet(os.path.join(honest["out_dir"],
                                      "contributing_guides.parquet"))
    fc = pd.read_parquet(os.path.join(forged["out_dir"],
                                      "contributing_guides.parquet"))
    assert set(hc[hc.target_id == VICTIM].guide_id.dropna()) == {"g-T0-1", "g-T0-2"}
    assert set(fc[fc.target_id == VICTIM].guide_id.dropna()) == set()


def test_the_forged_run_is_INTERNALLY_PERFECT(synthetic_run, blind_producer):
    """Nothing the producer wrote is inconsistent with anything else it wrote.

    This is what makes the attack an attack. The report balances, the manifest agrees
    with it, the hashes are right, and the NON-strict verifier — which can only read
    those documents — passes the run.
    """
    args = synthetic_run(manifest_rows_fn=downgrade())
    args.out_dir = build_screen(args)["out_dir"]

    assert verify(args, strict=False) == 0
    assert failed_checks(args, strict=False) == []


# --------------------------------------------------------------------------- #
# 2. THE STANDALONE VERIFIER, STRICT: the raw source refutes it.
# --------------------------------------------------------------------------- #
def test_the_STANDALONE_strict_verifier_catches_the_resealed_downgrade(synthetic_run,
                                                                       blind_producer):
    """Fully resealed: manifest, records, report, counts, hashes, run binding.

    The refusal must come from the SOURCE CLASSIFICATION by name. An incidental
    checksum, directory-name or schema failure would prove nothing about the rule.
    """
    args = synthetic_run(manifest_rows_fn=downgrade())
    args.out_dir = build_screen(args)["out_dir"]

    failed = failed_checks(args, strict=True)
    assert DOWNGRADE_CHECK in failed, failed
    assert verify(args, strict=True) == 1

    # ...and it is NOT a hash, an id, a schema or a directory-name failure
    incidental = [c for c in failed
                  if "sha256" in c or "run_id" in c or "bytes matching" in c
                  or "schema" in c]
    assert not incidental, f"the refusal was incidental, not semantic: {incidental}"


def test_the_strict_verifier_also_binds_the_two_HALVES_of_the_partition(
        synthetic_run, blind_producer):
    """The SUM is invariant under the swap. Each half is not."""
    args = synthetic_run(manifest_rows_fn=downgrade())
    args.out_dir = build_screen(args)["out_dir"]

    failed = failed_checks(args, strict=True)
    assert "STRICT: the DETERMINED half of the partition is the source's" in failed
    assert "STRICT: the AMBIGUOUS half of the partition is the source's" in failed
    # the old sum-only check is still satisfied by the forgery — which is why it was
    # never enough on its own
    assert ("STRICT: determined + ambiguous scopes are EVERY released scope"
            not in failed)


@pytest.mark.parametrize("victim", [TARGET_GENES[1], TARGET_GENES[2],
                                    TARGET_GENES[5]])
def test_the_strict_verifier_catches_a_downgrade_of_ANY_scope(synthetic_run,
                                                              blind_producer, victim):
    args = synthetic_run(manifest_rows_fn=downgrade(victim))
    args.out_dir = build_screen(args)["out_dir"]
    assert DOWNGRADE_CHECK in failed_checks(args, strict=True)


# --------------------------------------------------------------------------- #
# 3. THE RUNTIME, FRESH STRICT REPLAY: a release lane refuses to build it at all.
#
# The evidence bundle is sealed by the blind producer, so the PINNED report says zero
# downgrades. The release lane then re-derives completeness from the raw source in its
# own invocation — with the real rule — and the fresh verdict disagrees with the pinned
# one. There is no artifact.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("lane", ["production", "research_only"])
def test_a_release_lane_FRESH_replay_refuses_a_bundle_sealed_by_the_blind_producer(
        synthetic_run, monkeypatch, lane):
    monkeypatch.setattr(replay, "classify_scopes", _manifest_trusting_classify)
    args = synthetic_run(lane=lane, manifest_rows_fn=downgrade())
    monkeypatch.undo()                 # the RUN replays with the real rule

    from direct import gate
    with pytest.raises((gate.GateError, ManifestError)):
        build_screen(args)
    assert not os.path.exists(args.out_root)


def test_the_runtime_refuses_the_downgrade_by_NAME_when_it_replays_honestly(
        synthetic_run):
    """The everyday path: the producer is honest, so the report itself indicts."""
    with pytest.raises(ManifestError, match="raw source can DETERMINE"):
        build_screen(synthetic_run(manifest_rows_fn=downgrade()))


# --------------------------------------------------------------------------- #
# 4. THE MIRROR LIE: evidence invented for a scope the source cannot prove.
# --------------------------------------------------------------------------- #
def _unprovable_specs(target=TARGET_GENES[5]):
    """That target emits NO contributor rows in the raw source at all."""
    from dataclasses import replace
    return [replace(s, ambiguous_estimates=("main",)) if s.target == target else s
            for s in default_specs()]


def _rule_failures(rows, raw):
    """Drive the STANDALONE classification rule directly, over a raw source.

    Directly, and not through a built run, for the same reason the replay-arithmetic
    attacks are: a forged run also breaks its own hashes, so a test that only asserted a
    non-zero exit would pass even if the rule did not exist. What has to be shown is
    that the rule REFUSES a manifest the source refutes.
    """
    import numpy as np
    from direct import verify_classification as VC
    from direct.verify_run import Report

    cols = {k: np.array([r[k] for r in raw], dtype=object) for k in
            ("guide_id", "perturbed_gene_id", "culture_condition", "keep_for_DE",
             "guide_type")}
    rep = Report()
    VC.check_source_classification({"rows": rows},
                                   VC.source_determinable_scopes(cols), rep)
    return [name for name, _detail in rep.failures]


def _pooled(target, **over):
    row = {"estimate_type": "main", "estimate_id": "main", "target_id": target,
           "condition": "StimX", "donor_pair": None, "evidence_state": "determined",
           "guide_id": f"g-{target}-1"}
    return row | over


def test_the_standalone_RULE_refuses_an_OVERCLAIMED_scope():
    """The source kept no targeting guide for it. The manifest names one anyway."""
    from fixtures_evidence import raw_source_rows

    raw = raw_source_rows(_unprovable_specs())        # T5 has NO rows at all
    rows = [_pooled(TARGET_GENES[5], guide_id="g-T5-1")]
    assert OVERCLAIM_CHECK in _rule_failures(rows, raw)


def test_the_standalone_RULE_refuses_a_DOWNGRADED_scope():
    """The mirror: the source proves it, the manifest calls it unknown."""
    from fixtures_evidence import raw_source_rows

    raw = raw_source_rows(default_specs())            # T0 keeps g-T0-1, g-T0-2
    rows = [_pooled(VICTIM, evidence_state="ambiguous", guide_id=None)]
    assert DOWNGRADE_CHECK in _rule_failures(rows, raw)


def test_the_standalone_RULE_accepts_an_HONEST_partition():
    """A rule that refuses everything proves nothing."""
    from fixtures_evidence import raw_source_rows

    raw = raw_source_rows(_unprovable_specs())
    rows = [_pooled(VICTIM, guide_id="g-T0-1"), _pooled(VICTIM, guide_id="g-T0-2"),
            _pooled(TARGET_GENES[5], evidence_state="ambiguous", guide_id=None)]
    assert _rule_failures(rows, raw) == []


def test_the_two_RULES_together_leave_no_gap(synthetic_run):
    """Relabel and the source refutes the LABEL. Drop a guide and it refutes the SET.

    Keeping one determined row and dropping its sibling is not a downgrade — the scope
    is still determined, so classification is satisfied. It is a SHRUNKEN CONTRIBUTOR
    SET, and completeness is what must refuse it. Neither rule covers the other, and
    between them there is nowhere for a contributor to go.
    """
    from fixtures_evidence import raw_source_rows

    raw = raw_source_rows(default_specs())
    rows = [_pooled(VICTIM, guide_id="g-T0-1")]       # one of T0's two guides
    assert _rule_failures(rows, raw) == []            # classification: satisfied

    def drop_a_guide(rows):
        return [r for r in rows
                if not (r["target_id"] == VICTIM and r["guide_id"] == "g-T0-2")]

    with pytest.raises(ManifestError, match="whole contributor set"):
        build_screen(synthetic_run(manifest_rows_fn=drop_a_guide))


# --------------------------------------------------------------------------- #
# 5. NO FALSE POSITIVES. A rule that refuses everything is not a rule.
# --------------------------------------------------------------------------- #
def test_a_GENUINELY_unprovable_scope_passes_both_gates_cleanly(synthetic_run):
    """The source keeps no targeting guide for it, so ambiguous is the TRUTH."""
    args = synthetic_run(specs=_unprovable_specs())
    args.out_dir = build_screen(args)["out_dir"]

    assert verify(args, strict=True) == 0
    assert failed_checks(args, strict=True) == []

    screen = pd.read_parquet(os.path.join(args.out_dir, "screen.parquet")) \
        .set_index("target_id")
    assert bool(screen.loc[TARGET_GENES[5], "A_evaluable"]) is False


def test_the_honest_default_bundle_passes_both_gates_cleanly(synthetic_run):
    args = synthetic_run()
    args.out_dir = build_screen(args)["out_dir"]
    assert verify(args, strict=True) == 0
    assert failed_checks(args, strict=True) == []


def test_a_NON_TARGETING_control_never_makes_a_scope_determinable(synthetic_run):
    """The classification counts TARGETING guides only.

    A kept non-targeting control row is not evidence that a perturbation happened, so a
    scope whose only kept rows were controls must stay genuinely ambiguous — never
    forced into ``determined`` by the mere presence of rows.
    """
    from fixtures_evidence import NON_TARGETING_GUIDES, NON_TARGETING_TARGET, raw_source_rows
    raw = raw_source_rows(default_specs())
    controls = [r for r in raw if r["guide_id"] in NON_TARGETING_GUIDES]
    assert controls, "the fixture no longer ships non-targeting controls"
    assert all(r["perturbed_gene_id"] == NON_TARGETING_TARGET for r in controls)

    cols = {k: [r[k] for r in raw] for k in
            ("guide_id", "perturbed_gene_id", "culture_condition", "keep_for_DE",
             "guide_type")}
    import numpy as np
    provable = replay.source_provable_guides(
        {k: np.array(v, dtype=object) for k, v in cols.items()})

    # the control target is KEPT in the source, and is still not determinable
    assert not any(sc[0] == NON_TARGETING_TARGET for sc in provable)
    # ...while every real target is
    assert (TARGET_GENES[0], "StimX") in provable
