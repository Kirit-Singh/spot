"""Conflict-aware ENSG <-> UniProt <-> ChEMBL identity resolution for the universe store.

The run-independent universe cache joins a perturbation target (Ensembl gene, ENSG) to
its drug evidence through UniProt accessions and ChEMBL SINGLE PROTEIN targets. Two
multiplicities are handled EXPLICITLY, never by last-write-wins:

  * one gene -> many accessions        kept as a sorted relation (isoforms/entries);
  * one accession -> many genes         a SHARED accession: every gene that touches it is
                                        named, and NONE is silently dropped.

The existing ``targets.build`` does ``uniprot_to_gene[accession] = ensg`` (a dict
assignment), so a shared accession loses all but the last gene. This module refuses that:
resolution is a pure function of the *set* of relations — order-independent, duplicate-
tolerant, and it names conflicts rather than resolving them by arrival order.

``resolve_identity`` decides ONLY identity. It never touches direction, approval, or
ranking, and it invents no mapping a source did not state.
"""
from __future__ import annotations

from typing import Any, Iterable

IDENTITY_POLICY_VERSION = "stage3-universe-identity-v1"

STATUS_RESOLVED = "resolved"
STATUS_SHARED_ACCESSION = "shared_accession"
STATUS_UNMAPPED = "unmapped"


def resolve_identity(
    *,
    universe_ensg: Iterable[str],
    gene_accessions: Iterable[tuple[str, str]],
    accession_targets: Iterable[tuple[str, str]],
) -> dict[str, dict[str, Any]]:
    """Resolve each universe ENSG to its accessions and SINGLE-PROTEIN ChEMBL targets.

    Args:
      universe_ensg: the ENSG targets to resolve (symbol-only targets are NOT passed
        here; they are handled as ``unsupported_namespace`` by the store builder).
      gene_accessions: (ensg, uniprot_accession) relations from the UniProt Ensembl xref.
      accession_targets: (uniprot_accession, target_chembl_id) relations from ChEMBL
        SINGLE PROTEIN target components.

    Returns a dict ``ensg -> {accessions, targets, identity_status,
    shared_accession_genes}`` with deterministic, sorted, deduplicated contents.
    """
    universe = set(universe_ensg)

    # gene -> {accessions}, restricted to the universe. A set dedups and makes the
    # result independent of arrival order; a shared accession is preserved on BOTH genes.
    gene_to_acc: dict[str, set[str]] = {g: set() for g in universe}
    acc_to_genes: dict[str, set[str]] = {}
    for gene, acc in gene_accessions:
        if gene not in universe:
            continue
        gene_to_acc[gene].add(acc)
        acc_to_genes.setdefault(acc, set()).add(gene)

    acc_to_targets: dict[str, set[str]] = {}
    for acc, target in accession_targets:
        acc_to_targets.setdefault(acc, set()).add(target)

    out: dict[str, dict[str, Any]] = {}
    for gene in universe:
        accs = sorted(gene_to_acc[gene])
        targets: set[str] = set()
        shared: dict[str, list[str]] = {}
        for acc in accs:
            targets |= acc_to_targets.get(acc, set())
            sharers = acc_to_genes.get(acc, {gene})
            if len(sharers) > 1:
                shared[acc] = sorted(sharers)
        if not accs:
            status = STATUS_UNMAPPED
        elif shared:
            status = STATUS_SHARED_ACCESSION
        else:
            status = STATUS_RESOLVED
        out[gene] = {
            "accessions": accs,
            "targets": sorted(targets),
            "identity_status": status,
            "shared_accession_genes": shared,
        }
    return out
