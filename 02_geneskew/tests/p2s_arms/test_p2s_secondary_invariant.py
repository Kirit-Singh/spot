"""MUTATIONS 9 and 10 — the invariant that makes this lane safe, stated EXACTLY.

WHAT IS PROVEN HERE
-------------------
At one frozen integrated commit, EXECUTING the P2S lane versus OMITTING it leaves every
Direct artifact byte-identical — the bytes, the canonical rows, the ranks, and the
content-addressed run id.

WHAT IS **NOT** CLAIMED, AND WHY
--------------------------------
That ADDING the P2S source files leaves Direct's run id unchanged. It does not.

``direct/code_digest.py`` digests every ``.py`` and ``.json`` under ``02_geneskew/``, and
that digest flows: ``code_identity`` -> ``run_binding`` -> ``bundle_run_id`` -> stamped into
``arms.parquet``, ``arm_bundle.json`` and the output directory name. New source files
therefore MOVE the repository code digest and hence the content-addressed run id. The code
tree changed, and the digest says so. A digest engineered not to notice a new lane would be
the defect, not the fix.

What is invariant under that change is the SCIENCE: ``arm_rows_sha256`` is taken over
``canonical_rows()``, whose explicit projection excludes ``arm_bundle_run_id``. Arm values
and arm ranks do not move.

Consequence for W1: integrate P2S BEFORE the final commit is frozen and before the real
Direct run, so there is exactly one run-id generation.
"""
from __future__ import annotations

import hashlib
import os
import pathlib
import subprocess

import fixtures_p2s as fx
import pandas as pd
import pytest
from direct import arm_bundle
from p2s_arms import config as P2S_CONFIG


def _sha(path: str) -> str:
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def _snapshot(d: str) -> dict[str, str]:
    return {name: _sha(os.path.join(d, name)) for name in sorted(os.listdir(d))}


# --------------------------------------------------------------------------- #
# MUTATION 10 — same commit, P2S EXECUTED vs OMITTED.
# --------------------------------------------------------------------------- #
def test_MUTATION_direct_artifacts_are_byte_identical_with_p2s_executed_vs_omitted(
        tmp_path, view, w10_report, inputs):
    """The whole safety case for a secondary lane, in one test."""
    direct_dir = fx.write_full_bundle(str(tmp_path / "direct"), view)
    before = _snapshot(direct_dir)
    # the verified-artifact inventory PLUS verification.json (the producer's slot)
    assert set(before) == set(P2S_CONFIG.DIRECT_BUNDLE_FILES) | {"verification.json"}, \
        "the fixture must ship a REAL Direct bundle, or this proves nothing"

    report = fx.write_w10_report(str(tmp_path / "w10.json"), direct_dir, view)
    out = fx.run_producer(tmp_path, view=view, bundle_dir=direct_dir,
                          w10_report=report, inputs=inputs)

    after = _snapshot(direct_dir)
    assert after == before, "the P2S lane changed a Direct artifact"

    # ...and it wrote nothing into Direct's tree at all
    assert not os.path.commonpath([out["out_dir"], direct_dir]) == direct_dir
    assert sorted(os.listdir(direct_dir)) == sorted(before)


def test_the_p2s_run_writes_ONLY_into_its_own_content_addressed_directory(
        tmp_path, view, bundle_dir, w10_report, inputs):
    out = fx.run_producer(tmp_path, view=view, bundle_dir=bundle_dir,
                          w10_report=w10_report, inputs=inputs)
    written = sorted(os.listdir(out["out_dir"]))
    assert written == sorted([
        "p2s_arm_support.parquet", "p2s_coefficients.parquet",
        "p2s_provenance.json", "p2s_reconstruction.parquet", "p2s_support.json"])
    # the directory's NAME is its content hash, not a biology id
    assert os.path.basename(out["out_dir"]) == out["p2s_run_id"]
    assert len(out["p2s_run_id"]) == 16


# --------------------------------------------------------------------------- #
# MUTATION 9 — numerical non-regression over the canonical Direct arm rows and RANKS.
# --------------------------------------------------------------------------- #
def test_MUTATION_direct_canonical_rows_and_ranks_do_not_move(tmp_path, view, w10_report,
                                                              inputs):
    """Value-by-value and rank-by-rank, not merely file-hash-by-file-hash.

    A file hash proves the bytes did not move. This proves the NUMBERS did not — which is
    the claim a reader of the science actually cares about, and it would survive a change of
    parquet writer that a byte hash would not.
    """
    direct_dir = fx.write_full_bundle(str(tmp_path / "direct"), view)
    rows_path = os.path.join(direct_dir, "arms.parquet")

    before_rows = pd.read_parquet(rows_path).to_dict("records")
    before_canon = arm_bundle.canonical_rows(before_rows)
    before_sha = arm_bundle.rows_sha256(before_rows)

    fx.run_producer(tmp_path, view=view, bundle_dir=direct_dir,
                    w10_report=w10_report, inputs=inputs)

    after_rows = pd.read_parquet(rows_path).to_dict("records")
    after_canon = arm_bundle.canonical_rows(after_rows)

    assert after_canon == before_canon
    assert arm_bundle.rows_sha256(after_rows) == before_sha

    # the ranks specifically — the thing P2S is forbidden to touch
    def ranks(canon):
        return {(r["arm_key"], r["target_id"]): r["rank"] for r in canon}

    assert ranks(after_canon) == ranks(before_canon)
    assert any(v is not None for v in ranks(after_canon).values()), \
        "the fixture must actually rank something, or this test proves nothing"

    # ...and the values
    def values(canon):
        return {(r["arm_key"], r["target_id"]): r["value"] for r in canon}

    assert values(after_canon) == values(before_canon)


def test_arm_rows_sha256_EXCLUDES_the_run_id_so_the_science_survives_a_digest_change(
        tmp_path, view):
    """This is WHY the science is invariant while the run id is not.

    ``canonical_rows`` projects to an explicit key set that does not include
    ``arm_bundle_run_id``. Two bundles built from the same science under different code
    digests carry different run ids and the SAME ``arm_rows_sha256``.
    """
    direct_dir = fx.write_full_bundle(str(tmp_path / "direct"), view)
    rows = pd.read_parquet(os.path.join(direct_dir, "arms.parquet")).to_dict("records")

    assert "arm_bundle_run_id" in rows[0], "the run id really is stamped on every row"
    canon_keys = set(arm_bundle.canonical_rows(rows)[0])
    assert "arm_bundle_run_id" not in canon_keys

    # re-stamp every row with a different run id: the science hash must not move
    restamped = [dict(r, arm_bundle_run_id="deadbeefdeadbeef") for r in rows]
    assert arm_bundle.rows_sha256(restamped) == arm_bundle.rows_sha256(rows)


# --------------------------------------------------------------------------- #
# THE STATIC PROOF — Direct cannot even see this lane.
# --------------------------------------------------------------------------- #
def _analysis_dir() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2] / "analysis"


def test_NO_module_under_analysis_direct_imports_p2s_arms():
    """Direct cannot import P2S, so P2S cannot influence Direct. Structural, not a promise."""
    offenders = []
    for path in sorted((_analysis_dir() / "direct").rglob("*.py")):
        src = path.read_text()
        if "p2s_arms" in src:
            offenders.append(str(path.relative_to(_analysis_dir())))
    assert not offenders, f"Direct imports the secondary lane: {offenders}"


def test_this_branch_changed_ZERO_bytes_under_analysis_direct():
    """The producer may READ Direct's contract. It may not EDIT Direct's package.

    Asserted against git, not against a grep: the claim is about the bytes on disk, and the
    only thing that can settle it is the diff. A P2S change to ``analysis/direct/`` would
    move Direct's code digest for a reason that has nothing to do with Direct — and it would
    be invisible in every other test here.
    """
    repo = pathlib.Path(__file__).resolve().parents[3]

    def git(*args) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(repo), *args],
                              capture_output=True, text=True)

    # The base is located, not hard-coded: the parent of the FIRST commit that introduced
    # this lane. A pinned sha would rot the moment the branch is rebased, and a test that
    # rots into a skip is a test that stops guarding anything.
    added = git("log", "--diff-filter=A", "--format=%H", "--reverse", "--",
                "02_geneskew/analysis/p2s_arms/")
    shas = [s for s in added.stdout.split() if s]
    if not shas:
        pytest.skip("the p2s_arms lane is not committed yet, so there is no base to diff")

    base = git("rev-parse", f"{shas[0]}^")
    if base.returncode != 0:
        pytest.skip("the lane's first commit is a root commit; nothing to diff against")

    changed = git("diff", "--name-only", base.stdout.strip(), "HEAD", "--",
                  "02_geneskew/analysis/direct/")
    assert changed.stdout.strip() == "", (
        "this lane edited Direct's package, which moves Direct's code digest for a reason "
        "that has nothing to do with Direct:\n" + changed.stdout)


def test_v2_is_isolated_from_the_ARCHIVED_legacy_pair_bound_lane():
    """GATE 7 archived the pair-bound v1 lane out of the production package. v2 imports
    NOTHING from it (and the archived lane names nothing in v2), so the isolation is total."""
    for path in sorted((_analysis_dir() / "p2s_arms").rglob("*.py")):
        src = path.read_text()
        assert "from perturbate2state" not in src, path.name
        assert "import perturb2state" not in src and "from perturb2state" not in src, \
            f"v2 {path.name} depends on the archived legacy lane"

    # the legacy lane is no longer in the production package (GATE 7 archived it)
    assert not (_analysis_dir() / "perturb2state").exists() \
        or not list((_analysis_dir() / "perturb2state").glob("*.py")), \
        "the pair-bound legacy lane must not sit in the production analysis package"


def test_v2_emits_no_pair_named_away_or_toward_output():
    """The role a program plays is a property of a QUESTION, not of the program's effect."""
    from p2s_arms import emit

    for column in emit.SUPPORT_COLUMNS + emit.COEF_COLUMNS + emit.RECON_COLUMNS:
        low = column.lower()
        for banned in ("away_from_a", "toward_b", "combined", "balanced", "pareto", "rank"):
            assert banned not in low, f"{column!r} carries pair/ranking vocabulary"


def test_a_STAND_IN_MODEL_may_never_run_outside_the_synthetic_lane(tmp_path):
    """A stand-in is a DIFFERENT MODEL wearing the pinned model's provenance.

    The injectable fit is what lets this lane be developed on a host without the upstream
    package. That same seam, left ungated, is how a stand-in reaches a production artifact —
    so any release lane refuses it outright rather than trusting nobody will pass one.

    Driven straight at ``execute``: through ``run_producer`` the FIXTURE-RELEASE refusal now
    fires first (a fixture release may not back a production run), which is correct but would
    make this test pass for the wrong reason.
    """
    from p2s_arms import model, run_p2s_arms

    for lane in ("production", "research_only"):
        with pytest.raises(model.ModelError) as e:
            run_p2s_arms.execute(
                bound={}, release=None, view={}, paths={}, up={},
                out_root=str(tmp_path), lane=lane, fit=fx.linear_fit)
        assert e.value.reason == "stand_in_model_outside_the_synthetic_lane"
