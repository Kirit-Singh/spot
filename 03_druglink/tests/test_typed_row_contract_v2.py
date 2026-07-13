"""THE TYPED ROW CONTRACT: pathway-as-context, missing fields, namespace tokens, the Stage-2 admission carried on every edge, ranks-vs-rows, and epsilon."""
from __future__ import annotations

import pytest

from druglink import edge_build_v2 as eb2
from druglink import edges_v2 as e2
from druglink import modality_v2 as mv2
from druglink import pathway_context_v2 as pc2
from druglink import stage2_aggregate as sa
from druglink.hashing import content_hash
from sign_fixture_v2 import (
    CRISPRI,
    NS_ENSEMBL,
    NS_SYMBOL,
    aggregate,
    arm,
    edges_for,
    load_store,
    pick_drug_known,
    typed_row,
)

@pytest.fixture(scope="module")
def store():
    return load_store()


@pytest.fixture(scope="module")
def drug_known(store):
    return pick_drug_known(store)


# =========================================================================== #
# 5. PATHWAY IS CONTEXT. It never sources a drug edge.
# =========================================================================== #
def test_a_DRUG_KNOWN_pathway_member_gets_NO_EDGE_and_NO_CRASH(store, drug_known):
    """The case that used to CRASH: a pathway gene that HAS real ChEMBL mechanisms.

    build_edges used to feed pathway records into typed_identity/build_edge and abort only when a
    pathway target HAPPENED to have drug assertions — so it looked healthy purely because no
    pathway gene in the fixtures had a known drug. This target really does.
    """
    tid, ns = drug_known
    assert store.row_for(tid, ns)["drugs"], "NON-VACUITY: this target must really have drugs"

    pathway_arm = arm(sa.LANE_PATHWAY, [{
        "pathway_id": "GO:0006955", "pathway_source": "GO-BP", "enrichment_value": 2.7,
        "coverage": 0.4, "convergence": 0.8,
        "leading_edge": [{"target_id": tid, "target_id_namespace": ns}]}])
    built = eb2.build_edges(aggregate([pathway_arm]), store)          # NO CRASH

    assert built["target_drug_edges"] == []      # no edge, from a drug-known pathway gene
    # The lane is NOT ADMITTED, so it contributes ZERO context — and SAYS SO, by name.
    assert built["pathway_context"] == []
    states = {d["state"] for d in built["dispositions"]}
    assert eb2.STATE_PATHWAY_LANE_NOT_ADMITTED in states


def test_the_PATHWAY_LANE_IS_NOT_ADMITTED_and_contributes_ZERO(store, drug_known):
    """We do not consume bytes admitted by a fail-open gate. Zero is the honest output."""
    assert pc2.PATHWAY_LANE_ADMITTED is False
    assert "fails open" in pc2.PATHWAY_LANE_NOT_ADMITTED_REASON

    with pytest.raises(pc2.PathwayContextError) as exc:
        pc2.require_admitted("pathway|P0|increase|A")
    assert exc.value.gate == pc2.GATE_PATHWAY_LANE_NOT_ADMITTED

    # A measured arm still works: the Direct/temporal admission chain IS real.
    edges = edges_for(store, [arm(sa.LANE_DIRECT, [typed_row(drug_known, arm_value=1.5)])])
    assert edges, "NON-VACUITY: the measured lane is unaffected by the pathway refusal"


# --- The context SCHEMA, asserted exactly. No alias absorbs a renamed field. --- #
def test_a_RENAMED_pathway_field_is_REFUSED_BY_NAME():
    """`gene_set_id` and `set_id` are NOT accepted as `pathway_id`. Three spellings absorbed by
    an alias layer is how the contract rots while both lanes stay green."""
    for renamed in ("gene_set_id", "set_id", "native_set_id_field"):
        record = {renamed: "GO:1", "pathway_source": "GO-BP", "leading_edge": [],
                  "coverage": 0.1, "convergence": 0.2, "enrichment_value": 1.0}
        with pytest.raises(pc2.PathwayContextError) as exc:
            pc2.assert_context_schema(record, arm_key="A")
        assert exc.value.gate == pc2.GATE_PATHWAY_SCHEMA_FIELD_UNKNOWN


def test_a_MISSING_pathway_field_is_REFUSED_BY_NAME():
    record = {"pathway_id": "GO:1", "pathway_source": "GO-BP", "leading_edge": [],
              "coverage": 0.1, "convergence": 0.2}                 # no enrichment_value
    with pytest.raises(pc2.PathwayContextError) as exc:
        pc2.assert_context_schema(record, arm_key="A")
    assert exc.value.gate == pc2.GATE_PATHWAY_SCHEMA_FIELD_MISSING


def test_an_UNEXPECTED_EXTRA_pathway_field_is_REFUSED_BY_NAME():
    record = {"pathway_id": "GO:1", "pathway_source": "GO-BP", "leading_edge": [],
              "coverage": 0.1, "convergence": 0.2, "enrichment_value": 1.0,
              "combined_pathway_drug_score": 0.9}                  # nobody agreed to this
    with pytest.raises(pc2.PathwayContextError) as exc:
        pc2.assert_context_schema(record, arm_key="A")
    assert exc.value.gate == pc2.GATE_PATHWAY_SCHEMA_FIELD_UNKNOWN


def test_a_LEADING_EDGE_entry_with_NO_NAMESPACE_is_REFUSED_BY_NAME():
    """A namespace-less id is a name, and names are not identities."""
    with pytest.raises(pc2.PathwayContextError) as exc:
        pc2._leading_edge({"leading_edge": [{"target_id": "ENSG00000003436"}]})
    assert exc.value.gate == pc2.GATE_GENE_SET_ID_AS_TARGET


def test_an_ENRICHMENT_VALUE_used_to_SOURCE_an_edge_is_REFUSED_BY_NAME():
    with pytest.raises(pc2.PathwayContextError) as exc:
        pc2.check_no_set_level_source({"enrichment_value": 2.7}, arm_key="A")
    assert exc.value.gate == pc2.GATE_ENRICHMENT_VALUE_SOURCED_AN_EDGE


def test_a_GENE_SET_ID_reaching_the_target_join_is_REFUSED_BY_NAME():
    with pytest.raises(pc2.PathwayContextError) as exc:
        pc2._leading_edge({"leading_edge": ["GO:0006955"]})
    assert exc.value.gate == pc2.GATE_GENE_SET_ID_AS_TARGET


def test_a_PATHWAY_ORIGIN_EDGE_in_the_edge_table_is_REFUSED_BY_NAME():
    with pytest.raises(pc2.PathwayContextError) as exc:
        pc2.check_edges_are_all_measured(
            [{"edge_id": "E", "origin_type": "endpoint_pathway_context"}],
            ("endpoint_pathway_context",))
    assert exc.value.gate == pc2.GATE_PATHWAY_EDGE_IN_THE_EDGE_TABLE


# =========================================================================== #
# 6. check_edges is a GATE, not decoration: it must actually FIRE.
# =========================================================================== #
def test_check_edges_ACTUALLY_REFUSES_an_edge_with_no_declared_modality(store, drug_known):
    """The retired `check_edges` carried an UNDEFINED name, so it raised NameError the moment
    control reached it — which proved nothing ever reached it. This test reaches it."""
    edges = edges_for(store, [arm(sa.LANE_DIRECT, [typed_row(drug_known, arm_value=1.5)])])
    assert edges, "NON-VACUITY: there must be a real edge to mutate"

    forged = dict(edges[0], observed_perturbation_modality=None)
    with pytest.raises(e2.CandidatesV2Error) as exc:
        e2.check_edges([forged])
    assert exc.value.gate == e2.GATE_MEASURED_ORIGIN_NOT_MEASURED


def test_check_edges_ACTUALLY_REFUSES_an_INVERTED_modulation(store, drug_known):
    edges = edges_for(store, [arm(sa.LANE_DIRECT, [typed_row(drug_known, arm_value=-1.5)])])
    assert edges, "NON-VACUITY"
    # Re-fix the modulation the way the retired rule did: inhibit, whatever the sign.
    forged = dict(edges[0], desired_target_modulation=mv2.MOD_DECREASE)
    with pytest.raises(mv2.ModalityError) as exc:
        e2.check_edges([forged])
    assert exc.value.gate == mv2.GATE_MODULATION_DERIVED_FROM_MODALITY_ALONE


# =========================================================================== #
# 7. The typed row contract: a MISSING field is a NAMED REFUSAL, never a default.
# =========================================================================== #
@pytest.mark.parametrize("field,gate", [
    (mv2.FIELD_MODALITY, mv2.GATE_MODALITY_NOT_DECLARED),
    (mv2.FIELD_NAMESPACE, mv2.GATE_NAMESPACE_NOT_DECLARED),
    (mv2.FIELD_MODULATION, mv2.GATE_UNKNOWN_SERIALIZED_MODULATION),
    (mv2.FIELD_PHENOCOPY_CLASS, mv2.GATE_PHENOCOPY_CLASS_NOT_DECLARED),
    (mv2.FIELD_EVALUABLE, mv2.GATE_EVALUABILITY_NOT_DECLARED),
])
def test_a_MISSING_typed_field_REFUSES_the_arm_and_yields_ZERO_edges(store, drug_known,
                                                                     field, gate):
    row = typed_row(drug_known, arm_value=1.5)
    row.pop(field)
    with pytest.raises(mv2.ModalityError) as exc:
        edges_for(store, [arm(sa.LANE_DIRECT, [row])])
    assert exc.value.gate == gate


def test_an_UNKNOWN_namespace_token_is_REFUSED_and_never_coerced(store, drug_known):
    row = typed_row(drug_known, arm_value=1.5)
    row[mv2.FIELD_NAMESPACE] = "ensembl_gene"        # the store's OLD token — NOT W3's contract
    with pytest.raises(mv2.ModalityError) as exc:
        edges_for(store, [arm(sa.LANE_DIRECT, [row])])
    assert exc.value.gate == mv2.GATE_UNKNOWN_NAMESPACE


def test_the_STORE_NAMESPACE_VOCABULARY_divergence_is_SURFACED_not_translated():
    """No alias layer. If the store spells its namespaces differently, it REFUSES by name."""
    with pytest.raises(mv2.ModalityError) as exc:
        mv2.check_store_namespace_vocabulary(("ensembl_gene", "symbol"))
    assert exc.value.gate == mv2.GATE_NAMESPACE_VOCABULARY_DIVERGENCE
    # ...and the canonical vocabulary passes.
    mv2.check_store_namespace_vocabulary((NS_ENSEMBL, NS_SYMBOL))


def test_a_NULL_STAGE2_VERIFIER_IDENTITY_is_REFUSED(store, drug_known):
    """The retired columns read keys the loader never emitted, so every edge carried a null
    verifier and verdict — and the verifier read the same wrong keys, so both AGREED on None."""
    a = arm(sa.LANE_DIRECT, [typed_row(drug_known, arm_value=1.5)])
    broken = sa.LoadedArm(
        arm_key=a.arm_key, lane=a.lane, program_id=a.program_id,
        desired_change=a.desired_change, bundle=a.bundle, ranking=a.ranking,
        provenance={k: v for k, v in a.provenance.items()
                    if k not in ("aggregate_verifier_id", "aggregate_verdict")},
        records=a.records)
    with pytest.raises(e2.CandidatesV2Error) as exc:
        edges_for(store, [broken])
    assert exc.value.gate == e2.GATE_STAGE2_ADMISSION_NOT_CARRIED


def test_every_edge_carries_the_EXACT_stage2_verifier_identity_and_verdict(store, drug_known):
    """A test that only checked the KEY exists would pass while the VALUE was None."""
    edges = edges_for(store, [arm(sa.LANE_DIRECT, [typed_row(drug_known, arm_value=1.5)])])
    assert edges, "NON-VACUITY"
    for edge in edges:
        assert edge["stage2_aggregate_verifier_id"] == "spot.stage02.run_manifest.verifier.v1"
        assert edge["stage2_aggregate_verdict"] == "admit"


# =========================================================================== #
# 8. ROWS ARE NOT RANKS.
# =========================================================================== #
def test_n_ranked_counts_NON_NULL_RANKS_never_rows():
    records = [{"rank": 1}, {"rank": None}, {"rank": 3}, {"rank": None}]
    assert eb2.n_ranked(records) == 2                  # NOT 4
    assert eb2.n_ranked(records) != len(records)


def test_a_null_rank_NEVER_becomes_zero(store, drug_known):
    edges = edges_for(store, [arm(sa.LANE_DIRECT,
                                  [typed_row(drug_known, arm_value=1.5, rank=None)])])
    assert edges, "NON-VACUITY"
    for edge in edges:
        assert edge["arm_rank"] is None               # never 0, never last, never invented
        assert edge["arm_rank"] != 0
        assert edge["arm_rank_status"] == "unranked_by_source"


# =========================================================================== #
# 9. EPSILON is declared, and its basis is stated.
# =========================================================================== #
def test_the_sign_epsilon_is_declared_with_a_stated_basis_and_binds_stage2s_value():
    assert mv2.SIGN_EPS == 1e-9                       # stage-2 direct config.SIGN_EPS
    assert "config.SIGN_EPS" in mv2.SIGN_EPS_BASIS
    assert mv2.vocabularies()["sign_eps"] == repr(1e-9)
    # Inside the band there is no direction; a hair outside it there is.
    assert mv2.observed_sign_state(1e-10, evaluable=True, origin_is_measured=True) \
        == mv2.SIGN_NO_DIRECTIONAL_RESPONSE
    assert mv2.observed_sign_state(-1e-10, evaluable=True, origin_is_measured=True) \
        == mv2.SIGN_NO_DIRECTIONAL_RESPONSE
    assert mv2.observed_sign_state(1e-8, evaluable=True, origin_is_measured=True) \
        == mv2.SIGN_SUPPORTS_DESIRED_CHANGE


def test_a_CRISPRi_SIGN_can_NEVER_be_read_from_an_INFERRED_row():
    """A pathway enrichment value has no sign. Every value shape must hit the SAME refusal, so
    no number can smuggle a direction into a set-level statistic."""
    for value in (2.7, -2.7, 0.0, None):
        with pytest.raises(mv2.ModalityError) as exc:
            mv2.observed_sign_state(value, evaluable=True, origin_is_measured=False, arm_key="A")
        assert exc.value.gate == mv2.GATE_SIGN_READ_FROM_AN_INFERRED_ROW


def test_the_vocabulary_digest_MOVES_when_the_sign_rule_changes():
    """The rule is bound into the bundle id: changing it moves every downstream identifier."""
    before = content_hash(mv2.vocabularies())
    original = dict(mv2.MODULATION_FOR)
    try:
        mv2.MODULATION_FOR[(CRISPRI, mv2.SIGN_OPPOSES_DESIRED_CHANGE)] = mv2.MOD_DECREASE
        assert content_hash(mv2.vocabularies()) != before
    finally:
        mv2.MODULATION_FOR.clear()
        mv2.MODULATION_FOR.update(original)
    assert content_hash(mv2.vocabularies()) == before
