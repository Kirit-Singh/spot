"""THE PATHWAY LAYER: two evidence lines, never fused, and a rule about counting to two.

The requirement was pathway evidence built on the FULL target-masked perturbation
signatures — not on the marker panels. That distinction is the whole design:

  * the marker panels ARE the axis the arms are scored on, so two targets that both move
    the program agree on the panel BY CONSTRUCTION. Agreement there is close to circular;
  * the full signature contains everything the panels do not, and it is where two
    knockdowns can be shown to do the same thing for reasons the score never looked at —
    or to reach the same score by completely different routes.

So the record carries both, side by side, and fuses neither:

  (A) RANKED-ARM ENRICHMENT — does this pathway sit at the top of ONE arm's ranking?
      One statistic per arm. Never summed across arms: a pathway enriched in away_from_A
      and depleted in toward_B is a FINDING, and a single "pathway score" would erase it.

  (B) SIGNATURE CONVERGENCE — do knockdowns of DIFFERENT members do the same thing?
      Requires >= 2 measured perturbations, or it is not a convergence claim at all.
      One target is one experiment; calling it a pathway result launders an observation
      into a mechanism.

They can disagree, and both disagreements are informative: enriched-but-not-convergent is
one strong target dragging its pathway up behind it; convergent-but-not-enriched is a set
of members that agree with each other and none of which is near the top.
"""
from __future__ import annotations

import json
import os

import jsonschema
import pytest
from direct import (
    config,
    convergence,
    enrichment,
    genesets,
    pathway,
)
from direct.hashing import content_hash
from fixtures_pathway import (
    RELEASE_ID,
    masked_support,
    signatures,
    write_gene_sets,
)
from fixtures_spec import TARGET_GENES, UNIVERSE

SCHEMA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "analysis", "direct", "schemas", "stage02_pathway_record.schema.json")

UNIVERSE_SHA = content_hash(list(UNIVERSE))
CONFIG_SHA = "c" * 64


@pytest.fixture(scope="module")
def schema():
    with open(SCHEMA_PATH) as fh:
        return json.load(fh)


@pytest.fixture
def bundle(tmp_path):
    path = write_gene_sets(str(tmp_path), list(UNIVERSE), list(TARGET_GENES),
                           UNIVERSE_SHA)
    return genesets.load(path, effect_universe=list(UNIVERSE),
                         effect_universe_sha256=UNIVERSE_SHA)


@pytest.fixture
def sigs():
    return signatures(list(UNIVERSE), list(TARGET_GENES))


def _rows(scores):
    """A minimal screen: target -> (away, toward), all evaluable."""
    return [{"target_id": t, config.ARM_A: a, config.ARM_B: b,
             "A_evaluable": True, "B_evaluable": True}
            for t, (a, b) in scores.items()]


def _default_rows():
    # the CONVERGENT set's members are the top of the away arm
    scores = {}
    for i, t in enumerate(TARGET_GENES):
        scores[t] = (10.0 - i, 1.0 + (i % 3))
    return _rows(scores)


# --------------------------------------------------------------------------- #
# 1. THE GENE SETS ARE PINNED, NAMESPACED AND BOUND TO A UNIVERSE.
# --------------------------------------------------------------------------- #
def test_the_bundle_pins_its_release_and_its_bytes(bundle):
    rel = bundle["gene_set_release"]
    assert rel["release_id"] == RELEASE_ID
    assert len(rel["sha256"]) == 64
    assert rel["n_sets"] == 5


def test_a_bundle_that_names_no_RELEASE_is_refused(tmp_path):
    """'Reactome' is not a version. Membership changes between releases, so an
    enrichment against an unnamed release cannot be reproduced or contested."""
    def drop(doc):
        doc["release"].pop("release_id")
        return doc

    path = write_gene_sets(str(tmp_path), list(UNIVERSE), list(TARGET_GENES),
                           UNIVERSE_SHA, mutate=drop)
    with pytest.raises(genesets.GeneSetError, match="release_id"):
        genesets.load(path, list(UNIVERSE), UNIVERSE_SHA)


def test_a_bundle_bound_to_ANOTHER_universe_is_refused(tmp_path):
    """An enrichment statistic is a statement about a set RELATIVE TO a background.
    The same set against a different background is a different number."""
    path = write_gene_sets(str(tmp_path), list(UNIVERSE), list(TARGET_GENES),
                           "d" * 64)
    with pytest.raises(genesets.GeneSetError, match="another background"):
        genesets.load(path, list(UNIVERSE), UNIVERSE_SHA)


def test_a_SYMBOL_keyed_bundle_is_refused(tmp_path):
    """A symbol-keyed set against an Ensembl universe overlaps in almost nothing, and
    the 'no enrichment' it returns is a failed join, not a null result."""
    def to_symbols(doc):
        doc["gene_id_namespace"] = "gene_symbol"
        return doc

    path = write_gene_sets(str(tmp_path), list(UNIVERSE), list(TARGET_GENES),
                           UNIVERSE_SHA, mutate=to_symbols)
    with pytest.raises(genesets.GeneSetError, match="failed join"):
        genesets.load(path, list(UNIVERSE), UNIVERSE_SHA)


def test_a_duplicate_gene_in_a_set_is_refused(tmp_path):
    def dupe(doc):
        doc["sets"][0]["genes"] = doc["sets"][0]["genes"] + [doc["sets"][0]["genes"][0]]
        return doc

    path = write_gene_sets(str(tmp_path), list(UNIVERSE), list(TARGET_GENES),
                           UNIVERSE_SHA, mutate=dupe)
    with pytest.raises(genesets.GeneSetError, match="twice"):
        genesets.load(path, list(UNIVERSE), UNIVERSE_SHA)


def test_genes_absent_from_the_universe_are_COVERAGE_not_imputed(bundle):
    for s in bundle["sets"].values():
        # B1: TWO universes. Membership is decided in the TARGET space (the arms rank
        # perturbed targets); the readout space is where signature vectors live.
        assert set(s["genes_in_universe"]) <= set(UNIVERSE)          # readout
        assert set(s["genes_in_target_universe"]) <= set(UNIVERSE)   # target
        assert s["n_genes_in_readout_universe" if False else "n_genes_in_universe"] \
            <= s["n_genes_readout"]
        assert s["n_genes_in_target_universe"] <= s["n_genes_target"]
        assert 0.0 <= s["coverage"] <= 1.0


def test_an_ABSENT_bundle_is_a_STATE_not_a_crash():
    assert genesets.load(None) is None
    block = genesets.binding_block(None)
    assert block["status"] == "absent"
    assert block["pathway_layer_available"] is False


# --------------------------------------------------------------------------- #
# 2. (A) RANKED-ARM ENRICHMENT — per arm, with a leading edge, and no p/q.
# --------------------------------------------------------------------------- #
def test_enrichment_is_computed_ONCE_PER_ARM(bundle):
    rows = _default_rows()
    for arm in config.ARMS:
        res = enrichment.enrich_arm(rows, bundle, arm)
        assert {r["set_id"] for r in res} == set(bundle["sets"])
        assert {r["arm"] for r in res} == {arm}


def test_a_set_at_the_TOP_of_an_arm_enriches_POSITIVELY(bundle):
    """The convergent set's members are the three top-ranked away targets."""
    res = {r["set_id"]: r
           for r in enrichment.enrich_arm(_default_rows(), bundle, config.ARM_A)}
    e = res["FX:CONVERGENT"]
    assert e["enrichment_value"] > 0
    assert e["testable"] is True
    # the LEADING EDGE names the members actually responsible
    assert set(e["leading_edge"]) <= set(TARGET_GENES[0:3])
    assert e["n_leading_edge"] >= 1
    assert e["peak_rank"] is not None


def test_a_set_at_the_BOTTOM_of_an_arm_enriches_NEGATIVELY(bundle):
    """Reverse the away ranking and the same set must flip sign — the statistic is
    about position in the ranking, and nothing else."""
    scores = {t: (float(i), 1.0) for i, t in enumerate(TARGET_GENES)}
    res = {r["set_id"]: r
           for r in enrichment.enrich_arm(_rows(scores), bundle, config.ARM_A)}
    assert res["FX:CONVERGENT"]["enrichment_value"] < 0


def test_the_two_arms_are_enriched_SEPARATELY_and_may_DISAGREE(bundle):
    """A pathway can top one arm and bottom the other. That is a finding, not noise —
    and there is no single number that could carry it."""
    scores = {}
    for i, t in enumerate(TARGET_GENES):
        scores[t] = (10.0 - i, float(i))          # away: top   toward: bottom
    rows = _rows(scores)
    a = {r["set_id"]: r for r in enrichment.enrich_arm(rows, bundle, config.ARM_A)}
    b = {r["set_id"]: r for r in enrichment.enrich_arm(rows, bundle, config.ARM_B)}
    assert a["FX:CONVERGENT"]["enrichment_value"] > 0
    assert b["FX:CONVERGENT"]["enrichment_value"] < 0


def test_NO_p_value_q_value_or_fdr_is_emitted_anywhere(bundle):
    for arm in config.ARMS:
        for r in enrichment.enrich_arm(_default_rows(), bundle, arm):
            assert r["inference_status"] == "not_calibrated"
            assert not [k for k in r
                        if any(t in k.lower()
                               for t in ("pval", "p_value", "qval", "fdr", "signif"))]


def test_an_UNTESTABLE_set_is_still_EMITTED_with_a_reason(bundle):
    """A pathway missing from the table is indistinguishable from one tested and found
    nothing. 'Not asked' and 'asked and no' are different answers."""
    res = {r["set_id"]: r
           for r in enrichment.enrich_arm(_default_rows(), bundle, config.ARM_A)}
    small = res["FX:TOO_SMALL"]
    assert small["testable"] is False
    assert small["enrichment_value"] is None
    assert small["undefined_reason"] == "set_too_small_to_test"


def test_a_set_with_no_member_in_the_ranking_is_UNDEFINED_not_zero(bundle):
    """Zero would claim 'no enrichment'. The honest answer is 'we could not ask'."""
    res = {r["set_id"]: r
           for r in enrichment.enrich_arm(_default_rows(), bundle, config.ARM_A)}
    un = res["FX:UNMEASURED"]
    assert un["enrichment_value"] is None
    assert un["undefined_reason"] in ("no_set_gene_in_ranking", "set_too_small_to_test",
                                      "set_too_large_to_be_specific")


def test_a_target_the_arm_could_not_score_is_ABSENT_not_zero(bundle):
    """A non-evaluable target is not a zero-scoring target. It contributes to neither
    the hits nor the misses."""
    rows = _default_rows()
    rows[0]["A_evaluable"] = False
    ranked = enrichment.rank_targets(rows, config.ARM_A)
    assert TARGET_GENES[0] not in [t for t, _v in ranked]
    assert len(ranked) == len(rows) - 1


# --------------------------------------------------------------------------- #
# 3. (B) CONVERGENCE — the >= 2 rule, and the masks that make it honest.
# --------------------------------------------------------------------------- #
def test_the_similarity_is_computed_on_the_SHARED_unmasked_support(sigs):
    a, b = TARGET_GENES[0], TARGET_GENES[1]
    shared = set(sigs[a]) & set(sigs[b])
    sim, n = convergence.cosine_on_shared(sigs[a], sigs[b])
    assert n == len(shared)
    # the two supports genuinely DIFFER — each target masks its own gene
    assert set(sigs[a]) != set(sigs[b])
    assert sim is not None and sim > 0.9        # they converge


def test_a_similarity_over_TOO_FEW_shared_genes_is_UNDEFINED():
    """Two vectors always look similar on a handful of genes."""
    a = {f"G{i}": 1.0 for i in range(convergence.MIN_SHARED_GENES - 1)}
    sim, n = convergence.cosine_on_shared(a, dict(a))
    assert sim is None
    assert n < convergence.MIN_SHARED_GENES


def test_a_FLAT_signature_has_no_direction_and_no_similarity():
    """A zero vector's similarity is undefined, not 0.0 — 'unrelated' would be a claim."""
    flat = {f"G{i}": 0.0 for i in range(20)}
    live = {f"G{i}": 1.0 for i in range(20)}
    assert convergence.cosine_on_shared(flat, live)[0] is None


def test_a_pathway_with_ONE_measured_perturbation_is_NEVER_convergent(bundle, sigs):
    """THE RULE. One target is one experiment, however strong it looks."""
    pairs = convergence.pairwise(sigs)
    conv = {c["set_id"]: c
            for c in convergence.converge_sets(bundle, sigs, pairs)}

    single = conv["FX:SINGLE"]
    assert single["n_measured_perturbations"] == 1
    assert single["single_target_support"] is True
    assert single["convergent"] is False
    assert single["convergence_refused_reason"] == convergence.SINGLE_TARGET_SUPPORT
    # ...and it is EMITTED, not dropped
    assert single["set_id"] in conv


def test_a_pathway_whose_members_AGREE_is_convergent(bundle, sigs):
    pairs = convergence.pairwise(sigs)
    conv = {c["set_id"]: c
            for c in convergence.converge_sets(bundle, sigs, pairs)}

    c = conv["FX:CONVERGENT"]
    assert c["convergent"] is True
    assert c["n_supporting_perturbations"] >= 2
    assert c["single_target_support"] is False
    assert c["n_supportive_pairs"] >= 1
    # every pair it stands on is emitted, WITH the size of its shared support
    for p in c["pairwise_support"]:
        assert p["n_shared_unmasked_genes"] >= convergence.MIN_SHARED_GENES
        assert p["similarity"] >= convergence.SIMILARITY_THRESHOLD


def test_a_pathway_whose_members_DISAGREE_is_not_convergent(bundle, sigs):
    pairs = convergence.pairwise(sigs)
    conv = {c["set_id"]: c
            for c in convergence.converge_sets(bundle, sigs, pairs)}

    d = conv["FX:DIVERGENT"]
    assert d["n_measured_perturbations"] == 3
    assert d["convergent"] is False
    assert d["single_target_support"] is False
    assert d["convergence_refused_reason"] == "fewer_than_two_perturbations_converge"


def test_a_component_of_ONE_is_not_a_component(bundle, sigs):
    """A member with no supportive partner INSIDE its set is not a cluster of one."""
    pairs = convergence.pairwise(sigs)
    conv = {c["set_id"]: c for c in convergence.converge_sets(bundle, sigs, pairs)}
    for c in conv.values():
        for comp in c["intra_set_components"]:
            assert len(comp) >= convergence.MIN_PERTURBATIONS_FOR_CONVERGENCE
    # the lone strong target's set has no component at all
    assert conv["FX:SINGLE"]["intra_set_components"] == []


def test_the_clustering_is_deterministic_and_order_invariant(bundle, sigs):
    """No seed, no k, no resolution — three knobs that would each be a place to tune
    the answer after seeing it."""
    import random

    def components(signatures):
        pairs = convergence.pairwise(signatures)
        return {c["set_id"]: c["intra_set_components"]
                for c in convergence.converge_sets(bundle, signatures, pairs)}

    base = components(sigs)
    for seed in (1, 7, 20260712):
        keys = list(sigs)
        random.Random(seed).shuffle(keys)
        assert components({k: sigs[k] for k in keys}) == base


def test_the_mask_is_what_makes_two_supports_differ():
    """A target's own gene is out of its own signature. That is the point."""
    for t in TARGET_GENES[:3]:
        support = masked_support(list(UNIVERSE), t)
        assert t not in support


# --------------------------------------------------------------------------- #
# 4. THE RECORD: full evidence table, schema-valid, no combined score.
# --------------------------------------------------------------------------- #
@pytest.fixture
def records(bundle, sigs):
    return pathway.build_records(_default_rows(), bundle, sigs, CONFIG_SHA)


def test_EVERY_set_gets_a_record(records, bundle):
    assert records["n_records"] == len(bundle["sets"])
    assert {r["set_id"] for r in records["records"]} == set(bundle["sets"])


def test_the_record_validates_against_the_definitive_schema(records, schema):
    jsonschema.validate(records, schema)


def test_the_record_carries_BOTH_evidence_lines_side_by_side(records):
    for r in records["records"]:
        assert set(r["enrichment"]) == set(config.ARMS)
        assert "convergence" in r
        for arm in config.ARMS:
            e = r["enrichment"][arm]
            assert e["statistic_name"] == enrichment.STATISTIC_NAME
            assert e["method_id"] == enrichment.METHOD_ID
            assert e["rounding_rule"] == enrichment.ROUNDING_RULE


def test_the_enrichment_value_never_travels_without_its_binding(records):
    """A number is not interpretable without which statistic, which release, which
    universe. All four are on the record."""
    for r in records["records"]:
        assert r["gene_set_release"]["release_id"] == RELEASE_ID
        assert len(r["gene_set_release"]["sha256"]) == 64
        assert r["effect_universe_sha256"] == UNIVERSE_SHA
        assert r["gene_id_namespace"] == "ensembl_gene_id"
        assert r["direct_config_sha256"] == CONFIG_SHA


def test_there_is_NO_combined_pathway_score(records, schema):
    """The two arms are never fused, and additionalProperties=false means one cannot
    be added later either."""
    for r in records["records"]:
        assert not [k for k in r if "combined" in k.lower()
                    or "balanced" in k.lower() or "overall" in k.lower()]

    doc = json.loads(json.dumps(records))
    doc["records"][0]["combined_pathway_score"] = 1.0
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(doc, schema)


def test_a_record_claiming_CONVERGENCE_on_one_perturbation_fails_the_schema(records,
                                                                            schema):
    """The >= 2 rule is pinned in the schema, not only in the code that wrote it."""
    doc = json.loads(json.dumps(records))
    rec = next(r for r in doc["records"] if r["set_id"] == "FX:SINGLE")
    # its one measured member converges with nothing, so nothing supports it
    assert rec["convergence"]["n_measured_perturbations"] == 1
    assert rec["convergence"]["n_supporting_perturbations"] \
        < convergence.MIN_PERTURBATIONS_FOR_CONVERGENCE

    rec["convergence"]["convergent"] = True          # the lie the schema must refuse
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(doc, schema)


@pytest.mark.parametrize("pq", ["p_value", "q_value", "fdr", "padj"])
def test_a_p_value_injected_into_an_enrichment_block_fails_the_schema(records, schema,
                                                                      pq):
    doc = json.loads(json.dumps(records))
    doc["records"][0]["enrichment"][config.ARM_A][pq] = 0.01
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(doc, schema)


def test_an_absent_bundle_yields_an_explicit_UNAVAILABLE_record_set():
    out = pathway.build_records(_default_rows(), None, {}, CONFIG_SHA)
    assert out["pathway_layer_available"] is False
    assert out["records"] == []
    assert out["method"]["gene_sets"]["status"] == "absent"


# --------------------------------------------------------------------------- #
# 5. CLAUDE SCIENCE MAY INTERPRET. IT MAY NOT TOUCH A PRIMARY RANK.
# --------------------------------------------------------------------------- #
def test_science_evidence_refs_must_be_TYPED_and_HASHED():
    """Free text is not a citation. A reference nobody can resolve to exact bytes
    cannot be checked, cannot be contested — and will be believed anyway."""
    ok = [{"science_evidence_id": "cs:001", "sha256": "a" * 64,
           "record_type": "literature"}]
    assert pathway.validate_science_evidence(ok) == ok

    for bad in ([{"science_evidence_id": "cs:001"}],
                [{"science_evidence_id": "cs:001", "sha256": "a" * 64}],
                [{"science_evidence_id": "cs:001", "sha256": "a" * 64,
                  "record_type": "vibes"}],
                ["a paper I read"]):
        with pytest.raises(ValueError):
            pathway.validate_science_evidence(bad)


def test_a_science_ref_with_free_text_instead_of_a_hash_fails_the_schema(records,
                                                                         schema):
    doc = json.loads(json.dumps(records))
    doc["records"][0]["science_evidence_refs"] = [
        {"science_evidence_id": "cs:001", "sha256": "see the paper",
         "record_type": "literature"}]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(doc, schema)


@pytest.mark.parametrize("rank_field", ["rank_away_from_A", "rank_toward_B",
                                        "pareto_tier", "away_from_A", "toward_B"])
def test_science_CANNOT_write_a_primary_rank_into_a_pathway_record(records, schema,
                                                                   rank_field):
    """An interpretation that can quietly edit its own evidence is not an
    interpretation. There is no writable field here that any ranking reads."""
    doc = json.loads(json.dumps(records))
    doc["records"][0][rank_field] = 1
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(doc, schema)


def test_the_record_declares_that_science_may_not_change_ranks(records):
    assert pathway.SCIENCE_MAY_INTERPRET is True
    assert pathway.SCIENCE_MAY_CHANGE_PRIMARY_RANKS is False
    for r in records["records"]:
        assert r["science_may_change_primary_ranks"] is False
