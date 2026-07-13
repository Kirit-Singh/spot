"""The bound per-target IDENTITY/ASSAY artifact — the Stage-2 -> Stage-3 handoff.

The bundle shipped arm VALUES with no bound statement of WHAT each target_id IS. A consumer had
to infer the namespace from the SHAPE OF THE KEY — the one inference `identity.py` exists to
forbid, because four of this release's targets are bare SYMBOLS whose keys look nothing like the
other 11,522.

Derived from the ALREADY-ADMITTED identity table. Never parsed.
"""
from __future__ import annotations

import hashlib
import json
import os

import pytest
from direct import target_identity as ti
from direct.hashing import canonical_json, content_hash, sha256_hex


class _Ident:
    def __init__(self, ns, symbol, ensembl=None):
        self.target_id_namespace = ns
        self.target_symbol = symbol
        self.target_ensembl = ensembl


def _table():
    return {
        "ENSG00000000001": _Ident(ti.NAMESPACE_ENSEMBL, "AAA", "ENSG00000000001"),
        "ENSG00000000002": _Ident(ti.NAMESPACE_ENSEMBL, "BBB", "ENSG00000000002"),
        "MTRNR2L8": _Ident(ti.NAMESPACE_SYMBOL, "MTRNR2L8", None),   # a SYMBOL target
    }


class TestTheArtifactShipsInTheBundle:
    def test_the_direct_bundle_ships_it(self, synthetic_run, tmp_path):
        from direct import arm_artifacts, run_arms
        args = synthetic_run()
        args.condition = "StimX"
        args.out_root = str(tmp_path / "d")
        res = run_arms.build_bundle(args)
        path = os.path.join(res["out_dir"], arm_artifacts.TARGET_IDENTITY_FILE)
        assert os.path.exists(path)
        with open(path) as fh:
            doc = json.load(fh)
        assert doc["n_targets"] > 0

    def test_the_SHIPPED_BYTES_are_exactly_the_bytes_the_run_id_BOUND(self, synthetic_run,
                                                                     tmp_path):
        # the raw hash cannot normally exist before the id names the directory; the bytes are
        # deterministic, so they are hashed, bound, then written unchanged
        from direct import arm_artifacts, run_arms
        args = synthetic_run()
        args.condition = "StimX"
        args.out_root = str(tmp_path / "d")
        res = run_arms.build_bundle(args)
        with open(os.path.join(res["out_dir"], "provenance.json")) as fh:
            prov = json.load(fh)
        block = prov["run_binding"]["target_identity"]
        with open(os.path.join(res["out_dir"],
                               arm_artifacts.TARGET_IDENTITY_FILE), "rb") as fh:
            raw = fh.read()
        assert hashlib.sha256(raw).hexdigest() == block["raw_sha256"]
        assert content_hash(json.loads(raw)) == block["canonical_sha256"]

    def test_it_is_INSIDE_the_arm_bundle_run_id(self, synthetic_run, tmp_path):
        from direct import run_arms
        args = synthetic_run()
        args.condition = "StimX"
        args.out_root = str(tmp_path / "d")
        res = run_arms.build_bundle(args)
        with open(os.path.join(res["out_dir"], "provenance.json")) as fh:
            prov = json.load(fh)
        full = sha256_hex(canonical_json(prov["run_binding"]))
        assert prov["arm_bundle_run_id"] == full[:16]

        other = json.loads(json.dumps(prov["run_binding"]))
        other["target_identity"]["raw_sha256"] = "f" * 64
        assert sha256_hex(canonical_json(other))[:16] != prov["arm_bundle_run_id"]

    def test_it_COVERS_every_target_the_bundle_SCORED(self, synthetic_run, tmp_path):
        import pandas as pd
        from direct import arm_artifacts, run_arms
        args = synthetic_run()
        args.condition = "StimX"
        args.out_root = str(tmp_path / "d")
        res = run_arms.build_bundle(args)
        with open(os.path.join(res["out_dir"],
                               arm_artifacts.TARGET_IDENTITY_FILE)) as fh:
            ids = {r["target_id"] for r in json.load(fh)["records"]}
        arms = set(pd.read_parquet(
            os.path.join(res["out_dir"], "arms.parquet"))["target_id"])
        assert arms <= ids, "a scored target with no identity row drops out of the join"


class TestUniquenessAndCompleteness:
    def test_ONE_row_per_target(self):
        doc = ti.build(_table(), condition="Rest", scored_targets=set(_table()))
        seen = [r["target_id"] for r in doc["records"]]
        assert len(seen) == len(set(seen)) == doc["n_targets"]

    def test_a_SCORED_target_with_NO_identity_row_is_REFUSED(self):
        # it would drop out of Stage 3's join and disappear without a trace
        with pytest.raises(ti.TargetIdentityError) as exc:
            ti.build(_table(), condition="Rest",
                     scored_targets=set(_table()) | {"ENSG_NOT_IN_THE_TABLE"})
        assert exc.value.gate == ti.REFUSE_INCOMPLETE
        assert "ENSG_NOT_IN_THE_TABLE" in str(exc.value)

    def test_an_identity_row_the_bundle_NEVER_SCORED_is_REFUSED(self):
        # the quieter error: a missing row makes a target vanish from Stage 3's join; an EXTRA
        # one asserts this bundle measured something it did not. A condition bundle covers ITS
        # OWN targets — the three conditions do not ship the same set.
        with pytest.raises(ti.TargetIdentityError) as exc:
            ti.build(_table(), condition="Rest",
                     scored_targets={"ENSG00000000001"})     # the table has three
        assert exc.value.gate == ti.REFUSE_EXTRANEOUS

    def test_the_bundle_covers_EXACTLY_its_own_condition_not_a_global_union(self):
        # nothing hard-codes a release-wide count: the set is derived and then checked in BOTH
        # directions against what the bundle actually scored
        doc = ti.build(_table(), condition="Rest", scored_targets=set(_table()))
        assert {r["target_id"] for r in doc["records"]} == set(_table())
        assert doc["n_targets"] == len(_table())
        assert doc["condition"] == "Rest"


class TestTheMIXEDNamespaceUniverse:
    """11,522 Ensembl + 4 bare SYMBOL targets. A loader expecting one namespace drops four."""

    def test_both_namespaces_are_COUNTED_not_assumed(self):
        doc = ti.build(_table(), condition="Rest", scored_targets=set(_table()))
        assert doc["n_ensembl_gene_id"] == 2
        assert doc["n_gene_symbol"] == 1
        assert doc["n_ensembl_gene_id"] + doc["n_gene_symbol"] == doc["n_targets"]

    def test_a_SYMBOL_target_keeps_a_NULL_target_ensembl(self):
        doc = ti.build(_table(), condition="Rest", scored_targets=set(_table()))
        sym = next(r for r in doc["records"]
                   if r["target_id_namespace"] == ti.NAMESPACE_SYMBOL)
        assert sym["target_ensembl"] is None
        assert sym["target_symbol"] == "MTRNR2L8"

    def test_a_SYMBOL_row_carrying_an_ENSEMBL_id_is_REFUSED(self):
        # promoting a key prefix into an accession is the guess this lane forbids
        table = dict(_table())
        table["MTRNR2L8"] = _Ident(ti.NAMESPACE_SYMBOL, "MTRNR2L8", "ENSG00000999999")
        with pytest.raises(ti.TargetIdentityError) as exc:
            ti.build(table, condition="Rest", scored_targets=set(table))
        assert exc.value.gate == ti.REFUSE_SYMBOL_HAS_ENSEMBL

    def test_an_UNDECLARED_namespace_is_REFUSED(self):
        table = dict(_table())
        table["X"] = _Ident("entrez_id", "X")
        with pytest.raises(ti.TargetIdentityError) as exc:
            ti.build(table, condition="Rest", scored_targets=set(table))
        assert exc.value.gate == ti.REFUSE_NAMESPACE


class TestTheMODALITYIsDeclaredNotDefaulted:
    def test_every_row_declares_the_EXACT_pinned_modality(self):
        doc = ti.build(_table(), condition="Rest", scored_targets=set(_table()))
        assert doc["observed_perturbation_modality"] == "CRISPRi_knockdown"
        for r in doc["records"]:
            assert r["observed_perturbation_modality"] == "CRISPRi_knockdown"

    def test_a_DEFAULTED_or_ALTERED_modality_is_REFUSED_when_the_SHIPPED_doc_is_REOPENED(self):
        # `build` checks rows it created itself, so ITS modality check can never fire — a gate
        # that validates its own output validates nothing. `verify` runs against the bytes
        # somebody else shipped, which is the only place the check means anything. W10 calls it.
        doc = ti.build(_table(), condition="Rest", scored_targets=set(_table()))
        ti.verify(doc)                                   # honest artifact: admits

        doc["records"][0]["observed_perturbation_modality"] = ""      # defaulted
        with pytest.raises(ti.TargetIdentityError) as exc:
            ti.verify(doc)
        assert exc.value.gate == ti.REFUSE_MODALITY

    def test_an_OVEREXPRESSION_claim_is_REFUSED(self):
        doc = ti.build(_table(), condition="Rest", scored_targets=set(_table()))
        doc["records"][0]["observed_perturbation_modality"] = "CRISPRa_overexpression"
        with pytest.raises(ti.TargetIdentityError) as exc:
            ti.verify(doc)
        assert exc.value.gate == ti.REFUSE_MODALITY
        assert "flips the meaning of every sign" in str(exc.value)

    def test_a_REOPENED_duplicate_row_is_REFUSED(self):
        doc = ti.build(_table(), condition="Rest", scored_targets=set(_table()))
        doc["records"].append(dict(doc["records"][0]))
        with pytest.raises(ti.TargetIdentityError) as exc:
            ti.verify(doc)
        assert exc.value.gate == ti.REFUSE_DUPLICATE_TARGET

    def test_a_REOPENED_incomplete_artifact_is_REFUSED(self):
        doc = ti.build(_table(), condition="Rest", scored_targets=set(_table()))
        with pytest.raises(ti.TargetIdentityError) as exc:
            ti.verify(doc, scored_targets=set(_table()) | {"GHOST"})
        assert exc.value.gate == ti.REFUSE_INCOMPLETE

    def test_the_modality_is_bound_into_the_binding_block(self):
        doc = ti.build(_table(), condition="Rest", scored_targets=set(_table()))
        block = ti.binding_block(doc, "a" * 64)
        assert block["observed_perturbation_modality"] == "CRISPRi_knockdown"
        assert block["modality_rule_id"]



class TestTheProducerVerifierIntegration:
    """The EXACT contract W10 verifies against, and the format mismatch it must not create.

    The producer emits `target_identity.json`. That is the only shape there is. A verifier that
    expected a parquet would either fail to find the artifact or WRITE ONE OF ITS OWN — and a
    verifier that creates the file it is supposed to be checking has checked its own work.
    """

    @pytest.fixture
    def bundle(self, synthetic_run, tmp_path):
        from direct import run_arms
        args = synthetic_run()
        args.condition = "StimX"
        args.out_root = str(tmp_path / "d")
        return run_arms.build_bundle(args)["out_dir"]

    def test_the_file_is_JSON_and_there_is_NO_parquet_variant(self, bundle):
        import os
        assert os.path.exists(os.path.join(bundle, "target_identity.json"))
        assert not os.path.exists(os.path.join(bundle, "target_identity.parquet"))

    def test_ONE_shared_constant_not_two_literals(self):
        # two literals for one filename is how `.json` quietly becomes `.parquet` in a test
        from direct import arm_artifacts
        assert arm_artifacts.TARGET_IDENTITY_FILE is ti.TARGET_IDENTITY_FILE
        assert arm_artifacts.TARGET_IDENTITY_SCHEMA == ti.SCHEMA_VERSION

    def test_it_is_in_VERIFIED_PATHS_so_the_verifier_READS_it_BACK(self, bundle):
        from direct import arm_artifacts
        assert ti.TARGET_IDENTITY_FILE in arm_artifacts.VERIFIED_PATHS

    def test_it_is_in_the_bundle_ARTIFACT_MANIFEST_with_its_raw_hash(self, bundle):
        from direct import arm_artifacts
        names = {e["name"]: e for e in arm_artifacts.artifact_manifest(bundle)}
        assert ti.TARGET_IDENTITY_FILE in names
        assert len(names[ti.TARGET_IDENTITY_FILE]["raw_sha256"]) == 64

    def test_a_CONSUMER_reads_the_PRODUCER_BYTES_in_place_and_they_ADMIT(self, bundle):
        import pandas as pd
        arms = set(pd.read_parquet(os.path.join(bundle, "arms.parquet"))["target_id"])
        loaded = ti.load(bundle, scored_targets=arms)     # W10 / P2S / W3 entry point
        assert loaded["doc"]["schema_version"] == ti.SCHEMA_VERSION
        assert len(loaded["raw_sha256"]) == 64

    def test_the_LOADED_hash_is_the_hash_the_RUN_BOUND(self, bundle):
        loaded = ti.load(bundle)
        with open(os.path.join(bundle, "provenance.json")) as fh:
            block = json.load(fh)["run_binding"]["target_identity"]
        assert loaded["raw_sha256"] == block["raw_sha256"]
        assert loaded["canonical_sha256"] == block["canonical_sha256"]

    def test_reading_it_does_NOT_CREATE_OR_OVERWRITE_anything(self, bundle):
        # a verifier that writes the artifact it is checking has checked its own work
        before = {n: os.path.getmtime(os.path.join(bundle, n))
                  for n in sorted(os.listdir(bundle))}
        ti.load(bundle)
        after = {n: os.path.getmtime(os.path.join(bundle, n))
                 for n in sorted(os.listdir(bundle))}
        assert before == after, "loading the artifact must not touch the bundle"

    def test_a_MUTATION_is_made_on_a_COPY_and_the_PRODUCER_BYTES_survive(self, bundle,
                                                                        tmp_path):
        # the shipped bytes are evidence; a mutation test that edits them in place destroys the
        # very thing it is supposed to be attacking
        original = ti.load(bundle)["raw_sha256"]

        copy_dir = tmp_path / "attack"
        copy_dir.mkdir()
        with open(os.path.join(bundle, ti.TARGET_IDENTITY_FILE)) as fh:
            doc = json.load(fh)
        doc["records"][0]["observed_perturbation_modality"] = "CRISPRa_overexpression"
        with open(copy_dir / ti.TARGET_IDENTITY_FILE, "w") as fh:
            json.dump(doc, fh)

        with pytest.raises(ti.TargetIdentityError) as exc:
            ti.load(str(copy_dir))
        assert exc.value.gate == ti.REFUSE_MODALITY
        assert ti.load(bundle)["raw_sha256"] == original     # untouched

    def test_a_MISSING_artifact_is_REFUSED_not_INFERRED(self, tmp_path):
        # identity is not reconstructable from the masks or from the shape of a target_id: the
        # release perturbs four bare SYMBOLS whose keys look nothing like the other 11,522, so a
        # string heuristic is wrong for exactly the rows nobody thinks about
        with pytest.raises(ti.TargetIdentityError) as exc:
            ti.load(str(tmp_path))
        assert exc.value.gate == ti.REFUSE_ABSENT
