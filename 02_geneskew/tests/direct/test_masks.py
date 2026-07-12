"""Masks belong to ONE estimate and are built only from its contributing guides.

Only the pooled-main estimate has contributor evidence in this pass, so only it can be
masked. A guide-slot or donor-pair estimate is explicitly unavailable and gets NO mask
— never the pooled one borrowed sideways, and never a silently empty one, which would
read as "nothing needed masking" when the truth is "we never knew what to mask".
"""
from direct import domain, guides, masks
from direct.guides import Estimate

COND = "StimX"
T = "ENSG00000000200"
SYM = "SYM00"
NEIGHBOR_OF_G1 = "ENSG00000000002"
NEIGHBOR_OF_G2 = "ENSG00000000003"
NEIGHBOR_OF_G3 = "ENSG00000000777"
OFFTARGET = "ENSG00000000099"


def _row(sg, neighbors, alt_align=None, offtarget=None):
    return {
        "sgRNA": sg,
        "target_gene_id": T,
        "distance_to_closest_target_tss": 40.0,
        "nearby_gene_within_30kb": "['" + "' '".join([T] + neighbors) + "']",
        "other_alignment_chromosome": alt_align,
        "nearest_nontarget_gene_id": offtarget,
        "nearest_nontarget_gene_dist": 100.0,
        # boolean source flags travel with the row and must never become genes
        "neighboring_gene_KD": True,
        "distal_offtarget_flag": True,
    }


LIBRARY = guides.build_library({T: [
    _row("g-1", [NEIGHBOR_OF_G1], alt_align="chr5", offtarget=OFFTARGET),
    _row("g-2", [NEIGHBOR_OF_G2]),
]})


def _est(kind, eid, n_guides, **kw):
    return Estimate(estimate_type=kind, estimate_id=eid,
                    released_estimate_id=f"{T}_{COND}", target_id=T,
                    target_ensembl=T, condition=COND, n_guides=n_guides,
                    target_id_namespace="ensembl_gene_id", target_symbol=SYM,
                    released_target_ensembl=T, **kw)


def _manifest(est, guide_ids):
    """The manifest scope that proves this estimate's contributing guides."""
    return guides.build_manifest_index([
        {"estimate_type": est.estimate_type, "estimate_id": est.estimate_id,
         "released_estimate_id": est.released_estimate_id,
         "target_id": est.target_id, "target_id_namespace": est.target_id_namespace,
         "target_symbol": est.target_symbol, "target_ensembl": est.target_ensembl,
         "condition": est.condition,
         "donor_pair": est.donor_pair, "guide_id": g,
         "evidence_state": "determined",
         "identity_method": "released_per_guide_identity_column",
         "source_sha256": "a" * 64}
        for g in guide_ids])


def _mask_for(est, guide_ids, library=None):
    library = library or LIBRARY
    contrib = guides.resolve(est, library, _manifest(est, guide_ids))
    return masks.build_estimate_mask(est, contrib, library.get(T))


# --------------------------------------------------------------------------- #
# The mask is a function of THIS estimate's contributors -- nothing else.
# --------------------------------------------------------------------------- #
def test_the_mask_is_built_only_from_the_guides_the_manifest_names():
    """Same target, same library, two different proven contributor sets.

    Nothing but the manifest differs, so nothing but the manifest can be deciding the
    mask. This is the property the whole contributor contract exists to buy.
    """
    both = _mask_for(_est(guides.MAIN, "main", 2.0), ["g-1", "g-2"])
    only_g2 = _mask_for(_est(guides.MAIN, "main", 1.0), ["g-2"])

    # both guides: each one's neighbourhood, plus guide-1's resolved off-target
    assert both["gene_set"] == {T, NEIGHBOR_OF_G1, NEIGHBOR_OF_G2, OFFTARGET}
    # only g-2 contributed: guide-1's genes are NOT masked, though g-1 is right
    # there in the library
    assert only_g2["gene_set"] == {T, NEIGHBOR_OF_G2}
    assert NEIGHBOR_OF_G1 not in only_g2["gene_set"]
    assert OFFTARGET not in only_g2["gene_set"]


def test_unused_library_guide_cannot_enter_a_mask():
    """Three library guides, two contributed: the manifest names which two, and
    the third guide's neighbourhood must never reach the mask."""
    lib = guides.build_library({T: [
        _row("g-1", [NEIGHBOR_OF_G1]),
        _row("g-2", [NEIGHBOR_OF_G2]),
        _row("g-3", [NEIGHBOR_OF_G3]),
    ]})
    mask = _mask_for(_est(guides.MAIN, "main", 2.0), ["g-1", "g-2"], library=lib)
    assert mask["resolved"] is True
    assert NEIGHBOR_OF_G3 not in mask["gene_set"]     # the unused guide's gene
    assert mask["gene_set"] == {T, NEIGHBOR_OF_G1, NEIGHBOR_OF_G2}


def test_intended_target_is_always_masked():
    mask = _mask_for(_est(guides.MAIN, "main", 1.0), ["g-2"])
    reasons = {(e["masked_gene_ensembl"], e["mask_reason"]) for e in mask["entries"]}
    assert (T, "intended_target") in reasons


def test_offtarget_only_masked_when_an_alternate_alignment_exists():
    lib = guides.build_library({T: [_row("g-1", [], alt_align=None,
                                         offtarget=OFFTARGET)]})
    mask = _mask_for(_est(guides.MAIN, "main", 1.0), ["g-1"], library=lib)
    assert mask["resolved"] is True
    assert OFFTARGET not in mask["gene_set"]


# --------------------------------------------------------------------------- #
# SUPPORT GETS NO MASK. Not the pooled one, not an empty one.
# --------------------------------------------------------------------------- #
def test_a_support_estimate_gets_no_mask_and_never_borrows_the_pooled_one():
    pooled = _mask_for(_est(guides.MAIN, "main", 2.0), ["g-1", "g-2"])
    assert pooled["gene_set"]                         # the pooled mask is real

    for est in (_est(guides.GUIDE, "guide_1", 1.0),
                _est(guides.DONOR_PAIR, "CE1_CE2", 2.0, donor_pair="CE1_CE2")):
        # hand it the very manifest scope it would need. It still gets nothing.
        mask = _mask_for(est, ["g-1", "g-2"])
        assert mask["resolved"] is False
        assert mask["gene_set"] is None              # never a silently EMPTY mask
        assert mask["reason"] == domain.SUPPORT_UNAVAILABLE

        rows = masks.mask_rows_for_emit(est, mask, universe=[], run_id="r")
        assert [r["masked_gene_ensembl"] for r in rows] == [None]
        assert rows[0]["mask_reason"] == "mask_unresolved"
        assert rows[0]["mask_unresolved_reason"] == domain.SUPPORT_UNAVAILABLE


def test_an_unresolved_estimate_emits_no_mask_gene_at_all():
    lib = guides.build_library({T: [_row("g-1", [NEIGHBOR_OF_G1])]})
    est = _est(guides.MAIN, "main", 2.0)
    # no manifest -> no identity -> no mask
    mask = masks.build_estimate_mask(est, guides.resolve(est, lib, None), lib[T])
    assert mask["resolved"] is False
    assert mask["gene_set"] is None
    rows = masks.mask_rows_for_emit(est, mask, universe=[], run_id="r")
    assert [r["masked_gene_ensembl"] for r in rows] == [None]
    assert rows[0]["mask_reason"] == "mask_unresolved"
    assert rows[0]["mask_unresolved_reason"] == guides.NO_CONTRIBUTOR_MANIFEST


def test_a_manifest_count_disagreeing_with_the_pooled_fit_gets_no_mask():
    """The pooled fit says one guide; the manifest names two. Refuse, don't pick."""
    mask = _mask_for(_est(guides.MAIN, "main", 1.0), ["g-1", "g-2"])
    assert mask["resolved"] is False
    assert mask["gene_set"] is None                  # never a silently empty mask
    assert mask["reason"] == guides.MANIFEST_COUNT_DISAGREES


# --------------------------------------------------------------------------- #
# A boolean flag is not a gene.
# --------------------------------------------------------------------------- #
def test_boolean_flags_are_never_treated_as_gene_identities():
    assert masks.parse_gene_list(True) == []
    assert masks.parse_gene_list(False) == []
    assert masks.parse_gene_list("True") == []
    assert masks.parse_gene_list(1) == []
    assert masks.parse_gene_list(None) == []
    assert masks.parse_gene_list("nan") == []
    assert masks.parse_gene_list("['ENSG00000000002' 'ENSG00000000003']") == \
        ["ENSG00000000002", "ENSG00000000003"]

    # a row whose off-target "identity" is a boolean flag masks no extra gene
    row = _row("g-x", [])
    row["nearest_nontarget_gene_id"] = True
    row["other_alignment_chromosome"] = "chr1"
    genes = {e["masked_gene_ensembl"]
             for e in masks.guide_mask_entries(row, "nearby_gene_within_30kb")}
    assert genes == {T}
    assert True not in genes and "True" not in genes


def test_boolean_neighborhood_column_yields_no_masked_neighbors():
    row = _row("g-x", [])
    row["nearby_gene_within_30kb"] = True        # a flag, not a gene list
    genes = {e["masked_gene_ensembl"]
             for e in masks.guide_mask_entries(row, "nearby_gene_within_30kb")}
    assert genes == {T}                          # intended target only


def test_emitted_rows_intersect_the_gene_universe_and_carry_the_estimate_key():
    est = _est(guides.MAIN, "main", 2.0)
    mask = _mask_for(est, ["g-1", "g-2"])
    rows = masks.mask_rows_for_emit(est, mask, universe={T, NEIGHBOR_OF_G1},
                                    run_id="run-1")
    flags = {r["masked_gene_ensembl"]: r["in_gene_universe"] for r in rows}
    assert flags[T] is True
    assert flags[NEIGHBOR_OF_G1] is True
    assert flags[OFFTARGET] is False              # not in the DE universe
    assert {r["estimate_type"] for r in rows} == {"main"}
    assert {r["run_id"] for r in rows} == {"run-1"}
