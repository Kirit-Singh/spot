"""Read the NEBPI criteria out of the primary source's actual bytes.

Grossman et al., Neuro-Oncology 2026, doi:10.1093/neuonc/noag051, PMC13338342, CC BY 4.0.
Tables 1 (Part I criteria) and 2 (Part II permeability classes).

TWO THINGS THIS MODULE EXISTS TO PREVENT

1. **A transcription nobody checked.** The criteria used to be hand-typed into
   `method/nebpi_grossman2026_v1.json`. A hand-typed table is a claim about a paper, and a
   claim about a paper is exactly the kind of thing that drifts silently. This module parses
   the cells out of the cached BioC XML, and `verifier/nebpi_source.py` — which imports none
   of this — parses them again and compares the method file cell for cell.

2. **A hash that cannot be re-verified.** The PMC BioC endpoint stamps the RETRIEVAL DATE into
   the envelope of every response:

       <date>20260711</date>   (pinned)      <date>20260712</date>   (re-fetched next day)

   Exactly one byte moves, the article does not change, and `raw_sha256` no longer matches. A
   reviewer re-fetching tomorrow gets `MISMATCH` on an untouched paper — which trains everyone
   to ignore the check. So the raw byte hash is kept as a SNAPSHOT hash, and the scientific
   identity is `content_sha256`: the same document with the API's retrieval-date envelope
   removed. That one IS stable across re-fetches, and it is what a reviewer can actually pin.
"""

from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from typing import Any, Optional

SOURCE_ID = "grossman2026_nebpi"
PART_I_TABLE_ID = "noag051-T1"
PART_II_TABLE_ID = "noag051-T2"

# The BioC envelope field the API stamps with the retrieval date. It is metadata about the
# FETCH, not about the article, so it is excluded from the scientific content hash.
RETRIEVAL_DATE_RE = re.compile(rb"<date>\s*\d{8}\s*</date>")


class NebpiSourceError(ValueError):
    """The cached source is not the document the NEBPI method was transcribed from."""


def content_bytes(raw: bytes) -> bytes:
    """The document with the API's retrieval-date envelope removed.

    This is the byte string whose hash is stable across re-fetches. Nothing else is stripped:
    every character of the article — every table cell, every footnote — is still in here.
    """
    return RETRIEVAL_DATE_RE.sub(b"<date></date>", raw, count=1)


def content_sha256(raw: bytes) -> str:
    return hashlib.sha256(content_bytes(raw)).hexdigest()


def raw_sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def retrieval_date(raw: bytes) -> Optional[str]:
    m = re.search(rb"<date>\s*(\d{8})\s*</date>", raw)
    return m.group(1).decode() if m else None


# --------------------------------------------------------------------------- passages


def _passages(raw: bytes) -> list[dict[str, Any]]:
    root = ET.fromstring(raw)
    out: list[dict[str, Any]] = []
    for p in root.iter("passage"):
        infons = {i.get("key"): (i.text or "") for i in p.findall("infon")}
        out.append({
            "offset": int(p.findtext("offset") or -1),
            "type": infons.get("type", ""),
            "section_type": infons.get("section_type", ""),
            "id": infons.get("id", ""),
            "text": p.findtext("text") or "",
        })
    return out


def _table_passage(raw: bytes, table_id: str) -> dict[str, Any]:
    for p in _passages(raw):
        if p["id"] == table_id and p["type"] == "table":
            return p
    raise NebpiSourceError(
        f"the cached source has no table passage {table_id!r}. This is not the document the "
        "NEBPI method was transcribed from.")


def _footnotes(raw: bytes, table_id: str) -> list[str]:
    return [p["text"] for p in _passages(raw)
            if p["id"] == table_id and p["type"] == "table_footnote"]


def _cells(text: str) -> list[str]:
    """BioC flattens a table to tab-separated cells with a lone-space row separator."""
    return [c.strip() for c in text.split("\t") if c.strip()]


# ------------------------------------------------------------------------ Part I rows


def part_i_rows(raw: bytes) -> list[dict[str, Any]]:
    """-> [{criterion_verbatim, importance_verbatim, row_index}] straight from Table 1.

    Table 1 is a two-column table: `Evaluation criteria | Level of importance`. The header row
    is dropped; every remaining pair is one criterion.
    """
    p = _table_passage(raw, PART_I_TABLE_ID)
    cells = _cells(p["text"])
    if cells[:2] != ["Evaluation criteria", "Level of importancea"]:
        raise NebpiSourceError(
            f"Table 1 header is {cells[:2]!r}, not the two-column "
            "(criteria, level of importance) header the NEBPI transcription assumes.")
    body = cells[2:]
    if len(body) % 2:
        raise NebpiSourceError(
            f"Table 1 has {len(body)} body cells, which is not an even number of "
            "(criterion, importance) pairs.")

    rows = []
    for i in range(0, len(body), 2):
        rows.append({
            "row_index": i // 2,
            "criterion_verbatim": body[i],
            "importance_verbatim": body[i + 1],
        })
    return rows


def part_i_footnote(raw: bytes) -> str:
    notes = _footnotes(raw, PART_I_TABLE_ID)
    if not notes:
        raise NebpiSourceError("Table 1 has no footnote in the cached source")
    return notes[0]


# ----------------------------------------------------------------------- Part II rows


def part_ii_rows(raw: bytes) -> list[dict[str, Any]]:
    """-> [{class_verbatim, definition_verbatim, potential_uses_verbatim}] from Table 2."""
    p = _table_passage(raw, PART_II_TABLE_ID)
    cells = _cells(p["text"])
    if cells[:3] != ["Permeability class", "Definition", "Potential uses"]:
        raise NebpiSourceError(
            f"Table 2 header is {cells[:3]!r}, not the three-column header the NEBPI "
            "transcription assumes.")
    body = cells[3:]
    if len(body) % 3:
        raise NebpiSourceError(
            f"Table 2 has {len(body)} body cells, which is not a multiple of 3.")

    rows = []
    for i in range(0, len(body), 3):
        rows.append({
            "row_index": i // 3,
            "class_verbatim": body[i],
            "definition_verbatim": body[i + 1],
            "potential_uses_verbatim": body[i + 2],
        })
    return rows


def part_ii_footnotes(raw: bytes) -> list[str]:
    notes = _footnotes(raw, PART_II_TABLE_ID)
    if not notes:
        raise NebpiSourceError("Table 2 has no footnote in the cached source")
    return notes


def locators(raw: bytes) -> dict[str, Any]:
    """Where in the source each table sits, so a re-read can find it without guessing."""
    t1 = _table_passage(raw, PART_I_TABLE_ID)
    t2 = _table_passage(raw, PART_II_TABLE_ID)
    return {
        "part_i": {"passage_id": t1["id"], "offset": t1["offset"],
                   "section_type": t1["section_type"]},
        "part_ii": {"passage_id": t2["id"], "offset": t2["offset"],
                    "section_type": t2["section_type"]},
    }
