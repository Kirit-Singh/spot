"""Offline page-level checks: the bytes, the pagination chain, the releases.

Split out of :mod:`druglink.verify_acquisition` to keep both modules small. NOTHING
here opens a socket. Every check re-derives its answer from the cached bytes
themselves rather than from what the manifest says about them — a manifest that
agrees with itself has proved only that one producer was self-consistent.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Optional

from .acquisition import FIXTURE_MARKERS, RECORDS_KEY
from .hashing import canonical_json, content_hash, sha256_hex

LINK_NEXT = re.compile(r'<([^>]+)>\s*;[^<]*rel="next"')
EXPECTED_LICENSE = {"uniprot": "CC BY 4.0", "chembl": "CC BY-SA 3.0"}
NO_HASH = ("created_at", "retrieved_at", "access_record", "response_headers")


class Report:
    """Every check is named, printed, and counted. Silence is not a pass."""

    def __init__(self) -> None:
        self.rows: list[tuple[str, bool, str]] = []

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        self.rows.append((name, bool(ok), detail))
        return bool(ok)

    @property
    def failed(self) -> list[tuple[str, bool, str]]:
        return [r for r in self.rows if not r[1]]

    def render(self) -> str:
        lines = [f"[{'PASS' if ok else 'FAIL'}] {name}"
                 + (f" -- {detail}" if detail else "")
                 for name, ok, detail in self.rows]
        lines.append(f"{len(self.rows) - len(self.failed)}/{len(self.rows)} checks "
                     f"passed, {len(self.failed)} failed")
        return "\n".join(lines)


def _read_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _content_sha256(manifest: dict[str, Any]) -> str:
    """Re-implemented here: the verifier does not reuse the generator's hasher."""
    def strip(node: Any) -> Any:
        if isinstance(node, dict):
            return {k: strip(v) for k, v in node.items()
                    if k not in NO_HASH and k != "content_sha256"}
        if isinstance(node, list):
            return [strip(v) for v in node]
        return node
    return content_hash(strip(manifest))


def _body(cache_root: str, entry: dict[str, Any]) -> dict[str, Any]:
    """Missing or unreadable bytes yield an EMPTY body, never an exception.

    ``check_bytes`` has already failed the run for the missing file; crashing here
    would replace that precise, named failure with a stack trace — and a verifier
    that dies is a verifier that reported nothing.
    """
    try:
        with open(os.path.join(cache_root, entry["raw_file"]), "rb") as fh:
            return json.loads(fh.read().decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}


def _declared_next(entry: dict[str, Any], body: dict[str, Any]) -> Optional[str]:
    """The successor the RESPONSE stated -- header for UniProt, page_meta for ChEMBL."""
    if entry["source"] == "uniprot":
        link = (entry.get("response_headers") or {}).get("link")
        match = LINK_NEXT.search(link) if link else None
        return match.group(1).strip() if match else None
    nxt = (body.get("page_meta") or {}).get("next")
    if not nxt:
        return None
    return nxt if nxt.startswith("http") else "https://www.ebi.ac.uk" + nxt


def _declared_total(entry: dict[str, Any], body: dict[str, Any]) -> Optional[int]:
    if entry["source"] == "uniprot":
        raw = (entry.get("response_headers") or {}).get("x-total-results")
        return int(raw) if raw is not None else None
    total = (body.get("page_meta") or {}).get("total_count")
    return total if isinstance(total, int) else None


# --------------------------------------------------------------------------- #
# checks                                                                       #
# --------------------------------------------------------------------------- #

def check_bytes(rep: Report, cache_root: str, entries: list[dict[str, Any]]) -> None:
    bad_hash, bad_len, missing, absolute, relabelled = [], [], [], [], []
    for e in entries:
        if e["acquisition_status"] == "not_acquired":
            continue
        rel = e.get("raw_file") or ""
        if os.path.isabs(rel) or ".." in rel.split("/"):
            absolute.append(rel)
            continue
        path = os.path.join(cache_root, rel)
        if not os.path.exists(path):
            missing.append(rel)
            continue
        data = open(path, "rb").read()
        if sha256_hex(data) != e["raw_sha256"]:
            bad_hash.append(rel)
        if e.get("raw_bytes") is not None and len(data) != e["raw_bytes"]:
            bad_len.append(rel)
        if e["acquisition_status"] == "acquired_public":
            relabelled.extend(_fixture_bytes(e, data))

    rep.check("raw_files_present", not missing, f"missing: {missing}" if missing else "")
    rep.check("raw_paths_are_relative_and_in_cache", not absolute,
              f"machine-local/escaping: {absolute}" if absolute else "")
    rep.check("raw_bytes_hash_to_the_manifest", not bad_hash,
              f"changed bytes: {bad_hash}" if bad_hash else "")
    rep.check("raw_byte_counts_match", not bad_len,
              f"length mismatch: {bad_len}" if bad_len else "")
    rep.check("no_fixture_bytes_labelled_acquired_public", not relabelled,
              "; ".join(relabelled) if relabelled else "")


def _fixture_bytes(entry: dict[str, Any], data: bytes) -> list[str]:
    """Reasons these acquired_public bytes are not a real response from this source."""
    reasons: list[str] = []
    text = data.decode("utf-8", errors="replace")
    for marker in FIXTURE_MARKERS:
        if marker in text:
            reasons.append(f"{entry['raw_file']}: carries fixture marker {marker!r}")
    key = RECORDS_KEY.get(entry["adapter"])
    if key is None:
        return reasons
    try:
        body = json.loads(text)
    except json.JSONDecodeError:
        return reasons + [f"{entry['raw_file']}: not JSON"]
    if not isinstance(body, dict) or not isinstance(body.get(key), list):
        reasons.append(f"{entry['raw_file']}: no {key!r} array")
    elif entry["source"] == "chembl" and not isinstance(body.get("page_meta"), dict):
        reasons.append(f"{entry['raw_file']}: a real ChEMBL page states page_meta")
    elif entry["source"] == "uniprot" and (entry.get("response_headers") or {}).get(
            "x-uniprot-release") is None:
        reasons.append(f"{entry['raw_file']}: no UniProt release header was observed")
    return reasons


def check_chains(rep: Report, cache_root: str, entries: list[dict[str, Any]]) -> None:
    """Every page of every group: contiguous, linked both ways, and counted."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for e in entries:
        if e["acquisition_status"] != "acquired_public":
            continue
        groups.setdefault(e["request_group_id"], []).append(e)

    gaps, links, totals, queries = [], [], [], []
    for gid, rows in sorted(groups.items()):
        rows.sort(key=lambda r: r["page_index"])
        indices = [r["page_index"] for r in rows]
        if indices != list(range(len(rows))):
            gaps.append(f"{gid}: page indices {indices}")
            continue
        declared_n = {r["pagination"]["n_pages_in_group"] for r in rows}
        if declared_n != {len(rows)}:
            gaps.append(f"{gid}: declared {sorted(declared_n)} pages, retained "
                        f"{len(rows)}")
            continue
        if len({canonical_json(r["query"]) for r in rows}) != 1:
            queries.append(f"{gid}: pages disagree about the query")

        bodies = [_body(cache_root, r) for r in rows]
        observed = 0
        for i, (row, body) in enumerate(zip(rows, bodies)):
            pag = row["pagination"]
            key = RECORDS_KEY.get(row["adapter"])
            n = len(body.get(key) or []) if key else 0
            if pag["observed_count"] != n:
                totals.append(f"{gid} p{i}: declared {pag['observed_count']} "
                              f"record(s), bytes carry {n}")
            observed += n

            source_next = _declared_next(row, body)
            if source_next != pag.get("declared_next_url"):
                links.append(f"{gid} p{i}: the response's own next-link "
                             f"{source_next!r} != recorded "
                             f"{pag.get('declared_next_url')!r}")
            successor = rows[i + 1]["retrieval_url"] if i + 1 < len(rows) else None
            if pag["successor_url"] != successor:
                links.append(f"{gid} p{i}: successor {pag['successor_url']!r} is not "
                             f"the next retained page {successor!r}")
            if source_next != successor:
                links.append(f"{gid} p{i}: the source pointed at {source_next!r} but "
                             f"the next retained page is {successor!r} -- a page of "
                             "this chain is missing")
            predecessor = rows[i - 1]["retrieval_url"] if i else None
            if pag["predecessor_url"] != predecessor:
                links.append(f"{gid} p{i}: predecessor {pag['predecessor_url']!r} is "
                             f"not the previous retained page {predecessor!r}")

        expected = _declared_total(rows[0], bodies[0])
        if expected is not None and expected != observed:
            totals.append(f"{gid}: source declared total_count={expected} but the "
                          f"{len(rows)} retained page(s) carry {observed} record(s)")
        if expected != rows[0]["pagination"].get("expected_total_count"):
            totals.append(f"{gid}: recorded expected_total_count "
                          f"{rows[0]['pagination'].get('expected_total_count')!r} != "
                          f"the source's {expected!r}")

    rep.check("pagination_pages_are_contiguous", not gaps, "; ".join(gaps))
    rep.check("pagination_chain_is_linked_both_ways", not links, "; ".join(links[:6]))
    rep.check("page_counts_and_totals_are_bound_to_the_bytes", not totals,
              "; ".join(totals[:6]))
    rep.check("all_pages_of_a_group_share_one_query", not queries, "; ".join(queries))


def check_releases(rep: Report, cache_root: str, manifest: dict[str, Any],
                   entries: list[dict[str, Any]]) -> None:
    releases = manifest.get("releases") or {}

    uni = [e for e in entries if e["source"] == "uniprot"
           and e["acquisition_status"] == "acquired_public"]
    observed = {(e.get("response_headers") or {}).get("x-uniprot-release")
                for e in uni}
    declared = {e["source_release"] for e in uni}
    rep.check("uniprot_release_is_one_release_across_every_page",
              len(observed) <= 1 and None not in observed if uni else True,
              f"observed {sorted(map(str, observed))}" if len(observed) > 1 else "")
    rep.check("uniprot_release_is_the_observed_response_header",
              observed == declared if uni else True,
              f"headers say {sorted(map(str, observed))}, entries say "
              f"{sorted(map(str, declared))}")
    if uni:
        rep.check("uniprot_release_matches_the_manifest",
                  (releases.get("uniprot") or {}).get("source_release")
                  in observed, str(releases.get("uniprot")))

    chembl = [e for e in entries if e["source"] == "chembl"
              and e["acquisition_status"] == "acquired_public"]
    if chembl:
        rec = releases.get("chembl") or {}
        path = os.path.join(cache_root, rec.get("raw_file") or "")
        pinned = os.path.exists(path)
        rep.check("chembl_current_release_record_is_pinned", pinned,
                  "" if pinned else "no status.json bytes alongside the responses")
        if pinned:
            data = open(path, "rb").read()
            ok_hash = sha256_hex(data) == rec.get("raw_sha256")
            status = json.loads(data.decode("utf-8"))
            actual = status.get("chembl_db_version")
            rep.check("chembl_release_record_bytes_hash", ok_hash)
            rep.check("chembl_release_is_what_the_source_reports",
                      actual == rec.get("source_release"),
                      f"status.json says {actual!r}, manifest says "
                      f"{rec.get('source_release')!r}")
            rep.check("chembl_release_matches_the_declared_release",
                      str(actual or "").upper()
                      == str(rec.get("release_declared") or "").upper(),
                      f"{actual!r} vs declared {rec.get('release_declared')!r}")
            rep.check("every_chembl_page_carries_that_release",
                      {e["source_release"] for e in chembl} == {actual},
                      str(sorted({e["source_release"] for e in chembl})))

    bad = [f"{e['source']}:{e['license']}" for e in entries
           if e["acquisition_status"] == "acquired_public"
           and e["license"] != EXPECTED_LICENSE.get(e["source"])]
    rep.check("licenses_are_the_sources_own_licenses", not bad, "; ".join(sorted(bad)))
    missing = [e["raw_file"] for e in entries
               if e["acquisition_status"] == "acquired_public"
               and not (e.get("attribution") or "").strip()]
    rep.check("attribution_is_carried_on_every_public_page", not missing,
              "; ".join(missing[:4]))
