"""Standalone-verifier PARITY: the defects the independent real-pair audit isolated.

The verifier had drifted from the contract it is supposed to check. Every drift below
was found by running it against the REAL canonical manifest/record pair, and each is
pinned here as a regression:

  1. the identity-method rule was applied to EVERY row, so the release's six genuinely
     ambiguous scopes — which carry no proof fields at all, because they prove nothing
     — were read as ``identity_method=None`` and refused. An ambiguous row obeys its
     CONTROLLED-NULL contract, not the determined-row proof rules.
  2. the record table was indexed with a dict comprehension, so a DUPLICATE record id
     silently kept the last and dropped the rest — a forged twin planted under an
     honest id would resolve as its honest sibling.
  3. record ids were BELIEVED, and each record's own ``source_sha256`` was never
     compared to its pinned source.
  4. the contributor map was keyed by a reduced ``(estimate_type, estimate_id,
     target_id)``, so evidence for one released scope could be read as evidence for
     another that merely shares a gene.
  5. strict replay proved each cited guide EXISTS at one kept row. Existence is not
     completeness: a contributor silently dropped from a scope leaves every hash
     right, every locator replaying — and the mask built from the wrong guide set.
"""
from __future__ import annotations

import contextlib
import copy
import io
import os

import pytest

from direct import identity, manifest as mf, record_id
from direct import verify_evidence as E, verify_rules as R, verify_run
from direct.run_screen import build_screen

from fixtures_evidence import (NON_TARGETING_GUIDES, SOURCE_NAME, kept_proof,
                               link_citations, manifest_doc, manifest_rows,
                               raw_source_rows, source_record_doc, source_records)
from fixtures_direct import default_specs
from fixtures_spec import CONDITION, TARGET_GENES

pytestmark = pytest.mark.filterwarnings("ignore")

SHA = "c" * 64
SOURCE_SHAS = {SOURCE_NAME: SHA}

SPECS = default_specs()
PROOF = kept_proof(raw_source_rows(SPECS))

DECOY_SYMBOL = "MTRNR2L4"
DECOY_ENSG = "ENSG00000232196"
ENSG_TARGET = TARGET_GENES[0]

# The verifier's own name for the re-derivation check. It names the proof explicitly,
# because binding the proof into the id is the whole difference from the superseded rule.
RECORD_ID_CHECK = ("every source record id re-derives from the record's own payload, "
                   "INCLUDING its complete offset/row proof")


def honest_rows() -> list[dict]:
    rows = manifest_rows(SPECS, SHA)
    link_citations(rows, source_records(rows, PROOF))
    return rows


def _doc(rows):
    doc = manifest_doc(rows, sources=[])
    doc["source_class"] = mf.SOURCE_CLASS_MARSON
    return doc


def failures(rows, records_fn=None, source_shas=SOURCE_SHAS) -> set:
    rep = verify_run.Report()
    verify_run.resolve_contributors(
        _doc(rows), source_record_doc(source_records(rows, PROOF), records_fn),
        source_shas, rep)
    return {name for name, _detail in rep.failures}


def contrib_map(rows, records_fn=None) -> dict:
    rep = verify_run.Report()
    out = verify_run.resolve_contributors(
        _doc(rows), source_record_doc(source_records(rows, PROOF), records_fn),
        SOURCE_SHAS, rep)
    assert not rep.failures, rep.failures
    return out


def verify(args, strict: bool) -> int:
    from direct.verify_run import main as verify_main
    argv = ["--run-dir", args.out_dir, "--inputs-root",
            os.path.dirname(args.selection)]
    if strict:
        argv.append("--strict-replay")
    with contextlib.redirect_stdout(io.StringIO()):
        return verify_main(argv)


def claim_complete(report: dict) -> dict:
    """The producer's report LIES about the half of the gate that would catch it.

    Existence still holds — every cited locator really does point at a kept row that
    says what the record says — so an existence-only report is TELLING THE TRUTH here.
    That is precisely why existence-only was never a gate.
    """
    return dict(report, verdict="replayed", n_failed=0,
                n_replayed=report["n_records"], failures=[],
                completeness_verdict="complete", n_scopes_incomplete=0,
                n_scopes_complete=report["n_scopes_determined"],
                n_records_offset_proven=report["n_records"],
                n_nontargeting_guides_cited=0, completeness_failures=[])


# --------------------------------------------------------------------------- #
# 1. The ambiguous row's CONTROLLED-NULL contract.
# --------------------------------------------------------------------------- #
def strip_proof_fields(rows: list[dict]) -> list[dict]:
    """The REAL release's shape: an ambiguous row carries no proof fields at all.

    The canonical adapter drops identity_method / source_id / source_sha256 from a row
    that proves nothing. The verifier used to stringify the missing method to ``'None'``
    and refuse the row as an inadmissible method.
    """
    out = copy.deepcopy(rows)
    for row in out:
        if row.get("evidence_state") == mf.AMBIGUOUS:
            for key in ("identity_method", "source_id", "source_sha256"):
                row.pop(key, None)
    return out


def test_an_ambiguous_row_may_omit_every_proof_field():
    rows = strip_proof_fields(honest_rows())
    assert any(r.get("evidence_state") == mf.AMBIGUOUS for r in rows)
    assert all("identity_method" not in r for r in rows
               if r.get("evidence_state") == mf.AMBIGUOUS)
    assert not failures(rows)          # it proves nothing, so it owes no proof


def test_the_runtime_loader_also_accepts_the_proofless_ambiguous_row(synthetic_run):
    """Generator and verifier must agree: this is the release's own row shape."""
    assert build_screen(synthetic_run(manifest_rows_fn=strip_proof_fields))["run_id"]


def test_an_ambiguous_row_still_may_not_cite_evidence():
    """Controlled null means NULL — not "unchecked"."""
    rows = strip_proof_fields(honest_rows())
    for row in rows:
        if row.get("evidence_state") == mf.AMBIGUOUS:
            row["source_record_id"] = record_id.RECORD_ID_PREFIX + "0" * 64
            break
    assert "no ambiguous row carries a guide or a citation" in failures(rows)


def test_an_ambiguous_row_may_not_name_an_unsupported_method():
    rows = copy.deepcopy(honest_rows())
    for row in rows:
        if row.get("evidence_state") == mf.AMBIGUOUS:
            row["identity_method"] = "author_supplied_contributor_table"
            break
    assert ("an ambiguous row that names an identity method names a supported one"
            in failures(rows))


def test_a_determined_row_still_owes_its_proof():
    rows = copy.deepcopy(honest_rows())
    for row in rows:
        if row.get("evidence_state") == mf.DETERMINED:
            row["identity_method"] = "author_supplied_contributor_table"
            break
    assert ("every determined contributor row uses an identity method the release "
            "actually supports for its source class") in failures(rows)


# --------------------------------------------------------------------------- #
# 2. A duplicate record id is REFUSED, never collapsed.
# --------------------------------------------------------------------------- #
def test_a_duplicate_record_id_is_refused_not_silently_collapsed():
    """The twin is a perfect forgery except for its guide. Indexing by id would keep
    exactly one of them — and which one is an implementation detail, not evidence."""
    def forge(records):
        twin = dict(records[0], guide_id="g-IMPOSTOR")
        return records + [twin]         # SAME source_record_id, different claim

    assert "source record ids are unique" in failures(honest_rows(), records_fn=forge)


# --------------------------------------------------------------------------- #
# 3. Record ids are RE-DERIVED, and each record pins its own source.
# --------------------------------------------------------------------------- #
def test_a_record_id_that_its_payload_does_not_derive_is_refused():
    def forge(records):
        out = copy.deepcopy(records)
        out[0]["source_record_id"] = record_id.RECORD_ID_PREFIX + "0" * 64
        return out

    assert (RECORD_ID_CHECK in failures(honest_rows(), records_fn=forge))


def test_a_record_whose_PROOF_moved_no_longer_derives_its_id():
    """The completeness proof is INSIDE the payload, so the verifier catches a moved
    offset array with the same rule that catches a moved guide id. Under the superseded
    rule the proof was outside the payload and this forgery was invisible."""
    def forge(records):
        out = copy.deepcopy(records)
        out[0]["pseudobulk_source_offsets"] = list(
            out[0]["pseudobulk_source_offsets"]) + [999]
        out[0]["pseudobulk_source_rows"] = list(
            out[0]["pseudobulk_source_rows"]) + ["fabricated|row"]
        return out

    assert (RECORD_ID_CHECK in failures(honest_rows(), records_fn=forge))


def test_a_record_that_does_not_pin_the_bytes_of_its_own_source_is_refused():
    """The citing row's hash was checked; the RECORD's own hash never was."""
    def forge(records):
        out = copy.deepcopy(records)
        out[0]["source_sha256"] = "d" * 64      # a source that was never pinned
        out[0]["source_record_id"] = E.derive_record_id(out[0])   # resealed
        return out

    assert ("every source record pins the bytes of the source it names"
            in failures(honest_rows(), records_fn=forge))


def test_the_verifier_derives_record_ids_independently_of_the_generator():
    """Two implementations of the compiled rule, agreeing on every record."""
    from direct.record_id import derive_record_id as generator_derive
    rows = honest_rows()
    records = source_records(rows, PROOF)
    assert records
    for rec in records:
        assert E.derive_record_id(rec) == generator_derive(rec) \
            == rec["source_record_id"]
        assert rec["source_record_id"].startswith(record_id.RECORD_ID_PREFIX)
        assert len(rec["source_record_id"]) == len(record_id.RECORD_ID_PREFIX) + 64


# --------------------------------------------------------------------------- #
# 4. The contributor map is keyed by the FULL released scope identity.
# --------------------------------------------------------------------------- #
def test_the_contributor_map_is_keyed_by_the_whole_released_scope():
    contrib = contrib_map(honest_rows())
    assert contrib, "the honest fixture must resolve some contributors"
    for scope in contrib:
        assert len(scope) == len(R.CONTRIB_KEY)

    rows = [r for r in honest_rows()
            if r["evidence_state"] == mf.DETERMINED and r.get("guide_id")]
    row = rows[0]
    assert R.scope_of(row) in contrib
    assert contrib[R.scope_of(row)]

    reduced = (row["estimate_type"], row["estimate_id"], row["target_id"])
    assert reduced not in contrib      # the reduced key is not a scope


@pytest.mark.parametrize("field,value", [
    ("released_estimate_id", "ENSG09999999999_StimX"),
    ("target_id_namespace", "gene_symbol"),
    ("target_symbol", "A_DIFFERENT_SYMBOL"),
    ("condition", "Rest"),
])
def test_a_scope_that_differs_in_any_identity_field_is_a_different_scope(field, value):
    """The reduced key collided a target's scope across conditions and release keys.

    Change ONE identity field and the evidence must land under a DIFFERENT key — so a
    row that agrees about the gene but not about the namespace it was named in, its
    symbol, or the condition can never be read as evidence for this scope.
    """
    rows = honest_rows()
    row = next(r for r in rows
               if r["evidence_state"] == mf.DETERMINED and r.get("guide_id"))
    honest_scope = R.scope_of(row)
    other_scope = R.scope_of(dict(row, **{field: value}))
    assert other_scope != honest_scope

    contrib = contrib_map(rows)
    assert honest_scope in contrib
    assert other_scope not in contrib


# --------------------------------------------------------------------------- #
# 5. STRICT replay proves COMPLETENESS, not merely existence.
# --------------------------------------------------------------------------- #
def drop_one_contributor(rows: list[dict]) -> list[dict]:
    """Silently drop ONE guide from a pooled scope that has two.

    Everything that REMAINS is true: every named guide is real, every citation resolves,
    every locator replays against a kept source row. The manifest is simply not the
    whole truth — and the mask is then built from the wrong guide set, which changes
    the score. The scope's declared n_guides is lowered to match, so the count
    cross-check cannot be what refuses it: only the SOURCE can.
    """
    out = copy.deepcopy(rows)
    pooled: dict[str, list[dict]] = {}
    for row in out:
        if row["evidence_state"] == mf.DETERMINED and row.get("guide_id"):
            pooled.setdefault(row["target_id"], []).append(row)
    victim = next(rs[0] for rs in pooled.values() if len(rs) > 1)
    for row in out:
        if row["target_id"] == victim["target_id"]:
            row["n_guides"] = len(pooled[victim["target_id"]]) - 1
    return [r for r in out if r is not victim]


def test_a_silently_dropped_contributor_survives_existence_and_dies_on_completeness(
        synthetic_run):
    """The exact blind spot of the superseded existence-only replay.

    The producer's report is existence-TRUE and completeness-FALSE. The default
    verifier reads the pinned report and is satisfied; only re-deriving completeness
    from the raw source sees the missing contributor.
    """
    args = synthetic_run(manifest_rows_fn=drop_one_contributor,
                         source_replay_fn=claim_complete)
    args.out_dir = build_screen(args)["out_dir"]

    assert verify(args, strict=False) == 0     # the report is believed...
    assert verify(args, strict=True) == 1      # ...the source is not


def test_a_dropped_contributor_with_an_HONEST_report_never_even_builds(synthetic_run):
    """Without the lie, the producer's own completeness check refuses it up front."""
    from direct.manifest import ManifestError

    with pytest.raises(ManifestError):
        build_screen(synthetic_run(manifest_rows_fn=drop_one_contributor))


def test_the_honest_run_passes_strict_completeness(synthetic_run):
    args = synthetic_run()
    args.out_dir = build_screen(args)["out_dir"]
    assert verify(args, strict=True) == 0


def test_a_non_targeting_guide_can_never_be_a_contributor(synthetic_run):
    """obs.guide_type is the source's own word for it. A control never contributed.

    The cited guide is REAL and its rows really were kept for the fit — it is simply a
    non-targeting control. Existence cannot tell the difference; only guide_type can.
    """
    def cite_a_control(rows):
        out = copy.deepcopy(rows)
        for row in out:
            if row["evidence_state"] == mf.DETERMINED and row.get("guide_id"):
                row["guide_id"] = NON_TARGETING_GUIDES[0]
                break
        return out

    args = synthetic_run(manifest_rows_fn=cite_a_control,
                         source_replay_fn=claim_complete)
    args.out_dir = build_screen(args)["out_dir"]
    assert verify(args, strict=True) == 1


# --------------------------------------------------------------------------- #
# 6. The verifier catches every CONTENT forgery the runtime catches.
# --------------------------------------------------------------------------- #
def verifier_failures(rows, records_fn=None):
    return failures(rows, records_fn=records_fn)


def records_for(rows):
    return source_records(rows, PROOF)


def mutate(rows, on_target, **fields):
    """Break ONE field on the pooled-main rows of ONE target."""
    out = copy.deepcopy(rows)
    hit = 0
    for row in out:
        if row["target_id"] == on_target:
            row.update(fields)
            hit += 1
    assert hit, f"the attack matched no row ({on_target})"
    return out


def forge_one(records, **fields):
    out = copy.deepcopy(records)
    for rec in out:
        if rec["target_id"] == ENSG_TARGET:
            rec.update(fields)
            return out
    raise AssertionError("the forge matched no record")


def forge_promoted_symbol_record(records):
    """A fabricated SYMBOL record that promoted its decoy ENSG release key."""
    out = copy.deepcopy(records)
    out[0].update({
        "released_estimate_id": f"{DECOY_ENSG}_{CONDITION}",
        "target_id": DECOY_SYMBOL,
        "target_id_namespace": identity.GENE_SYMBOL,
        "target_symbol": DECOY_SYMBOL,
        "target_ensembl": DECOY_ENSG,
    })
    return out


def test_the_verifier_passes_the_honest_pair():
    assert not verifier_failures(honest_rows())


def test_the_verifier_catches_the_release_key_promotion():
    rows = mutate(honest_rows(), DECOY_SYMBOL, target_ensembl=DECOY_ENSG)
    assert ("every contributor-manifest row carries an admissible released target "
            "identity") in verifier_failures(rows)


def test_the_verifier_catches_a_forged_record_identity():
    assert ("every source record carries an admissible released target identity"
            in verifier_failures(honest_rows(),
                                 records_fn=forge_promoted_symbol_record))


def test_the_verifier_catches_an_ambiguous_row_carrying_a_citation():
    rows = mutate(honest_rows(), ENSG_TARGET, evidence_state="ambiguous",
                  guide_id=None,
                  source_record_id=record_id.RECORD_ID_PREFIX + "3" * 64)
    assert ("no ambiguous row carries a guide or a citation"
            in verifier_failures(rows))


def test_the_verifier_catches_a_record_that_contradicts_its_citation():
    assert ("every determined contributor row resolves to a real source record"
            in verifier_failures(
                honest_rows(),
                records_fn=lambda recs: forge_one(recs,
                                                  target_symbol="WRONG_SYMBOL")))


def test_the_verifier_catches_a_duplicate_record_key():
    def forge(records):
        twin = dict(records[0])
        return records + [twin]

    assert ("source records are 1:1 on (estimate key, guide)"
            in verifier_failures(honest_rows(), records_fn=forge))


def test_the_verifier_catches_an_inadmissible_method_for_the_source_class():
    rows = mutate(honest_rows(), ENSG_TARGET,
                  identity_method="author_supplied_contributor_table")
    assert ("every determined contributor row uses an identity method the release "
            "actually supports for its source class") in verifier_failures(rows)


def test_the_verifier_reimplements_the_identity_rule_independently():
    """verify_rules restates the contract; it must not import the generator."""
    src = open(os.path.join(os.path.dirname(os.path.abspath(R.__file__)),
                            "verify_rules.py")).read()
    assert "from .identity" not in src and "import identity" not in src
    for row in honest_rows():
        assert R.identity_violation(row) is identity.identity_violation(row) is None
