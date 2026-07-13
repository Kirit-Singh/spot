"""The ALL-ARM pathway bundle: 20 reusable enrichment arms, ONE shared convergence.

ROUND4_ADDENDUM c4773562. Six physical bundles — 3 conditions x 2 pinned sources — each
carrying every admitted program's two enrichment arms, keyed on `desired_change`. No pair,
no role, no pole.

THE ASYMMETRY THAT DRIVES THE WHOLE DESIGN
------------------------------------------
The two things this bundle holds are NOT the same kind of thing, and the addendum is explicit
about it:

  * ENRICHMENT is per (program, desired_change). It is computed over a RANKED LIST, and a
    ranking is NOT antisymmetric — the pathways at the top of an ordering are not the mirror
    image of those at the bottom. So all 20 arms are COMPUTED. Inferring the `decrease` arm
    from the `increase` arm by assumed rank antisymmetry is refused by name in ``arm_keys``,
    and it is not done here;

  * CONVERGENCE depends only on the masked perturbation SIGNATURES for the (condition,
    source). It does not know which program is being asked about, or in which direction. So
    it is computed ONCE and REFERENCED by all 20 arms. Restating one claim 20 times is 20
    chances to disagree with it, and a reader cannot tell which copy was the one that got
    checked.

So: 120 enrichment arms across the release (10 x 2 x 3 x 2), and 6 convergence artifacts —
not 120.
"""
from __future__ import annotations

from typing import Any, Optional

from . import arm_keys, convergence, enrichment, genesets, signature_matrix
from .hashing import content_hash

SCHEMA_VERSION = "spot.stage02_pathway_arm_bundle.v1"
BUNDLE_ID = "spot.stage02.pathway.all_arm_bundle.v1"
CONVERGENCE_SCHEMA = "spot.stage02_pathway_convergence.v2"


def ranked_by_arm(arm_rows: list[dict[str, Any]]) -> dict[str, list[tuple[str, float]]]:
    """Each arm's ranked target list, taken from the DIRECT arm rows.

    The pathway arms enrich the very ranking the Direct bundle emitted — not a ranking
    rebuilt here from the same inputs, which could differ. A pathway result that ranked its
    targets differently from the arm it claims to describe would be describing a different
    arm.
    """
    out: dict[str, list[tuple[str, float]]] = {}
    for r in arm_rows:
        if r.get("rank") is None or r.get("value") is None:
            continue
        out.setdefault(r["arm_key"], []).append((str(r["target_id"]), float(r["value"]),
                                                 int(r["rank"])))
    return {k: [(t, v) for t, v, _ in sorted(v3, key=lambda x: x[2])]
            for k, v3 in out.items()}


def enrichment_arms(*, arm_rows: list[dict[str, Any]], bundle: dict[str, Any],
                    admitted: list[str], condition: str,
                    source: str) -> list[dict[str, Any]]:
    """One record per (arm, gene set). Every arm COMPUTED — never inferred from its twin."""
    rankings = ranked_by_arm(arm_rows)
    records: list[dict[str, Any]] = []

    for program_id in admitted:
        for change in arm_keys.DESIRED_CHANGES:
            arm_key = arm_keys.direct_arm_key(program_id, change, condition)
            enr_key = arm_keys.pathway_arm_key(program_id, change, condition, source)
            ranked = rankings.get(arm_key, [])

            for set_id in sorted(bundle["sets"]):
                s = bundle["sets"][set_id]
                # membership is tested in the PERTURBATION-TARGET universe: the arms rank
                # perturbed targets, and a readout gene that was never perturbed cannot be
                # a hit in a ranking of perturbations (B1).
                e = enrichment.enrich_one(ranked, set(s["genes_in_target_universe"]))
                n_src = s["n_source_symbols"]

                gcov = genesets.coverage_disposition(
                    s["n_genes_in_target_universe"] / n_src if n_src else None)
                arm_disp = genesets.arm_disposition(
                    global_policy_passed=gcov["global_coverage_policy_passed"],
                    n_hits_in_ranking=e["n_hits_in_ranking"],
                    enrichment_value=e["enrichment_value"],
                    n_source_symbols=n_src)

                records.append({
                    "pathway_arm_key": enr_key,
                    "direct_arm_key": arm_key,
                    "program_id": program_id,
                    "desired_change": change,
                    "condition": condition,
                    "source": source,
                    "set_id": set_id,
                    "set_name": s["name"],
                    "n_source_symbols": n_src,
                    "n_genes_in_target_universe": s["n_genes_in_target_universe"],
                    "target_source_coverage": (
                        gcov["global_coverage_disposition"] and
                        (round(s["n_genes_in_target_universe"] / n_src, 6)
                         if n_src else None)),
                    "global_coverage_disposition": gcov["global_coverage_disposition"],
                    "global_coverage_policy_passed":
                        gcov["global_coverage_policy_passed"],
                    "enrichment_value": e["enrichment_value"],
                    "leading_edge": e["leading_edge"],
                    "n_leading_edge": e["n_leading_edge"],
                    "leading_edge_side": e["leading_edge_side"],
                    "peak_rank": e["peak_rank"],
                    "undefined_reason": e["undefined_reason"],
                    **arm_disp,
                    # WHICH convergence artifact this arm stands on. A REFERENCE, never a
                    # copy: see convergence_artifact().
                    "convergence_ref": arm_keys.convergence_key(condition, source),
                })
    return records


def convergence_artifact(*, bundle: dict[str, Any],
                         signatures: dict[str, dict[str, float]],
                         condition: str, source: str,
                         readout_universe_sha256: str,
                         pairwise_workers: int = convergence.DEFAULT_PAIRWISE_WORKERS,
                         pair_chunk_size: int = convergence.DEFAULT_PAIR_CHUNK_SIZE,
                         ) -> dict[str, Any]:
    """The ONE convergence claim for this (condition, source). Referenced, never copied.

    It carries no program and no desired_change, because it depends on neither: it is a
    statement about which perturbations move the transcriptome together, and that does not
    change with the direction somebody wishes a program would go.
    """
    pairs = convergence.pairwise_within_sets(
        bundle, signatures, workers=pairwise_workers, chunk_size=pair_chunk_size)
    sets = convergence.converge_sets(bundle, signatures, pairs)
    doc = {
        "schema_version": CONVERGENCE_SCHEMA,
        "convergence_key": arm_keys.convergence_key(condition, source),
        "condition": condition,
        "source": source,
        "convergence_method_id": convergence.METHOD_ID,
        "convergence_size_policy_id": convergence.CONVERGENCE_SIZE_POLICY_ID,
        "min_convergence_set_size": convergence.MIN_CONVERGENCE_SET_SIZE,
        "max_convergence_set_size": convergence.MAX_CONVERGENCE_SET_SIZE,
        "readout_universe_sha256": readout_universe_sha256,
        "is_shared_across_arms": True,
        "depends_on_program_or_desired_change": False,
        "n_signature_targets": len(signatures),
        "n_intra_set_pairs": len(pairs),
        "n_sets": len(sets),
        "n_convergence_evaluable_sets": sum(
            1 for record in sets if record["convergence_evaluable"]),
        "n_convergence_non_evaluable_sets": sum(
            1 for record in sets if not record["convergence_evaluable"]),
        "sets": sets,
    }
    doc["convergence_sha256"] = content_hash(
        {k: v for k, v in doc.items() if k != "convergence_sha256"})
    return doc


def arm_manifest(records: list[dict[str, Any]], *, admitted: list[str],
                 condition: str, source: str) -> list[dict[str, Any]]:
    """ONE entry per logical enrichment-arm slot: |admitted| x 2. Emitted even when empty."""
    index: dict[str, list[dict[str, Any]]] = {}
    for r in records:
        index.setdefault(r["pathway_arm_key"], []).append(r)

    out = []
    for program_id in admitted:
        for change in arm_keys.DESIRED_CHANGES:
            key = arm_keys.pathway_arm_key(program_id, change, condition, source)
            rs = index.get(key, [])
            out.append({
                "pathway_arm_key": key,
                "program_id": program_id,
                "desired_change": change,
                "condition": condition,
                "source": source,
                "n_sets": len(rs),
                "n_headline_rankable": sum(1 for r in rs if r["arm_headline_rankable"]),
                "n_enrichment_defined": sum(
                    1 for r in rs if r["enrichment_value"] is not None),
                "convergence_ref": arm_keys.convergence_key(condition, source),
                "records_sha256": content_hash(
                    sorted(rs, key=lambda r: r["set_id"])),
            })
    return out


def expected_slots(admitted: list[str]) -> int:
    """|admitted| x 2 desired changes. DERIVED — never a copied count."""
    return len(admitted) * len(arm_keys.DESIRED_CHANGES)


def method_block(bundle: Optional[dict[str, Any]], view: dict[str, Any]) -> dict[str, Any]:
    return {
        "bundle_id": BUNDLE_ID,
        "schema_version": SCHEMA_VERSION,
        "enrichment_method_id": enrichment.METHOD_ID,
        "enrichment_statistic_name": enrichment.STATISTIC_NAME,
        "convergence_method_id": convergence.METHOD_ID,
        "convergence_size_policy_id": convergence.CONVERGENCE_SIZE_POLICY_ID,
        "min_convergence_set_size": convergence.MIN_CONVERGENCE_SET_SIZE,
        "max_convergence_set_size": convergence.MAX_CONVERGENCE_SET_SIZE,
        "arm_key_rule_id": arm_keys.ARM_KEY_RULE_ID,
        "mapping_rule_id": arm_keys.MAPPING_RULE_ID,
        "coverage_policy_id": genesets.COVERAGE_POLICY_ID,
        "min_source_coverage": genesets.MIN_SOURCE_COVERAGE,
        "min_arm_ranked_members": genesets.MIN_ARM_RANKED_MEMBERS,
        "scorer_view_id": view["view_id"],
        "scorer_view_sha256": view["scorer_view_sha256"],
        "n_admitted_programs": view["n_admitted_programs"],
        "n_expected_arm_slots": expected_slots(view["admitted_program_ids"]),
        # every arm computed; convergence shared, not restated
        "enrichment_arms_are_computed_not_derived": True,
        "enrichment_rank_antisymmetry_assumed": False,
        "convergence_is_shared_across_arms": True,
        # the amended bitmap semantics this bundle's signatures were read under
        "bitmap_rule_id": signature_matrix.BITMAP_RULE_ID,
        "bitmap_rule": signature_matrix.BITMAP_RULE,
        # what this bundle will not carry, at any depth
        "pair_fields_emitted": False,
        "pole_or_role_emitted": False,
        "pareto_emitted": False,
        "joint_status_emitted": False,
        "combined_objective_permitted": False,
        "inference_status": enrichment.INFERENCE_STATUS,
        "gene_sets": genesets.binding_block(bundle),
    }


def build(*, condition: str, source: str, view: dict[str, Any],
          bundle: dict[str, Any], arm_rows: list[dict[str, Any]],
          convergence_doc: dict[str, Any]) -> dict[str, Any]:
    admitted = view["admitted_program_ids"]
    records = enrichment_arms(arm_rows=arm_rows, bundle=bundle, admitted=admitted,
                              condition=condition, source=source)
    manifest = arm_manifest(records, admitted=admitted, condition=condition,
                            source=source)
    return {
        "schema_version": SCHEMA_VERSION,
        "condition": condition,
        "source": source,
        "method": method_block(bundle, view),
        "scorer_view": view,
        "n_arm_slots": len(manifest),
        "n_expected_arm_slots": expected_slots(admitted),
        "n_records": len(records),
        "arms": manifest,
        "records": records,
        "convergence_ref": convergence_doc["convergence_key"],
        "convergence_sha256": convergence_doc["convergence_sha256"],
        "records_sha256": content_hash(
            sorted(records, key=lambda r: (r["pathway_arm_key"], r["set_id"]))),
    }
