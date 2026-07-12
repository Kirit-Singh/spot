"""Stage-2 direct screen orchestrator.

Consumes an immutable Stage-1 selection contract and the pinned perturbation
artifacts; emits, under ``<out_root>/<run_id>/``:

    axis.json  input_manifest.json  contributing_guides.parquet  masks.parquet
    screen.parquet  guide_support.parquet  donor_support.parquet
    provenance.json  verification.json

ONLY the pooled-main estimate is projected. It is masked with its own contributing
guides — proven by the contributor manifest over the GLOBAL all-condition pooled-main
scope domain (``domain.py``) — or it is explicitly unresolved.

The by-guide and donor-pair estimates carry NO contributor evidence in this pass. They
are enumerated and emitted with an explicit unavailable state: no mask, no projection,
no replication claim, and no power to elevate an evidence tier. Nothing about a support
object can refuse a valid main estimate.

There is NO primary/headline arm: away_from_A and toward_B are two separate objectives,
each ranked over its own evaluable population. No p/q is emitted.

This module GENERATES artifacts. It does not verify them.
"""
from __future__ import annotations

import datetime as _dt
import os
from typing import Any, Optional

import numpy as np

from . import (
    arms,
    config,
    disposition,
    domain,
    donors,
    emit,
    gate,
    guides,
    identity,
    io_data,
    masks,
    pareto,
    runid,
    screen_row,
    support_lanes,
    trust,
)
from . import manifest as mf
from . import projection as proj
from . import selection as sel_mod
from . import universe as uni

_HERE = os.path.dirname(os.path.abspath(__file__))


# --------------------------------------------------------------------------- #
# Projection helpers.
# --------------------------------------------------------------------------- #
def _both_deltas(effect_row, axis: dict, gene_index: dict, mask_set) -> tuple:
    """Each pole's masked projection, computed independently."""
    da = arms.project_arm(effect_row, axis, "A", gene_index, mask_set)
    db = arms.project_arm(effect_row, axis, "B", gene_index, mask_set)
    scores = proj.arm_scores(da["delta"], db["delta"],
                             axis["A"]["sign"], axis["B"]["sign"])
    return da, db, scores


def _f(v) -> Optional[float]:
    if v is None:
        return None
    try:
        fv = float(v)
    except (TypeError, ValueError):
        return None
    return None if np.isnan(fv) else fv


def _b(v) -> Optional[bool]:
    return None if v is None else bool(v)


# --------------------------------------------------------------------------- #
# Shared input binding: preflight and the real build take the SAME path.
#
# There is no separate "audit loader". A preflight that validated something other than
# what the run consumes would be a preflight of a different program.
# --------------------------------------------------------------------------- #
def prepare(args) -> dict[str, Any]:
    """Bind every input up to (and NOT including) any dense effect-layer read."""
    lane = getattr(args, "lane", None) or config.LANE_PRODUCTION
    if lane not in config.LANES:
        raise sel_mod.SelectionError(
            f"unknown lane {lane!r}; expected one of {list(config.LANES)}")

    if lane == config.LANE_PRODUCTION:
        selection = sel_mod.load_production_selection(args.selection)
        if not getattr(args, "stage1_release", None):
            raise sel_mod.SelectionError(
                "production run requires --stage1-release (the immutable Stage-1 "
                "release manifest); an unbound Stage-1 is an untrusted Stage-1")
        release = trust.load_production_release(args.stage1_release)
    elif lane == config.LANE_RESEARCH:
        selection = sel_mod.load_research_selection(args.selection)
        if not getattr(args, "stage1_release", None):
            raise sel_mod.SelectionError(
                "research run requires --stage1-release (the verified v3 measurement "
                "bundle); research relaxes only the production gate, never the "
                "evidence")
        release = trust.load_research_release(args.stage1_release)
    else:
        selection = sel_mod.load_fixture_selection(args.selection)
        release = trust.load_fixture_release(
            args.registry, args.stage1_validation, args.stage1_gate_spec)

    if lane != selection.lane:
        raise sel_mod.SelectionError(
            f"production firewall: caller requested lane {lane!r} but the "
            f"selection contract declares lane {selection.lane!r}")

    axis = sel_mod.bind_release(selection, release)
    id_check = sel_mod.recomputed_ids(selection)
    cond = selection.analysis_condition
    identity_map = identity.load_identity_map(getattr(args, "target_identity_map", None))

    # ---- the GLOBAL, all-condition pooled-main identity universe (METADATA ONLY) ----
    # This is the evidence domain. It is NOT the selected-condition estimate universe,
    # and conflating the two was the P0 bug: the audited artifact is 33,983 pooled-main
    # scopes across all three conditions, and could never satisfy a selected-condition
    # main+guide+donor universe of ~40k.
    raw_identities = io_data.load_main_identity_universe(args.de_main)
    identities_by_condition = {
        c: {t: identity.resolve(r["released_estimate_id"], r["target_id"],
                                r["target_symbol"], identity_map)
            for t, r in targets.items()}
        for c, targets in raw_identities.items()
    }
    if cond not in identities_by_condition:
        raise sel_mod.SelectionError(
            f"the release ships no pooled-main estimate for condition {cond!r}; "
            f"released conditions are {sorted(identities_by_condition)}")
    identities = identities_by_condition[cond]
    global_scopes = domain.global_pooled_main_scopes(identities_by_condition)

    # ---- support: enumerated for ACCOUNTING, never projected (METADATA ONLY) ----
    guide_mods = [m for m in io_data.list_modalities(args.by_guide)
                  if m.startswith("guide_")]
    guide_ids = {m: io_data.load_support_identities(args.by_guide, m, cond)
                 for m in sorted(guide_mods)}
    donor_mods = io_data.list_modalities(args.by_donors)
    donor_ids = {m: io_data.load_support_identities(args.by_donors, m, cond)
                 for m in sorted(donor_mods)}
    observed = domain.observed_support_scopes(
        {m: v["by_target"] for m, v in guide_ids.items()},
        {p: v["by_target"] for p, v in donor_ids.items()}, cond)
    support = domain.support_contract(observed)

    # ---- the contributor manifest must cover EXACTLY the global pooled-main domain ----
    source_registry = io_data.load_source_registry(args.source_registry)
    manifest_doc = mf.load(
        args.guide_manifest, global_scopes, source_registry,
        base_dir=os.path.dirname(os.path.abspath(args.source_registry))
        if args.source_registry else "")
    manifest_index = (guides.build_manifest_index(manifest_doc["rows"])
                      if manifest_doc is not None else None)

    library = guides.build_library(io_data.load_sgrna_rows_by_target(args.sgrna))

    # ---- the effect-gene universe, before any projection (var only) ----
    # POOLED-MAIN ONLY. Only main is projected in this pass, so there is no second
    # object to hold a common axis with. Intersecting with the by-guide/by-donor gene
    # sets would discard pooled genes to match matrices no score is ever taken over —
    # a real change to every primary score, bought for nothing.
    gene_universe = uni.primary_universe(io_data.load_main_gene_ids(args.de_main))

    splits = donors.complementary_splits(sorted(donor_mods))
    splits["n_pairs"] = len(donor_mods)
    crosswalk = donors.donor_crosswalk(
        splits["donor_tokens"], io_data.load_donor_crosswalk(args.donor_crosswalk))

    return {
        "lane": lane, "selection": selection, "release": release,
        "axis": _restrict_axis(axis, gene_universe["gene_ids"]),
        "id_check": id_check, "cond": cond,
        "identities": identities, "identities_by_condition": identities_by_condition,
        "global_scopes": global_scopes, "n_global_scopes": len(global_scopes),
        "guide_ids": guide_ids, "donor_ids": donor_ids,
        "guide_mods": sorted(guide_mods), "donor_mods": sorted(donor_mods),
        "observed_support": observed, "support_contract": support,
        "manifest_doc": manifest_doc, "manifest_index": manifest_index,
        "library": library, "gene_universe": gene_universe,
        "splits": splits, "crosswalk": crosswalk,
    }


# --------------------------------------------------------------------------- #
# Main build.
# --------------------------------------------------------------------------- #
def build_screen(args) -> dict:
    created_at = _dt.datetime.now(_dt.timezone.utc).isoformat()

    # PRODUCTION FIREWALL, Stage-1 binding, the pooled-main evidence domain, the
    # manifest and the gene universe — all bound BEFORE any dense layer is read, by the
    # same ``prepare`` the preflight runs.
    ctx = prepare(args)

    # ...and then the SAME gate the preflight applies, over the SAME ctx, BEFORE the
    # dense read and before a single artifact exists. A build that could skip this
    # would make ``--preflight-only`` an advisory notice rather than a gate: the two
    # would answer different questions about identical inputs, and the one that writes
    # the science would be the weaker of them.
    from . import preflight  # imported here: preflight imports this module
    verdict = preflight.assess(args, ctx)
    if verdict["verdict"] != preflight.GO:
        # The failure text is carried through verbatim, not summarised into check names.
        # A refusal is the one place prose earns its keep: whoever has to fix this needs
        # to know WHICH contract failed and what to do about it.
        detail = "; ".join(f"[{f['check']}] {f['error']}" for f in verdict["failures"])
        raise gate.GateError(
            f"release gate refused this run; no result artifact was written. {detail}",
            report=verdict)
    release_gate = verdict["release_gate"]

    lane, selection, axis = ctx["lane"], ctx["selection"], ctx["axis"]
    cond, identities = ctx["cond"], ctx["identities"]
    library, manifest_index = ctx["library"], ctx["manifest_index"]
    manifest_doc, gene_universe = ctx["manifest_doc"], ctx["gene_universe"]
    splits, support = ctx["splits"], ctx["support_contract"]
    universe_ids = gene_universe["gene_ids"]

    # ---- the input pins, taken BEFORE the loop so a row can name its own source ----
    # Hashed once. Computing this after the loop and then re-hashing the DE object to
    # stamp the rows would read the pinned ~16 GB source twice for one number.
    manifest = emit.input_manifest({
        "GWCD4i.DE_stats.h5ad": args.de_main,
        "GWCD4i.DE_stats.by_guide.h5mu": args.by_guide,
        "GWCD4i.DE_stats.by_donors.h5mu": args.by_donors,
        "sgrna_library_metadata.suppl_table.csv": args.sgrna,
        "stage01_program_registry.json": args.registry,
        "stage01_selection_contract.json": args.selection,
    })
    identity_hashes = {
        "direct_method_version": config.METHOD_VERSION,
        "direct_config_sha256": runid.config_sha256(),
        "effect_source_sha256": next(
            e["sha256"] for e in manifest if e["name"] == "GWCD4i.DE_stats.h5ad"),
    }

    # ---- the ONLY dense read in the lane: the pooled main effect layers ----
    main = io_data.load_main(args.de_main, cond)
    meta, gene_index = main["meta"], main["gene_index"]
    targets = [str(t) for t in meta["target_id"]]

    screen_rows: list[dict] = []
    contrib_rows: list[dict] = []
    mask_rows: list[dict] = []
    guide_rows: list[dict] = []
    donor_rows: list[dict] = []

    for i, target in enumerate(targets):
        ident = identities[target]
        n_guides = _f(meta["n_guides"][i])
        n_cells = _f(meta["n_cells_target"][i])

        main_est = guides.Estimate(
            estimate_type=guides.MAIN, estimate_id="main",     # never the release key
            released_estimate_id=ident.released_estimate_id,
            target_id=target, target_ensembl=ident.target_ensembl,
            condition=cond, n_guides=n_guides, n_cells=n_cells,
            target_id_namespace=ident.target_id_namespace,
            target_symbol=ident.target_symbol,
            released_target_ensembl=ident.released_target_ensembl)
        # Resolved from the pooled manifest row and the POOLED n_guides alone. No
        # support object is consulted, so none can refuse a valid main estimate.
        main_contrib = guides.resolve(main_est, library, manifest_index)
        main_mask = masks.build_estimate_mask(main_est, main_contrib,
                                              library.get(ident.target_ensembl))
        contrib_rows += guides.contributor_rows(main_est, main_contrib)
        mask_rows += masks.mask_rows_for_emit(main_est, main_mask, universe_ids,
                                              run_id=None)
        mask_set = main_mask["gene_set"]

        da, db, scores = _both_deltas(main["log_fc"][i], axis, gene_index, mask_set)
        zda, zdb, zscores = _both_deltas(main["zscore"][i], axis, gene_index,
                                         mask_set)

        # BASE QC once: a function of neither arm's outcome.
        base_state, base_passed, base_reasons = disposition.base_qc(
            row_present=True, mask_resolved=main_mask["resolved"],
            n_cells=n_cells,
            low_target_gex=_b(meta["low_target_gex"][i]),
            ontarget_significant=_b(meta["ontarget_significant"][i]),
            n_guides=n_guides,
            target_identity_resolved=ident.ensembl_resolved)

        # SUPPORT: enumerated, explicitly unavailable, never projected, never masked.
        g_contrib, slots = support_lanes.guide_lane(ident, cond, ctx["guide_ids"])
        contrib_rows += g_contrib
        guide_rows += arms.guide_support_rows(target, cond, slots, run_id=None)

        d_contrib, pair_values = support_lanes.donor_lane(ident, cond, ctx["donor_ids"])
        contrib_rows += d_contrib
        donor_rows += arms.donor_support_rows(target, cond, pair_values,
                                              splits["splits"], scores,
                                              run_id=None, support_available=False)

        screen_rows.append(screen_row.screen_row(
            ident=ident, i=i, meta=meta, cond=cond, mask=main_mask,
            contrib=main_contrib, deltas={"A": da, "B": db},
            zdeltas={"A": zda, "B": zdb}, scores=scores, zscores=zscores,
            base_state=base_state, base_passed=base_passed,
            base_reasons=base_reasons, slots=slots, pair_values=pair_values,
            splits=splits, n_guides=n_guides, identity_hashes=identity_hashes))

    # ---- INDEPENDENT ranks: one per arm, over that arm's own population ----
    for arm in config.ARMS:
        proj.rank_arm(screen_rows, arm,
                      evaluable_key=f"{config.ARM_POLE[arm]}_evaluable",
                      rank_column=config.ARM_RANK_COLUMN[arm])

    # ---- the JOINT ordering: Pareto tiers over the two arms, added ALONGSIDE ----
    # Strictly additive. It reads the arm values and writes only its own three columns,
    # so neither arm's value nor either arm's rank can move because a joint field exists.
    # The verifier re-derives both arms from the inputs and would see it if they did.
    pareto.assign_tiers(screen_rows)
    ordered = proj.emit_order(screen_rows)

    # ---- identifiers: masks and inputs are bound BEFORE the run is named ----
    mask_sha = emit.mask_content_sha256(mask_rows)
    guide_manifest_block = mf.provenance_block(manifest_doc)
    binding = runid.build_run_binding(
        selection=selection, lane=lane, stage1_release=ctx["release"],
        stage2_inputs=manifest,
        # the BINDING carries the manifest's semantics, not its byte formatting: a
        # reordered manifest is the same manifest and must give the same run_id
        guide_manifest=mf.binding_block(manifest_doc), mask_sha256=mask_sha,
        gene_universe_sha256=gene_universe["sha256"],
        code_tree=runid.code_tree_sha256(_HERE),
        env_lock=runid.env_lock_block(args.env_lock),
        # what support the run claims is part of what the run IS
        support_contract=support,
        # ...as is WHICH evidence domain it stood on, and how big that domain was: a run
        # that silently changed domain, or that matched its manifest against a universe
        # one scope smaller, must not be able to keep this id
        evidence_domain=_domain_block(ctx),
        # ...and WHAT proved the release gate. An unbound gate can be swapped for a
        # friendlier one after the fact and the run would still answer to its name.
        release_gate=release_gate)
    run_id, run_sha = runid.run_id_of(binding)

    for rows in (screen_rows, mask_rows, guide_rows, donor_rows, contrib_rows):
        for r in rows:
            r["run_id"] = run_id

    out_dir = os.path.join(args.out_root, run_id)
    os.makedirs(out_dir, exist_ok=True)
    emit.write_parquet(mask_rows, os.path.join(out_dir, "masks.parquet"),
                       ["estimate_type", "estimate_id", "target_id",
                        "masked_gene_ensembl", "mask_reason", "guide_id"])
    emit.write_parquet(contrib_rows,
                       os.path.join(out_dir, "contributing_guides.parquet"),
                       ["estimate_type", "estimate_id", "target_id", "guide_id"])
    # emitted in stable target order: sorting by an arm would BE a headline rank
    emit.write_parquet(ordered, os.path.join(out_dir, "screen.parquet"),
                       ["target_id"],
                       nullable_int_columns=(tuple(config.ARM_RANK_COLUMN.values())
                                             + (pareto.TIER_COLUMN,)))
    emit.write_parquet(guide_rows, os.path.join(out_dir, "guide_support.parquet"),
                       ["target_id", "estimate_id", "arm"])
    emit.write_parquet(donor_rows, os.path.join(out_dir, "donor_support.parquet"),
                       ["target_id", "split_id", "arm"])
    emit.write_json(os.path.join(out_dir, "axis.json"),
                    emit.axis_record(run_id, selection, axis))
    emit.write_json(os.path.join(out_dir, "gene_universe.json"),
                    {"schema_version": "spot.stage02_gene_universe.v1",
                     "run_id": run_id, **gene_universe})
    emit.write_json(os.path.join(out_dir, "input_manifest.json"),
                    {"schema_version": emit.SCHEMA_MANIFEST, "run_id": run_id,
                     "files": manifest})

    prov = emit.provenance(
        run_id=run_id, run_sha256=run_sha, run_binding=binding, selection=selection,
        axis=axis, id_check=ctx["id_check"], guide_lanes=ctx["guide_mods"],
        guide_manifest=guide_manifest_block,
        donor_splits=splits, donor_crosswalk=ctx["crosswalk"],
        gene_universe=gene_universe,
        mask_sha256=mask_sha, manifest=manifest, created_at=created_at,
        support_contract=support, evidence_domain=_domain_block(ctx))
    emit.write_json(os.path.join(out_dir, "provenance.json"), prov)

    verification = emit.verification(
        out_dir=out_dir, run_id=run_id, run_sha256=run_sha, rows=ordered,
        mask_sha256=mask_sha, contributor_rows=contrib_rows, provenance_doc=prov,
        n_source_targets=len(targets), gene_universe=gene_universe, lane=lane)
    emit.write_json(os.path.join(out_dir, "verification.json"), verification)

    return {"run_id": run_id, "out_dir": out_dir, "n_rows": len(ordered),
            "lane": lane,
            "support_contract": support,
            "evidence_domain": _domain_block(ctx),
            "namespace": axis["namespace"],
            "production_eligible": axis["production_eligible"],
            "stage3_eligible": axis["stage3_eligible"],
            "mask_sha256": mask_sha,
            "gene_universe_sha256": gene_universe["sha256"],
            "verification": verification}


def _domain_block(ctx: dict) -> dict[str, Any]:
    """What evidence domain this run stood on, and how big it actually was."""
    return {
        "domain_id": domain.DOMAIN_ID,
        "rule_id": domain.DOMAIN_RULE_ID,
        "n_global_pooled_main_scopes": ctx["n_global_scopes"],
        "released_conditions": sorted(ctx["identities_by_condition"]),
        "analysis_condition": ctx["cond"],
        "n_main_estimates_in_analysis_condition": len(ctx["identities"]),
        "n_support_estimates_observed":
            ctx["observed_support"]["n_support_estimates"],
        "manifest_n_scopes": (None if ctx["manifest_doc"] is None
                              else ctx["manifest_doc"]["n_scopes"]),
        "manifest_n_rows": (None if ctx["manifest_doc"] is None
                            else ctx["manifest_doc"]["n_rows"]),
    }


def _restrict_axis(axis: dict, universe_ids: list[str]) -> dict:
    """Project every estimate on the SAME genes, whichever object it came from."""
    out = dict(axis)
    for pole in ("A", "B"):
        out[pole] = dict(axis[pole],
                         panel=uni.restrict(axis[pole]["panel"], universe_ids),
                         control=uni.restrict(axis[pole]["control"], universe_ids))
    return out



def main(argv=None):
    """CLI entry point (implemented in ``cli`` to keep this module focused)."""
    from .cli import main as _main
    return _main(argv)


if __name__ == "__main__":
    main()
