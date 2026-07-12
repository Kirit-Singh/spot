"""THE RELEASE GATE: a build may not be weaker than the preflight of its own inputs.

Three bypasses existed. The first two are the same shape — a check that lived only on a
path nobody was obliged to take:

  1. ``--preflight-only`` ran the refusals. A normal build called ``build_screen``
     directly, so the checks that turn a missing manifest into a NO_GO never ran, and
     the run emitted a complete screen of nulls with a run_id, a provenance block and a
     verification record. "We were never shown the evidence" was dressed up as "we
     looked and found nothing".
  2. strict replay was the release gate in the docs, and optional in the code. A
     release-grade lane could stand on the PINNED replay report — a claim by the
     producer, certifying itself — while the artifact recorded that the gate had been
     satisfied.

The third was the FIX for (2), and it was worse than the bug. A release lane could skip
strict replay by presenting a "pinned strict-preflight GO artifact", whose sha256 was
hashed into run_id. But the artifact was authenticated against NOTHING: the entire check
was that a JSON object said ``verdict: GO`` and ``strict_replay: {ran: true, agrees:
true}``. Five fields, all of them the forger's to write. It was also bound to no context
— nothing tied it to this run's manifest, sources, table or domain — so a GENUINE GO
from one run authorised any other run over different evidence. Hashing it into run_id
proved only which forgery the run had committed to.

So it is gone: no argument, no state, no loader, no path. A release-grade lane
(``production`` / ``research_only``) must re-derive completeness from the raw source in
THIS invocation, and nothing may stand in for that. Every refusal below writes ZERO
artifacts: the tests assert the absence of the output tree, not merely the absence of a
score.
"""
from __future__ import annotations

import ast
import inspect
import json
import os

import pytest

from direct import cli, gate, preflight, runid
from direct.run_screen import build_screen, prepare


def _artifacts(args):
    """Every file the run could possibly have written."""
    root = args.out_root
    if not os.path.exists(root):
        return []
    return [os.path.join(d, f) for d, _s, fs in os.walk(root) for f in fs]


# --------------------------------------------------------------------------- #
# 1. Absent contributor evidence — on EVERY path, not just --preflight-only.
# --------------------------------------------------------------------------- #
def test_a_build_with_no_manifest_refuses_and_writes_nothing(synthetic_run):
    args = synthetic_run(manifest=False)
    with pytest.raises(gate.GateError):
        build_screen(args)
    assert _artifacts(args) == []


def test_the_direct_API_fails_closed_too_not_just_the_CLI(synthetic_run):
    """build_screen IS the API a notebook or a sibling lane would call."""
    args = synthetic_run(manifest=False)
    with pytest.raises(gate.GateError) as exc:
        build_screen(args)
    assert exc.value.report["verdict"] == preflight.NO_GO


def test_the_cli_turns_the_refusal_into_a_nonzero_exit(synthetic_run):
    """A gate nobody can branch on is a gate nobody will gate on."""
    from direct import cli
    args = synthetic_run(manifest=False)
    argv = ["--selection", args.selection, "--registry", args.registry,
            "--de-main", args.de_main, "--by-guide", args.by_guide,
            "--by-donors", args.by_donors, "--sgrna", args.sgrna,
            "--source-registry", args.source_registry,
            "--stage1-validation", args.stage1_validation,
            "--stage1-gate-spec", args.stage1_gate_spec,
            "--lane", "synthetic", "--out-root", args.out_root]
    result = cli.main(argv)
    assert result["verdict"] == preflight.NO_GO
    assert cli._exit_code(result) == 1
    assert _artifacts(args) == []


# --------------------------------------------------------------------------- #
# 2. A failed preflight check aborts the build.
# --------------------------------------------------------------------------- #
def test_a_failed_preflight_check_stops_the_build_before_any_output(synthetic_run,
                                                                    monkeypatch):
    """Any NO_GO — not only the manifest one — must abort before the dense read."""
    args = synthetic_run()

    real = preflight.assess

    def refusing(a, ctx):
        report = real(a, ctx)
        report["failures"] = [{"check": "support_is_explicitly_unavailable",
                               "error": "the support contract claims support"}]
        report["verdict"] = preflight.NO_GO
        return report

    monkeypatch.setattr(preflight, "assess", refusing)
    with pytest.raises(gate.GateError):
        build_screen(args)
    assert _artifacts(args) == []


def test_the_build_and_the_preflight_ask_the_SAME_questions(synthetic_run):
    """A preflight of different checks would certify a different program."""
    args = synthetic_run()
    ctx = prepare(args)
    assert preflight.assess(args, ctx)["checks"] == list(preflight.CHECKS)
    assert gate.CHECK_STRICT in preflight.CHECKS


# --------------------------------------------------------------------------- #
# 3. STRICT REPLAY: fresh, or pinned-and-bound. Never "the report says so".
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("lane", ["production", "research_only"])
def test_a_release_lane_may_not_stand_on_the_pinned_report_alone(synthetic_run, lane):
    """The bypass: trusting the producer's own claim and calling it a gate.

    ``strict_replay=False`` is now the ONLY way a release lane can arrive at the gate
    without a fresh replay, and there is nothing left to present instead. It refuses.
    """
    args = synthetic_run(lane=lane, strict_replay=False)
    with pytest.raises(gate.GateError, match="release-grade"):
        build_screen(args)
    assert _artifacts(args) == []


@pytest.mark.parametrize("lane", ["production", "research_only"])
def test_a_release_lane_accepts_a_FRESH_strict_replay(synthetic_run, lane):
    """The ONE way through: replay the raw source HERE, and bind that into run_id."""
    args = synthetic_run(lane=lane, strict_replay=True)
    result = build_screen(args)
    bound = result["verification"]
    assert bound["run_id"] == result["run_id"]

    with open(os.path.join(result["out_dir"], "provenance.json")) as fh:
        prov = json.load(fh)
    g = prov["run_binding"]["stage2_release_gate"]
    assert g["state"] == gate.GATE_FRESH
    assert g["strict_replay_required"] is True
    assert g["strict_replay_ran"] is True
    # ...and the gate really is INSIDE the identity: it is hashed with the rest.
    assert prov["run_binding_sha256"] == runid.run_id_of(prov["run_binding"])[1]
    assert g["gate_id"] == gate.GATE_ID


def test_a_synthetic_fixture_lane_needs_no_gate_and_says_so(synthetic_run):
    """The fixture lane is a unit-test lane. It must never LOOK like a release."""
    result = build_screen(synthetic_run(lane="synthetic"))
    with open(os.path.join(result["out_dir"], "provenance.json")) as fh:
        prov = json.load(fh)
    g = prov["run_binding"]["stage2_release_gate"]
    assert g["state"] == gate.GATE_NOT_REQUIRED
    assert g["strict_replay_required"] is False


# --------------------------------------------------------------------------- #
# 4. THE DELETED SHORTCUT: a "pinned strict-preflight GO artifact".
#
# It let a release lane skip strict replay by presenting a JSON file. The whole
# authentication was that the file said GO and claimed a strict replay had agreed —
# five fields, every one of them the forger's to write, checked against no expected
# hash and bound to no manifest, source, table or domain.
#
# These tests attack what a forger would actually do, and each must fail for a
# STRUCTURAL reason: the path does not exist to be attacked.
# --------------------------------------------------------------------------- #
FORGED_GO = {
    "schema_version": "spot.stage02_direct_preflight.v1",
    "verdict": "GO",
    "strict_replay": {"ran": True, "agrees_with_pinned_report": True,
                      "verdict": "replayed", "completeness_verdict": "complete"},
    "release_gate": {"state": "pinned_strict_preflight_go"},
    "failures": [],
}


def test_a_hand_authored_GO_artifact_has_nowhere_left_to_be_passed(synthetic_run,
                                                                   tmp_path):
    """THE forgery, written out in full — and there is no longer an argument for it.

    This is the exact five-field document the old loader accepted. It is not refused by
    a better check; it is refused because the parameter, the loader, the gate state and
    the RunArgs field it needed have all been removed. A gate a producer can satisfy by
    authoring a file is not a gate, so the file has nowhere to go.
    """
    path = os.path.join(str(tmp_path), "forged_preflight.json")
    with open(path, "w") as fh:
        json.dump(FORGED_GO, fh)

    # (a) the CLI will not accept it
    with pytest.raises(SystemExit):
        cli.main(["--selection", "x", "--registry", "x", "--de-main", "x",
                  "--by-guide", "x", "--by-donors", "x", "--sgrna", "x",
                  "--strict-preflight", path])

    # (b) the gate module has no loader, no pinned state and no parameter for it
    assert not hasattr(gate, "load_strict_preflight")
    assert not hasattr(gate, "GATE_PINNED")
    assert "pinned_strict_preflight_go" not in gate.GATE_STATES
    assert "strict_preflight_path" not in inspect.signature(
        gate.release_gate).parameters

    # (c) ...so a release run holding the forgery still refuses, and writes nothing
    args = synthetic_run(lane="production", strict_replay=False)
    with pytest.raises(gate.GateError, match="release-grade"):
        build_screen(args)
    assert _artifacts(args) == []


RETIRED_PINNED_TOKENS = (
    "strict_preflight", "strict-preflight", "GATE_PINNED",
    "pinned_strict_preflight_go", "load_strict_preflight",
    "strict_preflight_sha256",
)

# The verifier names the retired state ON PURPOSE — it refuses it by name, so a run that
# somehow emitted one gets a named refusal instead of a puzzled "unknown state".
REFUSES_BY_NAME = {"verify_binding.py"}


def _executable_tokens(path):
    """Every identifier and non-docstring string literal in a module.

    Docstrings and comments are excluded deliberately: the modules EXPLAIN why the
    pinned-preflight shortcut was deleted, and that prose is the point — it is what
    stops someone reintroducing it. What must not survive is anything the interpreter
    can reach. So this walks the AST rather than grepping the text: a name that no
    longer exists cannot be called, and a flag that is not registered cannot be passed.
    """
    tree = ast.parse(open(path).read())
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            body = getattr(node, "body", None)
            if body and isinstance(body[0], ast.Expr) \
                    and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                docstrings.add(id(body[0].value))

    tokens = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            tokens.add(node.id)
        elif isinstance(node, ast.Attribute):
            tokens.add(node.attr)
        elif isinstance(node, ast.arg):
            tokens.add(node.arg)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            tokens.add(node.name)
        elif isinstance(node, ast.keyword) and node.arg:
            tokens.add(node.arg)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and id(node) not in docstrings:
            tokens.add(node.value)
    return tokens


def test_no_pinned_preflight_PATH_survives_anywhere_in_the_package():
    """Dead code is a live gate. Prove the shortcut is unreachable, by AST.

    A removed call site is not a removed capability: as long as the loader, the gate
    state or the CLI flag still EXISTS, re-enabling the bypass is a one-line change that
    no test would notice. So every module is parsed and every reachable identifier,
    keyword and string literal is checked — the argparse flag included, since it is a
    plain string constant.
    """
    import direct
    pkg = os.path.dirname(os.path.abspath(direct.__file__))
    offenders = {}
    for fn in sorted(os.listdir(pkg)):
        if not fn.endswith(".py") or fn in REFUSES_BY_NAME:
            continue
        tokens = _executable_tokens(os.path.join(pkg, fn))
        hits = sorted({t for t in RETIRED_PINNED_TOKENS
                       if any(t in tok for tok in tokens)})
        if hits:
            offenders[fn] = hits
    assert not offenders, f"the retired pinned-preflight path survives: {offenders}"


def test_a_genuine_strict_GO_from_run_A_cannot_authorise_run_B(synthetic_run):
    """The forgery nobody needed to forge: a REAL, honest GO from a different run.

    The deleted shortcut bound the artifact's hash into run_id but never bound the
    artifact to the run's own evidence — not the manifest, not the sources, not the
    source-record table, not the domain. So a perfectly genuine strict-preflight GO,
    produced by a real strict replay of run A's raw source, authorised run B over
    entirely different evidence. Run B is now required to replay its OWN source.
    """
    run_a = synthetic_run(lane="production", strict_replay=True)
    report_a = preflight.run(run_a)
    assert report_a["verdict"] == preflight.GO
    assert report_a["strict_replay"]["ran"] is True          # genuinely fresh
    assert report_a["strict_replay"]["agrees_with_pinned_report"] is True

    # run B: different inputs, no strict replay of its own. A's GO buys it nothing,
    # because there is no channel through which A's GO can be offered at all.
    run_b = synthetic_run(lane="production", strict_replay=False)
    assert not hasattr(run_b, "strict_preflight")
    with pytest.raises(gate.GateError, match="release-grade"):
        build_screen(run_b)
    assert _artifacts(run_b) == []


@pytest.mark.parametrize("lane", ["production", "research_only"])
def test_a_release_run_performs_its_OWN_strict_replay_and_binds_it(synthetic_run, lane):
    """The replacement for the shortcut: replay THIS run's source, in THIS invocation."""
    args = synthetic_run(lane=lane, strict_replay=True)
    report = preflight.assess(args, prepare(args))
    assert report["verdict"] == preflight.GO
    assert report["strict_replay"]["ran"] is True
    assert report["strict_replay"]["agrees_with_pinned_report"] is True
    assert report["release_gate"]["state"] == gate.GATE_FRESH

    result = build_screen(args)
    with open(os.path.join(result["out_dir"], "provenance.json")) as fh:
        prov = json.load(fh)
    g = prov["run_binding"]["stage2_release_gate"]
    assert g["state"] == gate.GATE_FRESH
    # the retired field is not merely None — it is not emitted at all
    assert "strict_preflight_sha256" not in g
    # and the gate is inside run_id: recomputing the binding hash reproduces the id
    assert runid.run_id_of(prov["run_binding"])[0] == result["run_id"]


@pytest.mark.parametrize("lane", ["production", "research_only"])
def test_every_gate_refusal_writes_zero_scientific_artifacts(synthetic_run, lane):
    """A refusal that leaves a partial screen behind is not a refusal."""
    for args in (synthetic_run(lane=lane, strict_replay=False),
                 synthetic_run(lane=lane, strict_replay=False, manifest=False)):
        with pytest.raises(gate.GateError):
            build_screen(args)
        assert _artifacts(args) == []
        assert not os.path.exists(args.out_root)
