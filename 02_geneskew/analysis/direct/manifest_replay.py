"""THE RELEASE GATE: the contributor evidence must have been confirmed by the SOURCE.

Split out of ``manifest_validate`` so each module states one contract. ``validate_replay``
is the gate a run must pass before any evidence is admitted, and it is the single place
that binds a pinned replay report to:

  * the raw SOURCE that produced it (its bytes, its records, its offsets);
  * the MANIFEST it describes (its rows, its scopes, its determined/ambiguous split);
  * the RELEASED universe the manifest was matched against.

A manifest and a source-record table that agree with each other prove only that one
producer was self-consistent. Provenance requires the raw source.
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

from .manifest_schema import (COMPLETENESS_RULE_ID, DETERMINED,
                              REPLAY_COMPLETE, REPLAY_COMPLETENESS_KEYS,
                              REPLAY_REPLAYED, REPLAY_RULE_ID, REPLAY_SCHEMA,
                              SOURCE_CLASSIFICATION_RULE_ID,
                              SUPERSEDED_REPLAY_SCHEMAS,
                              is_nullish, require, scope_of, scope_partition)




# --------------------------------------------------------------------------- #
# THE RELEASE GATE.
# --------------------------------------------------------------------------- #
def _require_summary_is_derived(report: dict[str, Any], n_records: int) -> None:
    """The report's TOP-LEVEL verdicts must be what its own fields imply. Both ways.

    Every check above interrogates a specific field, and a forger who reseals a report
    can leave all of them intact while forging — or simply OMITTING — the one-word
    summary that consumers actually branch on. Nothing then compares the headline to the
    body: the summary is asserted alongside the specifics rather than derived from them,
    and "replayed / complete" becomes a free-standing claim.

    So the canonical derivation (the one ``replay.py`` performs) is restated here and
    required as an EQUIVALENCE, not an implication:

        complete  <->  no incomplete scope, no non-targeting citation, no downgrade,
                       no overclaim, and every record's offset proof confirmed
        replayed  <->  no failed record AND complete

    Both directions matter. "Claims replayed but is not" is the forgery; "claims refused
    but every field passes" is a report whose summary was produced by different logic
    than its body, and a report that cannot agree with itself is not evidence. A missing
    verdict fails here too — absence is not assent.
    """
    n_failed = int(report.get("n_failed", -1))
    derived_complete = (
        int(report.get("n_scopes_incomplete", -1)) == 0
        and int(report.get("n_nontargeting_guides_cited", -1)) == 0
        and int(report.get("n_scopes_downgraded", -1)) == 0
        and int(report.get("n_scopes_overclaimed", -1)) == 0
        and int(report.get("n_records_offset_proven", -1)) == n_records)
    derived_replayed = n_failed == 0 and derived_complete

    claimed_complete = str(report.get("completeness_verdict")) == REPLAY_COMPLETE
    claimed_replayed = str(report.get("verdict")) == REPLAY_REPLAYED

    implies_complete = REPLAY_COMPLETE if derived_complete else "incomplete"
    implies_replayed = REPLAY_REPLAYED if derived_replayed else "refused"
    require(claimed_complete == derived_complete,
            f"source replay report: completeness_verdict is "
            f"{report.get('completeness_verdict')!r}, but its own fields derive "
            f"{implies_complete!r}. A summary that does not follow from the report's "
            "own counters was not computed from them")
    require(claimed_replayed == derived_replayed,
            f"source replay report: verdict is {report.get('verdict')!r}, but its own "
            f"fields derive {implies_replayed!r} (n_failed={n_failed}, "
            f"complete={derived_complete}). A forged or omitted summary verdict is not "
            "redeemed by honest fields underneath it")

    # ...and having proven the summary is honest, require it to be the PASSING one.
    require(derived_replayed and derived_complete,
            f"source replay report: the source did not confirm this evidence "
            f"(verdict={report.get('verdict')!r}, "
            f"completeness={report.get('completeness_verdict')!r})")


def validate_replay(doc: dict[str, Any], rows: list[dict[str, Any]],
                    table: dict[str, dict], source_shas: dict[str, str],
                    source_registry: Optional[dict[str, dict]], base_dir: str,
                    table_name: str,
                    released_scopes: Optional[set[tuple]] = None) -> dict[str, Any]:
    """THE RELEASE GATE: the evidence must have been replayed against the SOURCE.

    A manifest and a source-record table that agree with each other prove only that
    one producer was self-consistent. Provenance requires the raw source, so the
    contributor evidence is admitted only with a pinned replay report that binds
    THESE exact table bytes to THOSE exact source bytes. Generated-table agreement
    is never silently accepted as source verification: with no report, there is no
    contributor evidence and the run fails closed.
    """
    name = doc.get("source_replay_report")
    require(bool(name),
            "contributor manifest: 'source_replay_report' is required; contributor "
            "evidence that was never replayed against the raw source is not "
            "provenance, it is two generated files agreeing with each other")
    require(str(name) in source_shas,
            f"contributor manifest: source_replay_report {name!r} is not one of the "
            "manifest's verified sources; an unpinned report is not a report")

    pin = (source_registry or {}).get(str(name)) or {}
    with open(os.path.join(base_dir, str(pin.get("path", "")))) as fh:
        report = json.load(fh)

    declared = str(report.get("schema_version"))
    require(declared not in SUPERSEDED_REPLAY_SCHEMAS,
            f"source replay report: schema_version {declared!r} is EXISTENCE-ONLY and "
            "is SUPERSEDED. It proves each cited locator points at a kept raw row — "
            "which cannot see a contributor that was silently DROPPED. Every named "
            "guide would be real, every hash right, every locator replayed, and the "
            "mask still built from an incomplete guide set. An existence-only report "
            f"is not the release gate; re-run the replay under {REPLAY_SCHEMA!r}")
    require(declared == REPLAY_SCHEMA,
            f"source replay report: schema_version must be {REPLAY_SCHEMA!r}, got "
            f"{declared!r}")

    # COMPLETENESS is a separate question from existence, and it must have been ASKED.
    # A report that omits these fields did not ask it, and must never be read as if it
    # had answered "yes".
    absent = [k for k in REPLAY_COMPLETENESS_KEYS if k not in report]
    require(not absent,
            f"source replay report: missing completeness field(s) {absent}; a report "
            "that never asked whether the contributor sets were COMPLETE cannot be "
            "the release gate")

    # WHICH rules produced this verdict. A report is only interpretable under the rule
    # it was computed by, so the ids are required EXACTLY — an unknown rule id means an
    # unknown question was answered, and its "complete" says nothing about this one.
    require(str(report.get("replay_rule_id")) == REPLAY_RULE_ID,
            f"source replay report: replay_rule_id must be exactly {REPLAY_RULE_ID!r}, "
            f"got {report.get('replay_rule_id')!r}")
    require(str(report.get("completeness_rule_id")) == COMPLETENESS_RULE_ID,
            f"source replay report: completeness_rule_id must be exactly "
            f"{COMPLETENESS_RULE_ID!r}, got {report.get('completeness_rule_id')!r}")

    # THE SOURCE CLASSIFICATION, diagnosed BEFORE the report's own summary verdict.
    #
    # ``verdict`` is a one-word conclusion the producer wrote about its own work. When a
    # scope has been downgraded, that word is "refused" — which is correct, and tells the
    # reader nothing: they get "the source did not confirm this evidence, 0 failed
    # records" and no idea that a determinable scope was quietly relabelled unknown.
    # The specific cause must outrank the producer's summary of it, or the most important
    # refusal in the lane is delivered as a shrug.
    require(str(report.get("source_classification_rule_id"))
            == SOURCE_CLASSIFICATION_RULE_ID,
            f"source replay report: source_classification_rule_id must be exactly "
            f"{SOURCE_CLASSIFICATION_RULE_ID!r}, got "
            f"{report.get('source_classification_rule_id')!r}; a report that classified "
            "the scopes under some other rule did not classify them under this one")
    n_downgraded = int(report["n_scopes_downgraded"])
    n_overclaimed = int(report["n_scopes_overclaimed"])
    require(n_downgraded == 0,
            f"source replay report: {n_downgraded} scope(s) the raw source can DETERMINE "
            "are labelled ambiguous. The source kept targeting guides for them; calling "
            "that identity unknown deletes evidence that exists, and silently strips the "
            "scope of its mask, its score and its rank")
    require(n_overclaimed == 0,
            f"source replay report: {n_overclaimed} scope(s) are labelled determined but "
            "the raw source kept no targeting guide for them; an identity the source "
            "cannot prove is not a determined identity")

    # EXISTENCE, before completeness. A record whose locator does not replay means the
    # source and the evidence disagree about what is even THERE, and every scope counter
    # downstream is computed over records that did not survive that. "How complete is
    # this set" is not a question worth asking about rows the source refutes.
    #
    # ``n_failed`` is the record-level fact. ``verdict`` is NOT: the producer folds
    # completeness into it, so a perfectly replayed report with one shrunken scope still
    # says "refused, 0 failed records" — a sentence that names the wrong thing and then
    # contradicts itself. The two are asked separately, each about what it actually knows.
    require(int(report.get("n_failed", 1)) == 0,
            f"source replay report: {report.get('n_failed')} record(s) did not replay "
            "against the raw source; the source did not confirm this evidence")

    # A cited guide the source does not keep as TARGETING. Named before the scope
    # arithmetic, because "this guide was never a contributor" explains the numbers
    # rather than being explained by them.
    require(int(report.get("n_nontargeting_guides_cited", 1)) == 0,
            f"source replay report: {report.get('n_nontargeting_guides_cited')} cited "
            "guide(s) are not TARGETING guides in the source; a non-targeting control "
            "never contributed to a perturbation estimate")

    # A SCOPE that names fewer guides than the source kept for it. Only claimed when
    # there actually is one: this message used to fire for record-level failures too,
    # announcing "at least one released pooled scope does not name the whole contributor
    # set" over a report that said ZERO incomplete scopes. A refusal that misdescribes
    # what it refused sends the reader looking for a bug that is not there.
    require(int(report.get("n_scopes_incomplete", 1)) == 0,
            f"source replay report: {report.get('n_scopes_incomplete')} released pooled "
            "scope(s) are INCOMPLETE — they do not name the whole contributor set the "
            "raw source kept for them; a mask built from a shrunken guide set is a "
            "different mask")

    # The two one-word summaries are checked at the END of this function, as a DERIVATION
    # rather than an assertion — see ``_require_summary_is_derived`` below.

    # "0 incomplete" is NOT coverage. A wholly dropped scope names nothing, so it
    # appears in no completeness iteration and is counted nowhere — the report would say
    # zero incomplete and mean it. So the report's scope arithmetic is bound to the
    # manifest it describes AND to the released universe the manifest was matched
    # against: determined + ambiguous must be every scope, and every scope must be one
    # the release actually ships.
    manifest_scopes = {scope_of(r) for r in rows}
    det_scopes, amb_scopes = scope_partition(rows)
    n_determined = int(report["n_scopes_determined"])
    n_ambiguous = int(report["n_scopes_ambiguous"])
    n_named = int(report["n_scopes_named"])
    n_complete = int(report["n_scopes_complete"])
    n_incomplete = int(report["n_scopes_incomplete"])

    # The report's OWN counters must add up before any of them is believed. A report is
    # self-hashed and internally consistent by default — nothing in a pinned artifact
    # stops a producer emitting "complete=33977, incomplete=0, determined=33983" — so
    # each identity below is checked rather than assumed. Every one of them is a way a
    # scope can be counted as proven while never having been proven.
    require(n_named == n_determined + n_ambiguous,
            f"source replay report: n_scopes_named={n_named} but determined "
            f"({n_determined}) + ambiguous ({n_ambiguous}) = "
            f"{n_determined + n_ambiguous}; the report cannot agree with itself")
    require(n_complete == n_determined,
            f"source replay report: {n_complete} of {n_determined} determined scope(s) "
            "were proven complete; an unproven determined scope is not complete")
    require(n_complete + n_incomplete == n_determined,
            f"source replay report: complete ({n_complete}) + incomplete "
            f"({n_incomplete}) = {n_complete + n_incomplete}, but {n_determined} scope"
            "(s) were determined; a determined scope that is neither complete nor "
            "incomplete was never examined")
    require(n_determined + n_ambiguous == len(manifest_scopes),
            f"source replay report: it accounts for {n_determined} determined + "
            f"{n_ambiguous} ambiguous = {n_determined + n_ambiguous} scope(s), but the "
            f"manifest holds {len(manifest_scopes)}; a scope the report never looked at "
            "cannot be reported complete")

    # ...and it must have split that universe the SAME WAY THE MANIFEST DOES. Every
    # identity above compares the report to a TOTAL, and a total cannot see a
    # relabelling: move a determined scope into the ambiguous column and named,
    # complete+incomplete, and the released-universe size all still balance — while a
    # scope that DOES carry evidence is quietly excused from ever being proven complete
    # (only determined scopes are). The split is derived from the CURRENT rows, so the
    # report is checked against the manifest it actually describes.
    require(not (det_scopes & amb_scopes),
            f"contributor manifest: {len(det_scopes & amb_scopes)} scope(s) are both "
            "determined and ambiguous; a scope either claims an identity or does not")
    require(det_scopes | amb_scopes == manifest_scopes,
            f"contributor manifest: {len(manifest_scopes - (det_scopes | amb_scopes))} "
            "scope(s) are neither determined nor explicitly ambiguous; a scope with no "
            "evidence state was never examined")
    require(n_determined == len(det_scopes),
            f"source replay report: it reports {n_determined} determined scope(s), but "
            f"the manifest determines {len(det_scopes)}. A report that relabels a "
            "determined scope as ambiguous keeps every total intact and drops it from "
            "the set that must be proven COMPLETE")
    require(n_ambiguous == len(amb_scopes),
            f"source replay report: it reports {n_ambiguous} ambiguous scope(s), but "
            f"the manifest declares {len(amb_scopes)} ambiguous")

    # ...and the partition the manifest declares must BE the partition the source found.
    #
    # Everything above compares the report to the MANIFEST. That is a self-consistency
    # check between two documents the same producer wrote, and it is invariant under the
    # one mutation that matters: relabel a scope's rows to ambiguous, drop its records,
    # regenerate the counts, and the report and the manifest agree perfectly — about a
    # scope whose kept targeting guides are sitting in the raw source, untouched. The
    # only witness is the source, and the counts it produced are bound here.
    n_src_determinable = int(report["n_scopes_source_determinable"])
    n_src_ambiguous = int(report["n_scopes_source_non_determinable"])
    require(n_determined == n_src_determinable,
            f"source replay report: it reports {n_determined} determined scope(s), but "
            f"the SOURCE determines {n_src_determinable}. The manifest's partition is "
            "not the source's partition")
    require(n_ambiguous == n_src_ambiguous,
            f"source replay report: it reports {n_ambiguous} ambiguous scope(s), but the "
            f"source finds {n_src_ambiguous} genuinely non-determinable")

    if released_scopes is not None:
        require(len(manifest_scopes) == len(released_scopes),
                f"source replay report: the manifest covers {len(manifest_scopes)} "
                f"scope(s) but the release ships {len(released_scopes)}; the "
                "completeness verdict describes a different universe than the run")
    require(int(report.get("n_records_offset_proven", -1)) == len(table),
            f"source replay report: {report.get('n_records_offset_proven')} of "
            f"{len(table)} record(s) had their complete offset proof confirmed against "
            "the raw source; an unproven offset set is not a proof")

    # THE SUMMARY MUST BE DERIVED FROM THE SPECIFICS, not merely asserted beside them.
    _require_summary_is_derived(report, n_records=len(table))

    # The report is about THESE bytes, not some other run's.
    require(str(report.get("source_record_table_sha256", "")).lower()
            == source_shas[table_name],
            "source replay report: it replays a DIFFERENT source-record table "
            f"({report.get('source_record_table_sha256')!r}) than the one this "
            f"manifest pins ({source_shas[table_name]!r})")

    replayed_source = str(report.get("source_id"))
    require(replayed_source in source_shas,
            f"source replay report: it replays {replayed_source!r}, which is not one "
            "of the manifest's verified sources")
    require(str(report.get("source_sha256", "")).lower()
            == source_shas[replayed_source],
            f"source replay report: it replays source bytes "
            f"{report.get('source_sha256')!r}, not the pinned "
            f"{source_shas[replayed_source]!r}")

    # ...and it covers EVERY record, from the source every determined row cites.
    require(int(report.get("n_records", -1)) == len(table)
            and int(report.get("n_replayed", -1)) == len(table),
            f"source replay report: it replayed {report.get('n_replayed')} of "
            f"{report.get('n_records')} record(s), but the table holds "
            f"{len(table)}; every record must be replayed")
    cited = {str(r["source_id"]) for r in rows
             if str(r.get("evidence_state")) == DETERMINED
             and not is_nullish(r.get("source_id"))}
    require(cited <= {replayed_source},
            f"source replay report: determined rows cite source(s) {sorted(cited)}, "
            f"but only {replayed_source!r} was replayed against")

    # What run_id binds about the release gate. The RULE IDS are here on purpose: a run
    # bound to "complete" without binding WHICH completeness rule produced it could be
    # re-gated later under a weaker rule while keeping its id. The obsolete
    # ``replay_rule`` / ``completeness_rule`` keys are gone rather than aliased — they
    # read as null from a v2 report, and a null that nobody checks is how a rule
    # silently stopped being bound at all.
    return {
        "status": REPLAY_REPLAYED,
        "schema_version": REPLAY_SCHEMA,
        "source_replay_report": str(name),
        "source_id": replayed_source,
        "source_sha256": str(report.get("source_sha256")),
        "source_record_table_sha256": str(report.get("source_record_table_sha256")),
        "n_source_rows": report.get("n_source_rows"),
        "n_records_replayed": report.get("n_replayed"),
        "evidence_columns": report.get("evidence_columns"),
        "replay_rule_id": REPLAY_RULE_ID,
        # the completeness half of the gate, bound into the run
        "completeness_rule_id": COMPLETENESS_RULE_ID,
        "completeness_verdict": str(report.get("completeness_verdict")),
        "n_scopes_determined": n_determined,
        "n_scopes_ambiguous": n_ambiguous,
        "n_scopes_named": n_named,
        "n_scopes_complete": n_complete,
        "n_scopes_incomplete": n_incomplete,
        "n_records_offset_proven": report.get("n_records_offset_proven"),
        "n_nontargeting_guides_cited": report.get("n_nontargeting_guides_cited"),
        # WHICH rule split the scopes, and what the SOURCE said the split was. Bound into
        # run_id: a run re-gated later under a manifest-trusting classification would be
        # standing on different evidence and must not keep this identity.
        "source_classification_rule_id": SOURCE_CLASSIFICATION_RULE_ID,
        "n_scopes_source_determinable": n_src_determinable,
        "n_scopes_source_non_determinable": n_src_ambiguous,
        "n_scopes_downgraded": n_downgraded,
        "n_scopes_overclaimed": n_overclaimed,
    }
