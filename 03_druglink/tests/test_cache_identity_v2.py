"""v2 cache identity — mutations from the independent source audit (sha fa64054e…).

"Human SINGLE PROTEIN" is a far weaker statement than it reads. Each mutation below is a
row ChEMBL really can return, which the current engine would admit into the direct gene
lane on `target_type` alone — silently attaching a drug to a human gene the screen never
perturbed.

Note on provenance: the audit document lives on the Mac
(`/Users/kiritsingh/.spot-runs/.../STAGE3_DRUG_CACHE_INDEPENDENT_SOURCE_AUDIT.md`) and is
not reachable from tcedirector. These encode the requirements as relayed, not as read from
the file — worth re-checking against the document itself.
"""
from __future__ import annotations

import pytest

from verifier import cache_identity as ci
from verifier.report import Report


def _target(**over):
    t = {
        "target_chembl_id": "CHEMBL1778",
        "target_type": "SINGLE PROTEIN",
        "target_taxon": 9606,
        "species_group_flag": 0,
        "target_components": [{
            "accession": "P16410",
            "component_type": "PROTEIN",
            "component_taxon": 9606,
            "relationship": "SINGLE PROTEIN",
        }],
    }
    t.update(over)
    return t


def _comp(**over):
    c = {"accession": "P16410", "component_type": "PROTEIN",
         "component_taxon": 9606, "relationship": "SINGLE PROTEIN"}
    c.update(over)
    return c


def _failed(rep):
    return [n for n, ok, _ in rep.checks if not ok]


# --------------------------------------------------------------------------- #
# The clean case, then every way ChEMBL can make it not-clean.
# --------------------------------------------------------------------------- #
def test_a_real_human_single_protein_is_admissible():
    ok, reason = ci.gene_lane_admissible(_target())
    assert ok
    assert reason == "human_single_protein_exactly_one_component"


def test_a_NON_HUMAN_single_protein_is_refused():
    """Mouse Ctla4 is also a SINGLE PROTEIN. The screen did not perturb it."""
    ok, reason = ci.gene_lane_admissible(_target(target_taxon=10090))
    assert not ok and "not_human" in reason


def test_a_SPECIES_GROUP_is_refused():
    """species_group_flag=1 is a protein ACROSS organisms — not one protein."""
    ok, reason = ci.gene_lane_admissible(_target(species_group_flag=1))
    assert not ok and "species_group_flag_is_set" in reason


def test_a_HOMOLOGUE_component_is_refused():
    """A homologue is a DIFFERENT gene that resembles this one."""
    ok, reason = ci.gene_lane_admissible(
        _target(target_components=[_comp(relationship="HOMOLOGOUS PROTEIN")]))
    assert not ok and "HOMOLOGUE" in reason


def test_a_homologue_FLAG_is_also_refused():
    ok, reason = ci.gene_lane_admissible(
        _target(target_components=[_comp(homologue=1)]))
    assert not ok and "HOMOLOGUE" in reason


def test_a_NON_PROTEIN_component_is_refused():
    ok, reason = ci.gene_lane_admissible(
        _target(target_components=[_comp(component_type="NUCLEIC ACID")]))
    assert not ok and "not_PROTEIN" in reason


def test_a_NON_HUMAN_component_is_refused_even_when_the_target_says_human():
    """The target row can say 9606 while its component is another organism."""
    ok, reason = ci.gene_lane_admissible(
        _target(target_components=[_comp(component_taxon=10090)]))
    assert not ok and "component_taxon" in reason


@pytest.mark.parametrize("n", [0, 2, 3])
def test_anything_other_than_EXACTLY_ONE_component_is_refused(n):
    ok, reason = ci.gene_lane_admissible(
        _target(target_components=[_comp() for _ in range(n)]))
    assert not ok and "exactly_one_component" in reason


def test_a_non_single_protein_target_type_is_refused():
    ok, reason = ci.gene_lane_admissible(_target(target_type="PROTEIN COMPLEX"))
    assert not ok and "not_SINGLE_PROTEIN" in reason


# --------------------------------------------------------------------------- #
# A coarser cache is REFUSED, never downgraded.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("field", ci.REQUIRED_TARGET_FIELDS)
def test_a_cache_that_cannot_answer_an_identity_question_is_refused(field):
    t = _target()
    del t[field]
    ok, reason = ci.gene_lane_admissible(t)
    assert not ok and "cache_too_coarse" in reason


@pytest.mark.parametrize("field", ci.REQUIRED_COMPONENT_FIELDS)
def test_a_component_missing_an_identity_field_is_refused(field):
    c = _comp()
    del c[field]
    ok, reason = ci.gene_lane_admissible(_target(target_components=[c]))
    assert not ok and "cache_too_coarse" in reason


def test_the_coarse_cache_check_names_the_missing_fields():
    rep = Report()
    coarse = _target()
    del coarse["species_group_flag"]
    ci.check_cache_is_not_coarser_than_the_contract(rep, [coarse])
    assert _failed(rep), "a coarser cache must FAIL, not degrade"


def test_a_complete_cache_passes_the_coarseness_check():
    rep = Report()
    ci.check_cache_is_not_coarser_than_the_contract(rep, [_target()])
    assert not _failed(rep)


# --------------------------------------------------------------------------- #
# The gene-lane gate, as a verifier check.
# --------------------------------------------------------------------------- #
def test_a_wrongly_admitted_mouse_target_FAILS_the_gene_lane_check():
    rep = Report()
    mouse = _target(target_chembl_id="CHEMBL_MOUSE", target_taxon=10090)
    ci.check_gene_lane_identity(rep, targets=[mouse],
                                admitted_entity_ids={"CHEMBL_MOUSE"})
    assert _failed(rep)


def test_a_mouse_target_that_was_NOT_admitted_does_not_fail_the_check():
    """Refusing it is correct; only ADMITTING it is the defect."""
    rep = Report()
    mouse = _target(target_chembl_id="CHEMBL_MOUSE", target_taxon=10090)
    ci.check_gene_lane_identity(rep, targets=[mouse], admitted_entity_ids=set())
    assert not _failed(rep)


# --------------------------------------------------------------------------- #
# One assertion per mec_id, with its context.
# --------------------------------------------------------------------------- #
def test_two_assertions_for_ONE_mec_id_is_double_counting():
    rep = Report()
    rows = [{"mec_id": 7, "variant_or_context": "a", "assertion_id": "x"},
            {"mec_id": 7, "variant_or_context": "a", "assertion_id": "y"}]
    ci.check_one_assertion_per_mechanism(rep, rows)
    assert any("ONE assertion per ChEMBL mec_id" in n for n in _failed(rep))


def test_one_assertion_per_mec_id_passes():
    rep = Report()
    rows = [{"mec_id": 7, "variant_or_context": "a"},
            {"mec_id": 8, "variant_or_context": "b"}]
    ci.check_one_assertion_per_mechanism(rep, rows)
    assert not _failed(rep)


def test_an_assertion_that_lost_its_variant_context_is_refused():
    rep = Report()
    ci.check_one_assertion_per_mechanism(rep, [{"mec_id": 7}])
    assert any("variant/context" in n for n in _failed(rep))


# --------------------------------------------------------------------------- #
# Verbatim action_type; translation at view time only.
# --------------------------------------------------------------------------- #
def test_an_assertion_that_lost_the_verbatim_action_type_is_refused():
    rep = Report()
    ci.check_verbatim_action_type(rep, [{"assertion_id": "a", "action_type_source": None}])
    assert any("VERBATIM" in n for n in _failed(rep))


def test_a_row_carrying_ONLY_the_interpretation_is_refused():
    """If the source string is gone, nobody can re-translate under a new vocabulary."""
    rep = Report()
    ci.check_verbatim_action_type(
        rep, [{"assertion_id": "a", "intervention_effect": "functional_inhibition"}])
    assert any("SEPARABLE" in n for n in _failed(rep))


def test_a_verbatim_row_with_its_interpretation_alongside_passes():
    rep = Report()
    ci.check_verbatim_action_type(rep, [{
        "assertion_id": "a", "action_type_source": "DISRUPTING AGENT",
        "intervention_effect": "unknown"}])
    assert not _failed(rep)


# --------------------------------------------------------------------------- #
# max_phase: context only, mutation-refused.
# --------------------------------------------------------------------------- #
def test_an_ordering_that_names_max_phase_FAILS():
    rep = Report()
    ci.check_max_phase_is_context_only(rep, [], ordering_keys=["arm_rank", "max_phase"])
    assert any("CONTEXT ONLY" in n for n in _failed(rep))


def test_a_row_declaring_max_phase_rankable_FAILS():
    rep = Report()
    ci.check_max_phase_is_context_only(
        rep, [{"max_phase_may_rank": True, "max_phase_source_record_id": "r"}],
        ordering_keys=["arm_rank"])
    assert any("rankable or gating" in n for n in _failed(rep))


def test_a_recorded_phase_that_lost_its_exact_value_FAILS():
    rep = Report()
    ci.check_max_phase_is_context_only(
        rep, [{"max_phase_state": "recorded", "max_phase_source_string": None,
               "max_phase_source_record_id": "r"}],
        ordering_keys=["arm_rank"])
    assert any("exact source string" in n for n in _failed(rep))


def test_a_row_claiming_development_state_preserves_max_phase_FAILS():
    rep = Report()
    ci.check_max_phase_is_context_only(
        rep, [{"development_state_preserves_max_phase": True,
               "max_phase_source_record_id": "r"}],
        ordering_keys=["arm_rank"])
    assert any("does not CLAIM" in n for n in _failed(rep))


def test_a_well_formed_context_only_phase_passes():
    rep = Report()
    ci.check_max_phase_is_context_only(rep, [{
        "max_phase_state": "recorded", "max_phase_source_string": "0.5",
        "max_phase_may_rank": False, "max_phase_may_gate": False,
        "development_state_preserves_max_phase": False,
        "max_phase_source_record_id": "r"}], ordering_keys=["arm_rank"])
    assert not _failed(rep)


# --------------------------------------------------------------------------- #
# Licences are per-source and do not merge.
# --------------------------------------------------------------------------- #
def test_each_source_keeps_its_own_license():
    rep = Report()
    ci.check_license_separation(rep, [
        {"source": "uniprot", "license": "CC BY 4.0", "source_record_id": "u1"},
        {"source": "chembl", "license": "CC BY-SA 3.0", "source_record_id": "c1"}])
    assert not _failed(rep)


def test_a_chembl_record_wearing_the_uniprot_license_is_refused():
    """CC BY 4.0 on a ChEMBL row states terms that are wrong for it."""
    rep = Report()
    ci.check_license_separation(rep, [
        {"source": "chembl", "license": "CC BY 4.0", "source_record_id": "c1"}])
    assert any("ITS OWN source's licence" in n for n in _failed(rep))


def test_a_BLENDED_license_is_refused():
    rep = Report()
    ci.check_license_separation(rep, [
        {"source": "chembl", "license": "CC BY-SA 3.0", "combined_license": "CC BY 4.0",
         "source_record_id": "c1"}])
    assert any("blended" in n for n in _failed(rep))


# --------------------------------------------------------------------------- #
# Namespace typing.
# --------------------------------------------------------------------------- #
def test_a_homogeneous_ensembl_universe_is_refused():
    rep = Report()
    ci.check_namespace_typing(rep, {"universe_is_homogeneous_ensembl": True,
                                    "namespaces_are_split": False})
    assert _failed(rep)


def test_the_typed_split_universe_passes():
    rep = Report()
    ci.check_namespace_typing(rep, {
        "universe_is_homogeneous_ensembl": False, "namespaces_are_split": True,
        "symbol_only_targets": list(ci.SYMBOL_ONLY_TARGETS)})
    assert not _failed(rep)


def test_the_audited_counts_are_pinned():
    assert ci.N_ENSEMBL == 11_522
    assert ci.N_UNSUPPORTED_SYMBOL == 4
    assert ci.SYMBOL_ONLY_TARGETS == ("MTRNR2L1", "MTRNR2L4", "MTRNR2L8", "OCLM")
