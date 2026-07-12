"""The contributing-guide contract: prove the guides, or refuse the estimate.

Guide identity has exactly ONE source — an explicit contributor manifest. There is no
alphanumeric rule and no suffix rule anywhere in the lane, so these tests assert what
the lane does with a manifest, and what it does without one (nothing).

TWO retired behaviours are pinned here as retired, because both were wrong in the same
way — they let a SUPPORT object's metadata decide a POOLED estimate's fate:

  * the slot-contradiction gate refused a whole target when the released guide slots
    disagreed with the pooled ``n_guides``. Measured against the release that rule
    would have refused 6,707 of 33,374 targets, on the strength of a field the pooled
    fit never depended on;
  * support ``n_guides`` was read as each estimate's own contributor count. It is a
    COPY of the pooled count (59,414/59,414 guide rows; 29,279/29,279 donor rows), so
    the "contradiction" it produced was largely an artefact of reading a copy as an
    independent witness.

The pooled estimate now resolves from its OWN manifest scope and its OWN n_guides, and
support resolves to an explicit unavailable state — never to a borrowed pooled
contributor set, and never to a guide guessed from a slot name.
"""
import pytest

from direct import domain, guides
from direct.guides import Estimate

COND = "StimX"
T = "ENSG00000000200"
SYM = "SYM00"
SHA = "a" * 64


def _rows(target, guide_ids):
    return {target: [{"sgRNA": g, "target_gene_id": target} for g in guide_ids]}


def _lib(guide_ids, target=T):
    return guides.build_library(_rows(target, guide_ids))


def _est(kind, eid, n_guides, **kw):
    """One released estimate, carrying the WHOLE released target identity."""
    return Estimate(estimate_type=kind, estimate_id=eid,
                    released_estimate_id=f"{T}_{COND}", target_id=T,
                    target_ensembl=T, condition=COND, n_guides=n_guides,
                    target_id_namespace="ensembl_gene_id", target_symbol=SYM,
                    released_target_ensembl=T, **kw)


def _manifest(guide_ids, estimate_id="main", kind=guides.MAIN, donor_pair=None,
              **extra):
    """A proven manifest scope: full identity + identity_method + source_sha256.

    The join is on the ENTIRE released scope, so every row carries the whole identity.
    A row that agrees about the gene but renames its symbol, or moves it to another
    namespace, is evidence for a scope it does not describe.
    """
    return guides.build_manifest_index([
        dict({"estimate_type": kind, "estimate_id": estimate_id,
              "released_estimate_id": f"{T}_{COND}", "target_id": T,
              "target_id_namespace": "ensembl_gene_id", "target_symbol": SYM,
              "target_ensembl": T,
              "condition": COND, "donor_pair": donor_pair,
              "guide_id": g, "evidence_state": "determined",
              "identity_method": "released_per_guide_identity_column",
              "source_sha256": SHA}, **extra)
        for g in guide_ids])


# --------------------------------------------------------------------------- #
# There is no inference path.
# --------------------------------------------------------------------------- #
def test_without_a_manifest_the_pooled_estimate_can_never_resolve():
    out = guides.resolve(_est(guides.MAIN, "main", 2.0), _lib(["g-1", "g-2"]),
                         manifest_index=None)
    assert out.status == guides.UNRESOLVED
    assert out.reason == guides.NO_CONTRIBUTOR_MANIFEST
    assert out.guide_ids == ()


def test_the_lane_never_maps_a_slot_by_its_name():
    """The manifest may name ANY guide; the alphanumeric rank proves nothing.

    guide_1 is proven to be the alphanumerically LAST library guide. A lane that read
    the published slot rank as identity would have picked g-alpha.
    """
    lib = _lib(["g-alpha", "g-omega"])
    out = guides.resolve(_est(guides.MAIN, "main", 1.0), lib,
                         _manifest(["g-omega"]))
    assert out.resolved
    assert out.guide_ids == ("g-omega",)      # not "g-alpha"
    assert out.source == "manifest"


# --------------------------------------------------------------------------- #
# SUPPORT IS OUT OF DOMAIN. It gets no contributors, whatever the manifest says.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("est", [
    _est(guides.GUIDE, "guide_1", 2.0),
    _est(guides.DONOR_PAIR, "CE1_CE2", 2.0, donor_pair="CE1_CE2"),
])
def test_a_support_estimate_is_explicitly_unavailable(est):
    """No mask, no contributors, no borrowed pooled set — and it says WHY."""
    out = guides.resolve(est, _lib(["g-1", "g-2"]), _manifest(["g-1", "g-2"]))
    assert out.status == guides.UNRESOLVED
    assert out.reason == domain.SUPPORT_UNAVAILABLE
    assert out.guide_ids == ()


def test_a_support_estimate_cannot_resolve_even_from_its_own_manifest_scope():
    """Handing support the very rows it would need changes nothing.

    The refusal is a property of the DOMAIN, not of the evidence being missing: this
    pass has no method to prove which guide contributed to a slot, so a row claiming
    to is not admitted just because it exists.
    """
    idx = _manifest(["g-1"], estimate_id="guide_1", kind=guides.GUIDE)
    out = guides.resolve(_est(guides.GUIDE, "guide_1", 1.0), _lib(["g-1", "g-2"]),
                         idx)
    assert out.reason == domain.SUPPORT_UNAVAILABLE


def test_support_metadata_can_never_refuse_the_pooled_estimate():
    """THE RETIRED SLOT-CONTRADICTION GATE.

    The observed pattern: the pooled DE declares n_guides = 1, the library maps exactly
    one guide, and by_guide still ships TWO guide-level DEs. The old rule read that as
    the release contradicting itself and refused the target outright — 6,707 of 33,374
    of them. But the disagreement is with a support object's COPIED metadata, and a
    copy is not an independent witness. The pooled estimate stands on its own evidence.
    """
    out = guides.resolve(_est(guides.MAIN, "main", 1.0), _lib(["g-1"]),
                         _manifest(["g-1"]))
    assert out.resolved
    assert out.guide_ids == ("g-1",)
    assert not hasattr(guides, "SLOT_COUNT_CONTRADICTS_N_GUIDES")
    assert not hasattr(guides, "slot_contradiction")
    assert not hasattr(guides, "SlotEvidence")


def test_resolve_does_not_accept_a_support_evidence_argument():
    """There is no 4th rung. ``resolve`` takes the estimate, the library, the manifest.

    A signature that still accepted released support evidence would be a place for it
    to re-enter the pooled decision by the back door.
    """
    with pytest.raises(TypeError):
        guides.resolve(_est(guides.MAIN, "main", 2.0), _lib(["g-1", "g-2"]),
                       _manifest(["g-1", "g-2"]), object())


# --------------------------------------------------------------------------- #
# Library indexing (mask lookup only -- never identity).
# --------------------------------------------------------------------------- #
def test_duplicate_guide_mapping_makes_the_estimate_unresolved():
    lib = guides.build_library({T: [
        {"sgRNA": "g-1", "target_gene_id": T},
        {"sgRNA": "g-1", "target_gene_id": T},   # duplicate id
        {"sgRNA": "g-2", "target_gene_id": T},
    ]})
    assert lib[T].duplicate_guide_ids == ("g-1",)
    out = guides.resolve(_est(guides.MAIN, "main", 2.0), lib,
                         _manifest(["g-1", "g-2"]))
    assert out.status == guides.UNRESOLVED
    assert out.reason == guides.DUPLICATE_GUIDE_IN_LIBRARY


def test_a_manifest_guide_absent_from_the_library_is_unresolved():
    out = guides.resolve(_est(guides.MAIN, "main", 2.0), _lib(["g-1", "g-2"]),
                         _manifest(["g-1", "g-9"]))
    assert out.reason == guides.MANIFEST_GUIDE_NOT_IN_LIBRARY


def test_a_target_absent_from_the_library_is_unresolved():
    out = guides.resolve(_est(guides.MAIN, "main", 1.0), _lib([], target="other"),
                         _manifest(["g-1"]))
    assert out.reason == guides.TARGET_ABSENT_FROM_LIBRARY


def test_a_target_with_no_resolved_ensembl_id_is_never_masked_by_its_symbol():
    """A gene_symbol scope cannot be joined to the Ensembl-keyed sgRNA library."""
    est = Estimate(estimate_type=guides.MAIN, estimate_id="main",
                   released_estimate_id="ENSG00000256618_StimX", target_id="MTRNR2L1",
                   target_ensembl=None, condition=COND, n_guides=2.0,
                   target_id_namespace="gene_symbol", target_symbol="MTRNR2L1",
                   released_target_ensembl=None)
    out = guides.resolve(est, _lib(["g-1", "g-2"]), _manifest(["g-1", "g-2"]))
    assert out.reason == guides.UNRESOLVED_TARGET_IDENTITY


# --------------------------------------------------------------------------- #
# The manifest is the authoritative -- and only -- identity path.
# --------------------------------------------------------------------------- #
def test_the_manifest_names_the_contributing_subset_no_rule_could_know():
    """Three library guides, two contributed. Only the manifest can say which."""
    out = guides.resolve(_est(guides.MAIN, "main", 2.0), _lib(["g-1", "g-2", "g-3"]),
                         _manifest(["g-1", "g-3"]))
    assert out.resolved
    assert out.guide_ids == ("g-1", "g-3")
    assert "g-2" not in out.guide_ids          # the unused guide cannot mask


def test_an_estimate_absent_from_the_manifest_is_unresolved():
    out = guides.resolve(_est(guides.MAIN, "main", 2.0), _lib(["g-1", "g-2"]),
                         guides.build_manifest_index([]))
    assert out.reason == guides.ABSENT_FROM_MANIFEST


def test_a_manifest_row_for_another_scope_is_not_evidence_for_this_one():
    """The join is the WHOLE identity. A renamed symbol is a different scope."""
    idx = _manifest(["g-1", "g-2"], target_symbol="SOMETHING_ELSE")
    out = guides.resolve(_est(guides.MAIN, "main", 2.0), _lib(["g-1", "g-2"]), idx)
    assert out.reason == guides.ABSENT_FROM_MANIFEST


def test_an_ambiguous_identity_stays_unavailable():
    ambiguous = guides.build_manifest_index([{
        "estimate_type": "main", "estimate_id": "main",
        "released_estimate_id": f"{T}_{COND}", "target_id": T,
        "target_id_namespace": "ensembl_gene_id", "target_symbol": SYM,
        "target_ensembl": T,
        "condition": COND, "donor_pair": None, "guide_id": None,
        "evidence_state": "ambiguous", "source_record_id": None}])
    out = guides.resolve(_est(guides.MAIN, "main", 2.0), _lib(["g-1", "g-2"]),
                         ambiguous)
    assert out.status == guides.UNRESOLVED
    assert out.reason == guides.MANIFEST_EVIDENCE_AMBIGUOUS
    assert out.guide_ids == ()                 # never rounded to a guess


def test_an_unproven_row_is_not_a_proof():
    """A determined row must carry its source and its method."""
    for missing in ("identity_method", "source_sha256"):
        idx = _manifest(["g-1", "g-2"], **{missing: None})
        out = guides.resolve(_est(guides.MAIN, "main", 2.0), _lib(["g-1", "g-2"]),
                             idx)
        assert out.reason == guides.MANIFEST_ROW_UNPROVEN, missing


def test_manifest_guides_must_be_distinct():
    out = guides.resolve(_est(guides.MAIN, "main", 2.0), _lib(["g-1", "g-2"]),
                         _manifest(["g-1", "g-1"]))
    assert out.reason == guides.MANIFEST_DUPLICATE_GUIDE


# --------------------------------------------------------------------------- #
# Cross-checks against the POOLED estimate's own obs fields -- never a support copy.
# --------------------------------------------------------------------------- #
def test_a_manifest_count_disagreeing_with_the_pooled_fit_is_unresolved():
    # the pooled fit says two guides contributed; the manifest names one
    out = guides.resolve(_est(guides.MAIN, "main", 2.0), _lib(["g-1", "g-2"]),
                         _manifest(["g-1"]))
    assert out.reason == guides.MANIFEST_COUNT_DISAGREES


def test_an_excluded_guide_is_not_a_contributor():
    out = guides.resolve(_est(guides.MAIN, "main", 2.0), _lib(["g-1", "g-2"]),
                         _manifest(["g-1", "g-2"], included=False))
    assert out.reason == guides.MANIFEST_GUIDE_EXCLUDED


def test_manifest_cell_counts_are_cross_checked_when_the_source_has_them():
    lib = _lib(["g-1", "g-2"])
    est = Estimate(estimate_type=guides.MAIN, estimate_id="main",
                   released_estimate_id=f"{T}_{COND}", target_id=T,
                   target_ensembl=T, condition=COND, n_guides=2.0, n_cells=100.0,
                   target_id_namespace="ensembl_gene_id", target_symbol=SYM,
                   released_target_ensembl=T)
    good = _manifest(["g-1", "g-2"], n_cells=50)        # halves sum to the total
    assert guides.resolve(est, lib, good).resolved
    bad = _manifest(["g-1", "g-2"], n_cells=999)
    assert guides.resolve(est, lib, bad).reason == guides.MANIFEST_CELLS_DISAGREE


def test_a_missing_pooled_n_guides_is_unresolved():
    out = guides.resolve(_est(guides.MAIN, "main", None), _lib(["g-1", "g-2"]),
                         _manifest(["g-1", "g-2"]))
    assert out.reason == guides.N_GUIDES_MISSING


# --------------------------------------------------------------------------- #
# Emitted contract rows.
# --------------------------------------------------------------------------- #
def test_contributor_rows_emit_one_row_per_guide_and_one_for_a_refusal():
    lib = _lib(["g-1", "g-2"])
    est = _est(guides.MAIN, "main", 2.0)
    rows = guides.contributor_rows(
        est, guides.resolve(est, lib, _manifest(["g-1", "g-2"])))
    assert [r["guide_id"] for r in rows] == ["g-1", "g-2"]
    assert {r["contributor_status"] for r in rows} == {"resolved"}

    refused = guides.contributor_rows(est, guides.resolve(est, lib, None))
    assert len(refused) == 1
    assert refused[0]["guide_id"] is None
    assert refused[0]["contributor_unresolved_reason"] == \
        guides.NO_CONTRIBUTOR_MANIFEST


def test_a_refused_support_estimate_still_emits_its_row_and_its_reason():
    """A silently absent estimate reads as 'the release does not ship it'."""
    est = _est(guides.DONOR_PAIR, "CE1_CE2", 2.0, donor_pair="CE1_CE2")
    rows = guides.contributor_rows(est, guides.resolve(est, _lib(["g-1"]), None))
    assert len(rows) == 1
    assert rows[0]["guide_id"] is None
    assert rows[0]["contributor_unresolved_reason"] == domain.SUPPORT_UNAVAILABLE
    assert (rows[0]["estimate_type"], rows[0]["donor_pair"]) == \
        ("donor_pair", "CE1_CE2")
