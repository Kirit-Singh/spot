"""THE record-identity rule, and the completeness proof it binds.

The superseded rule minted ``srec-`` + a 32-hex truncation of a payload that OMITTED
``pseudobulk_source_offsets`` / ``pseudobulk_source_rows``. It failed on three counts,
and the third is the dangerous one: the all-offset completeness proof was never bound
into the record's identity, so a producer could swap a record's offsets and row names
for a different, smaller or fabricated set and EVERY id would still re-derive perfectly.
The id certified the claim while leaving the evidence for that claim free to move.

The compiled rule is

    source_record_id = 'srcrec:sha256:' + sha256( canonical_json(identity_payload) )

over the FULL identity payload, offsets and row names included. Everything below is one
attack on one clause of it: the shape of the id, the derivation of the id, the
well-formedness of the proof the id hashes, and the table's own declaration of the rule
— which is machine-compared against the compiled one, because a rule nobody checks is
documentation rather than a contract.

An emitted table and a runtime that agree with each other under the same obsolete
algorithm have proved nothing.
"""
from __future__ import annotations

import copy
import json
import os

import pytest

from direct import identity, record_id, sources
from direct.sources import SourceRecordError

from fixtures_evidence import (kept_proof, link_citations, manifest_rows,
                               raw_source_rows, source_record_doc, source_records)
from fixtures_direct import default_specs
from fixtures_spec import CONDITION, TARGET_GENES

pytestmark = pytest.mark.filterwarnings("ignore")

SHA = "c" * 64
DECOY_SYMBOL = "MTRNR2L4"
DECOY_ENSG = "ENSG00000232196"
ENSG_TARGET = TARGET_GENES[0]

SPECS = default_specs()
PROOF = kept_proof(raw_source_rows(SPECS))


def honest_rows() -> list[dict]:
    rows = manifest_rows(SPECS, SHA)
    link_citations(rows, source_records(rows, PROOF))
    return rows


def records_for(rows: list[dict]) -> list[dict]:
    return source_records(rows, PROOF)


def table_for(tmp_path, rows, records_fn=None) -> dict:
    path = os.path.join(str(tmp_path), "records.json")
    with open(path, "w") as fh:
        json.dump(source_record_doc(records_for(rows), records_fn), fh)
    return sources.load_table(path)


def forge_one(records: list[dict], **fields) -> list[dict]:
    """Forge exactly ONE record — the first pooled record of the ENSG target.

    Exactly one: T0 contributes two guides, so rewriting both would collide them onto a
    single (key, guide) and trip the duplicate-key rule instead of the mismatch under
    test.
    """
    out = copy.deepcopy(records)
    for rec in out:
        if rec["target_id"] == ENSG_TARGET:
            rec.update(fields)
            return out
    raise AssertionError("the forge matched no record")



# --------------------------------------------------------------------------- #
# RUNTIME: the record id BINDS the completeness proof.
# --------------------------------------------------------------------------- #
def test_the_honest_ids_are_full_srcrec_sha256(tmp_path):
    table = table_for(tmp_path, honest_rows())
    assert table
    for rid, rec in table.items():
        assert rid.startswith("srcrec:sha256:")
        assert len(rid) == len("srcrec:sha256:") + 64
        assert record_id.id_shape_violation(rid) is None
        assert rid == record_id.derive_record_id(rec)
        # and the proof it binds is really there
        assert rec["pseudobulk_source_offsets"]
        assert len(rec["pseudobulk_source_rows"]) == \
            len(rec["pseudobulk_source_offsets"])
        assert rec["source_row_index"] in rec["pseudobulk_source_offsets"]


@pytest.mark.parametrize("bad_id", [
    "srec-" + "0" * 32,                                   # the SUPERSEDED rule
    record_id.RECORD_ID_PREFIX + "0" * 32,                # a TRUNCATED digest
    record_id.RECORD_ID_PREFIX + "Z" * 64,                # not lowercase hex
    "0" * 64,                                             # no prefix at all
])
def test_a_record_id_that_is_not_the_compiled_shape_is_refused(tmp_path, bad_id):
    with pytest.raises(SourceRecordError) as exc:
        table_for(tmp_path, honest_rows(),
                  records_fn=lambda recs: forge_one(recs, source_record_id=bad_id))
    assert sources.BAD_ID_SHAPE in str(exc.value)


def test_a_hand_picked_but_well_shaped_id_is_refused(tmp_path):
    """The id is a computation over the payload, not a name the producer chooses."""
    with pytest.raises(SourceRecordError) as exc:
        table_for(tmp_path, honest_rows(),
                  records_fn=lambda recs: forge_one(
                      recs, source_record_id=record_id.RECORD_ID_PREFIX + "a" * 64))
    assert sources.RECORD_ID_NOT_DERIVED in str(exc.value)


@pytest.mark.parametrize("field,value", [
    ("released_estimate_id", "ENSG09999999999_StimX"),
    ("target_symbol", "WRONG_SYMBOL"),
    ("condition", "Rest"),
    ("donor_pair", "CE9_CE8"),
    ("guide_id", "g-IMPOSTOR"),
    ("identity_method", "cell_level_assigned_guide_barcode_join"),
    ("source_id", "some_other_source.h5ad"),
    ("source_sha256", "d" * 64),
    # THE PROOF IS IN THE PAYLOAD. Under the superseded rule these two were NOT, so a
    # record's evidence could be swapped for a smaller or fabricated set and every id
    # would still derive. Now they cannot move without re-keying the record.
    # (0 stays in the offsets so the LOCATOR check passes and the ID is what refuses.)
    ("pseudobulk_source_offsets", [0, 4]),
    ("pseudobulk_source_rows", ["some|other|row|d1", "some|other|row|d2"]),
])
def test_a_forged_record_no_longer_matches_its_own_id(tmp_path, field, value):
    """Every payload field is inside the derived id, so forging ANY of them breaks it.

    This is what binding the proof buys: a record cannot be quietly edited to say
    something else — about the estimate, OR about which rows it stands on.
    """
    with pytest.raises(SourceRecordError) as exc:
        table_for(tmp_path, honest_rows(),
                  records_fn=lambda recs: forge_one(recs, **{field: value}))
    assert sources.RECORD_ID_NOT_DERIVED in str(exc.value)


def test_swapping_the_proof_for_another_records_proof_breaks_the_id(tmp_path):
    """The offsets of a REAL contributor, moved onto a different record.

    Every offset is a genuine kept row, the arrays are well formed, the record's
    identity is untouched — and the id still dies, because the id is a hash OF the
    proof. Under the superseded rule this forgery was invisible.
    """
    def forge(records):
        out = copy.deepcopy(records)
        donor = next(r for r in out if r["target_id"] != ENSG_TARGET)
        for rec in out:
            if rec["target_id"] == ENSG_TARGET:
                rec["pseudobulk_source_offsets"] = list(
                    donor["pseudobulk_source_offsets"])
                rec["pseudobulk_source_rows"] = list(donor["pseudobulk_source_rows"])
                rec["source_row_index"] = donor["source_row_index"]
                return out
        raise AssertionError("no record to forge")

    with pytest.raises(SourceRecordError) as exc:
        table_for(tmp_path, honest_rows(), records_fn=forge)
    assert sources.RECORD_ID_NOT_DERIVED in str(exc.value)


# --------------------------------------------------------------------------- #
# RUNTIME: the offset proof must BE a proof (checked before the id is derived).
# --------------------------------------------------------------------------- #
def _reforge_proof(**proof_fields):
    """Rewrite one record's proof AND re-key it, so the id can never be the refusal."""
    def forge(records):
        out = forge_one(records, **proof_fields)
        for rec in out:
            if rec["target_id"] == ENSG_TARGET:
                try:
                    rec["source_record_id"] = record_id.derive_record_id(rec)
                except record_id.RecordIdError:
                    pass          # a malformed proof cannot even be hashed
                break
        return out
    return forge


@pytest.mark.parametrize("fields,reason", [
    # MISSING: a record with no offsets claims a contributor it never showed rows for
    ({"pseudobulk_source_offsets": [], "pseudobulk_source_rows": []},
     sources.BAD_OFFSET_PROOF),
    # SWAPPED order: the proof's ORDER is part of the hashed identity
    ({"pseudobulk_source_offsets": [2, 0]}, sources.BAD_OFFSET_PROOF),
    # DUPLICATE: the same raw row cannot be counted twice
    ({"pseudobulk_source_offsets": [0, 0]}, sources.BAD_OFFSET_PROOF),
    # a negative offset is not a row index
    ({"pseudobulk_source_offsets": [-1, 2]}, sources.BAD_OFFSET_PROOF),
    # EXTRA row name: one name per offset, or the arrays do not describe each other
    ({"pseudobulk_source_rows": ["a", "b", "c"]}, sources.BAD_ROW_PROOF),
    # MISSING row name
    ({"pseudobulk_source_rows": ["a"]}, sources.BAD_ROW_PROOF),
])
def test_a_malformed_offset_proof_is_refused(tmp_path, fields, reason):
    with pytest.raises(SourceRecordError) as exc:
        table_for(tmp_path, honest_rows(), records_fn=_reforge_proof(**fields))
    assert reason in str(exc.value)


def test_a_locator_outside_the_records_own_offsets_is_refused(tmp_path):
    """The locator is one OF the kept rows, or it is pointing somewhere else."""
    with pytest.raises(SourceRecordError) as exc:
        table_for(tmp_path, honest_rows(),
                  records_fn=_reforge_proof(source_row_index=999))
    assert sources.LOCATOR_NOT_IN_PROOF in str(exc.value)


def test_a_record_missing_the_proof_columns_entirely_is_refused(tmp_path):
    def forge(records):
        out = copy.deepcopy(records)
        for field in ("pseudobulk_source_offsets", "pseudobulk_source_rows"):
            del out[0][field]
        return out

    with pytest.raises(SourceRecordError) as exc:
        table_for(tmp_path, honest_rows(), records_fn=forge)
    assert "missing columns" in str(exc.value)


# --------------------------------------------------------------------------- #
# RUNTIME: the table must DECLARE the rule the verifier compiles.
# --------------------------------------------------------------------------- #
def test_a_table_declaring_a_different_id_rule_is_refused(tmp_path):
    """A rule nobody checks is documentation, not a contract."""
    doc = source_record_doc(records_for(honest_rows()))
    doc[record_id.RULE_METADATA_KEY]["rule"] = "srec- + sha256(payload)[:32]"
    path = os.path.join(str(tmp_path), "records.json")
    with open(path, "w") as fh:
        json.dump(doc, fh)
    with pytest.raises(SourceRecordError) as exc:
        sources.load_table(path)
    assert sources.RULE_METADATA_MISMATCH in str(exc.value)


def test_a_table_that_drops_the_proof_from_its_declared_payload_is_refused(tmp_path):
    """THE drift that mattered: the payload field list is what decides whether the
    completeness proof is bound into the id at all."""
    doc = source_record_doc(records_for(honest_rows()))
    doc[record_id.RULE_METADATA_KEY]["identity_payload_fields"] = [
        f for f in record_id.IDENTITY_PAYLOAD_FIELDS
        if f not in record_id.PROOF_FIELDS]
    path = os.path.join(str(tmp_path), "records.json")
    with open(path, "w") as fh:
        json.dump(doc, fh)
    with pytest.raises(SourceRecordError) as exc:
        sources.load_table(path)
    assert sources.RULE_METADATA_MISMATCH in str(exc.value)


@pytest.mark.parametrize("schema", [
    "spot.stage02_source_records.v1",
    "spot.stage02_source_records.target_id_proposal.v1",
])
def test_a_superseded_source_record_schema_is_never_grandfathered(tmp_path, schema):
    doc = source_record_doc(records_for(honest_rows()))
    doc["schema_version"] = schema
    path = os.path.join(str(tmp_path), "records.json")
    with open(path, "w") as fh:
        json.dump(doc, fh)
    with pytest.raises(SourceRecordError) as exc:
        sources.load_table(path)
    assert "SUPERSEDED" in str(exc.value)

