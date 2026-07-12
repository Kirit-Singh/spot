"""SOURCE-NATIVE replay + CONTRIBUTOR COMPLETENESS: the release gate.

Resolving a manifest citation against a source-record table proves only that two
GENERATED artifacts agree with each other. Both were written by the same producer. If
that producer invented a contributor set, the manifest and the table would agree
perfectly and the run would sail through — agreement is not provenance.

So the evidence is replayed against the pinned raw source:

    GWCD4i.pseudobulk_merged.h5ad
      obs.guide_id            the literal per-guide identity column — THE evidence
      obs.perturbed_gene_id   the target, in ITS OWN namespace
      obs.culture_condition   Rest / Stim8hr / Stim48hr
      obs.keep_for_DE         whether the row entered the DE fit at all
      obs.guide_type          targeting vs non-targeting control
      obs index               the row NAMES the records claim

WHY v1 WAS NOT A GATE
---------------------
v1 asked one question — EXISTENCE: does each cited locator point at a kept raw row that
says what the record says? A subset-existence check cannot see a contributor that was
silently DROPPED. Every guide the manifest names is real, every hash is right, every
locator replays... and the mask is still built from an incomplete guide set, which
changes the score. So v1 could certify a wrong answer, and it is refused as a gate.

v2 asks BOTH questions:

  1. EXISTENCE   — every cited locator points at a kept row that matches the record.
  2. COMPLETENESS — for every released pooled scope, the guides the manifest names are
     EXACTLY the guides the source kept for that (target, condition); every record's
     offset array is EXACTLY the kept rows for its (target, condition, guide), with
     matching row NAMES and its locator among them; and every cited guide is a
     TARGETING guide, so a non-targeting control can never enter a contributor set.

Completeness is re-derived from the raw source, never inferred from the table.

Usage:
    python -m direct.replay --source-records <table.json> --manifest <manifest.json> \
        --source <pseudobulk.h5ad> --source-id <name> --out <replay_report.json>
Exit 0 = replayed AND complete; 1 = otherwise.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Optional

import h5py
import numpy as np

from .hashing import file_sha256
from .manifest_schema import COMPLETENESS_RULE_ID, REPLAY_RULE_ID
from .record_id import OFFSETS_FIELD, ROWS_FIELD

SCHEMA_VERSION = "spot.stage02_source_replay.v2"
SUPERSEDED_SCHEMA_VERSIONS = ("spot.stage02_source_replay.v1",)

REPLAYED = "replayed"
REFUSED = "refused"
COMPLETE = "complete"
INCOMPLETE = "incomplete"

# The literal evidence columns of the pinned release.
GUIDE_COL = "guide_id"
TARGET_COL = "perturbed_gene_id"
CONDITION_COL = "culture_condition"
KEEP_COL = "keep_for_DE"
GUIDE_TYPE_COL = "guide_type"
EVIDENCE_COLUMNS = (GUIDE_COL, TARGET_COL, CONDITION_COL, KEEP_COL, GUIDE_TYPE_COL)
TARGETING = "targeting"

POOLED_TYPE = "main"
POOLED_ID = "main"

# Refusal reasons. Each names the ONE thing the source did not confirm.
LOCATOR_OUT_OF_RANGE = "source_row_index_out_of_range"
GUIDE_MISMATCH = "guide_id_does_not_match_the_source_row"
TARGET_MISMATCH = "target_id_does_not_match_the_source_row"
CONDITION_MISMATCH = "condition_does_not_match_the_source_row"
NOT_KEPT_FOR_DE = "source_row_did_not_enter_the_DE_fit"
OFFSETS_NOT_THE_KEPT_ROWS = "offsets_are_not_exactly_the_kept_rows_for_this_contributor"
ROW_NAMES_MISMATCH = "pseudobulk_source_rows_do_not_name_the_offsets_rows"
SCOPE_INCOMPLETE = "pooled_scope_does_not_name_the_whole_kept_contributor_set"
NON_TARGETING = "cited_guide_is_not_a_targeting_guide_in_the_source"

# THE SOURCE CLASSIFICATION RULE.
#
# ``evidence_state`` is a CLAIM the manifest makes about itself, and until now the
# replay believed it. Completeness was only ever checked for scopes the manifest had
# already labelled ``determined``; a scope labelled ``ambiguous`` was skipped, because
# "the identity is unknown" was taken as a statement no source could contradict.
#
# The source contradicts it constantly. A scope whose raw rows hold kept TARGETING
# guides is determinable — the evidence is right there — and calling it ambiguous is not
# a confession of uncertainty, it is the deletion of evidence that exists. It is also
# free: relabel one scope's rows to a single ambiguous row, regenerate the counts, and
# every total still balances (determined-1, ambiguous+1, named unchanged). The victim
# silently loses its mask, its score and its rank, and no check in the lane looks at it.
#
# So the classification is DERIVED FROM THE SOURCE, never read from the manifest:
#
#   provable(scope) = { g : the source kept a row for this (target, condition) whose
#                           guide_type is TARGETING }
#
#   provable non-empty  -> the scope is DETERMINABLE. ``determined`` is mandatory, and
#                          the named guide set must be exactly provable(scope).
#   provable empty      -> the scope is genuinely non-determinable. ``ambiguous`` is the
#                          only honest label, and ``determined`` is an overclaim.
#
# The standalone verifier restates this rule independently; the two agreeing is the
# check, not the assumption.
SOURCE_CLASSIFICATION_RULE_ID = "spot.stage02.direct.source_classification_rule.v1"
SCOPE_DOWNGRADED = "source_determinable_scope_is_labelled_ambiguous"
SCOPE_OVERCLAIMED = "scope_labelled_determined_but_source_kept_no_targeting_guide"

# Compact rule IDs, not prose: the emitted report is a machine artifact and carries
# enums, counts and hashes. What the rules MEAN is stated once, in this docstring and in
# the method docs — never re-narrated inside every report. The ids themselves live in
# the frozen vocabulary (imported above), so the id a report is STAMPED with and the id
# its consumers REQUIRE cannot drift apart.


def _excluded(row) -> bool:
    """``included`` is false in every spelling a JSON producer might use."""
    return row.get("included", True) in (False, "false", "False", 0)


def _is_null(v) -> bool:
    return v is None or str(v).strip().lower() in ("", "none", "null", "nan", "na")


class ReplayError(ValueError):
    """The raw source cannot be replayed, so the evidence is unverified."""


def _decode(values) -> np.ndarray:
    return np.array([v.decode() if isinstance(v, (bytes, bytearray)) else str(v)
                     for v in values], dtype=object)


def read_obs_column(obs: h5py.Group, name: str) -> np.ndarray:
    """Read one obs column, categorical or plain, without loading the matrix."""
    if name not in obs:
        raise ReplayError(
            f"source replay: the pinned source has no obs.{name}; without it the "
            "evidence cannot be replayed")
    node = obs[name]
    if isinstance(node, h5py.Group):
        categories = _decode(node["categories"][:])
        codes = node["codes"][:]
        out = np.empty(codes.shape, dtype=object)
        out[:] = None
        out[codes >= 0] = categories[codes[codes >= 0]]
        return out
    return node[:]


def read_evidence(source_path: str) -> dict[str, np.ndarray]:
    """The release's own evidence columns, plus the raw row NAMES. obs only."""
    if not os.path.exists(source_path):
        raise ReplayError(f"source replay: the pinned source {source_path!r} is "
                          "absent; an absent source cannot confirm anything")
    with h5py.File(source_path, "r") as fh:
        if "obs" not in fh:
            raise ReplayError("source replay: the pinned source has no obs group")
        obs = fh["obs"]
        cols = {c: read_obs_column(obs, c) for c in EVIDENCE_COLUMNS}
        cols["row_names"] = _decode(obs[obs.attrs.get("_index", "index")][:])
    return cols


def _is_pooled(row: dict[str, Any]) -> bool:
    dp = row.get("donor_pair")
    return (str(row.get("estimate_type")) == POOLED_TYPE
            and str(row.get("estimate_id")) == POOLED_ID
            and (dp is None or str(dp).strip().lower() in ("", "none", "null", "nan")))


def derive_from_source(cols: dict[str, np.ndarray]) -> tuple[dict, dict, dict, dict]:
    """Every KEPT raw row, grouped the ways completeness needs. Vectorised."""
    guide, target = cols[GUIDE_COL], cols[TARGET_COL]
    cond, keep, gtype = cols[CONDITION_COL], cols[KEEP_COL], cols[GUIDE_TYPE_COL]
    names = cols["row_names"]

    complete: dict[tuple, set] = {}      # (target, condition) -> {guide}
    offsets: dict[tuple, list] = {}      # (target, condition, guide) -> [row index]
    row_names: dict[tuple, list] = {}    # (target, condition, guide) -> [row name]
    types: dict[str, set] = {}           # guide -> {guide_type}

    for i in np.flatnonzero(np.asarray(keep, dtype=bool)):
        i = int(i)
        g = str(guide[i])
        scope = (str(target[i]), str(cond[i]))
        complete.setdefault(scope, set()).add(g)
        offsets.setdefault(scope + (g,), []).append(i)
        row_names.setdefault(scope + (g,), []).append(str(names[i]))
        types.setdefault(g, set()).add(str(gtype[i]))
    return complete, offsets, row_names, types


def source_provable_guides(cols: dict[str, np.ndarray]) -> dict[tuple, set]:
    """Per-scope KEPT TARGETING guide set — the source's own classification.

    This is the only authority on whether a scope is determinable. It is derived from
    the raw rows and nothing else: no manifest field, no report count, no prior claim.
    A scope appears here IFF the source kept at least one targeting guide for it, so
    membership IS determinability and absence IS genuine ambiguity.

    Deliberately separate from ``derive_from_source``: the guide_type filter is the
    rule, and a rule that is inherited as a side effect of some other grouping is a rule
    nobody can find. A non-targeting control is kept, and is never a contributor.
    """
    guide, target = cols[GUIDE_COL], cols[TARGET_COL]
    cond, keep, gtype = cols[CONDITION_COL], cols[KEEP_COL], cols[GUIDE_TYPE_COL]

    provable: dict[tuple, set] = {}
    for i in np.flatnonzero(np.asarray(keep, dtype=bool)):
        i = int(i)
        if str(gtype[i]) != TARGETING:
            continue
        provable.setdefault((str(target[i]), str(cond[i])), set()).add(str(guide[i]))
    return provable


def classify_scopes(rows: list[dict[str, Any]],
                    provable: dict[tuple, set]) -> dict[str, Any]:
    """Compare every pooled-main scope's CLAIMED state against the SOURCE's.

    Returns the two failure classes separately, because they are different lies:
    a DOWNGRADE deletes evidence the source holds; an OVERCLAIM invents evidence the
    source does not hold.
    """
    labelled: dict[tuple, str] = {}
    for row in rows:
        if not _is_pooled(row):
            continue
        scope = (str(row.get("target_id")), str(row.get("condition")))
        state = str(row.get("evidence_state"))
        # A scope is determined if ANY row proves a guide for it; ambiguous only if no
        # row does. Reading the first row's label would let a forger hide a downgrade
        # behind one honest sibling row.
        if state == "determined" and not _excluded(row) \
                and not _is_null(row.get("guide_id")):
            labelled[scope] = "determined"
        else:
            labelled.setdefault(scope, "ambiguous")

    downgraded, overclaimed = [], []
    n_determinable = n_non_determinable = 0
    for scope, state in sorted(labelled.items()):
        kept = provable.get(scope) or set()
        if kept:
            n_determinable += 1
            if state != "determined":
                downgraded.append({"target_id": scope[0], "condition": scope[1],
                                   "reason": SCOPE_DOWNGRADED,
                                   "n_source_kept_targeting": len(kept)})
        else:
            n_non_determinable += 1
            if state == "determined":
                overclaimed.append({"target_id": scope[0], "condition": scope[1],
                                    "reason": SCOPE_OVERCLAIMED,
                                    "n_source_kept_targeting": 0})
    return {"n_scopes_source_determinable": n_determinable,
            "n_scopes_source_non_determinable": n_non_determinable,
            "n_scopes_downgraded": len(downgraded),
            "n_scopes_overclaimed": len(overclaimed),
            "failures": downgraded + overclaimed}


def replay_records(records: list[dict[str, Any]],
                   cols: dict[str, np.ndarray]) -> dict[str, Any]:
    """EXISTENCE: every cited locator points at a kept row that matches the record."""
    guide, target = cols[GUIDE_COL], cols[TARGET_COL]
    cond, keep = cols[CONDITION_COL], cols[KEEP_COL]
    n_rows = len(guide)
    failures: list[dict[str, Any]] = []
    n_replayed = 0

    for rec in records:
        rid = rec.get("source_record_id")
        i = rec.get("source_row_index")
        if not isinstance(i, int) or isinstance(i, bool) or not 0 <= i < n_rows:
            failures.append({"source_record_id": rid, "source_row_index": i,
                             "reason": LOCATOR_OUT_OF_RANGE})
        elif str(guide[i]) != str(rec.get("guide_id")):
            failures.append({"source_record_id": rid, "source_row_index": i,
                             "reason": GUIDE_MISMATCH, "source_says": str(guide[i]),
                             "record_says": rec.get("guide_id")})
        elif str(target[i]) != str(rec.get("target_id")):
            failures.append({"source_record_id": rid, "source_row_index": i,
                             "reason": TARGET_MISMATCH, "source_says": str(target[i]),
                             "record_says": rec.get("target_id")})
        elif str(cond[i]) != str(rec.get("condition")):
            failures.append({"source_record_id": rid, "source_row_index": i,
                             "reason": CONDITION_MISMATCH, "source_says": str(cond[i]),
                             "record_says": rec.get("condition")})
        elif not bool(keep[i]):
            failures.append({"source_record_id": rid, "source_row_index": i,
                             "reason": NOT_KEPT_FOR_DE})
        else:
            n_replayed += 1

    return {"n_source_rows": int(n_rows), "n_records": len(records),
            "n_replayed": n_replayed, "n_failed": len(failures),
            "failures": failures[:20]}


def check_completeness(records: list[dict[str, Any]], rows: list[dict[str, Any]],
                       cols: dict[str, np.ndarray]) -> dict[str, Any]:
    """COMPLETENESS: the whole kept contributor set, re-derived from the raw source."""
    complete, offsets, row_names, types = derive_from_source(cols)
    failures: list[dict[str, Any]] = []

    # 1. Every record's offset proof is EXACTLY the source's kept rows for it.
    n_offset_proven = 0
    for rec in records:
        triple = (str(rec.get("target_id")), str(rec.get("condition")),
                  str(rec.get("guide_id")))
        declared = rec.get(OFFSETS_FIELD)
        expected = offsets.get(triple, [])
        if not isinstance(declared, list) or list(declared) != expected:
            failures.append({"source_record_id": rec.get("source_record_id"),
                             "reason": OFFSETS_NOT_THE_KEPT_ROWS,
                             "n_declared": len(declared) if isinstance(declared, list)
                             else None,
                             "n_source_kept": len(expected)})
            continue
        if list(rec.get(ROWS_FIELD) or []) != row_names.get(triple, []):
            failures.append({"source_record_id": rec.get("source_record_id"),
                             "reason": ROW_NAMES_MISMATCH})
            continue
        if rec.get("source_row_index") not in expected:
            failures.append({"source_record_id": rec.get("source_record_id"),
                             "reason": OFFSETS_NOT_THE_KEPT_ROWS})
            continue
        n_offset_proven += 1

    # 2. Every released POOLED scope names the WHOLE kept guide set. This is the check
    #    a subset-existence replay cannot make, and the one a dropped contributor hides
    #    from.
    #
    #    Counting only the scopes the manifest NAMED would let a wholly dropped scope
    #    pass: it names nothing, so it appears in no iteration, and "0 incomplete of the
    #    ones I looked at" reads as complete. So the DETERMINED and the AMBIGUOUS scopes
    #    are both counted, and their sum is reported for the caller to bind against the
    #    released scope count (33,977 + 6 = 33,983 for the pinned release). Whether that
    #    sum IS the release is not decidable from the manifest alone, and this report
    #    does not pretend otherwise — ``validate_replay`` and the standalone verifier
    #    bind it to the independently derived DE scope set.
    determined: dict[tuple, set] = {}
    ambiguous: set[tuple] = set()
    for row in rows:
        if not _is_pooled(row):
            continue
        scope = (str(row.get("target_id")), str(row.get("condition")))
        state = str(row.get("evidence_state"))
        if state == "ambiguous":
            ambiguous.add(scope)
        elif state == "determined" and not _excluded(row) \
                and not _is_null(row.get("guide_id")):
            determined.setdefault(scope, set()).add(str(row["guide_id"]))

    incomplete = []
    for scope, gids in sorted(determined.items()):
        kept = complete.get(scope, set())
        if gids != kept:
            incomplete.append({"target_id": scope[0], "condition": scope[1],
                               "reason": SCOPE_INCOMPLETE,
                               "n_named": len(gids), "n_source_kept": len(kept)})

    # 3. A contributor is a TARGETING guide. A non-targeting control never contributed.
    cited = {str(r["guide_id"]) for r in rows if not _is_null(r.get("guide_id"))}
    mistyped = sorted(g for g in cited if types.get(g) != {TARGETING})

    # 4. THE SOURCE CLASSIFIES THE SCOPES — the manifest does not get to.
    #    Steps 1-3 all take ``evidence_state`` on trust: they check the scopes the
    #    manifest already called determined, and an ambiguous label is examined by
    #    nothing. So the cheapest possible forgery is to relabel a scope: its rows
    #    collapse to one ambiguous row, its records vanish, every count is regenerated
    #    honestly, and the arithmetic still balances. The victim loses its mask, its
    #    score and its rank, and the source — which holds its two kept targeting guides
    #    the whole time — is never asked.
    classification = classify_scopes(rows, source_provable_guides(cols))

    return {
        "n_scopes_determined": len(determined),
        "n_scopes_ambiguous": len(ambiguous),
        "n_scopes_named": len(determined) + len(ambiguous),
        "n_scopes_complete": len(determined) - len(incomplete),
        "n_scopes_incomplete": len(incomplete),
        "n_records_offset_proven": n_offset_proven,
        "n_nontargeting_guides_cited": len(mistyped),
        # what the SOURCE says the partition is, independent of what the manifest claims
        "source_classification_rule_id": SOURCE_CLASSIFICATION_RULE_ID,
        "n_scopes_source_determinable":
            classification["n_scopes_source_determinable"],
        "n_scopes_source_non_determinable":
            classification["n_scopes_source_non_determinable"],
        "n_scopes_downgraded": classification["n_scopes_downgraded"],
        "n_scopes_overclaimed": classification["n_scopes_overclaimed"],
        "completeness_verdict": (
            COMPLETE if not incomplete and not mistyped and not failures
            and not classification["failures"]
            and n_offset_proven == len(records) else INCOMPLETE),
        "completeness_failures": (failures[:20] + incomplete[:20]
                                  + classification["failures"][:20]
                                  + [{"guide_id": g, "reason": NON_TARGETING}
                                     for g in mistyped[:20]]),
    }


def load_json(path: str, what: str) -> dict[str, Any]:
    with open(path) as fh:
        doc = json.load(fh)
    if not isinstance(doc, dict):
        raise ReplayError(f"source replay: the {what} is malformed")
    return doc


def build_report(table_path: str, manifest_path: str, source_path: str,
                 source_id: Optional[str] = None) -> dict[str, Any]:
    """Replay AND prove completeness, then PIN the verdict to the exact bytes."""
    table = load_json(table_path, "source-record table")
    manifest = load_json(manifest_path, "contributor manifest")
    records, rows = table.get("records"), manifest.get("rows")
    if not isinstance(records, list) or not isinstance(rows, list):
        raise ReplayError("source replay: table 'records' / manifest 'rows' missing")

    cols = read_evidence(source_path)
    existence = replay_records(records, cols)
    completeness = check_completeness(records, rows, cols)

    verdict = (REPLAYED if existence["n_failed"] == 0
               and completeness["completeness_verdict"] == COMPLETE else REFUSED)
    return {
        "schema_version": SCHEMA_VERSION,
        "source_id": source_id or os.path.basename(source_path),
        # The artifacts this verdict is about, by their exact bytes. The contributor
        # manifest is deliberately NOT hashed here: the manifest must pin this report
        # among its sources, so a report that hashed the manifest back would be a cycle
        # no pair could ever satisfy. The manifest's SEMANTICS are bound instead by
        # 1:1 manifest<->table resolution plus the independently derived scope coverage
        # — both re-derived by the standalone verifier, neither trusting this file.
        "source_sha256": file_sha256(source_path),
        "source_record_table_sha256": file_sha256(table_path),
        "evidence_columns": list(EVIDENCE_COLUMNS),
        "replay_rule_id": REPLAY_RULE_ID,
        "completeness_rule_id": COMPLETENESS_RULE_ID,
        "verdict": verdict,
        **existence,
        **completeness,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Replay Stage-2 source records against the pinned raw source AND "
                    "prove the contributor sets are COMPLETE")
    ap.add_argument("--source-records", required=True)
    ap.add_argument("--manifest", required=True,
                    help="the contributor manifest whose pooled scopes must name the "
                         "WHOLE kept contributor set")
    ap.add_argument("--source", required=True,
                    help="the pinned raw source (GWCD4i.pseudobulk_merged.h5ad)")
    ap.add_argument("--source-id", default=None)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    try:
        report = build_report(args.source_records, args.manifest, args.source,
                              args.source_id)
    except ReplayError as exc:
        print(f"[FAIL] {exc}")
        return 1

    with open(args.out, "w") as fh:
        json.dump(report, fh, indent=2, sort_keys=True)

    ok = report["verdict"] == REPLAYED
    print(f"[{'PASS' if ok else 'FAIL'}] source replay: "
          f"{report['n_replayed']}/{report['n_records']} record(s) replayed against "
          f"{report['n_source_rows']} source rows; completeness="
          f"{report['completeness_verdict']} "
          f"({report['n_scopes_complete']}/{report['n_scopes_named']} scopes complete, "
          f"{report['n_records_offset_proven']}/{report['n_records']} offset-proven, "
          f"{report['n_nontargeting_guides_cited']} non-targeting guide(s) cited)")
    if not ok:
        for f in report["failures"] + report["completeness_failures"]:
            print(f"  - {f}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
