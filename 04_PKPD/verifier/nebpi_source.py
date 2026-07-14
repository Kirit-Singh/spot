"""Independent re-read: does the NEBPI method file say what the paper says?

Everything else in `verifier/` checks that Stage 4 computed correctly from its method. Nothing
checks that the METHOD is what the source states — and a method file is a hand-maintained claim
about a paper, which is exactly the kind of claim that drifts.

So this re-reads the primary source's bytes, re-parses Tables 1 and 2 with its OWN parser, and
compares every encoded criterion against them CELL FOR CELL:

    * the criterion's verbatim text is the cell that is actually in Table 1;
    * its level of importance is the letter that is actually beside it;
    * the row ORDER is the source's order (nothing reordered, dropped or merged);
    * Table 1 has exactly the rows the method says it has — no criterion invented, none lost;
    * every Part-II class definition is the definition Table 2 gives;
    * the footnotes are the footnotes.

It imports NOTHING from `analysis/` — not the extractor, not the models. If both parsers agree
because they share a bug, they are not two parsers. This one is deliberately written differently
(regex over the raw bytes, not an XML tree walk).

It also re-checks the source binding: `content_sha256` must reproduce, and it must be STABLE —
the raw byte hash is not, because the PMC BioC endpoint stamps the retrieval date into every
response, so an untouched paper re-fetched tomorrow has a different raw hash. Pinning only the
raw hash trains a reviewer to ignore a MISMATCH they see every day.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any

SOURCE_ID = "grossman2026_nebpi"
CACHE_FILENAME = "PMC13338342.bioc.xml"
PART_I_TABLE_ID = "noag051-T1"
PART_II_TABLE_ID = "noag051-T2"

DATE_ENVELOPE = re.compile(rb"<date>\s*\d{8}\s*</date>")

# Deliberately NOT an XML tree walk: `analysis/nebpi_source.py` uses ElementTree, so this one
# reads the passages out of the raw bytes with a regex. Two parsers that share an implementation
# are one parser.
PASSAGE_RE = re.compile(
    rb"<passage>(?P<body>.*?)</passage>", re.DOTALL)
INFON_RE = re.compile(rb'<infon key="(?P<k>[^"]+)">(?P<v>.*?)</infon>', re.DOTALL)
TEXT_RE = re.compile(rb"<text>(?P<t>.*?)</text>", re.DOTALL)


class NebpiRereadError(AssertionError):
    """The method file does not say what the source says."""


def _unescape(b: bytes) -> str:
    s = b.decode("utf-8")
    for a, x in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                 ("&quot;", '"'), ("&apos;", "'")):
        s = s.replace(a, x)
    return s


def _table_cells(raw: bytes, table_id: str, kind: bytes = b"table") -> list[str]:
    want_id = table_id.encode()
    for m in PASSAGE_RE.finditer(raw):
        body = m.group("body")
        infons = {k: v for k, v in INFON_RE.findall(body)}
        if infons.get(b"id") != want_id or infons.get(b"type") != kind:
            continue
        t = TEXT_RE.search(body)
        if not t:
            continue
        return [c.strip() for c in _unescape(t.group("t")).split("\t") if c.strip()]
    raise NebpiRereadError(f"the source has no {kind.decode()} passage {table_id!r}")


def _footnotes(raw: bytes, table_id: str) -> list[str]:
    want_id = table_id.encode()
    out = []
    for m in PASSAGE_RE.finditer(raw):
        body = m.group("body")
        infons = {k: v for k, v in INFON_RE.findall(body)}
        if infons.get(b"id") != want_id or infons.get(b"type") != b"table_footnote":
            continue
        t = TEXT_RE.search(body)
        if t:
            out.append(_unescape(t.group("t")).strip())
    return out


def content_sha256(raw: bytes) -> str:
    """The article, with the API's retrieval-date envelope blanked. Stable across re-fetches."""
    return hashlib.sha256(DATE_ENVELOPE.sub(b"<date></date>", raw, count=1)).hexdigest()


# --------------------------------------------------------------------------- the re-read


def reread(method: dict[str, Any], raw: bytes) -> list[str]:
    """-> [] when every encoded criterion matches the source cell for cell."""
    bad: list[str] = []

    # ---- source binding -------------------------------------------------------------
    binding = method.get("source_binding") or {}
    if binding.get("source_id") != SOURCE_ID:
        bad.append(f"source_binding.source_id={binding.get('source_id')!r}, expected {SOURCE_ID!r}")

    got = content_sha256(raw)
    if binding.get("content_sha256") != got:
        bad.append(f"content_sha256 declared {binding.get('content_sha256')!r}, recomputed {got!r}")

    raw_hash = hashlib.sha256(raw).hexdigest()
    if binding.get("raw_sha256") != raw_hash:
        # NOT fatal on its own: the raw hash is a snapshot of one fetch. But the method must
        # not claim a raw hash that this file does not have.
        bad.append(f"raw_sha256 declared {binding.get('raw_sha256')!r}, this file is {raw_hash!r}")

    # ---- Table 1: cell for cell ------------------------------------------------------
    cells = _table_cells(raw, PART_I_TABLE_ID)
    if cells[:2] != ["Evaluation criteria", "Level of importancea"]:
        bad.append(f"Table 1 header is {cells[:2]!r}")
        return bad
    body = cells[2:]
    source_rows = [(body[i], body[i + 1]) for i in range(0, len(body) - 1, 2)]

    declared = method.get("part_i_criteria") or []
    in_table = [c for c in declared if c.get("in_part_i_table")]

    if len(source_rows) != len(in_table):
        bad.append(
            f"Table 1 has {len(source_rows)} rows; the method encodes {len(in_table)} criteria "
            "as being in it. A criterion was invented or lost.")
    if method.get("part_i_criteria_count_in_source") != len(source_rows):
        bad.append(
            f"part_i_criteria_count_in_source={method.get('part_i_criteria_count_in_source')}, "
            f"the source has {len(source_rows)}")

    for i, c in enumerate(in_table):
        if i >= len(source_rows):
            break
        want_text, want_imp = source_rows[i]
        cid = c.get("criterion_id")
        if c.get("source_verbatim") != want_text:
            bad.append(f"{cid}: source_verbatim={c.get('source_verbatim')!r}, "
                       f"Table 1 row {i} says {want_text!r}")
        if c.get("importance") != want_imp:
            bad.append(f"{cid}: importance={c.get('importance')!r}, "
                       f"Table 1 row {i} says {want_imp!r}")
        loc = c.get("source_locator") or {}
        if loc.get("row_index") != i:
            bad.append(f"{cid}: source_locator.row_index={loc.get('row_index')}, "
                       f"it is row {i} of Table 1")

    # a criterion NOT in Table 1 must not claim an importance letter the source never gave it
    for c in declared:
        if c.get("in_part_i_table"):
            continue
        cid = c.get("criterion_id")
        if c.get("importance") is not None:
            bad.append(f"{cid}: is not in Table 1, but claims importance="
                       f"{c.get('importance')!r}. The source grades it nowhere.")
        if c.get("source_verbatim") is not None:
            bad.append(f"{cid}: is not in Table 1, but claims a Table-1 verbatim cell")
        if not c.get("not_in_part_i_table"):
            bad.append(f"{cid}: is outside Table 1 and does not say so")

    # ---- Table 1 footnote -------------------------------------------------------------
    notes = _footnotes(raw, PART_I_TABLE_ID)
    if binding.get("part_i_footnote_verbatim") not in notes:
        bad.append(f"part_i_footnote_verbatim is not a Table-1 footnote in the source "
                   f"(source says {notes!r})")

    # ---- Table 2: class definitions, cell for cell ------------------------------------
    t2 = _table_cells(raw, PART_II_TABLE_ID)
    if t2[:3] != ["Permeability class", "Definition", "Potential uses"]:
        bad.append(f"Table 2 header is {t2[:3]!r}")
        return bad
    b2 = t2[3:]
    class_defs = {b2[i]: b2[i + 1] for i in range(0, len(b2) - 2, 3)}

    # The method's normalised class ids -> the source's class name.
    want_class_name = {
        "sufficiently_permeable": "Sufficiently permeable",
        "insufficiently_permeable": "Insufficiently permeable",
        "impermeable": "Impermeable",
    }
    for klass in method.get("part_ii_classes") or []:
        cid = klass.get("class_id")
        name = want_class_name.get(cid)
        if name is None:
            bad.append(f"part_ii class {cid!r} is not one of the three classes Table 2 defines")
            continue
        if name not in class_defs:
            bad.append(f"Table 2 does not define a class named {name!r}")
            continue
        # the encoded source_quote must be the source's definition, modulo the source's own
        # missing spaces around the boolean connectives ("NEBaorRelevant" in the BioC flattening)
        want = _normalise(class_defs[name])
        got_q = _normalise(klass.get("source_quote") or "")
        if want != got_q:
            bad.append(f"{cid}: source_quote does not match Table 2.\n"
                       f"    source: {class_defs[name]!r}\n"
                       f"    method: {klass.get('source_quote')!r}")

    # ---- Table 2 footnote a -----------------------------------------------------------
    notes2 = _footnotes(raw, PART_II_TABLE_ID)
    if "Accounting for potency." not in notes2:
        bad.append(f"Table 2 footnote 'Accounting for potency.' not found (source: {notes2!r})")
    for n in binding.get("part_ii_footnotes_verbatim") or []:
        if n not in notes2:
            bad.append(f"declared Table-2 footnote {n!r} is not in the source")

    return bad


def _normalise(s: str) -> str:
    """Compare definitions modulo TWO artefacts of BioC's table flattening, and nothing else.

    The source cell arrives as:

        'PK with therapeutic levels in NEBa orRelevant PD effect in NEB orRadiographic ...'

    Two things happened to it on the way out of the PDF, neither of them scientific:

      1. the superscript footnote marker `a` (Table 2 footnote a, "Accounting for potency")
         is inlined against the word it marks -> `NEBa`;
      2. the line break before each `or` / `and` is dropped, gluing the connective to the next
         word -> `orRelevant`, `andNo`.

    Both are undone here. NOTHING else is: no case-insensitive word matching, no punctuation
    stripping, no fuzzy compare. A normaliser generous enough to hide a real difference would
    make this whole re-read decorative, so it is deliberately narrow — if the paper says
    `Low PK levels` and the method says `Lower PK levels`, that still fails.
    """
    s = s.replace("NEBa", "NEB")            # (1) inlined footnote marker
    s = re.sub(r"\b(or|and)(?=[A-Z])", r" \1 ", s)   # (2) connective glued to the next word
    return re.sub(r"\s+", " ", s).strip().lower()


def load_source(cache_root: str) -> bytes:
    path = os.path.join(cache_root, CACHE_FILENAME)
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    with open(path, "rb") as fh:
        return fh.read()


def verify(method_path: str, cache_root: str) -> list[str]:
    with open(method_path, encoding="utf-8") as fh:
        method = json.load(fh)
    return reread(method, load_source(cache_root))
