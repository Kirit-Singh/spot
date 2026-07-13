"""PRODUCTION INPUT PREPARATION: the real, pinned Marson inputs -> what the P2S lane eats.

    python -m p2s_arms.prepare_inputs \
        --ntc            <ntc_clustered.h5ad>              # PINNED public Marson
        --stage1-scores  <stage01_scores_full.parquet>     # by barcode; READ, never recomputed
        --de-main        <GWCD4i.DE_stats.h5ad>            # PINNED readout layers
        --direct-bundle  <the W10-ADMITTED bundle for that condition>
        --w10-report     <DIRECT_BUNDLE_ADMISSION_<cond>.json>
        --env-lock       analysis/stage02_solver_lock.txt
        --stage1-release <the bound v3 release>
        --condition      Stim48hr
        --out-root       <outside every tracked tree>

WHY THIS EXISTS
---------------
Until now the only things that could produce ``cells.npz`` / ``effects.parquet`` /
``eligible.parquet`` were the SYNTHETIC builders. A lane whose inputs can only be made up is
not production-runnable, whatever its tests say.

WHERE EACH INPUT COMES FROM, AND FROM NOWHERE ELSE
--------------------------------------------------
  cells.npz       the pinned 396k cell matrix, at ONE condition, joined to Stage-1's
                  authoritative full score table BY BARCODE. Scores are READ. Genes are
                  crossed from SYMBOL to ENSEMBL through the DE readout's own pairing, and an
                  ambiguous symbol is dropped by name rather than guessed;
  effects.parquet the pinned DE readout's own ``zscore`` and ``log_fc`` layers, at that
                  condition;
  masks.parquet   the ADMITTED Direct bundle's own masks. Not re-derived — a mask this lane
                  computed for itself would be a different mask with the same name;
  eligible.parquet the ADMITTED Direct bundle's own arm rows (``base_state``). P2S cannot
                  admit or rescue a target the Direct screen found ineligible.

TCEFOLD ONLY. tcedirector reads ``GWCD4i.DE_stats.h5ad`` NON-DETERMINISTICALLY — same mtime,
same size, a DIFFERENT sha256 on re-read. Preparation refuses on any host where the bytes do
not hash to the pin, and that refusal is the gate working.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
from typing import Any

import h5py
import numpy as np
import pandas as pd
from direct import code_digest
from direct import io_data as direct_io

from . import binding, config, direct_inventory, prepare_cells, w10
from . import disposition as D

CELLS_FILE = "cells.npz"
EFFECTS_FILE = "effects.npz"
MASKS_FILE = "masks.parquet"
ELIGIBLE_FILE = "eligible.parquet"
MANIFEST_FILE = "p2s_inputs.json"
ARTIFACT_FILES = (CELLS_FILE, EFFECTS_FILE, MASKS_FILE, ELIGIBLE_FILE)

# A path that NAMES a fixture is not an input. Checked by name AS WELL AS by hash: the hash
# already refuses the wrong bytes, but a caller who reached for a fixture deserves to be told
# what they reached for, rather than a bare "sha mismatch" they will assume is a stale pin.
#
# Deliberately NOT in this list: "/tmp/" and "sample". Scratch legitimately lives under /tmp
# (see CLAUDE.md), and a firewall that refuses every ordinary working path is a firewall
# somebody turns off.
FIXTURE_TOKENS = ("fixture", "synthetic", "/tests/", "tests/", "mock", "dummy")

PINS = {"ntc": config.NTC_H5AD_SHA256, "de_main": config.DE_MAIN_SHA256,
        "stage1_scores": config.STAGE1_SCORES_RAW_SHA256}


def refuse_fixture_path(name: str, path: str) -> None:
    low = str(path).lower()
    hit = [t for t in FIXTURE_TOKENS if t in low]
    if hit:
        raise D.RefusalError(
            D.REFUSE_FIXTURE_PATH,
            f"--{name} points at {path!r}, which names {hit[0]!r}. Fixture bytes carry fixture "
            "numbers; a production run that consumed them would ship made-up science under a "
            "real artifact's provenance")


def check_pin(name: str, path: str, expected: str) -> str:
    """Hash the bytes HANDED IN. A path is not an input."""
    if not os.path.exists(path):
        raise D.RefusalError(D.REFUSE_INPUT_NOT_PINNED, f"--{name} {path!r} does not exist")
    actual = w10.file_sha256(path)
    if actual != expected:
        hint = ""
        if name == "de_main":
            hint = (". NOTE: tcedirector reads this file NON-DETERMINISTICALLY (same mtime, "
                    "same size, a different sha256 on re-read). tcefold is stable at the pin "
                    "— run preparation there")
        raise D.RefusalError(
            D.REFUSE_INPUT_NOT_PINNED,
            f"--{name} hashes to {actual[:16]}..., not the pinned {expected[:16]}...{hint}")
    return actual


def load_readout(de_main: str, condition: str) -> dict[str, Any]:
    """The DE readout at one condition: Ensembl ids, symbols, and the two effect layers."""
    main = direct_io.load_main(de_main, condition)
    with h5py.File(de_main, "r") as f:
        var = f["var"]
        symbols = [s.decode() if isinstance(s, bytes) else str(s)
                   for s in var["gene_name"][:]] if "gene_name" in var else []
    if not symbols:
        raise D.RefusalError(
            D.REFUSE_NAMESPACE_DRIFT,
            "the DE readout has no var/gene_name, so there is no authority to cross the cell "
            "matrix's symbols into Ensembl. This lane does not guess a gene")
    # `target_id` is EXACT obs.target_contrast, and it lives under `meta` — the loader keeps
    # the released identity columns together, and it is never parsed out of an index.
    #
    # h5py hands back BYTES for a plain string dataset. `str(b'T00')` is `"b'T00'"` — a
    # target id that matches nothing and looks almost right in a log.
    def _s(v):
        return v.decode() if isinstance(v, bytes) else str(v)

    return {"gene_ids": [_s(g) for g in main["gene_ids"]], "symbols": symbols,
            "target_id": [_s(t) for t in main["meta"]["target_id"]],
            "zscore": main["zscore"], "log_fc": main["log_fc"]}


def effects_matrix(readout: dict[str, Any], targets: list[str]) -> dict[str, Any]:
    """The effect layers as a MATRIX (targets x genes), float32. Never 116M long rows.

    One real condition is ~11,300 eligible targets x 10,282 readout genes. Long format would
    be ~116 MILLION rows of repeated string keys to express a dense rectangle — and the first
    thing any consumer does is group it back into the rectangle. So the container is the
    rectangle.
    """
    want = {t: i for i, t in enumerate(targets)}
    rows_of = {}
    for i, t in enumerate(readout["target_id"]):
        if t in want and t not in rows_of:
            rows_of[t] = i

    missing = [t for t in targets if t not in rows_of]
    if missing:
        raise D.RefusalError(
            D.REFUSE_BUNDLE_INCOMPLETE,
            f"{len(missing)} evaluable target(s) have no row in the DE readout at this "
            f"condition (e.g. {missing[:3]}). A target the screen found evaluable but the "
            "readout never measured is a contradiction this lane will not paper over")

    order = sorted(rows_of)
    take = [rows_of[t] for t in order]
    return {
        "target_ids": order,
        "gene_ids": readout["gene_ids"],
        "zscore": np.asarray(readout["zscore"][take], dtype=np.float32),
        "log_fc": np.asarray(readout["log_fc"][take], dtype=np.float32),
    }


def from_bundle(bundle_dir: str, *, programs: list[str], condition: str,
                readout_symbols: set) -> dict[str, Any]:
    """MAIN-estimate masks and ARM-SPECIFIC eligibility, via ``direct_inventory``.

    Masks are selected on the full estimate identity (main/main), never unioned across
    scopes, and an empty main mask is refused. Eligibility is ``evaluable`` on each program's
    OWN arm — and each program's two sign arms are proven to share one inventory. Every
    evaluable target must carry a mask; a missing one refuses rather than defaulting to the
    (most-permissive) empty mask.

    The eligible OUTPUT is arm-keyed, so the producer can filter to the arm it is fitting
    rather than inheriting a global set.
    """
    masks = direct_inventory.main_estimate_masks(bundle_dir)

    eligible_rows: list[dict[str, Any]] = []
    union: set = set()
    per_program: dict[str, int] = {}
    unresolved_total = 0
    for program_id in programs:
        inv = direct_inventory.bind(bundle_dir, program_id=program_id, condition=condition)
        per_program[program_id] = inv["eligible"]["n_evaluable"]
        unresolved_total += inv["n_symbol_targets_unresolved"]
        for arm_key in (inv["eligible"]["arm_key"], inv["eligible"]["sibling_arm_key"]):
            for t in inv["targets"]:
                eligible_rows.append({
                    "arm_key": arm_key, "program_id": program_id, "condition": condition,
                    "target_id": t, "state": inv["eligible"]["base_state_by_target"][t],
                    # target_ensembl from the MAIN MASK rows; null for symbol-namespace targets
                    "target_ensembl": inv["target_ensembl_by_target"].get(t),
                    "evaluable": True})
        union |= set(inv["targets"])

    # SYMBOL-NAMESPACE TARGETS: a null target_ensembl is legitimate ONLY IF the target's
    # symbol is PROVEN ABSENT from the pinned DE gene_name crosswalk. If the symbol is present
    # but was not uniquely mapped, its self-gene would go unmasked — REFUSE that target.
    ens_by_target: dict[str, Any] = {}
    for program_id in programs:
        inv = direct_inventory.bind(bundle_dir, program_id=program_id, condition=condition)
        ens_by_target.update(inv["target_ensembl_by_target"])
    null_targets = [t for t in union if not ens_by_target.get(t)]
    present_unmapped = sorted(t for t in null_targets if str(t) in readout_symbols)
    if present_unmapped:
        raise D.RefusalError(
            D.REFUSE_TARGET_SYMBOL_PRESENT_UNMAPPED,
            f"{len(present_unmapped)} target(s) have no target_ensembl yet their SYMBOL is "
            f"present in the DE readout (e.g. {present_unmapped[:3]}). A symbol that the "
            "crosswalk contains but did not map uniquely must be resolved or the target "
            "refused — never left with its self-gene unmasked")
    n_proven_absent = len([t for t in null_targets if str(t) not in readout_symbols])

    # every evaluable target (union across programs) MUST have a mask — checked here too, so
    # a target eligible for one program but unmasked cannot slip through on another's pass.
    unmasked = sorted(t for t in union if t not in masks["by_target"])
    if unmasked:
        raise D.RefusalError(
            D.REFUSE_MASK_MISSING_FOR_ELIGIBLE,
            f"{len(unmasked)} evaluable target(s) have NO main-estimate mask (e.g. "
            f"{unmasked[:3]}). A missing mask withholds nothing — the most permissive setting "
            "there is — and is never a default")

    return {"masks": masks["rows"], "mask_meta": {
                "n_rows_all_scopes": masks["n_rows_all_scopes"],
                "n_rows_main": masks["n_rows_main"], "scopes_unioned": masks["scopes_unioned"],
                "estimate_type": masks["estimate_type"], "estimate_id": masks["estimate_id"],
                "gene_column": masks["gene_column"],
                "n_symbol_targets_unresolved": len(null_targets),
                "n_symbol_targets_proven_absent_from_readout": n_proven_absent,
                "null_target_ensembl_requires_proven_absence": True,
                "target_genes_subtracted_globally": False},
            "eligible": eligible_rows,
            "targets": sorted(union),
            "n_evaluable_by_program": per_program}


def build(args, *, release=None, view=None) -> dict[str, Any]:
    """Prepare, bind, content-address, emit. Fail-closed with typed refusals.

    ``release``/``view`` are injectable so the tests can drive THIS function — the shipping
    one — without a full Stage-1 release tree on disk. Production always loads them from the
    bound release path.
    """
    created_at = _dt.datetime.now(_dt.timezone.utc).isoformat()

    if args.condition not in config.CONDITIONS:
        raise D.RefusalError(
            D.REFUSE_CONDITION_MISMATCH,
            f"--condition {args.condition!r} is not one of {list(config.CONDITIONS)}")

    for name, path in (("ntc", args.ntc), ("stage1-scores", args.stage1_scores),
                       ("de-main", args.de_main), ("direct-bundle", args.direct_bundle)):
        refuse_fixture_path(name, path)

    if args.max_cells is not None and args.lane in config.RELEASE_LANES:
        raise D.RefusalError(
            D.REFUSE_SUBSAMPLE_IN_PRODUCTION,
            f"--max-cells was supplied in the {args.lane!r} lane. A subsampled cell matrix is "
            "a smoke-test input: it produces real-looking numbers from a fraction of the "
            "cohort, and nothing downstream would say so")

    # 1. THE ADMISSION CHAIN — the same one the producer runs. Preparation may not build
    #    inputs against a bundle nobody admitted, or under an unpinned environment.
    admitted = binding.admit_inputs(
        bundle_dir=args.direct_bundle, w10_report=args.w10_report,
        env_lock=args.env_lock, lane=args.lane)
    admission = admitted["admission"]
    # THE SECOND ENVIRONMENT. The Direct lock pins where the arms came from; this pins where
    # preparation and the fit run. Two locks, bound separately.
    p2s_lock = binding.verify_p2s_runtime_lock(args.p2s_env_lock)

    if str(admission.get("condition")) != args.condition:
        raise D.RefusalError(
            D.REFUSE_CONDITION_MISMATCH,
            f"--condition {args.condition!r} is not the admitted bundle's condition "
            f"({admission.get('condition')!r})")

    # 2. THE PINS — hashed from the bytes handed in. Raw scores are HARD-GATED, not merely
    #    recorded; the canonical hash is gated inside prepare_cells.load_scores.
    ntc_sha = check_pin("ntc", args.ntc, PINS["ntc"])
    de_sha = check_pin("de_main", args.de_main, PINS["de_main"])
    scores_sha = check_pin("stage1-scores", args.stage1_scores, PINS["stage1_scores"])

    # 3. THE PROGRAM SET — derived from the bound release, never a copied count.
    if release is None or view is None:
        release, view = binding.load_release(
            release_path=args.stage1_release, kind=args.release_kind,
            validation_path=args.stage1_validation, gate_spec_path=args.stage1_gate_spec)
    binding.refuse_fixture_release(release, args.lane)

    if view["scorer_view_sha256"] != admission.get("scorer_view_sha256"):
        raise D.RefusalError(
            D.REFUSE_SCORER_MISMATCH,
            "the bound release derives a different scorer view from the one W10 admitted; "
            "these are not the same arms")

    # base-portable programs carry arms; the activation covariate must be SCORED (for the
    # design) but is NOT an arm and gets no eligibility of its own.
    arm_programs = list(view["admitted_program_ids"])
    score_programs = list(arm_programs)
    if config.ACTIVATION_PROGRAM_ID not in score_programs:
        score_programs.append(config.ACTIVATION_PROGRAM_ID)

    # 5. THE READOUT (loaded first — its symbols prove/refuse null target identities).
    readout = load_readout(args.de_main, args.condition)
    readout_symbols = {str(s) for s in readout["symbols"] if s}

    # 4. THE BUNDLE'S OWN masks (main estimate) and ARM-SPECIFIC eligibility.
    bundle = from_bundle(args.direct_bundle, programs=arm_programs, condition=args.condition,
                         readout_symbols=readout_symbols)
    cells = prepare_cells.build(
        ntc_path=args.ntc, scores_path=args.stage1_scores, condition=args.condition,
        program_ids=score_programs, readout_gene_ids=readout["gene_ids"],
        readout_symbols=readout["symbols"], max_cells=args.max_cells, seed=args.seed)

    eff = effects_matrix(readout, bundle["targets"])

    # 6. THE BINDING — what these inputs ARE, so a run cannot be re-attributed.
    inputs_binding = {
        "prepare_id": config.PREPARE_ID,
        "schema_version": config.SCHEMA_INPUTS,
        "lane": args.lane,
        "condition": args.condition,
        "raw_input_sha256": {
            "ntc_h5ad": ntc_sha, "stage1_scores": scores_sha, "de_main": de_sha},
        "pinned_input_sha256": dict(PINS),
        "stage1_scores": {
            "raw_sha256": scores_sha,
            "raw_sha256_pinned": config.STAGE1_SCORES_RAW_SHA256,
            "canonical_scores_sha256": cells["canonical"]["canonical_scores_sha256"],
            "canonical_scores_sha256_pinned": config.STAGE1_SCORES_CANONICAL_SHA256,
            "canonical_rederived": True,
            "read_by_barcode_never_recomputed": True,
        },
        "environment_locks": {
            "direct_solver_lock_sha256": admitted["solver_lock"]["sha256"],
            "p2s_runtime_lock_sha256": p2s_lock["sha256"],
            "direct_lock_executes_p2s": config.DIRECT_LOCK_EXECUTES_P2S,
        },
        "public_source": {"ntc": config.NTC_HF_SOURCE, "revision": config.NTC_HF_REVISION},
        "dims": cells["dims"],
        "n_effect_targets": len(eff["target_ids"]),
        "n_effect_genes": len(eff["gene_ids"]),
        "effect_container": "matrix (targets x genes), float32 — never long rows",
        "n_mask_rows": len(bundle["masks"]),
        "mask_contract": bundle["mask_meta"],
        "n_eligible_targets": len(bundle["targets"]),
        "eligibility_is_arm_specific": True,
        "n_evaluable_by_program": bundle["n_evaluable_by_program"],
        "barcode_join": cells["join"],
        "gene_namespace": {
            "cells": config.GENE_NAMESPACE_CELLS,
            "readout": config.GENE_NAMESPACE_READOUT,
            **{k: v for k, v in cells["crosswalk"].items() if k != "symbol_to_ensembl"},
        },
        "subsample": cells["subsample"],
        "program_ids": sorted(arm_programs),
        "scorer_view_sha256": view["scorer_view_sha256"],
        "donors": cells["donors_present"],
        "direct_binding": binding.bound_block(
            {"lane": args.lane, "solver_lock": admitted["solver_lock"],
             "admission": admission, "arm_bundle_run_id": admission.get("arm_bundle_run_id"),
             "arm_rows_sha256": admission.get("arm_rows_sha256"),
             "scorer_view_sha256": view["scorer_view_sha256"]}),
        "code_identity": code_digest.run_binding(
            require_clean=(args.lane in config.RELEASE_LANES
                           and not args.allow_dirty_tree)),
        "seed": args.seed,
    }
    run_id = w10.content_sha256(inputs_binding)[:config.RUN_ID_LEN]

    out_dir = os.path.join(args.out_root, run_id)
    os.makedirs(out_dir, exist_ok=True)

    np.savez(os.path.join(out_dir, CELLS_FILE),
             condition=np.asarray(args.condition),          # the scalar condition, in-band
             barcodes=np.asarray(cells["barcodes"], dtype=object).astype("U"),
             donors=np.asarray(cells["donors"], dtype=object).astype("U"),
             gene_ids=np.asarray(cells["gene_ids"], dtype=object).astype("U"),
             expr=cells["expr"],
             **{f"score__{p}": v for p, v in cells["scores"].items()})
    np.savez(os.path.join(out_dir, EFFECTS_FILE),
             target_ids=np.asarray(eff["target_ids"], dtype=object).astype("U"),
             gene_ids=np.asarray(eff["gene_ids"], dtype=object).astype("U"),
             zscore=eff["zscore"], log_fc=eff["log_fc"])
    # the producer loader reads (target_id, gene_id); the main-estimate gene is masked_gene_ensembl
    mask_out = [{"target_id": r["target_id"], "gene_id": r["gene_id"]}
                for r in bundle["masks"]]
    pd.DataFrame(mask_out).to_parquet(os.path.join(out_dir, MASKS_FILE), index=False)
    # eligibility is ARM-KEYED: the producer filters to the arm it is fitting
    pd.DataFrame(bundle["eligible"]).to_parquet(os.path.join(out_dir, ELIGIBLE_FILE),
                                                index=False)

    manifest = dict(
        inputs_binding,
        p2s_inputs_run_id=run_id,
        created_at=created_at,
        argv=list(sys.argv[1:]),
        artifact_sha256={n: w10.file_sha256(os.path.join(out_dir, n))
                         for n in ARTIFACT_FILES},
    )
    with open(os.path.join(out_dir, MANIFEST_FILE), "w") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True, default=str)
        fh.write("\n")

    return {"out_dir": out_dir, "p2s_inputs_run_id": run_id, "manifest": manifest,
            "paths": {"cells": os.path.join(out_dir, CELLS_FILE),
                      "effects": os.path.join(out_dir, EFFECTS_FILE),
                      "masks": os.path.join(out_dir, MASKS_FILE),
                      "eligible": os.path.join(out_dir, ELIGIBLE_FILE)}}


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Prepare the REAL, PINNED P2S inputs for one condition")
    ap.add_argument("--ntc", required=True, help="the pinned Marson cell matrix (h5ad)")
    ap.add_argument("--stage1-scores", required=True, dest="stage1_scores",
                    help="stage01_scores_full.parquet — scores are READ BY BARCODE")
    ap.add_argument("--de-main", required=True, dest="de_main",
                    help="GWCD4i.DE_stats.h5ad — TCEFOLD ONLY (tcedirector reads it "
                         "non-deterministically)")
    ap.add_argument("--direct-bundle", required=True, dest="direct_bundle")
    ap.add_argument("--w10-report", required=True, dest="w10_report")
    ap.add_argument("--env-lock", required=True, dest="env_lock",
                    help="the DIRECT solver lock (2983d140) — the environment the ARMS were "
                         "computed in")
    ap.add_argument("--p2s-env-lock", required=True, dest="p2s_env_lock",
                    help="the P2S RUNTIME lock (sklearn + pert2state_model) — a SEPARATE "
                         "environment; the Direct lock cannot execute this lane")
    ap.add_argument("--stage1-release", required=True)
    ap.add_argument("--condition", required=True, choices=list(config.CONDITIONS))
    ap.add_argument("--out-root", required=True)
    ap.add_argument("--release-kind", default="production",
                    choices=("production", "research_only", "fixture"))
    ap.add_argument("--stage1-validation", default=None)
    ap.add_argument("--stage1-gate-spec", default=None)
    ap.add_argument("--lane", default="production", choices=list(config.LANES))
    ap.add_argument("--seed", type=int, default=config.RANDOM_STATE)
    ap.add_argument("--max-cells", type=int, default=None,
                    help="SMOKE ONLY. Deterministic donor-balanced subsample; refused in a "
                         "release lane, recorded, and it changes the content id")
    ap.add_argument("--allow-dirty-tree", action="store_true")
    return ap


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    args = build_parser().parse_args(argv)
    try:
        out = build(args)
    except D.RefusalError as e:
        print(json.dumps({"state": "refused", "reason": e.reason,
                          "detail": e.message}, indent=2), file=sys.stderr)
        return 2

    m = out["manifest"]
    print(json.dumps({
        "p2s_inputs_run_id": out["p2s_inputs_run_id"],
        "out_dir": out["out_dir"],
        "condition": m["condition"],
        "dims": m["dims"],
        "barcode_join": m["barcode_join"],
        "n_eligible_targets": m["n_eligible_targets"],
        "subsampled": m["subsample"]["applied"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
