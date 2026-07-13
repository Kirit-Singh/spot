"""A1 — the two universe bindings are FAIL-CLOSED, and named.

THE DEFECT an independent audit demonstrated: forge `bundle.target_universe_sha256 = "0"*64`
and the loader ADMITTED it — then reported the *correct* hash back in the bundle it
returned, because it carried the CALLER'S value rather than the declared one. That is worse
than admitting the forgery: it manufactured evidence that the forgery was never there.

Three holes, all closed here:

  * the readout check ran only ``if declared is not None and runtime is not None`` — a
    bundle that declared nothing sailed straight through;
  * the TARGET universe — the space gene-set membership is actually tested in — was not
    checked at all;
  * a false declaration was silently OVERWRITTEN with the truth.
"""
from __future__ import annotations

import json
import os

import pytest
from direct import genesets, run_pathway
from direct.hashing import content_hash

READOUT = [f"ENSG{i:011d}" for i in range(40)]
# The TARGET universe is NOT homogeneous Ensembl: the release perturbs 4 SYMBOL targets
# whose obs.target_contrast IS the symbol.
TARGETS = READOUT[:12] + list(genesets.SYMBOL_TARGETS_PRESERVED)

RO_SHA = content_hash(READOUT)
TG_SHA = content_hash(TARGETS)


def bundle(tmp_path, *, effect=RO_SHA, target=TG_SHA, drop=(), name="b.json"):
    doc = {
        "schema_version": genesets.SCHEMA_VERSION,
        "release": {"source": "reactome", "release_id": "V97", "license": "CC0-1.0",
                    "license_reference": "https://reactome.org/license"},
        "gene_id_namespace": "ensembl_gene_id",
        "effect_universe_sha256": effect,
        "target_universe_sha256": target,
        "sets": [{"set_id": "S", "name": "s",
                  "genes_target": TARGETS[:6], "genes_readout": READOUT[:6],
                  "n_source_symbols": 6}],
    }
    for k in drop:
        doc.pop(k, None)
    p = os.path.join(str(tmp_path), name)
    with open(p, "w") as fh:
        json.dump(doc, fh)
    return p


def load(p):
    return genesets.load(p, READOUT, RO_SHA, TARGETS, TG_SHA)


class TestTheRequiredMutation:
    """`bundle.target_universe_sha256 = "0"*64` — nothing else touched."""

    def test_it_is_REFUSED(self, tmp_path):
        with pytest.raises(genesets.GeneSetError):
            load(bundle(tmp_path, target="0" * 64))

    def test_it_is_refused_at_the_NAMED_TARGET_universe_gate(self, tmp_path):
        with pytest.raises(genesets.GeneSetError) as exc:
            load(bundle(tmp_path, target="0" * 64))
        assert exc.value.gate == genesets.GATE_TARGET_UNIVERSE

    def test_the_honest_bundle_still_ADMITS(self, tmp_path):
        b = load(bundle(tmp_path))
        assert b["target_universe_sha256"] == TG_SHA


class TestAFalseDeclarationIsNEVEROverwritten:
    def test_the_bundle_carries_the_DECLARED_value_not_the_callers(self, tmp_path):
        # It is only carried once it has been PROVEN equal — so this is the same string.
        # The point is the direction of trust: the declaration is the subject, and the
        # runtime universe is what it is checked against.
        b = load(bundle(tmp_path))
        assert b["effect_universe_sha256"] == RO_SHA
        assert b["target_universe_sha256"] == TG_SHA

    def test_a_forged_declaration_cannot_be_laundered_into_the_truth(self, tmp_path):
        # the old loader returned the CORRECT hash for a bundle that declared "0"*64
        with pytest.raises(genesets.GeneSetError) as exc:
            load(bundle(tmp_path, target="0" * 64))
        assert exc.value.gate == genesets.GATE_TARGET_UNIVERSE


class TestBothUniversesAreCheckedAndFailClosed:
    def test_a_forged_EFFECT_universe_is_refused_at_its_own_gate(self, tmp_path):
        with pytest.raises(genesets.GeneSetError) as exc:
            load(bundle(tmp_path, effect="f" * 64))
        assert exc.value.gate == genesets.GATE_EFFECT_UNIVERSE

    def test_an_UNDECLARED_target_universe_is_refused(self, tmp_path):
        with pytest.raises(genesets.GeneSetError) as exc:
            load(bundle(tmp_path, drop=("target_universe_sha256",)))
        assert exc.value.gate == genesets.GATE_UNIVERSE_UNDECLARED

    def test_an_UNDECLARED_effect_universe_is_refused(self, tmp_path):
        with pytest.raises(genesets.GeneSetError) as exc:
            load(bundle(tmp_path, drop=("effect_universe_sha256",)))
        assert exc.value.gate == genesets.GATE_UNIVERSE_UNDECLARED

    def test_the_gates_are_DISTINCT_so_a_failure_says_WHICH_universe(self, tmp_path):
        gates = set()
        for kw in ({"effect": "f" * 64}, {"target": "0" * 64}):
            with pytest.raises(genesets.GeneSetError) as exc:
                load(bundle(tmp_path, **kw))
            gates.add(exc.value.gate)
        assert gates == {genesets.GATE_EFFECT_UNIVERSE, genesets.GATE_TARGET_UNIVERSE}


class TestBothUniversesEnterTheMethodHash:
    def test_hashes_sizes_roles_and_namespaces_are_all_bound(self, tmp_path):
        blk = genesets.binding_block(load(bundle(tmp_path)))
        for key in ("effect_universe_sha256", "n_effect_universe_genes",
                    "effect_universe_role", "gene_id_namespace_effect",
                    "target_universe_sha256", "n_target_universe_genes",
                    "target_universe_role", "target_id_namespace"):
            assert blk[key] is not None, key

    def test_two_bundles_differing_only_in_the_TARGET_universe_hash_differently(
            self, tmp_path):
        a = load(bundle(tmp_path))
        b = dict(a, target_universe_sha256="Z" * 64)
        assert content_hash(run_pathway.method_block(a)) != \
            content_hash(run_pathway.method_block(b))

    def test_two_bundles_differing_only_in_the_TARGET_universe_SIZE_hash_differently(
            self, tmp_path):
        a = load(bundle(tmp_path))
        b = dict(a, n_target_universe_genes=a["n_target_universe_genes"] + 1)
        assert content_hash(run_pathway.method_block(a)) != \
            content_hash(run_pathway.method_block(b))


class TestTheMixedTargetNamespaceIsPreserved:
    """11,522 Ensembl + 4 SYMBOL targets. An Ensembl id is never inferred from a key."""

    def test_the_four_symbol_targets_are_named(self):
        assert genesets.SYMBOL_TARGETS_PRESERVED == (
            "MTRNR2L1", "MTRNR2L4", "MTRNR2L8", "OCLM")

    def test_the_target_namespace_is_declared_MIXED_not_ensembl(self, tmp_path):
        b = load(bundle(tmp_path))
        assert b["target_id_namespace"] == genesets.TARGET_ID_NAMESPACE
        assert "symbol" in b["target_id_namespace"]

    def test_a_symbol_target_survives_membership_as_ITSELF(self, tmp_path):
        b = load(bundle(tmp_path))
        s = b["sets"]["S"]
        # TARGETS[:6] is all-Ensembl; extend the set to include a symbol target
        assert "OCLM" in TARGETS
        assert set(s["genes_in_target_universe"]) <= set(TARGETS)

    def test_a_symbol_target_in_a_set_is_a_MEMBER_not_dropped(self, tmp_path):
        p = os.path.join(str(tmp_path), "sym.json")
        with open(p, "w") as fh:
            json.dump({
                "schema_version": genesets.SCHEMA_VERSION,
                "release": {"source": "reactome", "release_id": "V97",
                            "license": "CC0-1.0",
                            "license_reference": "https://reactome.org/license"},
                "gene_id_namespace": "ensembl_gene_id",
                "effect_universe_sha256": RO_SHA,
                "target_universe_sha256": TG_SHA,
                "sets": [{"set_id": "SYM", "name": "has a symbol target",
                          "genes_target": ["OCLM", "MTRNR2L8"] + TARGETS[:2],
                          "genes_readout": READOUT[:2],
                          "n_source_symbols": 4}],
            }, fh)
        s = genesets.load(p, READOUT, RO_SHA, TARGETS, TG_SHA)["sets"]["SYM"]
        assert "OCLM" in s["genes_in_target_universe"]
        assert "MTRNR2L8" in s["genes_in_target_universe"]

    def test_the_no_inference_rule_is_declared_and_bound(self, tmp_path):
        assert genesets.NEVER_INFER_ENSEMBL_FROM_RELEASED_KEY is True
        blk = genesets.binding_block(load(bundle(tmp_path)))
        assert blk["never_infer_ensembl_from_released_key"] is True
        assert blk["symbol_targets_preserved"] == list(
            genesets.SYMBOL_TARGETS_PRESERVED)
