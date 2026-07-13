"""THE per-target identity/assay artifact — W10 verifies the PRODUCER's real emitted bytes.

The producer (9bd5895) emits target_identity.json. These tests build a REAL bundle, run W10's
gate against the artifact the producer actually wrote, and — for the refusals — mutate COPIES
of that file in place. Nothing here replaces the producer's bytes with a verifier reference.
"""
from __future__ import annotations

import json
import os
import sys

import pandas as pd
import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_ROOT, "analysis", "direct"))
sys.path.insert(0, os.path.join(_ROOT, "tests", "direct"))

import verify_target_identity as TI  # noqa: E402

LOCK = os.path.join(_ROOT, "analysis", "stage02_solver_lock.txt")


@pytest.fixture
def bundle(synthetic_run, tmp_path):
    """A real Direct bundle whose target_identity.json was written BY THE PRODUCER."""
    import fixtures_direct as F
    from direct import run_arms
    prod = synthetic_run()
    prod.condition, prod.env_lock = F.CONDITION, LOCK
    prod.out_root = str(tmp_path / "arms")
    res = run_arms.build_bundle(prod)
    bundle_dir = res["out_dir"]
    assert os.path.exists(os.path.join(bundle_dir, TI.TARGET_IDENTITY_FILE)), \
        "the producer did not emit target_identity.json"
    prov = json.load(open(os.path.join(bundle_dir, "provenance.json")))
    arms = pd.read_parquet(os.path.join(bundle_dir, "arms.parquet"))
    arm_ids = set(map(str, arms["target_id"].unique()))
    return bundle_dir, prod.de_main, prod.condition, arm_ids, prov["run_binding"]


def _run(bundle):
    bundle_dir, de_main, condition, arm_ids, binding = bundle
    rep = TI._MiniReport()
    TI.gate_bundle(bundle_dir, de_main, condition, arm_ids, binding, rep)
    return rep


def _mutate_json(bundle_dir, fn):
    path = os.path.join(bundle_dir, TI.TARGET_IDENTITY_FILE)
    doc = json.load(open(path))
    fn(doc)
    with open(path, "w") as fh:
        json.dump(doc, fh)


class TestTheProducerArtifactAdmits:
    def test_the_producer_emitted_artifact_passes_every_gate(self, bundle):
        rep = _run(bundle)
        assert rep.failed == [], rep.failed
        assert len(rep.gates) >= 8

    def test_it_is_a_MIXED_namespace_bundle_so_the_symbol_path_is_exercised(self, bundle):
        bundle_dir = bundle[0]
        doc = json.load(open(os.path.join(bundle_dir, TI.TARGET_IDENTITY_FILE)))
        assert doc["n_gene_symbol"] >= 1 and doc["n_ensembl_gene_id"] >= 1, \
            "the fixture must exercise both namespaces"

    def test_W10_re_derives_the_same_identity_the_producer_emitted(self, bundle):
        # the exact producer-verifier integration check: W10 independently re-derives the
        # rows from the SOURCE, and the producer's declared hash matches W10's re-derivation
        bundle_dir, de_main, condition, _, binding = bundle
        my_doc = TI.build_doc(de_main, condition)
        assert TI.content_sha256(my_doc) == binding["target_identity"]["canonical_sha256"]
        producer = json.load(open(os.path.join(bundle_dir, TI.TARGET_IDENTITY_FILE)))
        assert producer["records"] == my_doc["records"]


class TestEveryMutationOfTheProducerFileRefuses:
    def _failed(self, bundle, substring):
        return any(substring in g for g in _run(bundle).failed)

    def test_a_MISSING_artifact_refuses(self, bundle):
        os.remove(os.path.join(bundle[0], TI.TARGET_IDENTITY_FILE))
        assert self._failed(bundle, "ships a target_identity artifact")

    def test_a_DUPLICATE_target_refuses(self, bundle):
        _mutate_json(bundle[0],
                     lambda d: d["records"].append(dict(d["records"][0])))
        assert self._failed(bundle, "appears exactly once")

    def test_a_MISSING_target_refuses(self, bundle):
        _mutate_json(bundle[0], lambda d: d["records"].pop())
        assert self._failed(bundle, "EXACTLY this bundle's arm target set")

    def test_an_EXTRA_target_refuses(self, bundle):
        def add(d):
            r = dict(d["records"][0])
            r["target_id"] = "ENSG99999999999"
            d["records"].append(r)
        _mutate_json(bundle[0], add)
        assert self._failed(bundle, "EXACTLY this bundle's arm target set")

    def test_an_ALTERED_modality_refuses(self, bundle):
        _mutate_json(bundle[0], lambda d: d["records"][0].update(
            observed_perturbation_modality="CRISPRa"))
        assert self._failed(bundle, "EXACTLY CRISPRi_knockdown")

    def test_a_DEFAULTED_modality_at_the_DOC_level_refuses(self, bundle):
        _mutate_json(bundle[0], lambda d: d.update(
            observed_perturbation_modality="something_else"))
        assert self._failed(bundle, "EXACTLY CRISPRi_knockdown")

    def test_an_UNKNOWN_namespace_refuses(self, bundle):
        _mutate_json(bundle[0], lambda d: d["records"][0].update(
            target_id_namespace="made_up"))
        assert self._failed(bundle, "namespace RE-DERIVES from the source")

    def test_a_DISAGREEING_symbol_refuses(self, bundle):
        _mutate_json(bundle[0], lambda d: d["records"][0].update(
            target_symbol="WRONG_SYMBOL"))
        assert self._failed(bundle, "agrees with the re-derived source identity")

    def test_a_gene_symbol_row_with_a_NON_NULL_ensembl_refuses(self, bundle):
        def bad(d):
            sym = next((r for r in d["records"]
                        if r["target_id_namespace"] == "gene_symbol"), None)
            assert sym is not None
            sym["target_ensembl"] = "ENSG00000000001"
        _mutate_json(bundle[0], bad)
        assert self._failed(bundle, "agrees with the re-derived source identity")

    def test_a_MISCOUNTED_namespace_declaration_refuses(self, bundle):
        _mutate_json(bundle[0], lambda d: d.update(n_gene_symbol=999))
        assert self._failed(bundle, "recount from the rows")

    def test_a_TAMPERED_row_breaks_the_bound_HASH(self, bundle):
        # editing any row moves the canonical hash away from what the run bound
        _mutate_json(bundle[0], lambda d: d["records"][0].update(target_symbol="X"))
        assert self._failed(bundle, "RE-DERIVES from the shipped document")


class TestTheReleaseUnionGate:
    def test_a_namespace_that_CONFLICTS_across_conditions_refuses(self):
        rep = TI._MiniReport()
        TI.gate_release_union([
            [{"target_id": "X", "target_id_namespace": "ensembl_gene_id"}],
            [{"target_id": "X", "target_id_namespace": "gene_symbol"}]], rep)
        assert any("same in every condition" in g for g in rep.failed)

    def test_an_all_ensembl_union_is_not_MIXED(self):
        rep = TI._MiniReport()
        TI.gate_release_union(
            [[{"target_id": "ENSG1", "target_id_namespace": "ensembl_gene_id"}]], rep)
        assert any("MIXED namespace" in g for g in rep.failed)

    def test_the_production_universe_is_11522_ensembl_plus_4_symbol(self):
        rep = TI._MiniReport()
        TI.gate_release_union([
            [{"target_id": f"ENSG{i:011d}", "target_id_namespace": "ensembl_gene_id"}
             for i in range(TI.RELEASE_UNION_ENSEMBL)]
            + [{"target_id": s, "target_id_namespace": "gene_symbol"}
               for s in ("MTRNR2L1", "MTRNR2L4", "MTRNR2L8", "OCLM")]],
            rep, expect_production_universe=True)
        assert rep.failed == [], rep.failed

    def test_the_wrong_production_count_refuses(self):
        rep = TI._MiniReport()
        TI.gate_release_union([
            [{"target_id": f"ENSG{i:011d}", "target_id_namespace": "ensembl_gene_id"}
             for i in range(100)]
            + [{"target_id": s, "target_id_namespace": "gene_symbol"}
               for s in ("MTRNR2L1", "MTRNR2L4", "MTRNR2L8", "OCLM")]],
            rep, expect_production_universe=True)
        assert any("11,522 ensembl + 4 gene_symbol" in g for g in rep.failed)
