"""Generator-INDEPENDENT verifier for a built universe store + manifest (audit gate 10).

Imports only the shared content-addressing leaf (:mod:`druglink.hashing`) — never the
build logic (store/identity/eligibility/extract/manifest). It RE-DERIVES every identity
hash and every invariant from the store and manifest alone, so a store the generator
produced can be checked by code that shares none of the generator's assumptions. Any
silent mutation — a precomputed direction, a coarsened phase, a claimed ENSG coverage, a
dropped or duplicated assertion — fails closed.
"""
from __future__ import annotations

from typing import Any

from .hashing import content_hash

VERIFY_POLICY_VERSION = "stage3-universe-verify-v1"

# A cache drug row may carry only source-faithful fields. These are forbidden: they would
# mean the cache precomputed direction, coarsened the phase, invented a cross-ref, or
# smuggled a ranking in.
FORBIDDEN_DRUG_KEYS = frozenset({
    "direction", "intervention_effect", "directional_evidence_status",
    "development_state", "development_phase", "pubchem_cid", "unii",
    "rank", "score", "gate", "phase_rank", "priority",
})


def _manifest_identity(manifest: dict[str, Any]) -> str:
    def strip(node: Any) -> Any:
        if isinstance(node, dict):
            return {k: strip(v) for k, v in node.items()
                    if k not in ("created_at",) and k != "content_sha256"}
        if isinstance(node, list):
            return [strip(v) for v in node]
        return node
    return content_hash(strip(manifest))


def _typed_universe_hash(universe_targets: list[dict[str, str]]) -> str:
    typed = sorted(
        ({"target_id": t["target_id"],
          "target_id_namespace": t["target_id_namespace"]} for t in universe_targets),
        key=lambda r: (r["target_id_namespace"], r["target_id"]))
    return content_hash(typed)


def _recompute_coverage(store_rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "n_targets_total": len(store_rows),
        "n_ensg": sum(1 for r in store_rows
                      if r["target_id_namespace"] == "ensembl_gene"),
        "n_symbol_only_unsupported_namespace": sum(
            1 for r in store_rows if r["disposition"] == "unsupported_namespace"),
        "n_drug_evidence": sum(1 for r in store_rows
                               if r["disposition"] == "drug_evidence"),
        "n_no_drug_evidence": sum(1 for r in store_rows
                                  if r["disposition"] == "no_drug_evidence"),
        "n_ambiguous_identity": sum(1 for r in store_rows
                                    if r["disposition"] == "ambiguous_identity"),
        "n_variant_specific_assertions": sum(
            len(r.get("variant_specific_assertions") or []) for r in store_rows),
        "n_general_drug_assertions": sum(len(r.get("drugs") or [])
                                         for r in store_rows),
    }


def _independent_eligibility_verdict(rec: dict[str, Any]) -> str:
    """Re-derive the eligibility disposition from a record's predicate fields, WITHOUT
    importing the generator. Used to replay the frozen gate during admission."""
    if rec.get("target_type") != "SINGLE PROTEIN":
        return "reject_wrong_target_type"
    if rec.get("tax_id") != 9606:
        return "reject_nonhuman_target_taxon"
    if rec.get("species_group_flag") != 0:
        return "reject_species_group"
    if rec.get("n_components") != 1:
        return "reject_component_cardinality"
    c = (rec.get("components") or [{}])[0]
    if c.get("component_type") != "PROTEIN":
        return "reject_nonprotein_component"
    if c.get("tax_id") != 9606:
        return "reject_nonhuman_component_taxon"
    if c.get("homologue") != 0:
        return "reject_homologue"
    if not c.get("accession"):
        return "reject_missing_accession"
    return "eligible_human_single_protein"


def verify(*, store_rows: list[dict[str, Any]], manifest: dict[str, Any],
           universe_targets: list[dict[str, str]],
           eligibility_evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return {ok, violations}. ok is True only if no violation fires.

    If ``eligibility_evidence`` (the actual on-disk artifact) is supplied, its canonical
    hash is checked against the manifest pin AND every record's verdict is replayed from
    its predicate fields — so a mutated eligibility file fails closed even though the
    manifest and store are untouched.
    """
    v: list[str] = []

    # 1. manifest proves its own identity
    if _manifest_identity(manifest) != manifest.get("content_sha256"):
        v.append("manifest_identity_tamper")

    # 2. the store bytes hash to what the manifest recorded
    if content_hash(store_rows) != manifest.get("extraction", {}).get(
            "store_rows_sha256"):
        v.append("store_rows_hash_drift")

    # 3. the typed universe hashes to what the manifest bound
    if _typed_universe_hash(universe_targets) != manifest.get(
            "universe_binding", {}).get("universe_targets_sha256"):
        v.append("universe_targets_hash_mismatch")

    # 4. store_id binds source releases + typed universe + method
    ub = manifest.get("universe_binding", {})
    ext = manifest.get("extraction", {})
    rel = manifest.get("releases", {})
    recomputed_store_id = content_hash({
        "extraction_query_sha256": ext.get("extraction_query_sha256"),
        "chembl_source_sha256": rel.get("chembl", {}).get("source_sha256"),
        "uniprot_source_sha256": rel.get("uniprot", {}).get("source_sha256"),
        "universe_targets_sha256": ub.get("universe_targets_sha256"),
        "store_rows_sha256": ext.get("store_rows_sha256"),
        "eligibility_evidence_sha256": ext.get("eligibility_evidence_sha256"),
        "public_source_provenance_sha256": ext.get("public_source_provenance_sha256"),
    })
    if recomputed_store_id != manifest.get("store_id"):
        v.append("store_id_tamper")

    # 4b. the ACTUAL on-disk eligibility artifact (hash + verdict replay + counts)
    if eligibility_evidence is not None:
        if content_hash(eligibility_evidence) != ext.get("eligibility_evidence_sha256"):
            v.append("eligibility_evidence_hash_drift")
        recs = eligibility_evidence.get("records", [])
        for rec in recs:
            if _independent_eligibility_verdict(rec) != rec.get("disposition"):
                v.append(f"eligibility_verdict_replay_mismatch:{rec.get('target_chembl_id')}")
        counts = eligibility_evidence.get("counts", {})
        if counts.get("n_total") != len(recs):
            v.append("eligibility_counts_n_total_mismatch")
        if counts.get("n_eligible") != sum(1 for r in recs if r.get("eligible")):
            v.append("eligibility_counts_n_eligible_mismatch")

    # 5. coverage matches the typed universe rows; ENSG is never the total
    cov = manifest.get("coverage", {})
    recomputed = _recompute_coverage(store_rows)
    for k, val in recomputed.items():
        if cov.get(k) != val:
            v.append(f"coverage_mismatch:{k}")
    if recomputed["n_ensg"] + recomputed["n_symbol_only_unsupported_namespace"] \
            != recomputed["n_targets_total"]:
        v.append("coverage_split_incomplete")

    # 6. licenses packaged separately, verbatim
    if rel.get("chembl", {}).get("license") != "CC BY-SA 3.0":
        v.append("chembl_license")
    if rel.get("uniprot", {}).get("license") != "CC BY 4.0":
        v.append("uniprot_license")

    # 7. per-row invariants
    for r in store_rows:
        ns = r["target_id_namespace"]
        disp = r["disposition"]
        if ns != "ensembl_gene":
            if disp != "unsupported_namespace" or r["drugs"]:
                v.append(f"symbol_row_not_unsupported:{r['target_id']}")
            continue
        if disp == "unsupported_namespace":
            v.append(f"ensg_row_marked_unsupported:{r['target_id']}")
        # Ambiguous identity must carry NO rankable drug edge.
        if disp == "ambiguous_identity" and r["drugs"]:
            v.append(f"ambiguous_row_has_rankable_drugs:{r['target_id']}")
        seen_mec: set[Any] = set()
        for d in r["drugs"]:
            bad = FORBIDDEN_DRUG_KEYS & set(d.keys())
            if bad:
                v.append(f"forbidden_drug_key:{r['target_id']}:{sorted(bad)}")
            if d.get("source_row_id") is None:
                v.append(f"missing_mec_id:{r['target_id']}")
            elif d["source_row_id"] in seen_mec:
                v.append(f"duplicate_mec_id:{r['target_id']}:{d['source_row_id']}")
            else:
                seen_mec.add(d["source_row_id"])
            if not d.get("action_type_source"):
                v.append(f"missing_action_type:{r['target_id']}")
            if "max_phase_source" not in d or "max_phase_canonical" not in d:
                v.append(f"missing_exact_max_phase:{r['target_id']}")
            # only NULL-variant assertions may be in the general (rankable) lane
            if d.get("variant_id") is not None or d.get("general_gene_rankable") is False:
                v.append(f"variant_assertion_in_general_lane:{r['target_id']}")
        # preserved-but-non-rankable lists must still be source-clean (no direction etc.)
        for a in (r.get("variant_specific_assertions") or []):
            if FORBIDDEN_DRUG_KEYS & set(a.keys()):
                v.append(f"forbidden_key_in_variant_assertion:{r['target_id']}")
            if a.get("general_gene_rankable") is not False:
                v.append(f"variant_assertion_marked_rankable:{r['target_id']}")
        for a in (r.get("ambiguous_source_assertions") or []):
            if FORBIDDEN_DRUG_KEYS & set(a.keys()):
                v.append(f"forbidden_key_in_ambiguous_assertion:{r['target_id']}")
            # every nested/copied ambiguous assertion must be non-rankable AND carry the
            # named disposition, so a flattened consumer cannot treat it as general
            # evidence by following either field alone
            if a.get("general_gene_rankable") is not False:
                v.append(f"ambiguous_assertion_marked_rankable:{r['target_id']}")
            if a.get("ambiguity_disposition") != "ambiguous_identity_nonrankable":
                v.append(f"ambiguous_assertion_missing_disposition:{r['target_id']}")

    return {"ok": not v, "violations": sorted(set(v)),
            "verify_policy_version": VERIFY_POLICY_VERSION}


def verify_from_disk(*, store_dir: str, manifest: dict[str, Any],
                     universe_targets: list[dict[str, str]]) -> dict[str, Any]:
    """Disk-level admission: load and hash the ACTUAL store rows + eligibility artifact
    from ``store_dir`` (not the in-memory objects), then verify. Catches an artifact
    altered on disk after generation even when the manifest is untouched."""
    import json
    import os
    with open(os.path.join(store_dir, "universe_store.rows.json")) as fh:
        rows = json.load(fh)
    with open(os.path.join(store_dir, "target_eligibility_evidence.json")) as fh:
        elig = json.load(fh)
    return verify(store_rows=rows, manifest=manifest,
                  universe_targets=universe_targets, eligibility_evidence=elig)
