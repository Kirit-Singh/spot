"""Contributor evidence, RESOLVED — part of the STANDALONE verifier.

INDEPENDENCE RULE (test-enforced): this module imports nothing from the generator.
The evidence contract is restated here from the written spec (``sources.py`` /
``manifest.py``), so a bug in the producer cannot be reproduced by the checker that
is meant to catch it.

What "resolved" means here, and what it deliberately does NOT mean:

  * a citation is not a proof because it is a non-empty string. Every record id is
    RE-DERIVED from the record's own canonical payload, and every determined row
    re-derives the id it must cite — so a citation cannot be aimed at some other
    record, and a record cannot be quietly re-labelled;
  * two records may not share an id. Indexing by id with a dict comprehension keeps
    the LAST duplicate and silently drops the rest, so a forged twin planted under an
    honest record's id would resolve as its honest sibling. A duplicate id is a
    refusal, not a merge;
  * a record's OWN ``source_sha256`` must be the pinned bytes of the source it names
    — not merely the citing row's;
  * a row resolves on the FULL released scope identity (``CONTRIB_KEY``): the
    estimate AND the whole released target identity. A record that agrees about the
    gene but not about the namespace it was named in is not evidence for that row;
  * an AMBIGUOUS row asserts that the identity is UNKNOWN. It is held to its
    CONTROLLED-NULL contract — no guide, no citation — and NEVER to the determined-row
    proof rules. Demanding an ``identity_method`` from a row that claims no identity
    would refuse the release's own six genuinely ambiguous scopes, which carry no
    proof fields at all because they are proving nothing.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

# Standalone: the rule module is loaded BY PATH, never as part of the generator
# package — importing it as ``direct.verify_rules`` would make the verifier a
# component of the thing it is checking.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import verify_rules as R  # noqa: E402

# For the Marson GWCD4i release the only released guide identity is a per-guide
# column (pseudobulk obs.guide_id). That release ships no ready-made contributor
# table, so an "author-supplied" claim against this source class is evidence of
# fabrication, not of provenance. Re-declared here, deliberately, rather than
# imported: the verifier restates the policy from the public release itself.
ADMISSIBLE_METHODS = {
    "marson_gwcd4i_public_release": ("released_per_guide_identity_column",),
}

# THE record-id rule, REIMPLEMENTED here from the schema's own declaration rather than
# imported from the generator. A record id is a hash of the record's WHOLE claim —
# identity AND the complete offset/row proof — so a record whose evidence is edited
# cannot keep its id, and the manifest citation that named the old id stops resolving.
#
# The superseded rule (``srec-`` + a 32-hex truncation over a payload that OMITTED the
# offset and row-name arrays) is refused outright, not migrated: under it a producer
# could swap a record's offsets for a smaller or fabricated set and every id would still
# re-derive perfectly. The id certified the claim while leaving the evidence free to
# move. An emitted table and a runtime agreeing under the same obsolete algorithm have
# proved nothing.
OFFSETS_FIELD = "pseudobulk_source_offsets"
ROWS_FIELD = "pseudobulk_source_rows"
IDENTITY_PAYLOAD_FIELDS = (
    "estimate_type", "estimate_id", "released_estimate_id", "target_id",
    "target_id_namespace", "target_ensembl", "target_symbol", "condition",
    "donor_pair", "guide_id", "identity_method", "source_id", "source_sha256",
    OFFSETS_FIELD, ROWS_FIELD,
)
RECORD_ID_PREFIX = "srcrec:sha256:"
SHA256_HEX_LEN = 64
SUPERSEDED_ID_PREFIX = "srec-"

# The one estimate class this pass carries evidence for.
POOLED_TYPE = "main"
POOLED_ID = "main"

# The exact schema versions this verifier speaks. Enforced BEFORE anything is indexed:
# a table of an unknown shape cannot be checked, only guessed at.
MANIFEST_SCHEMA = "spot.stage02_contributor_manifest.v3"
RECORDS_SCHEMA = "spot.stage02_source_records.v2"
RULE_METADATA_KEY = "canonical_source_record_id_rule"
CANONICAL_JSON_RULE = ("json.dumps(obj, sort_keys=True, ensure_ascii=False, "
                       "separators=(',',':'), allow_nan=False) encoded UTF-8")
RECORD_ID_RULE = ("source_record_id = 'srcrec:sha256:' + sha256( "
                  "canonical_json(identity_payload) )")
# HOW the nullable payload fields serialize. This is part of the rule, not a footnote to
# it: `target_ensembl` is null for every gene_symbol scope and `donor_pair` is null for
# every pooled scope, so a table that serialized either as "" or omitted it would hash a
# DIFFERENT payload and mint different ids — while still declaring the same `rule`
# string and the same field list. Leaving it uncompared was a hole exactly the width of
# the two fields that are null on almost every record in the release.
NULL_HANDLING = ("target_ensembl and donor_pair serialize as JSON null when absent; "
                 "they are part of the hashed payload.")

# The EXACT rule metadata a v2 table must declare — every field, compared field by field.
RULE_METADATA_FIELDS = ("rule", "canonical_json", "null_handling",
                        "identity_payload_fields")

# The evidence domain's own RULE id: pooled-main scopes matched EXACTLY against the
# global released universe. Re-declared here, not imported.
EVIDENCE_DOMAIN_RULE_ID = ("spot.stage02.direct.domain_rule."
                           "pooled_main_exact_scope_match.v1")

# The proof an ambiguous row must NOT carry.
CONTROLLED_NULL_FIELDS = ("guide_id", "source_record_id")


def derive_record_id(payload) -> str:
    """THE record id, recomputed from the whole claim — identity AND proof."""
    body = {}
    for f in IDENTITY_PAYLOAD_FIELDS:
        v = payload.get(f)
        if f in (OFFSETS_FIELD, ROWS_FIELD):
            body[f] = v if isinstance(v, list) else None
        else:
            body[f] = R.norm(v)
    blob = json.dumps(body, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")
    return RECORD_ID_PREFIX + hashlib.sha256(blob).hexdigest()


def check_schema_versions(manifest_doc, table_doc, rep) -> bool:
    """The EXACT schemas, before a single record is indexed.

    A superseded schema is not "an older but acceptable shape": the v1/v2 pair's ids
    were minted under a rule that left the completeness proof outside the identity, so
    admitting one would admit exactly the forgery this gate exists to catch.
    """
    m = str(manifest_doc.get("schema_version"))
    t = str(table_doc.get("schema_version"))
    ok_m = rep.check("the contributor manifest declares the exact expected schema",
                     m == MANIFEST_SCHEMA, f"expected {MANIFEST_SCHEMA!r}, got {m!r}")
    ok_t = rep.check("the source-record table declares the exact expected schema",
                     t == RECORDS_SCHEMA, f"expected {RECORDS_SCHEMA!r}, got {t!r}")
    ok_d = rep.check("the manifest names the SAME evidence schema the table is",
                     str(manifest_doc.get("source_record_table_schema_version")) == t,
                     f"manifest says "
                     f"{manifest_doc.get('source_record_table_schema_version')!r}, "
                     f"table says {t!r}")

    # The table's DECLARED identity rule must be the rule this verifier compiles, in
    # EVERY field. A schema that describes one rule in prose while its producer
    # implements another is exactly how the superseded pair went unnoticed — and
    # ``null_handling`` is not a footnote to that rule, it is part of it: target_ensembl
    # and donor_pair are null on almost every record in the release, so a table that
    # serialized them differently would hash a different payload, mint different ids,
    # and still declare an identical `rule` string.
    declared = table_doc.get(RULE_METADATA_KEY)
    compiled = {"rule": RECORD_ID_RULE, "canonical_json": CANONICAL_JSON_RULE,
                "null_handling": NULL_HANDLING,
                "identity_payload_fields": list(IDENTITY_PAYLOAD_FIELDS)}
    mismatched = []
    if not isinstance(declared, dict):
        mismatched = list(RULE_METADATA_FIELDS)
    else:
        for f in RULE_METADATA_FIELDS:
            got = declared.get(f)
            got = ([str(x) for x in got] if f == "identity_payload_fields"
                   and isinstance(got, list) else got)
            if got != compiled[f]:
                mismatched.append(f)
    ok_r = rep.check(
        "the table's declared record-id rule IS the compiled rule, field for field "
        "(prefix, full digest, null handling, and a payload that binds the offset/row "
        "proof)",
        not mismatched,
        f"declared rule differs in {mismatched}")
    return ok_m and ok_t and ok_d and ok_r


# --------------------------------------------------------------------------- #
# Evidence state: determined rows PROVE, ambiguous rows CLAIM NOTHING.
# --------------------------------------------------------------------------- #
def check_evidence_states(manifest_doc, rep):
    cls = str(manifest_doc.get("source_class"))
    admissible = ADMISSIBLE_METHODS.get(cls)
    rep.check("manifest declares a known source class", admissible is not None,
              f"unknown source_class {cls!r}")
    if admissible is None:
        return
    rows = manifest_doc["rows"]

    bad_state = sorted({str(r.get("evidence_state")) for r in rows
                        if str(r.get("evidence_state")) not in R.EVIDENCE_STATES})
    rep.check("every contributor row declares an evidence state", not bad_state,
              f"evidence_state(s) {bad_state} are not one of "
              f"{list(R.EVIDENCE_STATES)}; a row that forgets to say whether its "
              "identity was determined is not implicitly determined")

    # A DETERMINED row proves an identity, so it must say by a method the release
    # actually supports for its source class.
    bad = sorted({str(r.get("identity_method")) for r in rows
                  if str(r.get("evidence_state")) == R.DETERMINED
                  and str(r.get("identity_method")) not in admissible})
    rep.check("every determined contributor row uses an identity method the release "
              "actually supports for its source class", not bad,
              f"inadmissible method(s) {bad} for source_class {cls!r}")

    # An AMBIGUOUS row proves nothing. It need not name an identity_method at all —
    # the release's own ambiguous scopes omit the proof fields entirely. But if it
    # DOES name one, an unsupported method is still a false claim.
    bad_amb = sorted({str(r.get("identity_method")) for r in rows
                      if str(r.get("evidence_state")) == R.AMBIGUOUS
                      and not R.is_null(r.get("identity_method"))
                      and str(r.get("identity_method")) not in admissible})
    rep.check("an ambiguous row that names an identity method names a supported one",
              not bad_amb, f"inadmissible method(s) {bad_amb} on ambiguous row(s)")


def check_identity_contract(manifest_doc, table_doc, rep):
    """Every manifest row and every source record obeys the identity contract.

    An ENSG-looking release key promoted into ``target_ensembl`` surfaces here as a
    gene_symbol row with a non-null target_ensembl. The release key is never parsed.
    """
    bad_rows = [(i, R.identity_violation(r))
                for i, r in enumerate(manifest_doc["rows"])
                if R.identity_violation(r) is not None]
    rep.check("every contributor-manifest row carries an admissible released target "
              "identity", not bad_rows, f"{len(bad_rows)} bad row(s): {bad_rows[:3]}")

    bad_recs = [(i, R.identity_violation(r))
                for i, r in enumerate(table_doc["records"])
                if R.identity_violation(r) is not None]
    rep.check("every source record carries an admissible released target identity",
              not bad_recs, f"{len(bad_recs)} bad record(s): {bad_recs[:3]}")

    # An ambiguous row proves nothing, so resolution skips it -- which is exactly
    # why it may not carry a citation nobody will ever check.
    forged = [i for i, r in enumerate(manifest_doc["rows"])
              if str(r.get("evidence_state")) == R.AMBIGUOUS
              and any(not R.is_null(r.get(f)) for f in CONTROLLED_NULL_FIELDS)]
    rep.check("no ambiguous row carries a guide or a citation", not forged,
              f"{len(forged)} ambiguous row(s) cite evidence they do not have")

    # 1:1. Two records for one (key, guide) means a citation resolves to "either".
    seen, dup = set(), []
    for rec in table_doc["records"]:
        key = R.scope_of(rec) + (R.norm(rec.get("guide_id")),)
        (dup.append(key) if key in seen else seen.add(key))
    rep.check("source records are 1:1 on (estimate key, guide)", not dup,
              f"{len(dup)} duplicate record key(s)")


# --------------------------------------------------------------------------- #
# The source-record table, INDEXED — duplicates refused, ids re-derived.
# --------------------------------------------------------------------------- #
def _offset_proof_violation(rec):
    """Why this record's completeness proof is not a proof, or None.

    EVERY record must carry it — not "all or none". A table where one record omits the
    proof is a table with an unproven record in it, and the run cannot tell which of
    its masks that record built.
    """
    offsets, rows = rec.get(OFFSETS_FIELD), rec.get(ROWS_FIELD)
    if not isinstance(offsets, list) or not offsets:
        return "offsets_missing_or_empty"
    if any(not isinstance(x, int) or isinstance(x, bool) or x < 0 for x in offsets):
        return "offset_is_not_a_non_negative_integer"
    if len(set(offsets)) != len(offsets):
        return "duplicate_offsets"
    if list(offsets) != sorted(offsets):
        return "offsets_not_in_ascending_order"
    if not isinstance(rows, list) or len(rows) != len(offsets):
        return "row_names_do_not_match_the_offsets_one_for_one"
    if any(not isinstance(x, str) or not x.strip() for x in rows):
        return "row_name_is_not_a_non_empty_string"
    if rec.get("source_row_index") not in offsets:
        return "locator_is_not_one_of_the_records_own_offsets"
    return None


def index_records(table_doc, source_shas, rep):
    """Index by ``source_record_id``, refusing anything a dict would swallow."""
    records = table_doc["records"]

    # The id SHAPE, before anything else. A surviving ``srec-`` id is not a cosmetic
    # detail: it is an id minted under a rule that did not bind the offset proof.
    bad_shape = []
    for rec in records:
        rid = R.norm(rec.get("source_record_id"))
        if rid is None:
            bad_shape.append("<null>")
        elif rid.startswith(SUPERSEDED_ID_PREFIX):
            bad_shape.append(rid)
        elif not rid.startswith(RECORD_ID_PREFIX) \
                or len(rid) != len(RECORD_ID_PREFIX) + SHA256_HEX_LEN:
            bad_shape.append(rid)
    rep.check("every source record id is shaped by the compiled rule "
              "(srcrec:sha256: + a full 64-hex digest, never a truncated srec- id)",
              not bad_shape, f"{len(bad_shape)} malformed id(s) (first: "
              f"{bad_shape[0] if bad_shape else None})")

    # The COMPLETE offset proof, on EVERY record.
    unproven = [(R.norm(r.get("source_record_id")), _offset_proof_violation(r))
                for r in records if _offset_proof_violation(r) is not None]
    rep.check("EVERY source record carries a well-formed complete offset/row proof",
              not unproven, f"{len(unproven)} of {len(records)} record(s) have no "
              f"usable proof (first: {unproven[0] if unproven else None}); a partial "
              "proof is not a proof, and 'all or none' is not the contract")

    index, dupes = {}, []
    for rec in records:
        rid = R.norm(rec.get("source_record_id"))
        if rid is None:
            continue                 # a null id is caught as an unresolvable citation
        if rid in index:
            dupes.append(rid)
            continue
        index[rid] = rec
    rep.check("source record ids are unique", not dupes,
              f"{len(dupes)} duplicate record id(s) (first: "
              f"{dupes[0] if dupes else None}); indexing by id would keep one and "
              "silently drop the rest")

    # The id is RE-DERIVED from the record's own payload — identity AND proof — never
    # believed. This is what makes an edited offset array fatal: the record cannot keep
    # the id its citation names.
    not_derived = sorted(rid for rid, rec in index.items()
                         if rid != derive_record_id(rec))
    rep.check("every source record id re-derives from the record's own payload, "
              "INCLUDING its complete offset/row proof",
              not not_derived, f"{len(not_derived)} record(s) declare an id their "
              f"own payload does not derive (first: "
              f"{not_derived[0] if not_derived else None})")

    # ...and the record's OWN source hash must be the PINNED bytes of the source it
    # names. A record that cites a source it does not pin is not evidence from it.
    bad_sha = sorted(rid for rid, rec in index.items()
                     if source_shas.get(str(rec.get("source_id"))) is None
                     or str(rec.get("source_sha256", "")).lower()
                     != source_shas.get(str(rec.get("source_id"))))
    rep.check("every source record pins the bytes of the source it names",
              not bad_sha, f"{len(bad_sha)} record(s) whose own source_sha256 is not "
              f"the pinned hash of their source_id (first: "
              f"{bad_sha[0] if bad_sha else None})")
    return index


# --------------------------------------------------------------------------- #
# Resolution, on the FULL released scope identity.
# --------------------------------------------------------------------------- #
def is_excluded(row) -> bool:
    """``included`` is false in every spelling a JSON producer might use."""
    return row.get("included", True) in (False, "false", "False", 0)


def check_domain(manifest_doc, table_doc, rep):
    """POOLED-MAIN ONLY. A support row here is a claim with no method behind it."""
    for what, items in (("manifest row", manifest_doc["rows"]),
                        ("source record", table_doc["records"])):
        stray = sorted({(str(r.get("estimate_type")), str(r.get("estimate_id")),
                         R.norm(r.get("donor_pair")))
                        for r in items if not _is_pooled_main(r)})
        rep.check(f"every {what} is an all-condition POOLED-MAIN scope",
                  not stray,
                  f"{len(stray)} out-of-domain key(s) (first: "
                  f"{stray[0] if stray else None}); by-guide and donor-pair support "
                  "has no provenance method in this pass, and admitting it would let "
                  "a support estimate acquire a mask it never earned")


def _is_pooled_main(row) -> bool:
    return (str(row.get("estimate_type")) == POOLED_TYPE
            and str(row.get("estimate_id")) == POOLED_ID
            and R.is_null(row.get("donor_pair")))


def resolve_contributors(manifest_doc, table_doc, source_shas, rep):
    """Rebuild the contributor map only from rows that RESOLVE to a source record.

    The map is keyed by the FULL released scope identity, because that is the only
    thing a citation is allowed to be about.
    """
    if not check_schema_versions(manifest_doc, table_doc, rep):
        return {}                 # an unknown shape cannot be checked, only guessed at
    check_domain(manifest_doc, table_doc, rep)
    check_evidence_states(manifest_doc, rep)
    check_identity_contract(manifest_doc, table_doc, rep)
    records = index_records(table_doc, source_shas, rep)

    contrib, unresolved = {}, []
    for row in manifest_doc["rows"]:
        if str(row.get("evidence_state")) != R.DETERMINED:
            continue
        excluded = is_excluded(row)
        if excluded and R.is_null(row.get("source_record_id")):
            continue
        rid = R.norm(row.get("source_record_id"))
        rec = records.get(str(rid))
        pinned = source_shas.get(str(row.get("source_id")))
        # The row canNOT re-derive the id it cites: the payload binds the offset proof,
        # which lives in the table, not in the row. It does not need to. A row resolves
        # only against a record matching its ENTIRE released scope identity plus the
        # guide, the method and the source — and the table is 1:1 on that key — so it
        # still cannot borrow another estimate's evidence. The record's OWN id, in turn,
        # is a hash of its own proof, so the evidence cannot move under the citation.
        # BOTH the row's and the RECORD's source hash must be the pinned bytes.
        ok = (rid is not None and rec is not None
              and all(R.norm(rec.get(f)) == R.norm(row.get(f))
                      for f in R.CONTRIB_KEY
                      + ("guide_id", "identity_method", "source_id"))
              and pinned is not None
              and str(row.get("source_sha256", "")).lower() == pinned
              and str(rec.get("source_sha256", "")).lower() == pinned)
        if not ok:
            unresolved.append(rid)
            continue
        if excluded or not row.get("guide_id"):
            continue
        contrib.setdefault(R.scope_of(row), []).append(str(row["guide_id"]))
    rep.check("every determined contributor row resolves to a real source record",
              not unresolved, f"{len(unresolved)} unresolved citation(s)")

    # An ORPHAN record is evidence for a claim nobody made.
    cited = {R.norm(r.get("source_record_id")) for r in manifest_doc["rows"]
             if str(r.get("evidence_state")) == R.DETERMINED
             and not R.is_null(r.get("source_record_id"))}
    orphans = sorted(set(records) - cited)
    rep.check("no source record is cited by nobody", not orphans,
              f"{len(orphans)} orphan record(s) (first: "
              f"{orphans[0] if orphans else None})")
    return contrib


def scope_coverage(manifest_doc, released_scopes, rep) -> dict:
    """The manifest covers EXACTLY the independently derived global pooled-main set.

    ``released_scopes`` is re-derived from the RAW DE obs metadata by the verifier
    itself (``verify_run.derive_global_scopes``) — never read from the run's own
    provenance, which is the thing under test. A wholly dropped scope fails here: it
    is invisible to any per-row check, because the row that would have carried it is
    simply not there.
    """
    manifest_scopes = {R.scope_of(r) for r in manifest_doc["rows"]}
    missing = sorted(released_scopes - manifest_scopes, key=R.scope_sort_key)
    extra = sorted(manifest_scopes - released_scopes, key=R.scope_sort_key)
    rep.check("the manifest names no scope the release does not contain", not extra,
              f"{len(extra)} extra scope(s) (first: {extra[0] if extra else None})")
    rep.check("the manifest covers EVERY released pooled-main scope", not missing,
              f"{len(missing)} missing scope(s) (first: "
              f"{missing[0] if missing else None})")

    determined, ambiguous = set(), set()
    for row in manifest_doc["rows"]:
        state = str(row.get("evidence_state"))
        scope = R.scope_of(row)
        if state == R.DETERMINED and not is_excluded(row) \
                and not R.is_null(row.get("guide_id")):
            determined.add(scope)
        elif state == R.AMBIGUOUS:
            ambiguous.add(scope)
    # NOTE ON AUTHORITY. The split below is the manifest's OWN claim about itself, and it
    # is used here only to prove that every released scope is accounted for SOMEHOW —
    # that none is silently missing. It is NOT evidence that the split is correct, and it
    # cannot be: the same producer wrote both halves, so a scope moved from determined to
    # ambiguous is still "accounted for". Whether a scope may be called ambiguous is
    # decided by the RAW SOURCE alone, in ``verify_source.check_source_classification``,
    # which the strict path runs. This function must never be read as classifying.
    rep.check("every released scope is either determined or explicitly ambiguous",
              determined | ambiguous == released_scopes,
              f"determined={len(determined)} ambiguous={len(ambiguous)} "
              f"released={len(released_scopes)}; "
              f"{len(released_scopes - (determined | ambiguous))} scope(s) are neither")
    rep.check("a scope is not both determined and ambiguous",
              not (determined & ambiguous),
              f"{len(determined & ambiguous)} scope(s) claim both")
    return {"n_released": len(released_scopes), "n_determined": len(determined),
            "n_ambiguous": len(ambiguous),
            # counted from the manifest ITSELF, so the run's copies of these numbers
            # (in the binding, in the domain block, in provenance) have something other
            # than each other to agree with
            "n_manifest_scopes": len(manifest_scopes),
            "n_manifest_rows": len(manifest_doc["rows"])}
