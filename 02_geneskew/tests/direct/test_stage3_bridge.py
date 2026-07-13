"""THE TWO ATTACKS THAT BEAT SELF-CONSISTENCY, and the reconstruction that stops them.

The previous verifier checked that the artifact hashed to what it claimed and that each row's
direction re-derived from THE VALUE PRINTED ON THAT ROW. Both attacks walk straight through:

  1. COHERENT RESEAL — flip a value, coherently flip the direction and class it implies,
     recompute the hash. Every internal check agrees. The document is perfectly consistent; it
     is simply no longer a statement about the experiment.
  2. FORGED PATHWAY CONTEXT — the contexts were never read at all, so a gene set could declare
     itself a CRISPRi target row with an arm value and a drug direction, and be admitted.

A verifier that only asks "does this agree with itself" cannot tell evidence from fiction,
because fiction can be made to agree with itself. So the bridge verifier REBUILDS every row
and context from the admitted native bytes.

Every bundle here is a FIXTURE. What is real is the refusal.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

import pytest
from direct import stage3_bridge as B
from direct import stage3_rows as S

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "analysis", "direct"))
import verify_stage3_bridge as V  # noqa: E402

CTX = {"from_condition": "Rest", "to_condition": "Stim48hr"}
ARM = "temporal|PRG-1|increase|from_condition=Rest|to_condition=Stim48hr"
UNIVERSE = {"ENSG00000111111": "ensembl_gene_id", "OCLM": "gene_symbol"}


def _sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _native_temporal(root, value=0.5):
    """A native temporal bundle: a bound ranking + the base_records it joins to."""
    d = os.path.join(root, "temporal", "Rest__Stim48hr")
    os.makedirs(os.path.join(d, "rankings"), exist_ok=True)
    with open(os.path.join(d, "arm_bundle.json"), "w") as fh:
        json.dump({"schema_version": "spot.stage02_temporal_arm_bundle.v1",
                   "bundle_id": "T-1", "lane": "temporal", "context": CTX,
                   "base_records": [{"base_key": "PRG-1|ENSG00000111111",
                                     "target_id": "ENSG00000111111",
                                     "target_id_namespace": "ensembl_gene_id",
                                     "target_symbol": "SYM", "target_ensembl":
                                     "ENSG00000111111",
                                     "perturbation_modality": "CRISPRi_knockdown"}]}, fh)
    with open(os.path.join(d, "rankings", "PRG-1__increase.json"), "w") as fh:
        json.dump({"records": [{"target_id": "ENSG00000111111",
                                "base_key": "PRG-1|ENSG00000111111",
                                "arm_key": ARM, "arm_value": value,
                                "evaluable": True, "rank": 1}]}, fh)
    return d


def _bindings(root, d):
    rel = os.path.relpath(d, root).replace(os.sep, "/")
    return {
        "native_bundles": {rel: {
            "lane": "temporal", "bundle_id": "T-1", "context": CTX,
            "identity_source": {"kind": "base_records", "file": "arm_bundle.json"},
            "files": {"arm_bundle.json": _sha(os.path.join(d, "arm_bundle.json")),
                      "rankings/PRG-1__increase.json":
                          _sha(os.path.join(d, "rankings", "PRG-1__increase.json"))},
        }},
        "lane_admissions": {"temporal": {"native_verdict": "ADMIT", "report_id": "r-1"}},
        "stage1": {"release_canonical_sha256": "s" * 64},
        "identity_source": {"temporal": "base_records"},
    }


def _rows(value=0.5):
    return [S.build_row(
        lane="temporal",
        record={"target_id": "ENSG00000111111", "arm_value": value, "evaluable": True,
                "rank": 1},
        identity={"target_id": "ENSG00000111111", "target_id_namespace": "ensembl_gene_id",
                  "target_symbol": "SYM", "target_ensembl": "ENSG00000111111",
                  "perturbation_modality": "CRISPRi_knockdown"},
        arm_key=ARM, program_id="PRG-1", program_effect_direction="increase", context=CTX)]


def _write_bridge(root, doc):
    os.makedirs(os.path.join(root, "bridge"), exist_ok=True)
    path = os.path.join(root, "bridge", B.BRIDGE_FILE)
    with open(path, "w") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True)
    return path


def _reseal(doc):
    doc.pop("bridge_sha256", None)
    doc["bridge_sha256"] = hashlib.sha256(
        json.dumps(doc, sort_keys=True, separators=(",", ":"),
                   ensure_ascii=True).encode()).hexdigest()
    return doc


class TestTheBridgeLivesBESIDETheBundlesNeverINSIDEThem:
    def test_building_the_bridge_writes_NOTHING_into_the_native_bundle(self, tmp_path):
        """Adding a file to an admitted bundle changes the tree its admission was shown."""
        root = str(tmp_path)
        d = _native_temporal(root)
        before = sorted(os.listdir(d))
        B.build_bridge(bindings=_bindings(root, d), rows=_rows(), contexts=[])
        assert sorted(os.listdir(d)) == before

    def test_the_bridge_admits_NOTHING_of_its_own(self, tmp_path):
        root = str(tmp_path)
        d = _native_temporal(root)
        doc = B.build_bridge(bindings=_bindings(root, d), rows=_rows(), contexts=[])
        assert doc["verdict"] == "pending_independent_verification"
        assert doc["admitted"] is False and doc["self_admitted"] is False


class TestTheRECONSTRUCTION:
    def test_an_HONEST_bridge_is_ADMITTED(self, tmp_path):
        root = str(tmp_path)
        d = _native_temporal(root, value=0.5)
        _write_bridge(root, B.build_bridge(bindings=_bindings(root, d), rows=_rows(0.5),
                                           contexts=[]))
        report = V.verify(os.path.join(root, "bridge"), bundles_root=root)
        assert report["verdict"] == "admit", report["failures"]
        assert report["reconstructs_from_admitted_native_bytes"] is True
        assert report["self_hash_alone_is_sufficient"] is False

    def test_THE_COHERENT_RESEAL_ATTACK_is_REFUSED(self, tmp_path):
        """YOUR ATTACK. +0.5 -> -0.5, direction and class coherently flipped, hash recomputed.

        The old verifier returned ADMIT with 0 failures: every internal check agreed. It fails
        here because the native ranking record still says +0.5, and the row is REBUILT from it.
        """
        root = str(tmp_path)
        d = _native_temporal(root, value=0.5)              # the experiment says +0.5
        doc = B.build_bridge(bindings=_bindings(root, d), rows=_rows(0.5), contexts=[])

        row = doc["target_rows"][0]
        row["arm_value"] = -0.5                            # the forgery...
        row["desired_target_modulation"] = "increase"      # ...made coherent...
        row["phenocopy_class"] = "inhibitor_opposed"
        _write_bridge(root, _reseal(doc))                  # ...and resealed

        report = V.verify(os.path.join(root, "bridge"), bundles_root=root)
        assert report["verdict"] == "reject"
        # the seal is VALID — and that is precisely why a seal is not enough
        assert not any(V.G_SELF_HASH in f for f in report["failures"])
        assert any(V.G_RECONSTRUCTED in f for f in report["failures"])
        assert any("rebuilt from the admitted native bytes" in f for f in report["failures"])

    def test_a_row_the_NATIVE_BYTES_DO_NOT_PRODUCE_is_REFUSED(self, tmp_path):
        root = str(tmp_path)
        d = _native_temporal(root)
        doc = B.build_bridge(bindings=_bindings(root, d), rows=_rows(), contexts=[])
        ghost = dict(doc["target_rows"][0], target_id="ENSG00000777777")
        doc["target_rows"].append(ghost)
        _write_bridge(root, _reseal(doc))

        report = V.verify(os.path.join(root, "bridge"), bundles_root=root)
        assert report["verdict"] == "reject"
        assert any(V.G_ORPHAN_ROW in f for f in report["failures"])

    def test_a_DROPPED_row_is_REFUSED(self, tmp_path):
        """A dropped row and a row that never existed look identical. So say so."""
        root = str(tmp_path)
        d = _native_temporal(root)
        doc = B.build_bridge(bindings=_bindings(root, d), rows=[], contexts=[])
        _write_bridge(root, _reseal(doc))

        report = V.verify(os.path.join(root, "bridge"), bundles_root=root)
        assert report["verdict"] == "reject"
        assert any("the bridge dropped it" in f for f in report["failures"])

    def test_a_bridge_that_BINDS_NOTHING_is_REFUSED(self, tmp_path):
        root = str(tmp_path)
        _native_temporal(root)
        _write_bridge(root, _reseal(B.build_bridge(bindings={}, rows=[], contexts=[])))
        report = V.verify(os.path.join(root, "bridge"), bundles_root=root)
        assert report["verdict"] == "reject"
        assert any(V.G_BINDINGS in f for f in report["failures"])

    def test_NATIVE_BYTES_CHANGED_after_the_bridge_was_built_are_REFUSED(self, tmp_path):
        root = str(tmp_path)
        d = _native_temporal(root, value=0.5)
        _write_bridge(root, B.build_bridge(bindings=_bindings(root, d), rows=_rows(0.5),
                                           contexts=[]))
        # somebody edits the ADMITTED ranking afterwards
        with open(os.path.join(d, "rankings", "PRG-1__increase.json"), "w") as fh:
            json.dump({"records": [{"target_id": "ENSG00000111111",
                                    "base_key": "PRG-1|ENSG00000111111", "arm_key": ARM,
                                    "arm_value": -0.5, "evaluable": True, "rank": 1}]}, fh)

        report = V.verify(os.path.join(root, "bridge"), bundles_root=root)
        assert report["verdict"] == "reject"
        assert any(V.G_SOURCE_BYTES in f for f in report["failures"])


class TestTheFORGEDPATHWAYCONTEXTAttack:
    """YOUR SECOND ATTACK. The contexts were ignored entirely, so this was admitted."""

    def _pathway(self, root):
        d = os.path.join(root, "pathway", "Stim48hr__GO-BP")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "arm_bundle.json"), "w") as fh:
            json.dump({"schema_version": "spot.stage02_pathway_arm_bundle.v1",
                       "pathway_run_id": "P-1", "condition": "Stim48hr", "source": "GO-BP",
                       "records": [{"pathway_arm_key":
                                    "pathway|PRG-1|increase|condition=Stim48hr",
                                    "set_id": "GO:0006955", "enrichment_value": 2.4,
                                    "leading_edge": ["ENSG00000111111"]}]}, fh)
        return d

    def _bind(self, root, d):
        rel = os.path.relpath(d, root).replace(os.sep, "/")
        b = {"native_bundles": {rel: {
                "lane": "pathway", "bundle_id": "P-1",
                "context": {"condition": "Stim48hr", "gene_set_source": "GO-BP"},
                "files": {"arm_bundle.json": _sha(os.path.join(d, "arm_bundle.json"))}}},
             "lane_admissions": {"pathway": {"native_verdict": "ADMIT",
                                            "native_self_hash": "p" * 64}},
             "stage1": {"release_canonical_sha256": "s" * 64},
             "identity_source": {"pathway": "none_target_evidence"}}
        return b

    def _ctx(self, d):
        rec = json.load(open(os.path.join(d, "arm_bundle.json")))["records"][0]
        return S.pathway_context(arm_key=rec["pathway_arm_key"], program_id="PRG-1", record=rec,
                                 context={"condition": "Stim48hr"}, namespace_of=UNIVERSE)

    def test_an_HONEST_pathway_context_is_ADMITTED(self, tmp_path):
        root = str(tmp_path)
        d = self._pathway(root)
        _write_bridge(root, B.build_bridge(bindings=self._bind(root, d), rows=[],
                                           contexts=[self._ctx(d)]))
        report = V.verify(os.path.join(root, "bridge"), bundles_root=root)
        assert report["verdict"] == "admit", report["failures"]

    def test_A_GENE_SET_DECLARING_ITSELF_A_DRUG_TARGET_is_REFUSED(self, tmp_path):
        """is_a_crispri_target_row=true, may_be_matched_to_a_drug_as_a_target=true,
        arm_value=99, desired_target_modulation=decrease — resealed. Previously: ADMIT, 0."""
        root = str(tmp_path)
        d = self._pathway(root)
        ctx = self._ctx(d)
        ctx["is_a_crispri_target_row"] = True
        ctx["may_be_matched_to_a_drug_as_a_target"] = True
        ctx["arm_value"] = 99
        ctx["desired_target_modulation"] = "decrease"
        _write_bridge(root, _reseal(B.build_bridge(bindings=self._bind(root, d), rows=[],
                                                   contexts=[ctx])))

        report = V.verify(os.path.join(root, "bridge"), bundles_root=root)
        assert report["verdict"] == "reject"
        assert any(V.G_CTX_FLAGS in f for f in report["failures"])
        assert any(V.G_CTX_ALLOWLIST in f for f in report["failures"])
        assert any("wearing a pathway's clothes" in f for f in report["failures"])

    def test_a_FORGED_enrichment_value_is_REFUSED(self, tmp_path):
        root = str(tmp_path)
        d = self._pathway(root)
        ctx = self._ctx(d)
        ctx["enrichment_value"] = 99.0
        _write_bridge(root, _reseal(B.build_bridge(bindings=self._bind(root, d), rows=[],
                                                   contexts=[ctx])))
        report = V.verify(os.path.join(root, "bridge"), bundles_root=root)
        assert report["verdict"] == "reject"
        assert any(V.G_CTX_RECONSTRUCTED in f for f in report["failures"])

    def test_a_context_for_a_GENE_SET_THAT_DOES_NOT_EXIST_is_REFUSED(self, tmp_path):
        root = str(tmp_path)
        d = self._pathway(root)
        ctx = self._ctx(d)
        ctx["gene_set_id"] = "GO:9999999"
        _write_bridge(root, _reseal(B.build_bridge(bindings=self._bind(root, d), rows=[],
                                                   contexts=[ctx])))
        report = V.verify(os.path.join(root, "bridge"), bundles_root=root)
        assert report["verdict"] == "reject"
        assert any("no such (arm, gene set)" in f for f in report["failures"])

    def test_a_leading_edge_target_FAKING_a_namespace_is_REFUSED(self, tmp_path):
        root = str(tmp_path)
        d = self._pathway(root)
        ctx = self._ctx(d)
        ctx["leading_edge"][0]["joinable"] = False
        # non-joinable, yet still carrying a namespace: sniffed, not resolved
        _write_bridge(root, _reseal(B.build_bridge(bindings=self._bind(root, d), rows=[],
                                                   contexts=[ctx])))
        report = V.verify(os.path.join(root, "bridge"), bundles_root=root)
        assert report["verdict"] == "reject"
        assert any(V.G_CTX_RECONSTRUCTED in f for f in report["failures"])


class TestDIRECTCannotEnterTheBridgeYet:
    def test_a_DIRECT_bundle_REBUILDS_NO_ROWS_because_it_binds_no_identity_source(self,
                                                                                  tmp_path):
        """So a bridge shipping Direct rows has rows the native bytes do not produce."""
        root = str(tmp_path)
        d = os.path.join(root, "direct", "Stim48hr")
        os.makedirs(os.path.join(d, "rankings"), exist_ok=True)
        with open(os.path.join(d, "arm_bundle.json"), "w") as fh:
            json.dump({"schema_version": "spot.stage02_direct_arm_bundle.v1",
                       "arm_bundle_run_id": "D-1", "condition": "Stim48hr"}, fh)
        with open(os.path.join(d, "rankings", "PRG-1__increase.json"), "w") as fh:
            json.dump({"records": [{"target_id": "ENSG00000111111", "arm_value": 0.5,
                                    "arm_key": "direct|PRG-1|increase|condition=Stim48hr",
                                    "evaluable": True, "rank": 1}]}, fh)

        bound = {"lane": "direct", "bundle_id": "D-1", "context": {"condition": "Stim48hr"},
                 "identity_source": None, "files": {}}
        assert V._rebuild_rows(d, bound) == {}

    def test_the_bridge_carries_the_DIRECT_producer_requirement(self, tmp_path):
        doc = B.build_bridge(bindings={}, rows=[], contexts=[])
        req = doc["direct_identity_requirement"]
        # LANDED at 5e9902a — the producer now emits it; W10's independent gate is pending
        assert req["file"] == "target_identity.json"
        assert req["schema_version"] == "spot.stage02_target_identity.v1"
        assert "observed_perturbation_modality" in req["required_columns"]


@pytest.mark.parametrize("field", ["native_bundles", "lane_admissions", "stage1",
                                   "identity_source"])
def test_every_required_binding_is_REQUIRED(tmp_path, field):
    root = str(tmp_path)
    d = _native_temporal(root)
    bindings = _bindings(root, d)
    del bindings[field]
    _write_bridge(root, _reseal(B.build_bridge(bindings=bindings, rows=_rows(), contexts=[])))
    report = V.verify(os.path.join(root, "bridge"), bundles_root=root)
    assert report["verdict"] == "reject"
    assert any(V.G_BINDINGS in f and field in f for f in report["failures"])


# --------------------------------------------------------------------------- #
# DIRECT, THROUGH THE SHARED ARTIFACT (9bd5895). The bundle now ships its own identity.
# --------------------------------------------------------------------------- #
DARM = "direct|PRG-1|increase|condition=Stim48hr"


def _native_direct(root, value=0.5, identity_rows=None):
    """A native Direct bundle: a bound ranking + the PRODUCER'S `target_identity.json`."""
    from direct import target_identity as TI

    d = os.path.join(root, "direct", "Stim48hr")
    os.makedirs(os.path.join(d, "rankings"), exist_ok=True)
    with open(os.path.join(d, "arm_bundle.json"), "w") as fh:
        json.dump({"schema_version": "spot.stage02_direct_arm_bundle.v1",
                   "arm_bundle_run_id": "D-1", "condition": "Stim48hr"}, fh)
    with open(os.path.join(d, "rankings", "PRG-1__increase.json"), "w") as fh:
        json.dump({"records": [{"target_id": "ENSG00000111111", "arm_key": DARM,
                                "arm_value": value, "evaluable": True, "rank": 1}]}, fh)
    # the artifact, in the producer's OWN shape: `records`, and the pinned modality
    rows_ = identity_rows if identity_rows is not None else [{
        "target_id": "ENSG00000111111", "target_id_namespace": "ensembl_gene_id",
        "target_symbol": "SYM", "target_ensembl": "ENSG00000111111",
        "observed_perturbation_modality": TI.OBSERVED_PERTURBATION_MODALITY}]
    with open(os.path.join(d, TI.TARGET_IDENTITY_FILE), "w") as fh:
        json.dump({"schema_version": TI.SCHEMA_VERSION, "condition": "Stim48hr",
                   "columns": list(TI.COLUMNS),
                   "observed_perturbation_modality": TI.OBSERVED_PERTURBATION_MODALITY,
                   "modality_rule_id": TI.MODALITY_RULE_ID, "n_targets": len(rows_),
                   "n_ensembl_gene_id": 1, "n_gene_symbol": 0, "records": rows_}, fh)
    return d


def _direct_bindings(root, d):
    from direct import target_identity as TI
    rel = os.path.relpath(d, root).replace(os.sep, "/")
    names = ["arm_bundle.json", "rankings/PRG-1__increase.json", TI.TARGET_IDENTITY_FILE]
    return {
        "native_bundles": {rel: {
            "lane": "direct", "bundle_id": "D-1", "context": {"condition": "Stim48hr"},
            "identity_source": {"kind": "identity_artifact",
                                "file": TI.TARGET_IDENTITY_FILE,
                                "schema_version": TI.SCHEMA_VERSION},
            "files": {n: _sha(os.path.join(d, n)) for n in names},
        }},
        "lane_admissions": {"direct": {"native_verdict": "ADMIT",
                                       "native_self_hash": "d" * 64}},
        "stage1": {"release_canonical_sha256": "s" * 64},
        "identity_source": {"direct": TI.TARGET_IDENTITY_FILE},
    }


def _direct_rows(value=0.5):
    from direct import target_identity as TI
    return [S.build_row(
        lane="direct",
        record={"target_id": "ENSG00000111111", "arm_value": value, "evaluable": True,
                "rank": 1},
        identity={"target_id": "ENSG00000111111", "target_id_namespace": "ensembl_gene_id",
                  "target_symbol": "SYM", "target_ensembl": "ENSG00000111111",
                  "observed_perturbation_modality": TI.OBSERVED_PERTURBATION_MODALITY},
        arm_key=DARM, program_id="PRG-1", program_effect_direction="increase",
        context={"condition": "Stim48hr"})]


class TestDIRECTThroughTheSHAREDIdentityArtifact:
    """9bd5895. One filename, one schema, one loader — and the verifier reads the same bytes."""

    def test_the_CONSTANTS_ARE_THE_PRODUCERS_and_have_not_DRIFTED(self):
        """The `.json` -> `.parquet` drift, made a failing test instead of a silent miss.

        The bridge VERIFIER may not import the producer (the audit probe forbids it), so it
        restates these. Restating is safe only if a disagreement is loud.
        """
        from direct import target_identity as TI
        assert V.IDENTITY_FILE == TI.TARGET_IDENTITY_FILE == "target_identity.json"
        assert V.IDENTITY_SCHEMA == TI.SCHEMA_VERSION
        assert V.IDENTITY_MODALITY_FIELD in TI.COLUMNS
        assert S.TARGET_IDENTITY_FILE == TI.TARGET_IDENTITY_FILE

    def test_the_records_key_is_RECORDS_not_targets(self):
        """It was `targets` in my verifier: it would have rebuilt ZERO rows and then failed
        every Direct row as an orphan — a wrong answer that looks like a strict one."""
        assert V.IDENTITY_RECORDS_KEY == "records"

    def test_a_DIRECT_bridge_on_REAL_producer_bytes_is_ADMITTED(self, tmp_path):
        root = str(tmp_path)
        d = _native_direct(root, value=0.5)
        _write_bridge(root, B.build_bridge(bindings=_direct_bindings(root, d),
                                           rows=_direct_rows(0.5), contexts=[]))
        report = V.verify(os.path.join(root, "bridge"), bundles_root=root)
        assert report["verdict"] == "admit", report["failures"]
        assert report["n_rebuilt"] == 1

    def test_the_COHERENT_RESEAL_ATTACK_on_the_DIRECT_lane_is_REFUSED(self, tmp_path):
        root = str(tmp_path)
        d = _native_direct(root, value=0.5)          # the experiment says +0.5
        doc = B.build_bridge(bindings=_direct_bindings(root, d), rows=_direct_rows(0.5),
                             contexts=[])
        row = doc["target_rows"][0]
        row["arm_value"] = -0.5
        row["desired_target_modulation"] = "increase"
        row["phenocopy_class"] = "inhibitor_opposed"
        _write_bridge(root, _reseal(doc))

        report = V.verify(os.path.join(root, "bridge"), bundles_root=root)
        assert report["verdict"] == "reject"
        assert any(V.G_RECONSTRUCTED in f for f in report["failures"])

    def test_MUTATING_the_identity_artifact_FAILS_ADMISSION(self, tmp_path):
        """The wrong gene, attached to a drug. The bytes are bound, so the edit is caught."""
        from direct import target_identity as TI
        root = str(tmp_path)
        d = _native_direct(root)
        _write_bridge(root, B.build_bridge(bindings=_direct_bindings(root, d),
                                           rows=_direct_rows(), contexts=[]))
        # relabel the target's namespace AFTER it was bound and admitted
        path = os.path.join(d, TI.TARGET_IDENTITY_FILE)
        doc = json.load(open(path))
        doc["records"][0]["target_id_namespace"] = "gene_symbol"
        with open(path, "w") as fh:
            json.dump(doc, fh)

        report = V.verify(os.path.join(root, "bridge"), bundles_root=root)
        assert report["verdict"] == "reject"
        assert any(V.G_SOURCE_BYTES in f for f in report["failures"])

    def test_a_DUPLICATED_identity_row_rebuilds_NOTHING_and_so_REFUSES(self, tmp_path):
        """A join key that is not unique silently multiplies every row it is joined to."""
        from direct import target_identity as TI
        root = str(tmp_path)
        dupe = [{"target_id": "ENSG00000111111", "target_id_namespace": "ensembl_gene_id",
                 "target_symbol": "SYM", "target_ensembl": "ENSG00000111111",
                 "observed_perturbation_modality": TI.OBSERVED_PERTURBATION_MODALITY}] * 2
        d = _native_direct(root, identity_rows=dupe)
        _write_bridge(root, B.build_bridge(bindings=_direct_bindings(root, d),
                                           rows=_direct_rows(), contexts=[]))
        report = V.verify(os.path.join(root, "bridge"), bundles_root=root)
        assert report["verdict"] == "reject"
        assert any(V.G_ORPHAN_ROW in f for f in report["failures"])

    def test_an_artifact_by_ANOTHER_NAME_is_not_this_artifact(self, tmp_path):
        """A consumer that expected a parquet would either miss the file or write its own."""
        root = str(tmp_path)
        d = _native_direct(root)
        bindings = _direct_bindings(root, d)
        rel = next(iter(bindings["native_bundles"]))
        bindings["native_bundles"][rel]["identity_source"]["file"] = "target_identity.parquet"
        _write_bridge(root, B.build_bridge(bindings=bindings, rows=_direct_rows(),
                                           contexts=[]))
        report = V.verify(os.path.join(root, "bridge"), bundles_root=root)
        assert report["verdict"] == "reject"
        assert any(V.G_ORPHAN_ROW in f or V.G_COMPLETENESS in f for f in report["failures"])
