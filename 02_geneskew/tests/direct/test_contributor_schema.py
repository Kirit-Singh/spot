"""The PINNED contributor-evidence JSON Schema, checked with a real validator.

The schema is the contract handed to the pending Claude Science pooled-contributor
artifact. If it disagrees with the runtime by so much as one field, the adapter is
built against a lie. So this module:

  * validates the schema itself as Draft 2020-12;
  * validates the REAL artifacts a synthetic run writes;
  * proves all 12 released gene-symbol scopes are representable with a null
    target_ensembl, and that an Ensembl scope is unchanged;
  * refuses each identity forgery, asserting the precise schema failure;
  * pins the schema TO the runtime constants, so the two cannot drift;
  * and states the one invariant JSON Schema cannot express, proving it is caught
    by the runtime and the verifier instead.

``jsonschema`` is imported unconditionally: a conformance test that silently skips
when its validator is absent is a vacuous guarantee.
"""
from __future__ import annotations

import copy
import json
import os

import pytest
from jsonschema import Draft202012Validator

from direct import identity, manifest as mf, record_id, sources

from fixtures_direct import (IDENTITY_METHOD, RECORD_TABLE_NAME,
                             REPLAY_REPORT_NAME, SOURCE_CLASS, SOURCE_NAME,
                             PINNED_REVISION)
from fixtures_spec import RELEASE_CONDITIONS, SYMBOL_TARGETS

SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(identity.__file__)),
                           "schemas", "stage02_contributor_evidence.schema.json")
with open(SCHEMA_PATH) as _fh:
    SCHEMA = json.load(_fh)

VALIDATOR = Draft202012Validator(SCHEMA)
ROW_VALIDATOR = Draft202012Validator(
    {**SCHEMA["$defs"]["manifestRow"], "$defs": SCHEMA["$defs"]})
RECORD_VALIDATOR = Draft202012Validator(
    {**SCHEMA["$defs"]["sourceRecord"], "$defs": SCHEMA["$defs"]})

SHA = "b" * 64


# --------------------------------------------------------------------------- #
# Helpers.
# --------------------------------------------------------------------------- #
def refusals(validator, doc) -> str:
    return " | ".join(
        f"{'/'.join(str(p) for p in e.absolute_path)}: {e.message}"
        for e in validator.iter_errors(doc))


def assert_accepted(validator, doc) -> None:
    errs = refusals(validator, doc)
    assert not errs, f"the schema REFUSED a conforming document: {errs}"


def assert_refused(validator, doc, *needles: str) -> None:
    """One broken invariant, one precise refusal. Never a bare 'it failed'."""
    errs = refusals(validator, doc)
    assert errs, "the schema ACCEPTED a document it must refuse"
    for needle in needles:
        assert needle in errs, f"expected {needle!r} in the refusal, got: {errs}"


# The COMPLETE offset proof every record must carry: the kept raw rows for this
# contributor, in ascending order, with the names the source gives them.
OFFSETS = [4, 7]
ROW_NAMES = ["pb|row|4", "pb|row|7"]


def record_of(row: dict, **over) -> dict:
    """The RECORD a row cites: identity + guide + the all-offset/row proof.

    The id is derived only once the proof is on the record, because the compiled rule
    hashes it. This is why a manifest row cannot mint its own citation.
    """
    rec = {k: row[k] for k in sources.REQUIRED_RECORD_COLUMNS if k in row}
    rec.setdefault("pseudobulk_source_offsets", list(OFFSETS))
    rec.setdefault("pseudobulk_source_rows", list(ROW_NAMES))
    rec.setdefault("source_row_index", OFFSETS[0])
    rec.update(over)
    if "source_record_id" not in over:
        rec["source_record_id"] = record_id.derive_record_id(rec)
    return rec


def ensembl_row(**over) -> dict:
    """An ordinary Ensembl-namespace pooled-main row: 33,971 of the release look so."""
    row = {
        "estimate_type": "main", "estimate_id": "main",
        "released_estimate_id": "ENSG00000141510_Rest",
        "target_id": "ENSG00000141510", "target_id_namespace": "ensembl_gene_id",
        "target_symbol": "TP53", "target_ensembl": "ENSG00000141510",
        "condition": "Rest", "donor_pair": None, "guide_id": "sg-TP53-1",
        "evidence_state": "determined", "included": True,
        "identity_method": IDENTITY_METHOD, "source_id": SOURCE_NAME,
        "source_sha256": SHA,
    }
    row.update(over)
    if "source_record_id" not in over:
        # The row does NOT derive its citation — it holds no proof to hash. It names
        # the id of the record built FROM it, which is the only direction available.
        row["source_record_id"] = record_of(row)["source_record_id"]
    return row


def symbol_row(symbol: str, condition: str, **over) -> dict:
    """One of the 12. Its release key may carry a DECOY ENSG prefix of another gene."""
    decoy = SYMBOL_TARGETS[symbol]
    fields = {
        "released_estimate_id": f"{decoy or symbol}_{condition}",
        "target_id": symbol, "target_id_namespace": "gene_symbol",
        "target_symbol": symbol, "target_ensembl": None,
        "condition": condition, "guide_id": f"sg-{symbol}-1",
    }
    fields.update(over)                    # the attack overrides the honest field
    return ensembl_row(**fields)


# --------------------------------------------------------------------------- #
# The schema itself, and the artifacts a real run writes.
# --------------------------------------------------------------------------- #
def test_the_pinned_schema_is_a_valid_draft_2020_12_schema():
    Draft202012Validator.check_schema(SCHEMA)


def test_the_schema_ids_are_the_production_ids_not_the_superseded_ones():
    assert SCHEMA["$id"] == "spot.stage02_contributor_evidence.v1"
    props = SCHEMA["properties"]
    assert (props["manifest"]["properties"]["schema_version"]["const"]
            == mf.SCHEMA_VERSION == "spot.stage02_contributor_manifest.v3")
    assert (props["source_record_table"]["properties"]["schema_version"]["const"]
            == sources.SCHEMA_VERSION == "spot.stage02_source_records.v2")
    # the manifest must name the SAME evidence schema the table actually is
    assert (props["manifest"]["properties"]["source_record_table_schema_version"]
            ["const"] == mf.SOURCE_RECORD_TABLE_SCHEMA == sources.SCHEMA_VERSION)
    assert (SCHEMA["$defs"]["sourceReplayReport"]["properties"]["schema_version"]
            ["const"] == mf.REPLAY_SCHEMA == "spot.stage02_source_replay.v2")


def test_the_artifacts_a_real_run_writes_conform_to_the_pinned_schema(synthetic_run):
    """The fixtures, the runtime and the schema are the SAME contract or none is."""
    from direct.run_screen import build_screen
    args = synthetic_run()
    build_screen(args)                                   # the run accepts them...

    base = os.path.dirname(args.guide_manifest)
    bundle = {
        "manifest": json.load(open(args.guide_manifest)),
        "source_record_table": json.load(open(os.path.join(base,
                                                           RECORD_TABLE_NAME))),
        "source_replay_report": json.load(open(os.path.join(base,
                                                            REPLAY_REPORT_NAME))),
        "source_registry": json.load(open(args.source_registry)),
    }
    assert_accepted(VALIDATOR, bundle)                   # ...and so does the schema
    assert bundle["manifest"]["rows"]
    assert bundle["source_record_table"]["records"]
    # ...and the evidence was confirmed by the SOURCE, not merely by the table
    assert bundle["source_replay_report"]["verdict"] == "replayed"
    assert bundle["source_replay_report"]["n_failed"] == 0


# --------------------------------------------------------------------------- #
# Both namespaces are first-class. Neither may be dropped.
# --------------------------------------------------------------------------- #
def test_an_ordinary_ensembl_scope_is_representable():
    assert_accepted(ROW_VALIDATOR, ensembl_row())
    assert_accepted(RECORD_VALIDATOR, record_of(ensembl_row()))


def test_all_twelve_released_symbol_scopes_are_representable():
    """4 symbols x 3 conditions. The obsolete accession-only contract dropped all 12."""
    scopes = [(s, c) for s in SYMBOL_TARGETS for c in RELEASE_CONDITIONS]
    assert len(scopes) == 12

    for symbol, condition in scopes:
        row = symbol_row(symbol, condition)
        assert_accepted(ROW_VALIDATOR, row)
        assert_accepted(RECORD_VALIDATOR, record_of(row))


def test_target_ensembl_is_null_for_every_one_of_the_twelve():
    for symbol in SYMBOL_TARGETS:
        for condition in RELEASE_CONDITIONS:
            row = symbol_row(symbol, condition)
            assert row["target_ensembl"] is None
            assert row["target_id_namespace"] == "gene_symbol"
            # the release key keeps its decoy prefix, verbatim and unparsed
            decoy = SYMBOL_TARGETS[symbol]
            assert row["released_estimate_id"] == f"{decoy or symbol}_{condition}"
            assert_accepted(ROW_VALIDATOR, row)


def test_a_symbol_target_may_never_carry_an_ensembl_id():
    """Not even a REAL one: gene_symbol => target_ensembl is null, full stop."""
    row = symbol_row("OCLM", "Rest", target_ensembl="ENSG00000262180")
    assert_refused(ROW_VALIDATOR, row, "target_ensembl", "null")


def test_an_ensembl_looking_symbol_name_is_still_a_valid_symbol():
    """Six released Ensembl rows carry an ENSG-looking gene NAME. That is allowed:
    target_symbol is an exact string, not a pattern."""
    assert_accepted(ROW_VALIDATOR, ensembl_row(target_symbol="ENSG00000284662"))


# --------------------------------------------------------------------------- #
# The forgeries the schema itself refuses.
# --------------------------------------------------------------------------- #
def test_the_obsolete_target_ensembl_only_row_is_refused():
    """The contract this file replaces. It cannot express a symbol scope at all."""
    obsolete = {"estimate_type": "main", "estimate_id": "main",
                "target_ensembl": "ENSG00000141510", "condition": "Rest",
                "donor_pair": None, "guide_id": "sg-1",
                "evidence_state": "determined", "identity_method": IDENTITY_METHOD,
                "source_id": SOURCE_NAME, "source_record_id": "r1",
                "source_sha256": SHA}
    assert_refused(ROW_VALIDATOR, obsolete,
                   "'released_estimate_id' is a required property",
                   "'target_id' is a required property",
                   "'target_id_namespace' is a required property",
                   "'target_symbol' is a required property")


@pytest.mark.parametrize("field", ["released_estimate_id", "target_id",
                                   "target_id_namespace", "target_symbol",
                                   "target_ensembl"])
def test_every_identity_field_is_required_on_both_row_types(field):
    row = ensembl_row()
    row.pop(field)
    assert_refused(ROW_VALIDATOR, row, f"'{field}' is a required property")

    rec = record_of(ensembl_row())
    rec.pop(field)
    assert_refused(RECORD_VALIDATOR, rec, f"'{field}' is a required property")


def test_the_ensg_looking_release_key_may_not_be_promoted():
    """THE trap: the key says ENSG00000232196, the target is MTRNR2L4."""
    row = symbol_row("MTRNR2L4", "Rest", target_ensembl="ENSG00000232196")
    assert row["released_estimate_id"] == "ENSG00000232196_Rest"
    assert_refused(ROW_VALIDATOR, row, "target_ensembl", "null")
    assert_refused(RECORD_VALIDATOR, record_of(row), "target_ensembl", "null")


def test_a_namespace_outside_the_enum_is_refused():
    assert_refused(ROW_VALIDATOR, ensembl_row(target_id_namespace="hgnc"),
                   "target_id_namespace", "is not one of")
    assert_refused(ROW_VALIDATOR, ensembl_row(target_id_namespace="Ensembl_Gene_ID"),
                   "target_id_namespace", "is not one of")


def test_an_ensembl_namespace_with_a_non_accession_target_id_is_refused():
    row = ensembl_row(target_id="MTRNR2L4", target_ensembl="ENSG00000232196")
    assert_refused(ROW_VALIDATOR, row, "target_id", "ENSG")


def test_an_ensembl_namespace_with_a_null_target_ensembl_is_refused():
    assert_refused(ROW_VALIDATOR, ensembl_row(target_ensembl=None),
                   "target_ensembl")


def test_a_symbol_namespace_whose_target_id_is_an_accession_is_refused():
    row = symbol_row("OCLM", "Rest", target_id="ENSG00000262180")
    assert_refused(ROW_VALIDATOR, row, "target_id")


def test_an_empty_target_symbol_is_refused():
    assert_refused(ROW_VALIDATOR, ensembl_row(target_symbol=""),
                   "target_symbol", "too short")


def test_a_malformed_target_ensembl_is_refused():
    assert_refused(ROW_VALIDATOR, ensembl_row(target_ensembl="ENSG"),
                   "target_ensembl")


def test_an_ambiguous_row_may_not_carry_a_guide_or_a_citation():
    amb = ensembl_row(evidence_state="ambiguous")
    assert_refused(ROW_VALIDATOR, amb, "guide_id", "null")

    honest = ensembl_row(evidence_state="ambiguous", guide_id=None,
                         source_record_id=None)
    assert_accepted(ROW_VALIDATOR, honest)          # ...and it KEEPS its identity
    assert honest["target_id"] and honest["target_symbol"]


def test_a_determined_included_row_must_bind_its_proof():
    row = ensembl_row()
    row.pop("source_record_id")
    assert_refused(ROW_VALIDATOR, row, "'source_record_id' is a required property")


def test_an_arbitrary_identity_method_is_refused():
    assert_refused(ROW_VALIDATOR, ensembl_row(identity_method="trust_me"),
                   "identity_method", "is not one of")


def test_a_mutable_revision_and_a_quarantined_source_are_refused(synthetic_run):
    reg = {"sources": {SOURCE_NAME: {"path": SOURCE_NAME, "sha256": SHA,
                                     "revision": "main"}}}
    assert_refused(Draft202012Validator(
        {**SCHEMA["properties"]["source_registry"], "$defs": SCHEMA["$defs"]}),
        reg, "revision")

    man = {"schema_version": mf.SCHEMA_VERSION, "source_class": SOURCE_CLASS,
           "source_record_table": RECORD_TABLE_NAME,
           "sources": [{"name": "contributing_guides.mixed.csv.gz", "sha256": SHA,
                        "revision": PINNED_REVISION}],
           "rows": [ensembl_row()]}
    assert_refused(Draft202012Validator(
        {**SCHEMA["properties"]["manifest"], "$defs": SCHEMA["$defs"]}),
        man, "name")


# --------------------------------------------------------------------------- #
# The schema must not be READ as stronger than it is.
# --------------------------------------------------------------------------- #
def test_the_one_invariant_json_schema_cannot_express_is_named_and_enforced():
    """target_ensembl == target_id is an equality between two sibling properties.

    Draft 2020-12 has no $data, so it cannot be expressed. The schema therefore only
    requires both to be well-formed accessions — and SAYS SO — while the runtime and
    the standalone verifier enforce the equality. A schema that implied a guarantee
    it does not make would be worse than no schema.
    """
    # a well-formed accession... of a DIFFERENT gene
    forged = ensembl_row(target_ensembl="ENSG09999999999")

    # the schema, honestly, accepts it
    assert_accepted(ROW_VALIDATOR, forged)

    # the invariant is NAMED in the schema as runtime-enforced
    gap = SCHEMA["x-runtime-enforced-invariants"]["target_ensembl_equals_target_id"]
    assert "$data" in gap and "refused at runtime" in gap

    # ...and the runtime and the independent verifier both refuse it
    from direct import verify_rules as R
    assert (identity.identity_violation(forged)
            == identity.ENSEMBL_NS_ENSEMBL_NOT_TARGET_ID)
    assert R.identity_violation(forged) == identity.ENSEMBL_NS_ENSEMBL_NOT_TARGET_ID


# --------------------------------------------------------------------------- #
# Anti-drift: the schema IS the runtime constants.
# --------------------------------------------------------------------------- #
def test_the_schema_required_fields_are_exactly_the_runtime_required_keys():
    row_required = set(SCHEMA["$defs"]["targetIdentity"]["required"])
    for part in SCHEMA["$defs"]["manifestRow"]["allOf"]:
        row_required |= set(part.get("required", ()))
    assert row_required == set(mf.REQUIRED_ROW_KEYS)

    rec_required = set(SCHEMA["$defs"]["targetIdentity"]["required"])
    for part in SCHEMA["$defs"]["sourceRecord"]["allOf"]:
        rec_required |= set(part.get("required", ()))
    assert rec_required == set(sources.REQUIRED_RECORD_COLUMNS)


def test_the_schema_enums_are_exactly_the_runtime_enums():
    defs = SCHEMA["$defs"]
    assert (defs["targetIdentity"]["properties"]["target_id_namespace"]["enum"]
            == list(identity.NAMESPACES))
    assert set(defs["identityMethod"]["enum"]) == set(mf.ALLOWED_IDENTITY_METHODS)
    assert set(defs["sourceClass"]["enum"]) == set(mf.SOURCE_CLASSES)
    assert set(defs["manifestRow"]["allOf"][1]["properties"]
               ["evidence_state"]["enum"]) == set(mf.EVIDENCE_STATES)
    assert (defs["targetIdentity"]["properties"]["target_ensembl"]["pattern"]
            == identity.ENSG_RE.pattern)
    quarantined = defs["manifestRow"]  # noqa: F841  (kept for symmetry of reading)
    src_names = (SCHEMA["properties"]["manifest"]["properties"]["sources"]
                 ["items"]["properties"]["name"]["not"]["enum"])
    assert set(src_names) == set(mf.QUARANTINED_SOURCES)


def test_the_schema_names_the_only_admissible_method_for_the_marson_release():
    """The enum is the vocabulary; admissibility is narrower and per-class."""
    assert mf.ADMISSIBLE_IDENTITY_METHODS[mf.SOURCE_CLASS_MARSON] == (
        "released_per_guide_identity_column",)
    text = SCHEMA["$defs"]["identityMethod"]["description"]
    assert "released_per_guide_identity_column" in text
    assert "author-supplied contributor table" in text
    assert ("identity_method_admissible_for_source_class"
            in SCHEMA["x-runtime-enforced-invariants"])


# --------------------------------------------------------------------------- #
# SCHEMA/RUNTIME AGREEMENT.
#
# A schema laxer than the runtime certifies nothing: it validates artifacts the lane
# would refuse, so "schema-valid" stops being evidence of anything. These pin the
# schema's constants TO the compiled ones, so the two cannot drift apart silently —
# which is exactly how the v2 report's rule ids ended up typed as a bare string, absent
# from `required`, while the runtime demanded them exactly.
# --------------------------------------------------------------------------- #
REPLAY_REPORT_SCHEMA = SCHEMA["$defs"]["sourceReplayReport"]
RECORD_ID_RULE_SCHEMA = SCHEMA["$defs"]["recordIdRule"]

REPLAY_VALIDATOR = Draft202012Validator(
    {**REPLAY_REPORT_SCHEMA, "$defs": SCHEMA["$defs"]})


def test_the_schema_pins_the_exact_v2_rule_ids():
    from direct import manifest_schema as MS
    assert (REPLAY_REPORT_SCHEMA["properties"]["replay_rule_id"]["const"]
            == MS.REPLAY_RULE_ID)
    assert (REPLAY_REPORT_SCHEMA["properties"]["completeness_rule_id"]["const"]
            == MS.COMPLETENESS_RULE_ID)


def test_the_schema_REQUIRES_every_field_the_runtime_requires():
    from direct import manifest_schema as MS
    missing = [k for k in MS.REPLAY_COMPLETENESS_KEYS
               if k not in REPLAY_REPORT_SCHEMA["required"]]
    assert not missing, f"the schema would validate a report the lane refuses: {missing}"


def test_the_schema_pins_the_compiled_record_id_rule_including_null_handling():
    props = RECORD_ID_RULE_SCHEMA["properties"]
    assert props["rule"]["const"] == record_id.RULE
    assert props["canonical_json"]["const"] == record_id.CANONICAL_JSON_RULE
    assert props["null_handling"]["const"] == record_id.NULL_HANDLING
    assert (props["identity_payload_fields"]["const"]
            == list(record_id.IDENTITY_PAYLOAD_FIELDS))


def _honest_report() -> dict:
    from direct import manifest_schema as MS
    return {
        "schema_version": MS.REPLAY_SCHEMA,
        "source_id": SOURCE_NAME,
        "source_sha256": "a" * 64,
        "source_record_table_sha256": "b" * 64,
        "verdict": "replayed",
        "n_records": 10, "n_replayed": 10, "n_failed": 0,
        "completeness_verdict": "complete",
        "n_scopes_determined": 8, "n_scopes_ambiguous": 2, "n_scopes_named": 10,
        "n_scopes_complete": 8, "n_scopes_incomplete": 0,
        "n_records_offset_proven": 10, "n_nontargeting_guides_cited": 0,
        "replay_rule_id": MS.REPLAY_RULE_ID,
        "completeness_rule_id": MS.COMPLETENESS_RULE_ID,
        # the SOURCE's own partition: the manifest's 8/2 split is only admissible
        # because the raw source independently determines exactly 8 and cannot
        # determine exactly 2
        "source_classification_rule_id": MS.SOURCE_CLASSIFICATION_RULE_ID,
        "n_scopes_source_determinable": 8,
        "n_scopes_source_non_determinable": 2,
        "n_scopes_downgraded": 0, "n_scopes_overclaimed": 0,
    }


def test_an_honest_v2_report_validates():
    REPLAY_VALIDATOR.validate(_honest_report())


@pytest.mark.parametrize("key", ["replay_rule_id", "completeness_rule_id"])
def test_the_schema_rejects_a_report_that_names_no_rule(key):
    report = _honest_report()
    report.pop(key)
    assert not REPLAY_VALIDATOR.is_valid(report)


@pytest.mark.parametrize("key", ["replay_rule_id", "completeness_rule_id"])
def test_the_schema_rejects_a_report_computed_under_a_FOREIGN_rule(key):
    report = _honest_report()
    report[key] = "spot.stage02.direct.replay_rule.v1"
    assert not REPLAY_VALIDATOR.is_valid(report)


def test_the_schema_rejects_a_rule_that_misdeclares_null_handling():
    rule = dict(record_id.RULE_METADATA,
                null_handling="nulls serialize as empty strings")
    validator = Draft202012Validator(
        {**RECORD_ID_RULE_SCHEMA, "$defs": SCHEMA["$defs"]})
    assert not validator.is_valid(rule)
    assert validator.is_valid(record_id.RULE_METADATA)
