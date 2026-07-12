"""A pathway node must bind the enrichment it came from, by HASH.

A node is an inferred lever: nobody perturbed it. Its only claim to relevance is the
enrichment that produced it — which gene set, which release, which universe, which
statistic. A node that names a parent it cannot prove, or names none at all, is not a
hypothesis. It is a claim with nothing behind it.

So every node must either reference a parent enrichment RECORD by its content hash
(``pathway_record_id``, plus the gene-set release and universe hashes), or repeat that
complete binding inline. A dangling parent is refused, a partial reference is refused, and
a reference that disagrees with the parent it names is refused.

The hash is what makes the binding real: ``pathway_record_id`` is the content address of
the enrichment record itself, so a node cannot keep pointing at a parent whose gene set,
universe or method has since changed underneath it.
"""
from __future__ import annotations

import pytest
import science_fixture

from druglink import canonical_number as cn, pathways, science_registry as sr

BINDING_FIELDS = ("pathway_record_id", "gene_set_release_id", "gene_set_sha256",
                  "universe_id", "universe_sha256")
CTLA4 = "ENSG00000163599"


def _enrichment(**over):
    """The parent enrichment: the statistic, the gene-set release, and the universe."""
    enr = {"method_id": "enrich.v1", "desired_arm": "away_from_A",
           "statistic_name": "hypergeometric_odds_ratio",
           "enrichment_value": 4.2,
           "inference_status": "not_calibrated",
           "rounding_rule": "ieee754_float64_no_rounding",
           "gene_set_release": "GO-2026-05",
           "gene_set_sha256": "b" * 64,
           "universe_binding": {"universe_id": "stage2_common_universe",
                                "universe_sha256": "c" * 64, "n_genes": 18000}}
    enr.update(over)
    return enr


def _prog(arm="away_from_A", *, bound=True, **over):
    """A node's own computed evidence, repeating the parent binding inline when bound."""
    prog = {"method_id": "enrich.v1", "desired_arm": arm,
            "statistic_name": "hypergeometric_odds_ratio",
            "enrichment_value": 3.7,
            "inference_status": "not_calibrated",
            "rounding_rule": "ieee754_float64_no_rounding"}
    if bound:
        prog.update({"gene_set_release": "GO-2026-05", "gene_set_sha256": "b" * 64,
                     "universe_binding": {"universe_id": "stage2_common_universe",
                                          "universe_sha256": "c" * 64,
                                          "n_genes": 18000}})
    prog.update(over)
    return prog


def _node(**over):
    # A node states its OWN desired direction. It never inherits one from its pathway.
    node = {"target_ensembl": CTLA4, "target_symbol": "CTLA4",
            "desired_arm": "away_from_A",
            "desired_target_modulation": "decrease",
            "evidence_status": "computed_enrichment_member",
            "programmatic_evidence": _prog()}
    node.update(over)
    return node


def _doc(direct, node, enrichment=None):
    return {
        "schema_version": pathways.PATHWAY_SCHEMA,
        "artifact_class": "analysis",
        "direct_run_id": direct.run_id,
        "direct_run_binding_sha256": direct.binding_sha256,
        "pathways": [{
            "pathway_id": "GO:0042110", "pathway_source": "GO",
            "pathway_source_release": "2026-05",
            "pathway_source_sha256": "a" * 64,
            "computed_enrichment": enrichment or _enrichment(),
            "nodes": [node],
        }],
    }


def _admit(doc, root=None):
    return pathways.admit(doc, artifact_class="analysis", direct=_admit.direct,
                          science_registry_root=root)


# --------------------------------------------------------------------------- #
# The binding travels, and it is a HASH.
# --------------------------------------------------------------------------- #
def test_a_node_carries_the_hash_bound_parent_enrichment(loaded_direct):
    _admit.direct = loaded_direct
    admitted = _admit(_doc(loaded_direct, _node()))

    node = admitted["levers"][0]
    parent = admitted["pathways"][0]

    for field in BINDING_FIELDS:
        assert node[field], f"the node did not carry {field}"

    # The node's parent really is THIS enrichment: same content address.
    assert node["pathway_record_id"] == parent["pathway_record_id"]
    assert len(node["pathway_record_id"]) == 64
    assert node["gene_set_sha256"] == "b" * 64
    assert node["universe_sha256"] == "c" * 64


def test_the_parent_record_id_is_the_content_address_of_the_enrichment(loaded_direct):
    """Change the gene set, the universe or the statistic, and the parent changes."""
    _admit.direct = loaded_direct
    base = _admit(_doc(loaded_direct, _node()))["pathways"][0]["pathway_record_id"]

    other_universe = {"universe_id": "other", "universe_sha256": "e" * 64,
                      "n_genes": 12000}

    # A different gene-set RELEASE is a different parent: the term's membership moved.
    changed = _admit(_doc(loaded_direct,
                          _node(programmatic_evidence=_prog(
                              gene_set_release="GO-2026-06")),
                          _enrichment(gene_set_release="GO-2026-06")))
    assert changed["pathways"][0]["pathway_record_id"] != base

    # A different UNIVERSE is a different parent: the same overlap means something else.
    changed = _admit(_doc(loaded_direct,
                          _node(programmatic_evidence=_prog(
                              universe_binding=other_universe)),
                          _enrichment(universe_binding=other_universe)))
    assert changed["pathways"][0]["pathway_record_id"] != base

    # A different enrichment VALUE is a different parent — and no rounding hides it.
    # 4.200000000000001 is the very next representable float64 above 4.2. One ULP apart,
    # and the content address must still separate them.
    changed = _admit(_doc(loaded_direct, _node(),
                          _enrichment(enrichment_value=4.200000000000001)))
    assert changed["pathways"][0]["pathway_record_id"] != base

    # A different STATISTIC is a different parent.
    changed = _admit(_doc(loaded_direct, _node(),
                          _enrichment(statistic_name="fisher_exact_odds_ratio")))
    assert changed["pathways"][0]["pathway_record_id"] != base


# --------------------------------------------------------------------------- #
# A dangling parent is refused.
# --------------------------------------------------------------------------- #
def test_a_node_with_no_parent_binding_at_all_is_refused(loaded_direct):
    _admit.direct = loaded_direct
    node = _node(programmatic_evidence=_prog(bound=False))  # no gene set, no universe

    with pytest.raises(pathways.PathwayError,
                       match="NO resolvable parent enrichment|dangling"):
        _admit(_doc(loaded_direct, node))


def test_a_partial_parent_reference_is_refused(loaded_direct):
    """Half a binding is not a binding. It is a citation nobody can follow."""
    _admit.direct = loaded_direct
    full = _admit(_doc(loaded_direct, _node()))["levers"][0]
    complete = {f: full[f] for f in BINDING_FIELDS}

    for missing in BINDING_FIELDS:
        partial = {k: v for k, v in complete.items() if k != missing}
        node = _node(parent_enrichment_ref=partial,
                     programmatic_evidence=_prog(bound=False))
        with pytest.raises(pathways.PathwayError, match="missing|parent enrichment"):
            _admit(_doc(loaded_direct, node))


def test_a_parent_reference_that_names_the_wrong_enrichment_is_refused(loaded_direct):
    """A node cannot cite a parent it does not actually descend from."""
    _admit.direct = loaded_direct
    full = _admit(_doc(loaded_direct, _node()))["levers"][0]

    for field in BINDING_FIELDS:
        wrong = {f: full[f] for f in BINDING_FIELDS}
        wrong[field] = "f" * 64 if field.endswith("sha256") else "something_else"
        node = _node(parent_enrichment_ref=wrong)
        with pytest.raises(pathways.PathwayError,
                           match="does not resolve|disagree"):
            _admit(_doc(loaded_direct, node))


def test_a_node_may_reference_its_parent_instead_of_repeating_it(loaded_direct):
    """The reference form is equivalent to the inline form — and just as bound."""
    _admit.direct = loaded_direct
    inline = _admit(_doc(loaded_direct, _node()))["levers"][0]
    ref = {f: inline[f] for f in BINDING_FIELDS}

    node = _node(parent_enrichment_ref=ref, programmatic_evidence=_prog(bound=False))
    referenced = _admit(_doc(loaded_direct, node))["levers"][0]

    for field in BINDING_FIELDS:
        assert referenced[field] == inline[field]


# --------------------------------------------------------------------------- #
# Numbers go through the ONE canonical path.
# --------------------------------------------------------------------------- #
def test_enrichment_values_are_canonicalised_by_the_one_frozen_rule(loaded_direct):
    _admit.direct = loaded_direct
    admitted = _admit(_doc(loaded_direct, _node()))

    parent = admitted["pathways"][0]
    node = admitted["levers"][0]

    assert parent["computed_enrichment_value"] == cn.canonical_number(4.2)
    assert node["programmatic_enrichment_value"] == cn.canonical_number(3.7)
    assert parent["computed_rounding_rule_id"] == cn.ROUNDING_RULE_ID
    assert node["programmatic_rounding_rule_id"] == cn.ROUNDING_RULE_ID

    # The document hash is taken over canonical bytes, so it cannot drift with a
    # serialiser's rendering of a float.
    assert len(admitted["ref"]["pathway_document_sha256"]) == 64
    assert admitted["ref"]["rounding_rule_id"] == cn.ROUNDING_RULE_ID


# --------------------------------------------------------------------------- #
# Science references: the FULL triple, resolved, end to end.
# --------------------------------------------------------------------------- #
def test_the_typed_triple_is_preserved_end_to_end(tmp_path, loaded_direct):
    """An id alone is not a binding. The hash and the type must travel WITH it."""
    _admit.direct = loaded_direct
    root = str(tmp_path / "registry")
    refs = science_fixture.make(root)

    node = _node(science_evidence_refs=[refs["sci_1"]])
    doc = _doc(loaded_direct, node)
    doc["pathways"][0]["science_evidence_refs"] = [refs["sci_2"], refs["sci_3"]]

    admitted = _admit(doc, root=root)

    on_node = admitted["levers"][0]["science_evidence_refs"]
    on_pathway = admitted["pathways"][0]["science_evidence_refs"]

    assert on_node == [refs["sci_1"]]
    assert on_pathway == [refs["sci_2"], refs["sci_3"]]
    assert admitted["levers"][0]["n_science_evidence_refs"] == 1
    assert admitted["pathways"][0]["n_science_evidence_refs"] == 2

    # Every carried reference is a complete triple, and every one really resolves.
    for ref in on_node + on_pathway:
        assert set(ref) == set(sr.REF_FIELDS)
        assert sr.resolve(root, ref)["science_evidence_id"] == ref["science_evidence_id"]

    assert admitted["ref"]["science_evidence_records_are_resolved_and_rehashed"] is True
    assert admitted["ref"]["every_node_binds_a_hash_bound_parent_enrichment"] is True


def test_a_node_citing_an_altered_record_is_refused(tmp_path, loaded_direct):
    """Fail CLOSED: the node is not emitted with its evidence quietly dropped."""
    import os

    _admit.direct = loaded_direct
    root = str(tmp_path / "registry")
    refs = science_fixture.make(root)
    entry = sr.load_index(root)["records"]["sci_1"]
    with open(os.path.join(root, entry["structured_file"]), "wb") as fh:
        fh.write(b'{"claim":"substituted"}')

    doc = _doc(loaded_direct, _node(science_evidence_refs=[refs["sci_1"]]))
    with pytest.raises(sr.ScienceRegistryError, match="ALTERED"):
        _admit(doc, root=root)


def test_a_node_citing_a_missing_record_is_refused(tmp_path, loaded_direct):
    _admit.direct = loaded_direct
    root = str(tmp_path / "registry")
    science_fixture.make(root)

    doc = _doc(loaded_direct, _node(science_evidence_refs=[
        {"science_evidence_id": "sci_ghost", "science_evidence_sha256": "d" * 64,
         "record_type": "mechanistic_rationale"}]))
    with pytest.raises(sr.ScienceRegistryError, match="not in the registry|dangling"):
        _admit(doc, root=root)


def test_a_resolvable_science_record_still_cannot_stand_in_for_the_enrichment(
        tmp_path, loaded_direct):
    """Interpretation is provenance. Even PERFECT provenance is not a statistic.

    The record resolves, re-hashes and is correctly typed — and it still cannot supply the
    node's computed evidence. A citation is not a measurement.
    """
    _admit.direct = loaded_direct
    root = str(tmp_path / "registry")
    refs = science_fixture.make(root)

    node = _node(science_evidence_refs=[refs["sci_1"]])
    del node["programmatic_evidence"]

    with pytest.raises(pathways.PathwayError,
                       match="Claude Science reading is provenance, not enrichment"):
        _admit(_doc(loaded_direct, node), root=root)
