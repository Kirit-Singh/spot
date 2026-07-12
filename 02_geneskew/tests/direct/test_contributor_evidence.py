"""Adversarial attacks on the contributor-evidence CONTRACT.

The manifest names a released target; the source-record table is the evidence that the
naming is real. Every attack breaks exactly ONE invariant and must be refused with
exactly ONE reason — a broad "it raised something" assertion would pass even if the
lane refused for an unrelated reason, and would not be a test of the contract.

THE IDENTITY RULE THIS FILE EXISTS FOR
--------------------------------------
A record's id is ``srcrec:sha256:`` + the FULL digest of a payload that INCLUDES the
complete offset/row proof. The superseded rule truncated the digest to 32 hex over a
payload that OMITTED the proof — so a producer could swap a record's offsets and row
names for a smaller or fabricated set and every id would still re-derive perfectly.
The id certified the claim while leaving the evidence for that claim free to move.

The consequence is a direction that cannot be reversed: a manifest row CANNOT mint the
id it cites, because it does not hold the proof the id is a hash of. So the fixtures
build source -> proof -> records -> ids -> citations, and a row can only resolve
against a record matching its ENTIRE released scope key and guide.

Three surfaces, all of which must agree:
  * the RUNTIME loader          (direct.manifest / direct.sources)
  * the WHOLE run               (build_screen, which loads both)
  * the STANDALONE verifier     (direct.verify_evidence, which reimplements the rules)
"""
from __future__ import annotations

import copy
import json
import os

import pytest
from direct import identity, record_id, sources
from direct import manifest as mf
from direct.manifest import ManifestError
from direct.run_screen import build_screen
from direct.sources import SourceRecordError
from fixtures_direct import default_specs
from fixtures_evidence import (
    SOURCE_NAME,
    kept_proof,
    link_citations,
    manifest_rows,
    raw_source_rows,
    source_record_doc,
    source_records,
)
from fixtures_spec import CONDITION, TARGET_GENES

pytestmark = pytest.mark.filterwarnings("ignore")

SHA = "c" * 64
SOURCE_SHAS = {SOURCE_NAME: SHA}

# The symbol scope whose RELEASE KEY carries a decoy ENSG belonging to another gene.
DECOY_SYMBOL = "MTRNR2L4"
DECOY_ENSG = "ENSG00000232196"
ENSG_TARGET = TARGET_GENES[0]

SPECS = default_specs()
# The TRUE proof, derived from the synthetic raw source without writing it: the same
# grouping replay.derive_from_source makes, computed here so the fixture never asks
# the code under test what the truth is.
PROOF = kept_proof(raw_source_rows(SPECS))


# --------------------------------------------------------------------------- #
# Helpers.
# --------------------------------------------------------------------------- #
def honest_rows() -> list[dict]:
    """Pooled-main rows with their citations minted the only way they can be."""
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


def mutate(rows: list[dict], on_target: str, **fields) -> list[dict]:
    """Break ONE field on the pooled-main rows of ONE target. The rest stays honest."""
    out = copy.deepcopy(rows)
    hit = 0
    for row in out:
        if row["target_id"] == on_target:
            row.update(fields)
            hit += 1
    assert hit, f"the attack matched no row ({on_target})"
    return out


def reseal(rows: list[dict]) -> list[dict]:
    """A CONSISTENT forger: after tampering it re-mints every record AND citation.

    Without this, a tampered row is caught merely because its citation went stale.
    Resealing makes the forgery internally perfect, so the refusal has to come from
    the pinned source or from a rule — never from the producer's sloppiness.
    """
    out = copy.deepcopy(rows)
    link_citations(out, records_for(out))
    return out


def first_determined(rows: list[dict]) -> dict:
    return next(r for r in rows if r["evidence_state"] == "determined")


def forge_one(records: list[dict], **fields) -> list[dict]:
    """Forge exactly ONE record — the first pooled record of the ENSG target.

    Exactly one: T0 contributes two guides, so rewriting both would collide them onto
    a single (key, guide) and trip the duplicate-key rule instead of the mismatch
    actually under test.
    """
    out = copy.deepcopy(records)
    for rec in out:
        if rec["target_id"] == ENSG_TARGET:
            rec.update(fields)
            return out
    raise AssertionError("the forge matched no record")


def forge_promoted_symbol_record(records: list[dict]) -> list[dict]:
    """A source record for a SYMBOL scope that promoted the decoy release key.

    Built by rewriting a real record rather than by mutating a symbol one: every symbol
    scope is ambiguous in the fixtures (no library guides), so it cites no evidence and
    therefore HAS no source record. This is what a fabricated symbol record would look
    like if one appeared.
    """
    out = copy.deepcopy(records)
    out[0].update({
        "released_estimate_id": f"{DECOY_ENSG}_{CONDITION}",
        "target_id": DECOY_SYMBOL,
        "target_id_namespace": identity.GENE_SYMBOL,
        "target_symbol": DECOY_SYMBOL,
        "target_ensembl": DECOY_ENSG,          # the promotion
    })
    return out


def refusal(rows: list[dict]) -> str:
    with pytest.raises(ManifestError) as exc:
        mf.validate_rows(rows)
    return str(exc.value)


# --------------------------------------------------------------------------- #
# RUNTIME: the released target identity on a manifest row.
# --------------------------------------------------------------------------- #
def test_a_missing_identity_field_is_refused():
    rows = copy.deepcopy(honest_rows())
    del rows[0]["target_id_namespace"]
    assert "missing keys ['target_id_namespace']" in refusal(rows)


@pytest.mark.parametrize("field", ["released_estimate_id", "target_id",
                                   "target_symbol"])
def test_a_null_key_component_is_refused(field):
    rows = mutate(honest_rows(), ENSG_TARGET, **{field: None})
    assert f"null key component {field}" in refusal(rows)


def test_a_namespace_outside_the_enum_is_refused():
    rows = mutate(honest_rows(), ENSG_TARGET, target_id_namespace="hgnc_symbol")
    assert identity.BAD_NAMESPACE in refusal(rows)


def test_an_ensembl_namespace_on_a_symbol_target_is_refused():
    """Relabel MTRNR2L4 as an accession namespace. Its target_id is not one."""
    rows = mutate(honest_rows(), DECOY_SYMBOL,
                  target_id_namespace=identity.ENSEMBL_GENE_ID)
    assert identity.ENSEMBL_NS_TARGET_ID_NOT_ENSEMBL in refusal(rows)


def test_a_symbol_namespace_on_an_ensembl_target_is_refused():
    rows = mutate(honest_rows(), ENSG_TARGET,
                  target_id_namespace=identity.GENE_SYMBOL, target_ensembl=None)
    assert identity.SYMBOL_NS_TARGET_ID_IS_ENSEMBL in refusal(rows)


@pytest.mark.parametrize("value", ["ENSG09999999999", None])
def test_a_target_ensembl_that_is_not_this_target_is_refused(value):
    """A well-formed accession is not the same thing as THIS target's accession.

    This is the equality JSON Schema cannot express (there is no $data): the schema
    accepts the row, the runtime does not.
    """
    rows = mutate(honest_rows(), ENSG_TARGET, target_ensembl=value)
    assert identity.ENSEMBL_NS_ENSEMBL_NOT_TARGET_ID in refusal(rows)


def test_promoting_the_ensg_looking_release_key_is_refused():
    """THE trap. The key is ENSG00000232196_StimX; the target is MTRNR2L4.

    The prefix is a real accession — of a DIFFERENT gene. Adopting it would attach the
    wrong gene to a mask and to every downstream drug identity.
    """
    rows = honest_rows()
    row = next(r for r in rows if r["target_id"] == DECOY_SYMBOL)
    assert row["released_estimate_id"] == f"{DECOY_ENSG}_{CONDITION}"
    assert row["target_ensembl"] is None                     # the honest state

    attacked = mutate(rows, DECOY_SYMBOL, target_ensembl=DECOY_ENSG)
    assert identity.SYMBOL_NS_ENSEMBL_NOT_NULL in refusal(attacked)


def test_the_symbol_scopes_survive_the_honest_manifest():
    """The contract must not achieve its refusals by dropping the hard rows."""
    rows = honest_rows()
    mf.validate_rows(rows)                                   # no exception
    symbols = {r["target_id"] for r in rows
               if r["target_id_namespace"] == identity.GENE_SYMBOL}
    assert symbols == {"MTRNR2L1", "MTRNR2L4", "MTRNR2L8", "OCLM"}
    assert all(r["target_ensembl"] is None for r in rows
               if r["target_id_namespace"] == identity.GENE_SYMBOL)


# --------------------------------------------------------------------------- #
# RUNTIME: THE EVIDENCE DOMAIN — global, all-condition, POOLED-MAIN only.
# --------------------------------------------------------------------------- #
def test_the_honest_manifest_is_pooled_main_only():
    rows = honest_rows()
    assert {r["estimate_type"] for r in rows} == {"main"}
    assert {r["estimate_id"] for r in rows} == {"main"}
    assert all(r["donor_pair"] is None for r in rows)


@pytest.mark.parametrize("fields,why", [
    ({"estimate_type": "guide", "estimate_id": "guide_1"}, "estimate_type="),
    ({"estimate_id": "guide_1"}, "estimate_id="),
    ({"estimate_type": "donor_pair", "estimate_id": "CE1_CE2",
      "donor_pair": "CE1_CE2"}, "estimate_type="),
    ({"donor_pair": "CE1_CE2"}, "donor_pair="),
])
def test_a_support_row_inside_the_pooled_main_manifest_is_refused(fields, why):
    """A by-guide or donor-pair row here is not extra evidence.

    It is a claim this pass has no method to check, and admitting it would let a
    support estimate acquire a mask and an evidence tier it never earned.
    """
    rows = mutate(honest_rows(), ENSG_TARGET, **fields)
    message = refusal(rows)
    assert why in message
    assert "pooled-main evidence domain" in message


# --------------------------------------------------------------------------- #
# RUNTIME: evidence_state and fabricated citations.
# --------------------------------------------------------------------------- #
def test_an_ambiguous_row_may_not_cite_evidence():
    """Resolution SKIPS an ambiguous row — so an unchecked citation is exactly where
    a fabrication would hide. It is refused rather than ignored."""
    rows = mutate(honest_rows(), ENSG_TARGET, evidence_state="ambiguous",
                  guide_id=None,
                  source_record_id=record_id.RECORD_ID_PREFIX + "0" * 64)
    assert "an ambiguous row cites source_record_id" in refusal(rows)


def test_an_ambiguous_row_may_not_name_a_guide():
    rows = mutate(honest_rows(), ENSG_TARGET, evidence_state="ambiguous",
                  source_record_id=None)
    assert "an ambiguous row names guide_id" in refusal(rows)


def test_the_honest_ambiguous_scopes_carry_no_guide_and_no_citation():
    """The release's own six-style scopes: they prove nothing and claim nothing."""
    ambiguous = [r for r in honest_rows() if r["evidence_state"] == "ambiguous"]
    assert ambiguous
    for row in ambiguous:
        assert row["guide_id"] is None
        assert row["source_record_id"] is None
        # a row that proves nothing owes no proof: the release omits these entirely
        assert "identity_method" not in row
        assert "source_sha256" not in row


def test_a_missing_evidence_state_is_not_implicitly_determined():
    rows = copy.deepcopy(honest_rows())
    del rows[0]["evidence_state"]
    assert "missing keys ['evidence_state']" in refusal(rows)


def test_an_inadmissible_identity_method_is_refused():
    """The Marson release ships NO author-supplied contributor table."""
    rows = mutate(honest_rows(), ENSG_TARGET,
                  identity_method="author_supplied_contributor_table")
    with pytest.raises(ManifestError) as exc:
        mf.validate_rows(rows, source_class=mf.SOURCE_CLASS_MARSON)
    assert "is NOT admissible for source_class" in str(exc.value)


def test_an_arbitrary_identity_method_is_refused():
    rows = mutate(honest_rows(), ENSG_TARGET, identity_method="trust_me")
    assert "is not one of" in refusal(rows)


# --------------------------------------------------------------------------- #
# RUNTIME: resolution is 1:1 on the whole key.
# --------------------------------------------------------------------------- #
def test_a_record_missing_an_identity_column_is_refused(tmp_path):
    def forge(records):
        out = copy.deepcopy(records)
        del out[0]["target_symbol"]
        return out

    with pytest.raises(SourceRecordError) as exc:
        table_for(tmp_path, honest_rows(), records_fn=forge)
    assert "missing columns ['target_symbol']" in str(exc.value)


def test_a_record_that_promotes_the_release_key_is_refused(tmp_path):
    with pytest.raises(SourceRecordError) as exc:
        table_for(tmp_path, honest_rows(),
                  records_fn=forge_promoted_symbol_record)
    assert identity.SYMBOL_NS_ENSEMBL_NOT_NULL in str(exc.value)


def test_an_identical_twin_record_is_refused(tmp_path):
    """Two records for one (key, guide) derive the SAME id, so they collide."""
    with pytest.raises(SourceRecordError) as exc:
        table_for(tmp_path, honest_rows(),
                  records_fn=lambda recs: recs + [dict(recs[0])])
    assert sources.DUPLICATE_RECORD_ID in str(exc.value)


@pytest.mark.parametrize("field,value,reason", [
    ("released_estimate_id", "ENSG09999999999_StimX", sources.RECORD_KEY_MISMATCH),
    ("target_symbol", "WRONG_SYMBOL", sources.RECORD_KEY_MISMATCH),
    ("condition", "Rest", sources.RECORD_KEY_MISMATCH),
    ("donor_pair", "CE9_CE8", sources.RECORD_KEY_MISMATCH),
    ("guide_id", "g-IMPOSTOR", sources.RECORD_GUIDE_MISMATCH),
    ("identity_method", "cell_level_assigned_guide_barcode_join",
     sources.RECORD_METHOD_MISMATCH),
    ("source_id", "some_other_source.h5ad", sources.RECORD_SOURCE_MISMATCH),
])
def test_resolve_refuses_a_record_that_contradicts_the_citation(field, value, reason):
    """Defence in depth, exercised directly on ``resolve_row``.

    Re-deriving the id makes this contradiction unreachable through ``load_table`` —
    the record would no longer match its own id. The per-field checks stay, and are
    tested here by handing ``resolve_row`` a table that could not exist, so a future
    change to the id rule cannot silently remove the only thing checking the key.
    """
    rows = honest_rows()
    row = first_determined(rows)
    rid = row["source_record_id"]
    forged = dict(next(rec for rec in records_for(rows)
                       if rec["source_record_id"] == rid), **{field: value})
    assert sources.resolve_row(row, {rid: forged}, SOURCE_SHAS) == reason


def test_a_citation_with_the_superseded_prefix_is_refused(tmp_path):
    rows = mutate(honest_rows(), ENSG_TARGET,
                  source_record_id="srec-" + "0" * 32)
    table = table_for(tmp_path, honest_rows())
    with pytest.raises(SourceRecordError) as exc:
        sources.resolve_manifest(rows, table, SOURCE_SHAS)
    assert sources.BAD_ID_SHAPE in str(exc.value)


def test_a_citation_naming_no_record_at_all_is_refused(tmp_path):
    rows = mutate(honest_rows(), ENSG_TARGET,
                  source_record_id=record_id.RECORD_ID_PREFIX + "b" * 64)
    table = table_for(tmp_path, honest_rows())
    with pytest.raises(SourceRecordError) as exc:
        sources.resolve_manifest(rows, table, SOURCE_SHAS)
    assert sources.RECORD_NOT_FOUND in str(exc.value)


def test_a_row_cannot_borrow_another_estimates_record(tmp_path):
    """The row cannot mint its citation, so borrowing is refused a different way:
    the record must match the row's ENTIRE released scope key and guide."""
    rows = honest_rows()
    mine = first_determined(rows)
    theirs = next(r for r in rows if r["evidence_state"] == "determined"
                  and r["target_id"] != mine["target_id"])
    attacked = copy.deepcopy(rows)
    for row in attacked:
        if row is not None and row.get("target_id") == mine["target_id"] \
                and row.get("guide_id") == mine["guide_id"]:
            row["source_record_id"] = theirs["source_record_id"]

    table = table_for(tmp_path, rows)
    with pytest.raises(SourceRecordError) as exc:
        sources.resolve_manifest(attacked, table, SOURCE_SHAS)
    assert sources.RECORD_KEY_MISMATCH in str(exc.value)


def test_a_source_hash_that_is_not_the_pinned_hash_is_refused(tmp_path):
    """A CONSISTENTLY forged producer: it re-mints every record and citation around
    the bad hash. Every id derives, the row and record agree perfectly — and it is
    still refused, because the hash is not the pinned source's bytes."""
    rows = reseal(mutate(honest_rows(), ENSG_TARGET, source_sha256="d" * 64))
    table = table_for(tmp_path, rows)
    with pytest.raises(SourceRecordError) as exc:
        sources.resolve_manifest(rows, table, SOURCE_SHAS)
    assert sources.RECORD_HASH_MISMATCH in str(exc.value)


def test_an_orphan_source_record_is_refused(tmp_path):
    """Evidence for a claim nobody made."""
    rows = honest_rows()
    keep = [r for r in rows if r["target_id"] != ENSG_TARGET]
    table = table_for(tmp_path, rows)            # records for ALL rows...
    with pytest.raises(SourceRecordError) as exc:
        sources.resolve_manifest(keep, table, SOURCE_SHAS)   # ...but fewer claims
    assert sources.ORPHAN_RECORD in str(exc.value)


def test_an_excluded_row_that_cites_evidence_is_still_checked(tmp_path):
    """included=false does not make a citation unfalsifiable."""
    rows = mutate(honest_rows(), ENSG_TARGET, included=False,
                  source_record_id=record_id.RECORD_ID_PREFIX + "1" * 64)
    table = table_for(tmp_path, honest_rows())
    with pytest.raises(SourceRecordError) as exc:
        sources.resolve_manifest(rows, table, SOURCE_SHAS)
    assert sources.RECORD_NOT_FOUND in str(exc.value)


def test_the_honest_pair_resolves(tmp_path):
    rows = honest_rows()
    table = table_for(tmp_path, rows)
    out = sources.resolve_manifest(rows, table, SOURCE_SHAS)
    assert out["status"] == sources.RESOLVED
    assert out["n_determined_rows_resolved"] == len(table) > 0


# --------------------------------------------------------------------------- #
# THE WHOLE RUN.
# --------------------------------------------------------------------------- #
def test_a_renamed_target_symbol_is_not_the_released_scope(synthetic_run):
    """An ambiguous row cites nothing, so ONLY scope coverage binds its identity."""
    def attack(rows):
        return [dict(r, target_symbol="IMPOSTOR") if r["target_id"] == ENSG_TARGET
                else r for r in rows]

    with pytest.raises(ManifestError, match="does not contain"):
        build_screen(synthetic_run(manifest_rows_fn=attack))


def test_a_forged_evidence_table_is_refused_on_its_CONTENT(synthetic_run):
    """The forgery is pinned HONESTLY — its hash is correct. The refusal must come
    from what it says, not from a hash mismatch."""
    with pytest.raises(SourceRecordError, match=sources.RECORD_ID_NOT_DERIVED):
        build_screen(synthetic_run(
            source_records_fn=lambda recs: forge_one(recs, guide_id="g-IMPOSTOR")))


def test_the_honest_run_still_builds(synthetic_run):
    result = build_screen(synthetic_run())
    assert result["run_id"]


def test_the_honest_run_records_the_source_replay_in_its_provenance(synthetic_run):
    result = build_screen(synthetic_run())
    prov = json.load(open(os.path.join(result["out_dir"], "provenance.json")))
    replay = prov["run_binding"]["guide_manifest"]["source_replay"]
    assert replay["status"] == "replayed"
    assert replay["n_records_replayed"] > 0
    # the COMPLETENESS half of the gate is bound into the run, not just existence
    assert replay["completeness_verdict"] == "complete"
    assert replay["n_scopes_incomplete"] == 0
    assert replay["n_nontargeting_guides_cited"] == 0
    assert replay["n_records_offset_proven"] == replay["n_records_replayed"]
    assert replay["evidence_columns"] == ["guide_id", "perturbed_gene_id",
                                          "culture_condition", "keep_for_DE",
                                          "guide_type"]
