"""UniProt adapter: Ensembl gene <-> UniProt accession crosswalk.

Only an explicit Ensembl ``GeneId`` cross-reference produces a mapping row. An
entry without one maps nothing: the gene stays unmapped rather than guessed. A
gene SYMBOL that merely resembles the entry's name is not a cross-reference and
never becomes a mapping.

Real UniProt returns VERSIONED gene IDs (``ENSG00000163599.18``); the version
suffix is stripped so the ID joins Direct's unversioned ``target_ensembl``. Every
accession an entry set carries is preserved: one Ensembl gene legitimately maps to
several accessions (one reviewed Swiss-Prot entry plus TrEMBL entries), and
collapsing that to "the" accession would silently drop real targets.

``research_ready``: this parse is tested against pinned REAL UniProtKB responses
(release 2026_02) in ``tests/test_public_acquisition.py``. It is not production-ready.
"""
from __future__ import annotations

from typing import Any

from . import base
from .base import require

SOURCE = "uniprot"
VERSION = "uniprot-adapter-v2"


def parse_search(raw: Any, entry: dict[str, Any], src_id: str) -> list[dict[str, Any]]:
    require(isinstance(raw, dict) and isinstance(raw.get("results"), list),
            "UniProt search response must carry a 'results' array")
    out: list[dict[str, Any]] = []
    for rec in raw["results"]:
        acc = rec.get("primaryAccession")
        if not acc:
            continue
        organism = (rec.get("organism") or {}).get("scientificName")
        genes: set[str] = set()
        for xref in rec.get("uniProtKBCrossReferences") or []:
            if xref.get("database") != "Ensembl":
                continue
            for prop in xref.get("properties") or []:
                if prop.get("key") == "GeneId" and prop.get("value"):
                    genes.add(str(prop["value"]).split(".")[0])
        for ensembl in sorted(genes):
            out.append(base.gene_map(source=SOURCE, source_record_id=src_id,
                                     target_ensembl=ensembl, uniprot_id=acc,
                                     organism=organism))
    return out


ADAPTERS = {
    "uniprot_search": base.Adapter(
        "uniprot_search", VERSION, SOURCE, base.RESEARCH_READY,
        ("/uniprotkb/search",), parse_search,
        note="parse tested against pinned real UniProtKB 2026_02 responses"),
}
