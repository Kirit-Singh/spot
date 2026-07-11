"""Target/off-target mask tests (plan §5.4, §13)."""
from direct import masks


def test_parse_gene_list_numpy_and_python_repr():
    assert masks.parse_gene_list("['ENSG1' 'ENSG2' 'ENSG3']") == ["ENSG1", "ENSG2", "ENSG3"]
    assert masks.parse_gene_list("['ENSG9']") == ["ENSG9"]
    assert masks.parse_gene_list("nan") == []
    assert masks.parse_gene_list(None) == []
    assert masks.parse_gene_list("[]") == []


def _guide(sg, target, nearby, other_align=None, offtarget=None):
    return {
        "sgRNA": sg,
        "target_gene_id": target,
        "target_gene_name": "T",
        "designed_target_gene_id": target,
        "distance_to_closest_target_tss": 40.0,
        "nearby_gene_within_30kb": nearby,
        "other_alignment_chromosome": other_align,
        "other_alignment_pos": None,
        "nearest_nontarget_gene_id": offtarget,
        "nearest_nontarget_gene_name": "OFF",
        "nearest_nontarget_gene_dist": 100.0,
    }


def test_target_mask_includes_intended_neighbor_offtarget():
    rows = {
        "ENSG00000000001": [
            _guide("G-1", "ENSG00000000001",
                   "['ENSG00000000001' 'ENSG00000000002']",
                   other_align="chr5", offtarget="ENSG00000000099"),
            _guide("G-2", "ENSG00000000001",
                   "['ENSG00000000001' 'ENSG00000000003']"),
        ]
    }
    built = masks.build_target_masks(rows, "nearby_gene_within_30kb")
    m = built["ENSG00000000001"]
    assert m["gene_set"] == {
        "ENSG00000000001",  # intended target
        "ENSG00000000002",  # neighbor (guide 1)
        "ENSG00000000003",  # neighbor (guide 2)
        "ENSG00000000099",  # resolved off-target (guide 1 alt alignment)
    }
    assert m["guide_ids"] == ["G-1", "G-2"]
    reasons = {(e["masked_gene_ensembl"], e["mask_reason"]) for e in m["entries"]}
    assert ("ENSG00000000099", "offtarget_alignment") in reasons
    assert ("ENSG00000000002", "neighbor_within_30kb") in reasons


def test_offtarget_not_masked_without_alt_alignment():
    rows = {"ENSG00000000001": [
        _guide("G-1", "ENSG00000000001", "['ENSG00000000001']",
               other_align=None, offtarget="ENSG00000000099")]}
    m = masks.build_target_masks(rows, "nearby_gene_within_30kb")["ENSG00000000001"]
    assert "ENSG00000000099" not in m["gene_set"]  # no alt alignment -> not an off-target


def test_mask_rows_intersect_universe():
    rows = {"ENSG00000000001": [
        _guide("G-1", "ENSG00000000001", "['ENSG00000000001' 'ENSG00000000002']")]}
    m = masks.build_target_masks(rows, "nearby_gene_within_30kb")["ENSG00000000001"]
    emit = masks.mask_rows_for_emit("ENSG00000000001", "Stim48hr", "cid", m,
                                    universe={"ENSG00000000001"})  # neighbor absent
    flags = {r["masked_gene_ensembl"]: r["in_gene_universe"] for r in emit}
    assert flags["ENSG00000000001"] is True
    assert flags["ENSG00000000002"] is False


def test_fallback_self_mask():
    m = masks.fallback_self_mask("ENSG00000000042")
    assert m["gene_set"] == {"ENSG00000000042"}
    assert m["guide_ids"] == []
