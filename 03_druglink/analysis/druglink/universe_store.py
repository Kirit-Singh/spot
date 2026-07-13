"""The run-independent, gene-keyed universe drug-evidence store.

One record per perturbation target. The store is a pure function of (universe targets,
resolved identity, ChEMBL evidence): it carries what the sources said and nothing more.

  * ``target_id_namespace`` is preserved on every row. Only ``ensembl_gene`` targets can
    join to drug evidence (via the Ensembl xref); a ``symbol``-only target is an explicit
    ``unsupported_namespace`` disposition, never a silent empty and never counted as ENSG.
  * ``action_type_source`` is carried VERBATIM. The store embeds no action vocabulary and
    NO precomputed direction: mechanism direction and arm compatibility are decided only
    at view time by the frozen :mod:`druglink.direction`. So the cache can never promote
    an action type the policy calls unknown.
  * ``max_phase`` is kept EXACTLY (:mod:`druglink.universe_max_phase`) — context only.

The store never ranks and never gates. Ranking, direction compatibility and admission are
computed downstream over a per-run VIEW of this store.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

from .hashing import content_hash
from .universe_max_phase import max_phase_fields

STORE_POLICY_VERSION = "stage3-universe-store-v1"

NS_ENSEMBL = "ensembl_gene"

DISP_DRUG_EVIDENCE = "drug_evidence"
DISP_NO_DRUG_EVIDENCE = "no_drug_evidence"
DISP_UNSUPPORTED_NAMESPACE = "unsupported_namespace"
DISP_AMBIGUOUS_IDENTITY = "ambiguous_identity"


def _drug_row(target_chembl_id: str, ev: dict[str, Any]) -> dict[str, Any]:
    """ONE assertion per ChEMBL ``mec_id``: full source/context identity, action_type
    VERBATIM, exact max_phase. Never collapsed by (molecule, target, action).

    Built explicitly (never copies the source dict) so no ``direction`` /
    ``development_state`` / precomputed field can leak into the cache. PubChem CID and
    UNII are NOT sourced by the pinned SQLite join and are omitted with explicit
    provenance; InChIKey (from ``compound_structures``) is retained.
    """
    row = {
        "source_row_id": ev.get("mec_id"),      # ChEMBL drug_mechanism PK — assertion id
        "molecule_chembl_id": ev["molecule_chembl_id"],
        "pref_name": ev.get("pref_name"),
        "target_chembl_id": target_chembl_id,
        "action_type_source": ev.get("action_type_source"),   # VERBATIM ChEMBL string
        "mechanism_of_action": ev.get("mechanism_of_action"),
        "molecular_mechanism": ev.get("molecular_mechanism"),
        "direct_interaction": ev.get("direct_interaction"),
        "disease_efficacy": ev.get("disease_efficacy"),
        "variant_id": ev.get("variant_id"),
        "variant_specific": ev.get("variant_id") is not None,
        # Only a NULL variant is general wild-type-gene evidence. A variant assertion
        # (incl. the ChEMBL sentinel -1 = 'UNDEFINED MUTATION') is not.
        "general_gene_rankable": ev.get("variant_id") is None,
        "selectivity_comment": ev.get("selectivity_comment"),
        "mechanism_refs": list(ev.get("mechanism_refs") or []),
        "molecule_type": ev.get("molecule_type"),
        "inchikey": ev.get("inchikey"),
        "cross_ref_provenance": {"pubchem_cid": "not_in_pinned_sqlite_source",
                                 "unii": "not_in_pinned_sqlite_source"},
    }
    row.update(max_phase_fields(ev.get("max_phase")))
    return row


def build_store_rows(
    *,
    universe_targets: Iterable[dict[str, str]],
    resolution: dict[str, dict[str, Any]],
    evidence_by_target: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Build one store row per universe target. Order-independent, source-faithful."""
    rows: list[dict[str, Any]] = []
    for tgt in universe_targets:
        tid = tgt["target_id"]
        ns = tgt["target_id_namespace"]
        if ns != NS_ENSEMBL:
            rows.append({
                "target_id": tid, "target_id_namespace": ns,
                "disposition": DISP_UNSUPPORTED_NAMESPACE,
                "identity": None, "drugs": [],
                "no_evidence_reason": "symbol_only_target_no_ensembl_xref_join",
            })
            continue

        res = resolution.get(tid, {"accessions": [], "targets": [],
                                   "identity_status": "unmapped",
                                   "shared_accession_genes": {}})
        _sort = lambda d: (d["target_chembl_id"], d["molecule_chembl_id"],
                           d.get("action_type_source") or "", str(d.get("source_row_id")))
        assertions = sorted(
            (_drug_row(t, ev) for t in res["targets"]
             for ev in evidence_by_target.get(t, [])), key=_sort)

        # (1) Ambiguous identity: a UniProt accession shared by >1 gene cannot attribute a
        # gene-drug edge to any one gene. Fail closed — preserve, never rank.
        if res["identity_status"] == "shared_accession":
            rows.append({
                "target_id": tid, "target_id_namespace": ns,
                "disposition": DISP_AMBIGUOUS_IDENTITY, "identity": res, "drugs": [],
                "ambiguous_source_assertions": assertions,
                "no_evidence_reason": "shared_uniprot_accession_maps_to_multiple_genes",
            })
            continue

        # (2) Variant split: only NULL-variant assertions are general wild-type-gene
        # evidence; variant-specific ones (incl. -1 UNDEFINED MUTATION) are preserved but
        # never enter the general gene-drug lane.
        drugs = [a for a in assertions if a["general_gene_rankable"]]
        variant = []
        for a in assertions:
            if not a["general_gene_rankable"]:
                a = dict(a, variant_disposition="variant_specific_nonrankable")
                variant.append(a)

        if drugs:
            disposition, reason = DISP_DRUG_EVIDENCE, None
        else:
            disposition = DISP_NO_DRUG_EVIDENCE
            if variant:
                reason = "only_variant_specific_assertions"
            elif res["identity_status"] == "unmapped":
                reason = "unmapped_no_uniprot_accession"
            elif not res["targets"]:
                reason = "no_single_protein_chembl_target"
            else:
                reason = "no_drug_mechanism_on_target"
        rows.append({
            "target_id": tid, "target_id_namespace": ns, "disposition": disposition,
            "identity": res, "drugs": drugs,
            "variant_specific_assertions": variant, "no_evidence_reason": reason,
        })
    return rows


def coverage_summary(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Namespace-split coverage. The ENSG denominator is NEVER conflated with the total."""
    rows = list(rows)
    n_ensg = sum(1 for r in rows if r["target_id_namespace"] == NS_ENSEMBL)
    n_symbol = sum(1 for r in rows
                   if r["disposition"] == DISP_UNSUPPORTED_NAMESPACE)
    return {
        "n_targets_total": len(rows),
        "n_ensg": n_ensg,
        "n_symbol_only_unsupported_namespace": n_symbol,
        "n_drug_evidence": sum(1 for r in rows
                               if r["disposition"] == DISP_DRUG_EVIDENCE),
        "n_no_drug_evidence": sum(1 for r in rows
                                  if r["disposition"] == DISP_NO_DRUG_EVIDENCE),
        "n_ambiguous_identity": sum(1 for r in rows
                                    if r["disposition"] == DISP_AMBIGUOUS_IDENTITY),
        "n_variant_specific_assertions": sum(
            len(r.get("variant_specific_assertions") or []) for r in rows),
        "n_general_drug_assertions": sum(len(r.get("drugs") or []) for r in rows),
        "coverage_denominator_note": (
            "general drug evidence is built over ENSG targets with UNAMBIGUOUS identity "
            "and NULL-variant assertions only; symbol-only => unsupported_namespace; "
            "shared-accession => ambiguous_identity; variant assertions are preserved but "
            "non-rankable; never reported as ENSG coverage"),
    }


def view_for_queue(*, store_rows: Iterable[dict[str, Any]],
                   target_queue: Iterable[str]) -> dict[str, Any]:
    """A per-run VIEW: a pure selection over the run-independent store.

    Re-acquires nothing, computes no ranks, and is independent of queue order — the same
    store and the same set of requested targets always yield the same ``view_id``. A
    requested target absent from the store is reported, never fabricated.
    """
    index = {r["target_id"]: r for r in store_rows}
    requested = sorted(set(target_queue))
    rows = [index[t] for t in requested if t in index]
    missing = [t for t in requested if t not in index]
    view_id = content_hash({
        "requested_targets": requested,
        "store_universe": sorted(index.keys()),
    })
    return {
        "view_id": view_id,
        "rows": rows,
        "missing_from_store": missing,
        "n_requested": len(requested),
        "n_covered": len(rows),
        "reacquired": False,
    }
