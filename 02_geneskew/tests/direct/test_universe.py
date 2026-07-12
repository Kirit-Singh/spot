"""One common effect-gene universe across the released objects."""
import pytest
from direct import universe as uni
from direct.universe import UniverseError

# The real release: the pooled matrix has 10,282 genes, the donor-pair matrices
# 10,273. The intersection is what every estimate must be projected on.
POOLED = [f"ENSG{i:08d}" for i in range(10282)]
BY_GUIDE = list(POOLED)
BY_DONORS = [g for g in POOLED if g not in set(POOLED[:9])]      # 10,273


def test_objects_with_differing_universes_intersect_to_one_ordered_set():
    out = uni.common_gene_universe(
        POOLED, {"by_guide": BY_GUIDE, "by_donors": BY_DONORS})
    assert out["n_genes"] == 10273
    assert out["gene_ids"] == BY_DONORS               # pooled order, preserved
    assert out["object_sizes"] == {"__reference__": 10282, "by_guide": 10282,
                                   "by_donors": 10273}
    assert len(out["sha256"]) == 64


def test_the_universe_hash_moves_with_the_gene_set_and_with_its_order():
    base = uni.common_gene_universe(POOLED, {"d": BY_DONORS})["sha256"]
    same = uni.common_gene_universe(POOLED, {"d": list(BY_DONORS)})["sha256"]
    assert base == same

    fewer = uni.common_gene_universe(POOLED, {"d": BY_DONORS[:-1]})["sha256"]
    assert fewer != base

    reordered = uni.common_gene_universe(list(reversed(POOLED)),
                                         {"d": BY_DONORS})["sha256"]
    assert reordered != base                         # order is part of the identity


def test_every_estimate_projects_on_the_same_genes():
    common = uni.common_gene_universe(POOLED, {"d": BY_DONORS})["gene_ids"]
    panel = POOLED[:20]                              # spans the dropped genes
    restricted = uni.restrict(panel, common)
    assert set(restricted) <= set(common)
    assert set(POOLED[:9]).isdisjoint(restricted)    # dropped genes cannot survive
    # restricting twice is the same as restricting once
    assert uni.restrict(restricted, common) == restricted


def test_an_empty_intersection_is_a_hard_failure():
    with pytest.raises(UniverseError, match="shares no gene"):
        uni.common_gene_universe(POOLED, {"other": ["ENSG99999999"]})


def test_an_incompatible_intersection_is_a_hard_failure_not_a_rump():
    half = POOLED[:5000]
    with pytest.raises(UniverseError, match="not compatible"):
        uni.common_gene_universe(POOLED, {"other": half})


def test_an_empty_object_universe_is_a_hard_failure():
    with pytest.raises(UniverseError, match="empty gene universe"):
        uni.common_gene_universe(POOLED, {"other": []})
    with pytest.raises(UniverseError, match="empty gene universe"):
        uni.common_gene_universe([], {"other": POOLED})
