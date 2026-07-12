"""SOURCE-NATIVE replay and contributor COMPLETENESS — standalone verifier.

INDEPENDENCE RULE (test-enforced): imports nothing from the generator.

A source-record table that agrees with its manifest proves only that one producer was
self-consistent — both files were written by the same process. So the run is admitted
only with a pinned replay report binding THESE table bytes to THOSE source bytes, and
``--strict-replay`` re-derives the whole verdict from the raw source here.

Strict mode asks the source TWO questions, because the first one alone is not
provenance:

  1. EXISTENCE — does every cited record's locator point at a kept source row that
     says what the record says? (``replay_against_source``)
  2. COMPLETENESS — is the contributor set the manifest names for a released pooled
     scope the WHOLE set the source kept for that (target, condition)?
     (``check_completeness``)

A subset-existence check cannot see a contributor that was silently DROPPED: every
guide the manifest names is real, every hash is right, every locator replays — and the
mask is still built from the wrong guide set, which changes the score. Completeness is
therefore re-derived from the raw source rather than inferred from the table, and the
guides are checked to be TARGETING guides (obs.guide_type), so a non-targeting control
can never enter a contributor set.

The records' all-offset proof (``pseudobulk_source_offsets``) is BOUND here too: a
record's declared offsets must be exactly the kept rows the source holds for its
(target, condition, guide), and its locator must be one of them. An unchecked extra
field is not a proof.
"""
from __future__ import annotations

import json
import os
import sys

import h5py
import numpy as np

# Standalone: the rule module is loaded BY PATH, never as part of the generator
# package — importing it as ``direct.verify_rules`` would make the verifier a
# component of the thing it is checking.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import verify_rules as R  # noqa: E402

REPLAY_SCHEMA = "spot.stage02_source_replay.v2"
SUPERSEDED_REPLAY_SCHEMAS = ("spot.stage02_source_replay.v1",)

# THE rule ids a v2 report must declare, re-declared here from the written spec rather
# than imported from the generator. A report is only interpretable under the rule that
# produced it: "complete" computed by some other rule is not this report's "complete",
# and a report that names no rule at all has answered an unknown question.
REPLAY_RULE_ID = "spot.stage02.direct.replay_rule.v2"
COMPLETENESS_RULE_ID = "spot.stage02.direct.completeness_rule.v2"
# WHICH rule decided determined-vs-ambiguous. Not the manifest — the SOURCE.
# The rule itself is restated in ``verify_classification``.
SOURCE_CLASSIFICATION_RULE_ID = "spot.stage02.direct.source_classification_rule.v1"

COMPLETENESS_KEYS = ("completeness_verdict", "n_scopes_complete",
                     "n_scopes_incomplete", "n_scopes_determined",
                     "n_scopes_ambiguous", "n_scopes_named",
                     "n_records_offset_proven", "n_nontargeting_guides_cited",
                     "replay_rule_id", "completeness_rule_id",
                     # the SOURCE-derived partition. A report that carries none never
                     # asked whether the manifest's own labels were true.
                     "source_classification_rule_id",
                     "n_scopes_source_determinable",
                     "n_scopes_source_non_determinable",
                     "n_scopes_downgraded", "n_scopes_overclaimed")
ROWS_FIELD = "pseudobulk_source_rows"

# The literal evidence columns of the pinned release, re-declared (not imported).
GUIDE_COL = "guide_id"
TARGET_COL = "perturbed_gene_id"
CONDITION_COL = "culture_condition"
KEEP_COL = "keep_for_DE"
GUIDE_TYPE_COL = "guide_type"
REPLAY_COLUMNS = (GUIDE_COL, TARGET_COL, CONDITION_COL, KEEP_COL)

TARGETING = "targeting"
OFFSETS_FIELD = "pseudobulk_source_offsets"

# The POOLED scope: the estimate the contributor manifest is keyed to. A guide-slot
# or donor-pair estimate is a SUBSET of the pooled fit by construction, so exact
# set-equality is asked of the pooled scope and containment of the others.
POOLED_TYPE = "main"
POOLED_ID = "main"


def decode(values):
    return [v.decode() if isinstance(v, (bytes, bytearray)) else str(v)
            for v in values]


def obs_column(grp, name):
    """Read one obs column, categorical or plain, without loading the matrix."""
    node = grp[name]
    if isinstance(node, h5py.Group):
        cats = np.array(decode(node["categories"][:]), dtype=object)
        codes = node["codes"][:]
        out = np.empty(codes.shape, dtype=object)
        out[codes >= 0] = cats[codes[codes >= 0]]
        return out
    return node[:]


def read_evidence(source_path):
    """The release's own evidence columns, plus the raw row NAMES.

    guide_type is optional in the file and REQUIRED by strict completeness — its absence
    is reported, never assumed away.
    """
    with h5py.File(source_path, "r") as fh:
        obs = fh["obs"]
        cols = {c: obs_column(obs, c) for c in REPLAY_COLUMNS}
        cols[GUIDE_TYPE_COL] = (obs_column(obs, GUIDE_TYPE_COL)
                                if GUIDE_TYPE_COL in obs else None)
        idx = obs.attrs.get("_index", "index")
        cols["row_names"] = np.array(decode(obs[idx][:]), dtype=object)
    return cols


def _is_pooled(row) -> bool:
    return (str(row.get("estimate_type")) == POOLED_TYPE
            and str(row.get("estimate_id")) == POOLED_ID
            and R.is_null(row.get("donor_pair")))


def _source_scope(row) -> tuple:
    """The scope as the SOURCE names it: the target in its own namespace + condition."""
    return (str(row.get("target_id")), str(row.get("condition")))


# --------------------------------------------------------------------------- #
# 1. EXISTENCE: the locator, replayed against the raw source.
# --------------------------------------------------------------------------- #
def replay_against_source(records, cols):
    """Re-run the source-native replay INDEPENDENTLY. Returns the failures.

    ``perturbed_gene_id`` is compared to ``target_id`` as an exact string in whatever
    namespace the source used — never parsed.
    """
    n_rows = len(cols[GUIDE_COL])
    failures = []
    for rec in records:
        i = rec.get("source_row_index")
        rid = rec.get("source_record_id")
        if not isinstance(i, int) or isinstance(i, bool) or not 0 <= i < n_rows:
            failures.append((rid, "locator_out_of_range"))
        elif str(cols[GUIDE_COL][i]) != str(rec.get("guide_id")):
            failures.append((rid, "guide_id"))
        elif str(cols[TARGET_COL][i]) != str(rec.get("target_id")):
            failures.append((rid, "target_id"))
        elif str(cols[CONDITION_COL][i]) != str(rec.get("condition")):
            failures.append((rid, "condition"))
        elif not bool(cols[KEEP_COL][i]):
            failures.append((rid, "not_kept_for_DE"))
    return failures


# --------------------------------------------------------------------------- #
# 2. COMPLETENESS: the WHOLE contributor set, re-derived from the raw source.
# --------------------------------------------------------------------------- #
def derive_from_source(cols):
    """Every kept row, grouped the ways completeness needs."""
    guide, target = cols[GUIDE_COL], cols[TARGET_COL]
    cond, keep, gtype = cols[CONDITION_COL], cols[KEEP_COL], cols[GUIDE_TYPE_COL]
    names = cols.get("row_names")
    complete: dict[tuple, set] = {}
    offsets: dict[tuple, list] = {}
    row_names: dict[tuple, list] = {}
    types: dict[str, set] = {}
    for i in np.flatnonzero(np.asarray(keep, dtype=bool)):
        i = int(i)
        g, scope = str(guide[i]), (str(target[i]), str(cond[i]))
        complete.setdefault(scope, set()).add(g)
        offsets.setdefault(scope + (g,), []).append(i)
        if names is not None:
            row_names.setdefault(scope + (g,), []).append(str(names[i]))
        types.setdefault(g, set()).add(str(gtype[i]))
    return complete, offsets, row_names, types


def _excluded(row) -> bool:
    """``included`` is false in every spelling a JSON producer might use."""
    return row.get("included", True) in (False, "false", "False", 0)


def check_completeness(manifest_doc, records, cols, rep, coverage=None):
    """The contributor set must be the WHOLE set the source kept — not a subset."""
    if cols.get(GUIDE_TYPE_COL) is None:
        rep.check("STRICT: the source publishes obs.guide_type", False,
                  "without it a contributor set cannot be shown to be targeting-only")
        return
    complete, offsets, row_names, types = derive_from_source(cols)

    named: dict[tuple, set] = {}
    ambiguous: set = set()
    for row in manifest_doc["rows"]:
        if not _is_pooled(row):
            continue
        if str(row.get("evidence_state")) == R.AMBIGUOUS:
            ambiguous.add(_source_scope(row))
            continue
        if str(row.get("evidence_state")) != R.DETERMINED:
            continue
        if _excluded(row) or R.is_null(row.get("guide_id")):
            continue
        named.setdefault(_source_scope(row), set()).add(str(row["guide_id"]))

    incomplete = sorted(sc for sc, gids in named.items()
                        if gids != complete.get(sc, set()))
    rep.check("STRICT: every released pooled scope names the COMPLETE contributor "
              "set the raw source kept for it", not incomplete,
              f"{len(incomplete)} scope(s) whose named guides are not exactly the "
              f"source's kept guides (first: {incomplete[0] if incomplete else None})")

    # THE SOURCE CLASSIFIES. Everything above this line reads ``evidence_state`` and
    # believes it, so everything above this line is blind to a downgrade.
    from verify_classification import (check_source_classification,
                                       source_determinable_scopes)
    provable = source_determinable_scopes(cols)
    counts = check_source_classification(manifest_doc, provable, rep)

    # Counting only the scopes the manifest NAMED would let a wholly dropped scope pass:
    # it names nothing, appears in no iteration, and "0 incomplete of the ones I looked
    # at" reads as complete. So the determined + ambiguous scopes are bound to the
    # independently derived released universe.
    #
    # The SUM alone is invariant under a determined/ambiguous swap, which is exactly the
    # forgery, so the two halves are now bound SEPARATELY to the source's own partition.
    if coverage is not None:
        rep.check("STRICT: determined + ambiguous scopes are EVERY released scope",
                  len(named) + len(ambiguous) == coverage["n_released"],
                  f"determined={len(named)} ambiguous={len(ambiguous)} "
                  f"released={coverage['n_released']}")
        rep.check("STRICT: the DETERMINED half of the partition is the source's",
                  len(named) == counts["n_determinable"],
                  f"the manifest determines {len(named)} scope(s), the source determines "
                  f"{counts['n_determinable']}")
        rep.check("STRICT: the AMBIGUOUS half of the partition is the source's",
                  len(ambiguous) == counts["n_non_determinable"],
                  f"the manifest calls {len(ambiguous)} scope(s) ambiguous, the source "
                  f"finds {counts['n_non_determinable']} genuinely non-determinable")

    # A contributor is a TARGETING guide. A non-targeting control never contributed.
    cited = {str(r["guide_id"]) for r in manifest_doc["rows"]
             if not R.is_null(r.get("guide_id"))}
    mistyped = sorted(g for g in cited if types.get(g) != {TARGETING})
    rep.check("STRICT: every contributor guide is a TARGETING guide in the source",
              not mistyped, f"{len(mistyped)} cited guide(s) the source does not keep "
              f"as {TARGETING!r} (first: {mistyped[0] if mistyped else None})")

    # In the pooled-main domain there IS no non-pooled row. If one appears, the domain
    # gate already failed; this is the second lock on the same door.
    stray = sorted({(str(r.get("estimate_type")), str(r.get("estimate_id")))
                    for r in manifest_doc["rows"] if not _is_pooled(r)})
    rep.check("STRICT: no non-pooled row exists in the pooled-main evidence domain",
              not stray, f"{len(stray)} out-of-domain estimate class(es): {stray[:3]}")

    check_offset_proof(records, offsets, row_names, rep)


def check_offset_proof(records, offsets, row_names, rep):
    """BIND the records' all-offset proof: it must be complete, and it must be theirs.

    A record whose locator names one kept row while the source holds four for the same
    (target, condition, guide) has proved one row, not the claim. The declared offsets
    must be exactly the kept rows, IN ORDER, their row NAMES must be the source's own,
    and the locator must be one of them.

    EVERY record carries it. "All or none" was the wrong contract: a table where one
    record omits the proof is a table with an unproven record in it, and nothing tells
    you which of its masks that record built.
    """
    missing = [r.get("source_record_id") for r in records
               if not isinstance(r.get(OFFSETS_FIELD), list)
               or not isinstance(r.get(ROWS_FIELD), list)]
    rep.check("STRICT: EVERY source record carries the all-offset/row proof",
              not missing,
              f"{len(missing)} of {len(records)} record(s) omit it (first: "
              f"{missing[0] if missing else None}); a partial proof is not a proof")

    bad = []
    for rec in records:
        if not isinstance(rec.get(OFFSETS_FIELD), list):
            continue
        triple = _source_scope(rec) + (str(rec.get("guide_id")),)
        declared = rec[OFFSETS_FIELD]
        if list(declared) != offsets.get(triple, []) \
                or list(rec.get(ROWS_FIELD) or []) != row_names.get(triple, []) \
                or rec.get("source_row_index") not in declared:
            bad.append(rec.get("source_record_id"))
    rep.check("STRICT: every record's all-offset proof is exactly the kept source "
              "rows for its (target, condition, guide), in order, with the source's "
              "own row names, and holds its locator",
              not bad, f"{len(bad)} record(s) whose offsets are not the source's "
              f"(first: {bad[0] if bad else None})")


# --------------------------------------------------------------------------- #
# The report's OWN arithmetic — the half a self-hashed artifact can always fake.
# --------------------------------------------------------------------------- #
def _int(report, key):
    try:
        return int(report[key])
    except (KeyError, TypeError, ValueError):
        return None


def check_scope_arithmetic(report, coverage, rep):
    """The report must add up — to itself, and to the INDEPENDENTLY derived universe.

    Every field here is written by the producer and hashed by the producer, so internal
    consistency is not evidence of anything: nothing stops a report claiming
    "determined=33983, complete=33977, incomplete=0". Each identity below is a distinct
    way a scope can be counted as PROVEN without ever having been examined, so each is
    checked rather than inferred from the others:

      complete == determined                 no determined scope is silently unproven
      complete + incomplete == determined     none is neither
      named == determined + ambiguous         the report agrees with its own total
      determined + ambiguous == n_released    it looked at the whole release...
      determined == coverage.determined       ...and split it the same way the manifest
      ambiguous  == coverage.ambiguous         did. A report that swapped six determined
                                               scopes for six ambiguous ones has the same
                                               total and has proven six fewer things.
    """
    determined, ambiguous = _int(report, "n_scopes_determined"), \
        _int(report, "n_scopes_ambiguous")
    named = _int(report, "n_scopes_named")
    complete, incomplete = _int(report, "n_scopes_complete"), \
        _int(report, "n_scopes_incomplete")
    if None in (determined, ambiguous, named, complete, incomplete):
        rep.check("the replay report's scope counters are all present and numeric",
                  False, f"determined={determined} ambiguous={ambiguous} named={named} "
                         f"complete={complete} incomplete={incomplete}")
        return

    rep.check("every DETERMINED scope was proven complete", complete == determined,
              f"{complete} complete of {determined} determined")
    rep.check("no determined scope is neither complete nor incomplete",
              complete + incomplete == determined,
              f"complete({complete}) + incomplete({incomplete}) != "
              f"determined({determined})")
    rep.check("the replay report agrees with its own scope total",
              named == determined + ambiguous,
              f"named({named}) != determined({determined}) + ambiguous({ambiguous})")

    if coverage is None:
        return
    rep.check("the replay report's scope arithmetic IS the released universe",
              determined + ambiguous == coverage["n_released"],
              f"report accounts for {determined}+{ambiguous}, release ships "
              f"{coverage['n_released']}")
    # ...and it split that universe the SAME WAY. Matching only the TOTAL would let a
    # report relabel determined scopes as ambiguous — proving strictly less while its
    # sum stayed right.
    rep.check("the report's DETERMINED scope count is the manifest's own",
              determined == coverage["n_determined"],
              f"report says {determined}, the manifest determines "
              f"{coverage['n_determined']}")
    rep.check("the report's AMBIGUOUS scope count is the manifest's own",
              ambiguous == coverage["n_ambiguous"],
              f"report says {ambiguous}, the manifest calls "
              f"{coverage['n_ambiguous']} ambiguous")


# --------------------------------------------------------------------------- #
# The pinned replay report, and the strict re-derivation.
# --------------------------------------------------------------------------- #
def check_source_replay(manifest_doc, table_doc, table_path, shas, by_sha, rep,
                        strict=False, coverage=None):
    """The evidence must have been confirmed by the SOURCE, not by the table."""
    name = manifest_doc.get("source_replay_report")
    if not rep.check("the manifest names a source-native replay report", bool(name),
                     "contributor evidence was never replayed against the source"):
        return
    rpath = by_sha.get(shas.get(str(name), ""))
    if not rep.check("replay report present with bytes matching its pin",
                     rpath is not None):
        return

    with open(rpath) as fh:
        report = json.load(fh)
    records = table_doc["records"]
    declared = str(report.get("schema_version"))
    rep.check("the replay report is NOT an existence-only (superseded) report",
              declared not in SUPERSEDED_REPLAY_SCHEMAS,
              f"{declared!r} proves each locator points at a kept row — which cannot "
              "see a contributor that was silently DROPPED. It is not a release gate")
    rep.check("replay report carries the pinned schema", declared == REPLAY_SCHEMA,
              f"got {declared!r}")

    # COMPLETENESS must have been ASKED. A report missing these fields did not ask it,
    # and must never be read as though it had answered "yes".
    absent = [k for k in COMPLETENESS_KEYS if k not in report]
    rep.check("the replay report carries every completeness field", not absent,
              f"missing {absent}")

    # WHICH rules produced this verdict. Naming the rule is not obeying it — the
    # arithmetic below is what checks the obedience — but a report that names a
    # DIFFERENT rule answered a different question, and its "complete" is not this
    # gate's "complete".
    rep.check("the replay report declares the exact v2 replay rule",
              str(report.get("replay_rule_id")) == REPLAY_RULE_ID,
              f"expected {REPLAY_RULE_ID!r}, got {report.get('replay_rule_id')!r}")
    rep.check("the replay report declares the exact v2 completeness rule",
              str(report.get("completeness_rule_id")) == COMPLETENESS_RULE_ID,
              f"expected {COMPLETENESS_RULE_ID!r}, got "
              f"{report.get('completeness_rule_id')!r}")
    rep.check("the replay report declares the exact SOURCE classification rule",
              str(report.get("source_classification_rule_id"))
              == SOURCE_CLASSIFICATION_RULE_ID,
              f"expected {SOURCE_CLASSIFICATION_RULE_ID!r}, got "
              f"{report.get('source_classification_rule_id')!r}; a partition decided by "
              "the manifest's own labels is not a partition decided by the source")
    rep.check("the replay report found NO scope downgraded out of the evidence set",
              _int(report, "n_scopes_downgraded") == 0,
              f"{report.get('n_scopes_downgraded')} determinable scope(s) are labelled "
              "ambiguous")
    rep.check("the replay report found NO scope claiming evidence the source lacks",
              _int(report, "n_scopes_overclaimed") == 0,
              f"{report.get('n_scopes_overclaimed')} scope(s) are determined with no "
              "kept targeting guide in the source")
    rep.check("the report's determined/ambiguous split IS the source's split",
              _int(report, "n_scopes_determined")
              == _int(report, "n_scopes_source_determinable")
              and _int(report, "n_scopes_ambiguous")
              == _int(report, "n_scopes_source_non_determinable"),
              f"manifest split {report.get('n_scopes_determined')}/"
              f"{report.get('n_scopes_ambiguous')} vs source split "
              f"{report.get('n_scopes_source_determinable')}/"
              f"{report.get('n_scopes_source_non_determinable')}")

    rep.check("the source confirmed the contributor sets are COMPLETE",
              str(report.get("completeness_verdict")) == "complete"
              and int(report.get("n_scopes_incomplete", 1)) == 0
              and int(report.get("n_nontargeting_guides_cited", 1)) == 0
              and int(report.get("n_records_offset_proven", -1)) == len(records),
              f"completeness={report.get('completeness_verdict')!r} "
              f"incomplete={report.get('n_scopes_incomplete')} "
              f"nontargeting={report.get('n_nontargeting_guides_cited')} "
              f"offset_proven={report.get('n_records_offset_proven')}/{len(records)}")

    check_scope_arithmetic(report, coverage, rep)
    rep.check("the source CONFIRMED every contributor record",
              str(report.get("verdict")) == "replayed"
              and int(report.get("n_failed", 1)) == 0
              and int(report.get("n_records", -1)) == len(records)
              and int(report.get("n_replayed", -2)) == len(records),
              f"verdict={report.get('verdict')!r} "
              f"replayed={report.get('n_replayed')}/{len(records)} "
              f"failed={report.get('n_failed')}")
    rep.check("the replay report binds THIS source-record table",
              str(report.get("source_record_table_sha256", "")).lower()
              == R.sha256_file(table_path))

    sid = str(report.get("source_id"))
    rep.check("the replay report binds the PINNED raw source bytes",
              shas.get(sid) == str(report.get("source_sha256", "")).lower(),
              f"report replays {report.get('source_sha256')!r}, manifest pins "
              f"{shas.get(sid)!r}")

    if not strict:
        return
    spath = by_sha.get(shas.get(sid, ""))
    if not rep.check("STRICT: the raw source is present to replay against",
                     spath is not None):
        return
    cols = read_evidence(spath)
    failures = replay_against_source(records, cols)
    rep.check("STRICT: every source record replays against the RAW source",
              not failures, f"{len(failures)} record(s) the source does not "
              f"confirm (first: {failures[0] if failures else None})")
    check_completeness(manifest_doc, records, cols, rep, coverage=coverage)
