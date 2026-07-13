"""CLEARLY SYNTHETIC data for the P2S v2 lane — synthetic, but NOT fictional.

THE DEFECT THIS FIXTURE EXISTS NOT TO REPEAT
--------------------------------------------
The v1 lane's independent reviewer returned ``conditional_not_mergeable`` with a single
finding: "Perturb2State cannot read a single artifact the direct lane actually produces."
Every v1 test passed because its fixture wrote a FICTIONAL direct bundle — one carrying a
top-level ``mask_sha256``, a ``balanced_skew`` and an integer rank on an ineligible target.
The lane was green against a bundle that has never existed.

So the Direct bundle here is built by ``direct.arm_bundle.build`` and
``direct.scorer_view.view``, through the REAL code path, and written with the same files and
the same ``arm_bundle_run_id`` stamping that ``direct.run_arms`` uses. The DATA is synthetic;
the ARTIFACT is real. If Direct's bundle shape moves, this breaks — which is the point.

WHY THIS SHIPS IN THE PACKAGE AND NOT ONLY IN THE TESTS
------------------------------------------------------
W16 needs a real, verifier-ADMITTED payload to build the UI against BEFORE the real run
exists, and the tests need the same builders. One copy, used by both, so the bundle the UI
is built against is the bundle the tests certify.

``linear_fit`` is a DETERMINISTIC STAND-IN for the pinned model — it exists so the arm
arithmetic can be exercised on a host where the upstream package is not installed. It may
only ever run in the ``synthetic`` lane, and ``run_p2s_arms.execute`` REFUSES it anywhere
else: a stand-in model that could reach a production artifact would be a different model
producing numbers under this lane's name.
"""
from __future__ import annotations

import os
from typing import Any, Optional

import numpy as np
import pandas as pd
from direct import arm_bundle, trust  # noqa: E402
from direct import emit as direct_emit
from direct import projection as proj  # noqa: E402
from direct.hashing import canonical_json, sha256_hex  # noqa: E402

CONDITION = "Stim48hr"
PROGRAM = "treg_like"
ACTIVATION = "diff_activated"
DONORS = ("D1", "D2", "D3", "D4")

N_GENES = 240
N_TARGETS = 12

# The planted structure. T00 reconstructs the program; T01 OPPOSES it (a negative
# contributor — the inverse of the measured knockdown). Everything else is noise.
CONTRIBUTOR = "T00"
OPPONENT = "T01"
CONTRIBUTOR_WEIGHT = 2.0
OPPONENT_WEIGHT = -2.0


def gene_ids(n: int = N_GENES) -> list[str]:
    return [f"ENSG{i:08d}" for i in range(n)]


def target_ids(n: int = N_TARGETS) -> list[str]:
    return [f"T{i:02d}" for i in range(n)]


# --------------------------------------------------------------------------- #
# A REAL Stage-1 release object: base_portable is what admits a program.
# --------------------------------------------------------------------------- #
def make_release(*, portable: Optional[dict[str, bool]] = None,
                 panels: Optional[dict[str, list]] = None) -> trust.FixtureRelease:
    """A fixture release whose programs declare ``base_portable``, as the real one does.

    Th9 is present and NOT portable — so the admitted set is DERIVED to exclude it, exactly
    as the release excludes it in production. Nothing here hard-codes a count.
    """
    portable = portable or {}
    panels = panels or {}
    programs: dict[str, dict] = {}
    for i, pid in enumerate((PROGRAM, ACTIVATION, "th1_like", "th9_like")):
        default_panel = [f"ENSG9{i}{j:06d}" for j in range(3)]
        programs[pid] = {
            "program_id": pid,
            "base_portable": portable.get(pid, pid != "th9_like"),
            "panel_ensembl": panels.get(pid, default_panel),
            "control_ensembl": [f"ENSG8{i}{j:06d}" for j in range(2)],
        }
    return trust.FixtureRelease(
        kind="fixture", method_version="fixture-v1", programs=programs,
        hashes={}, selectable_pairs=frozenset())






# --------------------------------------------------------------------------- #
# A REAL all-arm Direct bundle, through direct.arm_bundle.
# --------------------------------------------------------------------------- #
def base_deltas(program_id: str, *, seed: int = 7,
                no_panel: bool = False) -> list[dict[str, Any]]:
    rng = np.random.default_rng(abs(hash(program_id)) % 2**32 if seed is None else seed)
    out = []
    for t in target_ids():
        out.append({
            "target_id": t,
            "delta": float(rng.normal()),
            "status": proj.OK,
            "base_state": "eligible_two_guide",
            "base_passed": True,
            "n_panel_surviving": 0 if no_panel else 3,
            "n_control_surviving": 2,
        })
    return out


def write_arm_bundle(out_root: str, view: dict[str, Any], *,
                     condition: str = CONDITION,
                     tamper_rank: bool = False) -> str:
    """Write a Direct all-arm bundle the way ``direct.run_arms`` writes one.

    ``tamper_rank`` edits a rank in the shipped parquet AFTER the bundle recorded its hash —
    the mutation that a secondary lane must never lend its credit to.
    """
    admitted = view["admitted_program_ids"]
    base_by_program = {p: base_deltas(p) for p in admitted}
    doc = arm_bundle.build(condition=condition, view=view,
                           base_by_program=base_by_program)

    binding = {"condition": condition, "method": doc["method"],
               "arm_rows_sha256": doc["arm_rows_sha256"]}
    run_id = sha256_hex(canonical_json(binding))[:16]

    out_dir = os.path.join(out_root, run_id)
    os.makedirs(out_dir, exist_ok=True)

    rows = arm_bundle.build_rows(condition=condition, admitted=admitted,
                                 base_by_program=base_by_program)
    for r in rows:
        r["arm_bundle_run_id"] = run_id

    if tamper_rank:
        # edit a RANK after the bundle hashed the rows. The values are untouched; only the
        # ordering claim moves — which is exactly the edit a rank-hash must catch.
        ranked = [r for r in rows if r["rank"] is not None]
        if ranked:
            ranked[0]["rank"] = int(ranked[0]["rank"]) + 99

    direct_emit.write_json(os.path.join(out_dir, "arm_bundle.json"),
                           dict(doc, arm_bundle_run_id=run_id))
    direct_emit.write_parquet(rows, os.path.join(out_dir, "arms.parquet"),
                              sort_by=["arm_key", "target_id"],
                              nullable_int_columns=("rank",))
    return out_dir






# --------------------------------------------------------------------------- #
# Synthetic cells / effects / masks / eligibility.
# --------------------------------------------------------------------------- #
def make_cells(path: str, *, n_cells: int = 800, seed: int = 3) -> str:
    """Cells whose expression genuinely tracks the program score, so a fit has signal."""
    rng = np.random.default_rng(seed)
    genes = gene_ids()
    donors = np.asarray([DONORS[i % len(DONORS)] for i in range(n_cells)])
    z_p = rng.normal(size=n_cells)
    z_act = rng.normal(size=n_cells)

    # the first 40 genes track the program; the next 20 track activation
    loading = np.zeros(len(genes))
    loading[:40] = rng.normal(1.5, 0.3, size=40)
    act_loading = np.zeros(len(genes))
    act_loading[40:60] = rng.normal(1.2, 0.3, size=20)

    expr = (np.outer(z_p, loading) + np.outer(z_act, act_loading)
            + rng.normal(0, 0.4, size=(n_cells, len(genes))))
    # a donor offset, so the donor dummies have something to absorb
    for i, d in enumerate(DONORS):
        expr[donors == d] += 0.3 * i

    np.savez(path, barcodes=np.asarray([f"BC{i:06d}" for i in range(n_cells)]),
             donors=donors, gene_ids=np.asarray(genes), expr=expr,
             **{f"score__{PROGRAM}": z_p, f"score__{ACTIVATION}": z_act})
    return path


def make_effects(path: str, *, seed: int = 11) -> str:
    """Effect vectors in which T00 reconstructs the program and T01 OPPOSES it."""
    rng = np.random.default_rng(seed)
    genes = gene_ids()
    targets = target_ids()

    program_direction = np.zeros(len(genes))
    program_direction[:40] = 1.5

    rows = []
    for t in targets:
        v = rng.normal(0, 0.5, size=len(genes))
        if t == CONTRIBUTOR:
            v = v + CONTRIBUTOR_WEIGHT * program_direction
        elif t == OPPONENT:
            v = v + OPPONENT_WEIGHT * program_direction
        for g, val in zip(genes, v):
            rows.append({"target_id": t, "gene_id": g,
                         "zscore": float(val), "log_fc": float(val * 0.8)})
    pd.DataFrame(rows).to_parquet(path, index=False)
    return path


def make_masks(path: str) -> str:
    """Each target masks its own coordinates. NEVER unioned across targets."""
    rows = [{"target_id": t, "gene_id": gene_ids()[i]}
            for i, t in enumerate(target_ids())]
    pd.DataFrame(rows).to_parquet(path, index=False)
    return path


def make_eligible(path: str, *, states: Optional[dict[str, str]] = None) -> str:
    states = states or {}
    rows = [{"target_id": t,
             "state": states.get(t, "eligible_two_guide"),
             "target_ensembl": f"ENSGT{i:06d}"}
            for i, t in enumerate(target_ids())]
    pd.DataFrame(rows).to_parquet(path, index=False)
    return path




# --------------------------------------------------------------------------- #
# A deterministic stand-in for the pinned model, so the ARM ARITHMETIC can be
# tested without the upstream package. Production always uses the pinned one.
# --------------------------------------------------------------------------- #
def linear_fit(x: pd.DataFrame, y: pd.Series, cfg, model_id: str, *, seed: int = 42):
    """Ridge-ish least squares with a hard sparsity threshold. Deterministic, sign-symmetric.

    It is sign-symmetric in ``y`` — which is what lets the sign-transform tests mean
    anything: a stand-in that were not symmetric would pass the test for the wrong reason.
    """
    xm = x.to_numpy()
    yv = y.to_numpy()
    lam = 1e-3 * (1 + (seed % 7))
    gram = xm.T @ xm + lam * np.eye(xm.shape[1])
    beta = np.linalg.solve(gram, xm.T @ yv)
    beta[np.abs(beta) < 0.05] = 0.0

    fitted = xm @ beta
    ss_res = float(((yv - fitted) ** 2).sum())
    ss_tot = float(((yv - yv.mean()) ** 2).sum()) or 1.0
    r2 = 1.0 - ss_res / ss_tot

    return {
        "coefficients": pd.DataFrame(
            {"coefficient": beta, "coef_fit_variation": np.abs(beta) * 0.01},
            index=pd.Index(list(x.columns), name="target_id")),
        "reconstruction": {
            "reconstruction_gene_cv_test_r2_mean": r2,
            "reconstruction_gene_cv_test_r2_median": r2,
            "reconstruction_gene_cv_test_spearman_mean": r2,
            "reconstruction_gene_cv_train_r2_mean": r2,
            "n_folds": 5,
            "cv_label": "reconstruction_gene_cv",
            "cv_semantics": "gene folds; not donor / guide / holdout / external validation",
            "seconds": 0.0,
        },
    }




# --------------------------------------------------------------------------- #
# Drive the REAL producer end to end, with the deterministic stand-in model.
#
# It calls ``run_p2s_arms.execute`` — the same function the CLI calls — so the tests
# exercise the shipping code path, not a re-implementation of it. Only the FIT is
# swapped, and only because the upstream package is not importable on every host.
# --------------------------------------------------------------------------- #
UPSTREAM_OBSERVED = {
    "commit": None,          # filled from config at call time
    "dirty": False,
    "version": None,
    "tree_sha256": "f" * 64,
}


def run_producer(tmp_path, *, view, bundle_dir, admit_report, inputs,
                 arm_key: Optional[str] = None, seed: int = 42,
                 lane: str = "synthetic") -> dict:
    from p2s_arms import binding, run_p2s_arms, upstream
    from p2s_arms import config as p2s_config

    observed = dict(UPSTREAM_OBSERVED,
                    commit=p2s_config.UPSTREAM_COMMIT,
                    version=p2s_config.UPSTREAM_VERSION)
    up = upstream.identity(observed)

    bound = binding.bind(
        arm_key=arm_key or f"direct|{PROGRAM}|increase|{CONDITION}",
        bundle_dir=bundle_dir, view=view, verifier_report=admit_report)

    return run_p2s_arms.execute(
        bound=bound, release=make_release(), view=view, up=up, paths=inputs,
        out_root=str(tmp_path / "p2s"), lane=lane, seed=seed,
        argv=["--arm-key", bound["arm"].arm_key], fit=linear_fit)
