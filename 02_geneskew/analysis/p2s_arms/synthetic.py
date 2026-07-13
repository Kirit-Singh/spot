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

import json
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
            "base_state": "qc_pass_two_guide",   # the REAL Direct vocabulary
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
    """The effect MATRIX (targets x genes): T00 reconstructs the program, T01 OPPOSES it.

    A matrix, not 116M long rows — see ``io_data.load_effects``.
    """
    if not path.endswith(".npz"):
        path = path.rsplit(".", 1)[0] + ".npz"
    rng = np.random.default_rng(seed)
    genes = gene_ids()
    targets = target_ids()

    direction = np.zeros(len(genes))
    direction[:40] = 1.5

    z = np.zeros((len(targets), len(genes)), dtype=np.float32)
    for i, t in enumerate(targets):
        v = rng.normal(0, 0.5, size=len(genes))
        if t == CONTRIBUTOR:
            v = v + CONTRIBUTOR_WEIGHT * direction
        elif t == OPPONENT:
            v = v + OPPONENT_WEIGHT * direction
        z[i] = v
    np.savez(path,
             target_ids=np.asarray(targets, dtype=object).astype("U"),
             gene_ids=np.asarray(genes, dtype=object).astype("U"),
             zscore=z, log_fc=(z * 0.8).astype(np.float32))
    return path


def make_masks(path: str) -> str:
    """Each target masks its own coordinates. NEVER unioned across targets."""
    rows = [{"target_id": t, "gene_id": gene_ids()[i]}
            for i, t in enumerate(target_ids())]
    pd.DataFrame(rows).to_parquet(path, index=False)
    return path


def make_eligible(path: str, *, states: Optional[dict[str, str]] = None,
                  program: str = PROGRAM, condition: str = CONDITION) -> str:
    """The ARM-KEYED eligibility the producer eats — one row per (sign arm, target).

    Real prepared eligibility carries ``arm_key`` and ``evaluable``: eligibility is a property
    of the ARM, and the producer filters to the arm it is fitting. A table without those
    columns is refused (no global fallback), so the fixture ships them for BOTH sign arms.
    """
    states = states or {}
    inc = f"direct|{program}|increase|{condition}"
    dec = f"direct|{program}|decrease|{condition}"
    rows = [{"arm_key": arm_key, "program_id": program, "condition": condition,
             "target_id": t, "state": states.get(t, "qc_pass_two_guide"),
             "target_ensembl": f"ENSGT{i:06d}",
             "target_id_namespace": "ensembl_gene_id", "evaluable": True}
            for arm_key in (inc, dec)
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
    "tree_sha256": None,   # callers fill from config.UPSTREAM_TREE_SHA256
}


def run_producer(tmp_path, *, view, bundle_dir, w10_report, inputs,
                 arm_key: Optional[str] = None, seed: int = 42,
                 lane: str = "synthetic", env_lock: Optional[str] = None,
                 release=None) -> dict:
    """Drive the REAL producer, through the REAL admission chain, on synthetic data."""
    from p2s_arms import binding, run_p2s_arms, upstream
    from p2s_arms import config as p2s_config

    observed = dict(UPSTREAM_OBSERVED,
                    commit=p2s_config.UPSTREAM_COMMIT,
                    version=p2s_config.UPSTREAM_VERSION,
                    tree_sha256=p2s_config.UPSTREAM_TREE_SHA256)
    up = upstream.identity(observed)

    rel = release if release is not None else make_release()
    bound = binding.bind(
        arm_key=arm_key or f"direct|{PROGRAM}|increase|{CONDITION}",
        bundle_dir=bundle_dir, w10_report=w10_report,
        env_lock=env_lock or REAL_SOLVER_LOCK, view=view, release=rel, lane=lane)

    return run_p2s_arms.execute(
        bound=bound, release=rel, view=view, up=up, paths=inputs,
        out_root=str(tmp_path / "p2s"), lane=lane, seed=seed,
        argv=["--arm-key", bound["arm"].arm_key], fit=linear_fit)


# --------------------------------------------------------------------------- #
# A REAL Direct bundle (all ten shipped files) and a REAL W10 ADMIT report.
#
# The report is built the way W10 builds one — content-addressed over its own body, with
# `verifier_code_sha256`, `spec_sha256` and a `bound_artifact` that names the exact bytes on
# disk. So the P2S admission gate is exercised against a report it must actually re-derive,
# not a stub that says {"verdict": "ADMIT"} and nothing else.
#
# The DATA is synthetic. The ADMISSION CHAIN is real.
# --------------------------------------------------------------------------- #
# THE REAL LOCK. Tests bind the actual committed stage02_solver_lock.txt, because the pin is
# the mechanism: a test that bound a synthetic lock and a synthetic pin would prove that two
# made-up numbers match each other, which is not the property under test.
from direct import envlock as _envlock  # noqa: E402

from p2s_arms import config as _cfg  # noqa: E402
from p2s_arms.w10 import content_sha256 as _csha  # noqa: E402
from p2s_arms.w10 import file_sha256 as _fsha  # noqa: E402

REAL_SOLVER_LOCK = _envlock.DEFAULT_PATH
REAL_P2S_LOCK = _cfg.P2S_RUNTIME_LOCK_PATH


def write_solver_lock(path: str, *, pinned: bool = True, stage1: bool = False) -> str:
    """The REAL pinned lock, or a lock that is not it (and must be refused)."""
    if pinned:
        return REAL_SOLVER_LOCK
    target = path
    if stage1:                                # the STAGE-1 lock: refused BY NAME
        target = os.path.join(os.path.dirname(path), _envlock.STAGE1_LOCK_FILENAME)
    with open(target, "wb") as fh:
        fh.write(b"# a valid lock for a DIFFERENT environment (scvi_gpu, py3.11)\n")
    return target


def write_full_bundle(out_root: str, view, *, condition: str = CONDITION,
                      lane: str = "synthetic", tamper_rank: bool = False,
                      self_admitted: bool = False, mask_scope_union: bool = False,
                      drop_mask_for: Optional[str] = None,
                      no_main_mask: bool = False,
                      symbol_namespace_target: bool = False) -> str:
    """All TEN files an admitted Direct bundle ships.

    ``masks.parquet`` carries the REAL schema: ``masked_gene_ensembl`` +
    ``estimate_type``/``estimate_id``, with a MAIN-estimate row for every target. The knobs
    inject the attacks: a guide-scope-only union, a dropped main mask for one target, or no
    main mask at all.
    """
    d = write_arm_bundle(out_root, view, condition=condition, tamper_rank=tamper_rank)

    # THE REAL MASK SCHEMA: main-estimate rows carry masked_gene_ensembl + target_ensembl,
    # and INCLUDE the target's OWN gene (its positive control). Each target's self-gene is a
    # distinct ENSG so the self-gene-masked check is meaningful.
    genes = gene_ids()
    mask_rows = []
    for i, t in enumerate(target_ids()):
        if drop_mask_for == t or no_main_mask:
            continue
        self_gene = genes[i]                     # the target's OWN gene, masked as its control
        for g in (self_gene, genes[(i + 50) % len(genes)]):   # self + one off-target
            mask_rows.append({"target_id": t, "masked_gene_ensembl": g,
                              "target_ensembl": self_gene,
                              "estimate_type": "main", "estimate_id": "main"})
    if mask_scope_union or no_main_mask:
        # guide-slot rows for the same targets — a DIFFERENT estimate. Unioning them would
        # mask genes for a perturbation that had no reason to mask them.
        for i, t in enumerate(target_ids()):
            mask_rows.append({"target_id": t, "masked_gene_ensembl": genes[100 + i],
                              "target_ensembl": genes[i],
                              "estimate_type": "guide", "estimate_id": "guide_1"})
    pd.DataFrame(mask_rows or [{"target_id": None, "masked_gene_ensembl": None,
                                "target_ensembl": None, "estimate_type": None,
                                "estimate_id": None}]).to_parquet(
        os.path.join(d, "masks.parquet"), index=False)

    for name in ("contributing_guides.parquet", "guide_support.parquet",
                 "donor_support.parquet"):
        pd.DataFrame([{"target_id": t, "gene_id": gene_ids()[0]}
                      for t in target_ids()[:2]]).to_parquet(os.path.join(d, name),
                                                             index=False)

    # target_identity.json — the AUTHORITATIVE bound identity, in the producer's schema.
    # Every scored target gets one row: ensembl_gene_id rows carry their Ensembl id (which is
    # the target's OWN masked gene); a symbol row carries a null target_ensembl.
    ti_records = []
    for i, t in enumerate(target_ids()):
        if i == 0 and symbol_namespace_target:
            ti_records.append({"target_id": t, "target_id_namespace": "gene_symbol",
                               "target_symbol": t, "target_ensembl": None,
                               "observed_perturbation_modality": "CRISPRi_knockdown"})
        else:
            ti_records.append({"target_id": t, "target_id_namespace": "ensembl_gene_id",
                               "target_symbol": f"SYM_{t}", "target_ensembl": genes[i],
                               "observed_perturbation_modality": "CRISPRi_knockdown"})
    n_ens = sum(1 for r in ti_records if r["target_id_namespace"] == "ensembl_gene_id")
    direct_emit.write_json(os.path.join(d, "target_identity.json"), {
        "schema_version": "spot.stage02_target_identity.v1", "condition": condition,
        "columns": ["target_id", "target_id_namespace", "target_symbol", "target_ensembl",
                    "observed_perturbation_modality"],
        "observed_perturbation_modality": "CRISPRi_knockdown",
        "modality_rule_id": "spot.stage02.target_identity.observed_modality.crispri_knockdown.v1",
        "n_targets": len(ti_records), "n_ensembl_gene_id": n_ens,
        "n_gene_symbol": len(ti_records) - n_ens, "records": ti_records})

    direct_emit.write_json(os.path.join(d, "input_manifest.json"), {"inputs": []})
    direct_emit.write_json(os.path.join(d, "gene_universe.json"),
                           {"gene_ids": gene_ids()[:5]})
    direct_emit.write_json(os.path.join(d, "provenance.json"), {
        "arm_bundle_run_id": os.path.basename(d),
        "run_binding": {"lane": lane, "environment_lock": {
            "lock_id": "spot.stage02.solver_lock.v1",
            "sha256": _cfg.PINNED_SOLVER_LOCK_SHA256, "verified": True, "status": "locked"}},
    })

    # the PRODUCER'S EMPTY SLOT — un-admitted, for an outsider to fill.
    verification = {
        "verifier_id": None,
        "verdict": _cfg.W10_VERDICT_PENDING,
        "admitted": False,
        "self_admitted": False,
        "produced_by": "spot.stage02.direct.all_arm_runner.v1",
    }
    if self_admitted:                       # the mutation: the bundle admits itself
        verification.update(verifier_id="spot.stage02.direct.all_arm_runner.v1",
                            verdict=_cfg.W10_VERDICT_ADMIT, admitted=True,
                            self_admitted=True)
    direct_emit.write_json(os.path.join(d, "verification.json"), verification)
    return d


def write_w10_report(path: str, bundle_dir: str, view, *, condition: str = CONDITION,
                     lane: str = "synthetic", verdict: Optional[str] = None,
                     verifier_id: Optional[str] = None,
                     spec_sha256: Optional[str] = None,
                     solver_lock_sha256: Optional[str] = None,
                     independent: bool = True,
                     bundle_run_id: Optional[str] = None,
                     verifier_code_sha256: Optional[str] = None,
                     omit_code_sha: bool = False,
                     tamper_hash: bool = False) -> str:
    """A W10 ADMIT report, content-addressed exactly as W10 writes one."""
    doc = json.load(open(os.path.join(bundle_dir, "arm_bundle.json")))
    # cover EXACTLY the authoritative inventory (VERIFIED_PATHS) — the exact-key check
    # refuses a subset or an extra.
    files = {n: _fsha(os.path.join(bundle_dir, n)) for n in _cfg.DIRECT_BUNDLE_FILES}

    body = {
        "schema_version": _cfg.W10_REPORT_SCHEMA,
        "verifier_id": verifier_id or _cfg.W10_VERIFIER_ID,
        "spec_sha256": spec_sha256 or _cfg.W10_SPEC_SHA256,
        "verifier_code_sha256": verifier_code_sha256 or _cfg.W10_VERIFIER_CODE_SHA256,
        "independent_of_generator": independent,
        "generator_modules_not_imported": ["direct.arm_bundle", "direct.run_arms"],
        "gate_inventory": ["g1", "g2"],
        "gate_inventory_sha256": _csha(["g1", "g2"]),
        "gates": [{"gate": "g1", "passed": True, "detail": ""},
                  {"gate": "g2", "passed": True, "detail": ""}],
        "n_gates": 2, "n_passed": 2, "n_failed": 0, "failed_gates": [],
        "verdict": verdict or _cfg.W10_VERDICT_ADMIT,
        "bound_artifact": {
            "arm_bundle_run_id": bundle_run_id or os.path.basename(bundle_dir),
            "arm_bundle_run_sha256": "b" * 64,
            "condition": condition,
            "lane": lane,
            "arm_rows_sha256": doc.get("arm_rows_sha256"),
            "scorer_view_sha256": view["scorer_view_sha256"],
            "stage1_scorer_view_canonical_sha256": "c" * 64,
            "solver_lock_sha256": solver_lock_sha256 or _cfg.PINNED_SOLVER_LOCK_SHA256,
            "solver_lock_pinned_sha256": _cfg.PINNED_SOLVER_LOCK_SHA256,
            "artifact_sha256": files,
            "n_admitted_programs": view["n_admitted_programs"],
            "n_arm_slots": len(doc.get("arms", [])),
            "n_arm_rows": doc.get("n_arm_rows"),
        },
    }
    if omit_code_sha:
        body.pop("verifier_code_sha256")

    # RE-SEALED HONESTLY: the body is hashed AFTER the edit, so report_sha256 agrees with it.
    # Every integrity gate is satisfied and the report is internally consistent. Only the PIN
    # refuses it.
    report = dict(body, report_sha256=_csha(body))
    if tamper_hash:                          # a flipped verdict that kept the old hash
        report["verdict"] = _cfg.W10_VERDICT_ADMIT
        report["bound_artifact"]["condition"] = condition
        report["report_sha256"] = "0" * 64
    with open(path, "w") as fh:
        json.dump(report, fh, indent=2, sort_keys=True)
    return path


# The Marson-SHAPED input builders live in `synthetic_inputs` — same fixtures, one module per
# purpose. Re-exported so callers keep a single import point.
from .synthetic_inputs import (  # noqa: E402,F401
    CELL_SYMBOLS,
    write_de_readout,
    write_ntc_h5ad,
    write_stage1_scores,
)

P2S_RUNTIME_LOCK_BYTES = b"# synthetic P2S runtime lock (sklearn + pert2state_model)\n"


def write_p2s_runtime_lock(path: str, *, pinned: bool = True) -> str:
    """A stand-in for stage02_p2s_runtime_lock.txt. Tests patch the pin to its hash.

    The real lock file does not exist yet (it must be generated in the spot-run env and
    committed); the GATE is what these tests exercise, not the specific bytes.
    """
    with open(path, "wb") as fh:
        fh.write(P2S_RUNTIME_LOCK_BYTES if pinned else b"# a different p2s environment\n")
    return path
