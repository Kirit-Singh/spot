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
    """A native temporal bundle — plus the two Direct endpoints its identity comes from.

    The temporal producer's own identity mirrors are NULL (276a9ad), so a temporal bundle
    ALONE cannot say who any of its targets are. Its endpoints can.
    """
    _direct_at(root, "Rest")
    _direct_at(root, "Stim48hr")

    d = os.path.join(root, "temporal", "Rest__Stim48hr")
    os.makedirs(os.path.join(d, "rankings"), exist_ok=True)
    with open(os.path.join(d, "arm_bundle.json"), "w") as fh:
        json.dump({"schema_version": "spot.stage02_temporal_arm_bundle.v1",
                   "bundle_id": "T-1", "lane": "temporal", "context": CTX,
                   # the NULL mirrors, exactly as the producer writes them
                   "base_records": [{"base_key": "PRG-1|ENSG00000111111",
                                     "target_id": "ENSG00000111111",
                                     "target_id_namespace": None, "target_symbol": None,
                                     "target_ensembl": None,
                                     "perturbation_modality": "CRISPRi_knockdown"}]}, fh)
    with open(os.path.join(d, "rankings", "PRG-1__increase.json"), "w") as fh:
        # arm_key ONCE, at the top of the document; the records do not repeat it
        json.dump({"arm_key": ARM,
                   "records": [{"target_id": "ENSG00000111111",
                                "base_key": "PRG-1|ENSG00000111111",
                                "arm_value": value, "evaluable": True, "rank": 1}]}, fh)
    return d


def _bindings(root, d):
    rel = os.path.relpath(d, root).replace(os.sep, "/")
    from direct import target_identity as TI
    endpoints = {}
    for cond in ("Rest", "Stim48hr"):
        dd = os.path.join(root, "direct", cond)
        endpoints[cond] = {
            "relative_dir": os.path.relpath(dd, root).replace(os.sep, "/"),
            "raw_sha256": _sha(os.path.join(dd, TI.TARGET_IDENTITY_FILE)),
        }
    return {
        "native_bundles": {rel: {
            "lane": "temporal", "bundle_id": "T-1", "context": CTX,
            # identity is the CANONICAL JOIN across BOTH admitted Direct endpoints
            "identity_source": {"kind": "direct_endpoints",
                                "file": TI.TARGET_IDENTITY_FILE,
                                "endpoints": endpoints,
                                "trusts_the_temporal_identity_mirrors": False},
            "files": {"arm_bundle.json": _sha(os.path.join(d, "arm_bundle.json")),
                      "rankings/PRG-1__increase.json":
                          _sha(os.path.join(d, "rankings", "PRG-1__increase.json"))},
        }},
        "lane_admissions": {"temporal": {"native_verdict": "ADMIT", "report_id": "r-1"}},
        "stage1": {"release_canonical_sha256": "s" * 64},
        "identity_source": {"temporal": TI.TARGET_IDENTITY_FILE},
        "aggregate": _aggregate(root),
    }


def _rows(value=0.5):
    from direct import target_identity as TI
    return [S.build_row(
        lane="temporal",
        record={"target_id": "ENSG00000111111", "arm_value": value, "evaluable": True,
                "rank": 1},
        # the CANONICAL identity, from the endpoints — never the temporal null mirror
        identity={"target_id": "ENSG00000111111", "target_id_namespace": "ensembl_gene_id",
                  "target_symbol": "SYM", "target_ensembl": "ENSG00000111111",
                  "observed_perturbation_modality": TI.OBSERVED_PERTURBATION_MODALITY},
        arm_key=ARM, program_id="PRG-1", program_effect_direction="increase", context=CTX)]


def _aggregate(root):
    """The ADMITTED aggregate the bridge is downstream of. Bound, never rewritten."""
    m = os.path.join(root, "stage2_run_manifest.json")
    r = os.path.join(root, "stage2_aggregate_verification.json")
    if not os.path.exists(m):
        with open(m, "w") as fh:
            json.dump({"lane_admissions": {}}, fh, indent=2, sort_keys=True)
        with open(r, "w") as fh:
            json.dump({"verdict": "admit", "n_failed": 0}, fh, indent=2, sort_keys=True)
    out = {}
    for role, p_ in (("manifest", m), ("report", r)):
        out[role] = {"path": p_, "raw_sha256": _sha(p_),
                     "canonical_sha256": hashlib.sha256(json.dumps(
                         json.load(open(p_)), sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True).encode()).hexdigest()}
    return out


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
            json.dump({"arm_key": ARM,
                       "records": [{"target_id": "ENSG00000111111",
                                    "base_key": "PRG-1|ENSG00000111111",
                                    "arm_value": -0.5, "evaluable": True, "rank": 1}]}, fh)

        report = V.verify(os.path.join(root, "bridge"), bundles_root=root)
        assert report["verdict"] == "reject"
        assert any(V.G_SOURCE_BYTES in f for f in report["failures"])


class TestTheFORGEDPATHWAYCONTEXTAttack:
    """YOUR SECOND ATTACK. The contexts were ignored entirely, so this was admitted."""

    def _pathway(self, root):
        # a Direct bundle MUST be present: target_identity.json is where a leading-edge gene's
        # namespace comes from, and a pathway that cannot resolve its leading edge cannot hand
        # Stage 3 a gene to look a drug up against.
        _native_direct(root)
        d = os.path.join(root, "pathway", "Stim48hr__GO-BP")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "arm_bundle.json"), "w") as fh:
            json.dump({"schema_version": "spot.stage02_pathway_arm_bundle.v1",
                       "pathway_run_id": "P-1", "condition": "Stim48hr", "source": "GO-BP",
                       "bindings": {"gene_set_membership": {"sha256": "m" * 64}},
                   # THE NATIVE PATHWAY RECORD (pathway_arms.enrichment_arms): the coverage is
                   # `target_source_coverage`, NOT `coverage`.
                   "records": [{"pathway_arm_key":
                                "pathway|PRG-1|increase|condition=Stim48hr",
                                "direct_arm_key": DARM, "program_id": "PRG-1",
                                "desired_change": "increase", "condition": "Stim48hr",
                                "source": "GO-BP", "set_id": "GO:0006955",
                                "target_source_coverage": 0.75,
                                "convergence_ref": "conv|Stim48hr|GO-BP",
                                "enrichment_value": 2.4,
                                "leading_edge": ["ENSG00000111111"]}]}, fh)
        return d

    def _bind(self, root, d):
        rel = os.path.relpath(d, root).replace(os.sep, "/")
        dd = os.path.join(root, "direct", "Stim48hr")
        drel = os.path.relpath(dd, root).replace(os.sep, "/")
        from direct import target_identity as TI
        b = {"native_bundles": {
             drel: {"lane": "direct", "bundle_id": "D-1",
                    "context": {"condition": "Stim48hr"},
                    "identity_source": {"kind": "identity_artifact",
                                        "file": TI.TARGET_IDENTITY_FILE},
                    "files": {}},
             rel: {
                "lane": "pathway", "bundle_id": "P-1",
                "context": {"condition": "Stim48hr", "gene_set_source": "GO-BP"},
                "files": {"arm_bundle.json": _sha(os.path.join(d, "arm_bundle.json"))}}},
             "lane_admissions": {"pathway": {"native_verdict": "ADMIT",
                                            "native_self_hash": "p" * 64}},
             "stage1": {"release_canonical_sha256": "s" * 64},
             "identity_source": {"pathway": "none_target_evidence"},
             "aggregate": _aggregate(root)}
        return b

    def _ctx(self, d):
        rec = json.load(open(os.path.join(d, "arm_bundle.json")))["records"][0]
        return S.pathway_context(arm_key=rec["pathway_arm_key"], program_id="PRG-1", record=rec,
                                 context={"condition": "Stim48hr"}, namespace_of=UNIVERSE,
                                 source_artifact={"sha256": "m" * 64})

    def test_an_HONEST_pathway_context_is_ADMITTED(self, tmp_path):
        root = str(tmp_path)
        d = self._pathway(root)
        _write_bridge(root, B.build_bridge(bindings=self._bind(root, d),
                                           rows=_direct_rows(), contexts=[self._ctx(d)]))
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
        _write_bridge(root, _reseal(B.build_bridge(bindings=self._bind(root, d),
                                                   rows=_direct_rows(), contexts=[ctx])))

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
        _write_bridge(root, _reseal(B.build_bridge(bindings=self._bind(root, d),
                                                   rows=_direct_rows(), contexts=[ctx])))
        report = V.verify(os.path.join(root, "bridge"), bundles_root=root)
        assert report["verdict"] == "reject"
        assert any(V.G_CTX_RECONSTRUCTED in f for f in report["failures"])

    def test_a_context_for_a_GENE_SET_THAT_DOES_NOT_EXIST_is_REFUSED(self, tmp_path):
        root = str(tmp_path)
        d = self._pathway(root)
        ctx = self._ctx(d)
        ctx["gene_set_id"] = "GO:9999999"
        _write_bridge(root, _reseal(B.build_bridge(bindings=self._bind(root, d),
                                                   rows=_direct_rows(), contexts=[ctx])))
        report = V.verify(os.path.join(root, "bridge"), bundles_root=root)
        assert report["verdict"] == "reject"
        assert any("no such (arm, gene set)" in f for f in report["failures"])

    def test_a_leading_edge_target_FAKING_a_namespace_is_REFUSED(self, tmp_path):
        root = str(tmp_path)
        d = self._pathway(root)
        ctx = self._ctx(d)
        ctx["leading_edge"][0]["joinable"] = False
        # non-joinable, yet still carrying a namespace: sniffed, not resolved
        _write_bridge(root, _reseal(B.build_bridge(bindings=self._bind(root, d),
                                                   rows=_direct_rows(), contexts=[ctx])))
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
    import pandas as pd
    from direct import target_identity as TI

    d = os.path.join(root, "direct", "Stim48hr")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "arm_bundle.json"), "w") as fh:
        json.dump({"schema_version": "spot.stage02_direct_arm_bundle.v1",
                   "arm_bundle_run_id": "D-1", "condition": "Stim48hr"}, fh)
    # DIRECT HAS NO rankings/ DIRECTORY. Its rows are arms.parquet (arm_artifacts.ROWS_FILE),
    # with the value in a column called `value`.
    pd.DataFrame([{"arm_key": DARM, "program_id": "PRG-1", "desired_change": "increase",
                   "condition": "Stim48hr", "target_id": "ENSG00000111111",
                   "value": value, "rank": 1, "evaluable": True}]
                 ).to_parquet(os.path.join(d, "arms.parquet"))
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
    names = ["arm_bundle.json", "arms.parquet", TI.TARGET_IDENTITY_FILE]
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
        "aggregate": _aggregate(root),
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


# --------------------------------------------------------------------------- #
# THE PRODUCTION CONTRACT: the bridge runs ONLY over an ADMITTED release.
# --------------------------------------------------------------------------- #
def _admitted_release(tmp_path, direct_value=0.5):
    """A release that has already passed lane + aggregate admission."""
    root = str(tmp_path)
    d = _native_direct(root, value=direct_value)
    p = os.path.join(root, "pathway", "Stim48hr__GO-BP")
    os.makedirs(p, exist_ok=True)
    with open(os.path.join(p, "arm_bundle.json"), "w") as fh:
        json.dump({"schema_version": "spot.stage02_pathway_arm_bundle.v1",
                   "pathway_run_id": "P-1", "condition": "Stim48hr", "source": "GO-BP",
                   "bindings": {"gene_set_membership": {"sha256": "m" * 64}},
                   # the NATIVE record: `target_source_coverage`, not `coverage`
                   "records": [{"pathway_arm_key": "pathway|PRG-1|increase|condition=Stim48hr",
                                "direct_arm_key": DARM, "program_id": "PRG-1",
                                "desired_change": "increase", "condition": "Stim48hr",
                                "source": "GO-BP", "set_id": "GO:0006955",
                                "target_source_coverage": 0.75,
                                "convergence_ref": "conv|Stim48hr|GO-BP",
                                "enrichment_value": 2.4,
                                "leading_edge": ["ENSG00000111111"]}]}, fh)

    # Direct's rows live in arms.parquet — there is no rankings/ dir on this lane
    import pandas as pd
    pd.DataFrame([{"arm_key": DARM, "program_id": "PRG-1", "desired_change": "increase",
                   "condition": "Stim48hr", "target_id": "ENSG00000111111",
                   "value": direct_value, "rank": 1, "evaluable": True}]
                 ).to_parquet(os.path.join(d, "arms.parquet"))

    manifest = {"schema_version": "spot.stage02_run_manifest.v1",
                "lane_admissions": {
                    "direct": {"aggregate_disposition": "admitted", "native_verdict": "ADMIT",
                               "native_self_hash": "d" * 64},
                    "pathway": {"aggregate_disposition": "admitted", "native_verdict": "ADMIT",
                                "native_self_hash": "p" * 64}},
                "stage1_v3_release": {"release_canonical_sha256": "s" * 64}}
    with open(os.path.join(root, "stage2_run_manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
    with open(os.path.join(root, "stage2_aggregate_verification.json"), "w") as fh:
        json.dump({"verifier_id": "spot.stage02.run_manifest.verifier.v1",
                   "verdict": "admit", "n_failed": 0, "failed_gates": []}, fh,
                  indent=2, sort_keys=True)
    return root, d, p


class TestTheBridgeRunsONLYOverAnADMITTEDRelease:
    def test_e2e_the_CLI_builds_and_the_SEPARATE_verifier_admits(self, tmp_path):
        from direct import stage3_bridge as BB
        root, _d, _p = _admitted_release(tmp_path)
        bridge = os.path.join(root, "bridge")
        rc = BB.main(["--bundles-root", root, "--bridge-root", bridge, "--verify"])
        assert rc == 0

        doc = json.load(open(os.path.join(bridge, BB.BRIDGE_FILE)))
        assert doc["n_target_rows"] == 1 and doc["n_pathway_contexts"] == 1
        report = json.load(open(os.path.join(bridge, BB.BRIDGE_REPORT_FILE)))
        assert report["verdict"] == "admit", report["failures"]

    def test_the_RECEIPT_binds_the_aggregate_WITHOUT_RESEALING_it(self, tmp_path):
        """The aggregate was hashed when it was admitted. It is never rewritten."""
        from direct import stage3_bridge as BB
        root, _d, _p = _admitted_release(tmp_path)
        agg = os.path.join(root, "stage2_run_manifest.json")
        before = _sha(agg)

        bridge = os.path.join(root, "bridge")
        assert BB.main(["--bundles-root", root, "--bridge-root", bridge, "--verify"]) == 0

        assert _sha(agg) == before                       # NOT mutated, NOT resealed
        rec = json.load(open(os.path.join(bridge, BB.RECEIPT_FILE)))
        assert rec["aggregate_is_immutable"] is True
        assert rec["aggregate_was_resealed"] is False
        # both hashes of both artifacts, so a reader can walk admitted release -> handoff
        for side in ("aggregate", "bridge", "bridge_report"):
            assert rec[side]
        assert rec["aggregate"]["manifest"]["raw_sha256"] == before
        assert rec["bridge"]["raw_sha256"] and rec["bridge"]["canonical_sha256"]

    def test_it_writes_NOTHING_into_any_bundle_directory(self, tmp_path):
        from direct import stage3_bridge as BB
        root, d, p = _admitted_release(tmp_path)
        before = {b: sorted(os.listdir(b)) for b in (d, p)}
        BB.main(["--bundles-root", root, "--bridge-root", os.path.join(root, "bridge"),
                 "--verify"])
        assert {b: sorted(os.listdir(b)) for b in (d, p)} == before

    def test_a_REJECTED_aggregate_REFUSES_to_build(self, tmp_path):
        """A Stage-3 handoff for a release nobody cleared looks exactly like one that was."""
        from direct import stage3_bridge as BB
        root, _d, _p = _admitted_release(tmp_path)
        path = os.path.join(root, "stage2_aggregate_verification.json")
        with open(path, "w") as fh:
            json.dump({"verdict": "reject", "n_failed": 3, "failed_gates": ["x"]}, fh)

        with pytest.raises(BB.BridgeError, match="not 'admit'"):
            BB.assemble(root, os.path.join(root, "bridge"))

    def test_an_UNADMITTED_LANE_REFUSES_to_build(self, tmp_path):
        from direct import stage3_bridge as BB
        root, _d, _p = _admitted_release(tmp_path)
        path = os.path.join(root, "stage2_run_manifest.json")
        doc = json.load(open(path))
        doc["lane_admissions"]["pathway"]["aggregate_disposition"] = "refused"
        with open(path, "w") as fh:
            json.dump(doc, fh)

        with pytest.raises(BB.BridgeError, match="not independently admitted"):
            BB.assemble(root, os.path.join(root, "bridge"))

    def test_NO_aggregate_at_all_REFUSES_to_build(self, tmp_path):
        from direct import stage3_bridge as BB
        root, _d, _p = _admitted_release(tmp_path)
        os.remove(os.path.join(root, "stage2_aggregate_verification.json"))
        with pytest.raises(BB.BridgeError, match="DOWNSTREAM of aggregate admission"):
            BB.assemble(root, os.path.join(root, "bridge"))


class TestTheFiveSWAPS:
    """Swap any referent the bridge was built over. Each must refuse."""

    def _built(self, tmp_path):
        from direct import stage3_bridge as BB
        root, d, p = _admitted_release(tmp_path)
        bridge = os.path.join(root, "bridge")
        assert BB.main(["--bundles-root", root, "--bridge-root", bridge, "--verify"]) == 0
        return root, d, p, bridge

    def _reverify(self, bridge, root):
        return V.verify(bridge, bundles_root=root)

    def test_SWAP_the_aggregate_REPORT(self, tmp_path):
        root, _d, _p, bridge = self._built(tmp_path)
        with open(os.path.join(root, "stage2_aggregate_verification.json"), "w") as fh:
            json.dump({"verdict": "admit", "n_failed": 0, "swapped": True}, fh)
        r = self._reverify(bridge, root)
        assert r["verdict"] == "reject"
        assert any(V.G_AGGREGATE in f for f in r["failures"])

    def test_SWAP_the_W10_IDENTITY_artifact(self, tmp_path):
        from direct import target_identity as TI
        root, d, _p, bridge = self._built(tmp_path)
        path = os.path.join(d, TI.TARGET_IDENTITY_FILE)
        doc = json.load(open(path))
        doc["records"][0]["target_id_namespace"] = "gene_symbol"   # the wrong gene
        with open(path, "w") as fh:
            json.dump(doc, fh)
        r = self._reverify(bridge, root)
        assert r["verdict"] == "reject"
        assert any(V.G_SOURCE_BYTES in f for f in r["failures"])

    def test_SWAP_the_DIRECT_bundle_rows(self, tmp_path):
        import pandas as pd
        root, d, _p, bridge = self._built(tmp_path)
        pd.DataFrame([{"arm_key": DARM, "program_id": "PRG-1", "desired_change": "increase",
                       "condition": "Stim48hr", "target_id": "ENSG00000111111",
                       "value": -0.5, "rank": 1, "evaluable": True}]   # sign flipped
                     ).to_parquet(os.path.join(d, "arms.parquet"))
        r = self._reverify(bridge, root)
        assert r["verdict"] == "reject"
        assert any(V.G_SOURCE_BYTES in f for f in r["failures"])

    def test_SWAP_the_AGGREGATE_MANIFEST(self, tmp_path):
        root, _d, _p, bridge = self._built(tmp_path)
        path = os.path.join(root, "stage2_run_manifest.json")
        doc = json.load(open(path))
        doc["lane_admissions"]["direct"]["native_self_hash"] = "0" * 64
        with open(path, "w") as fh:
            json.dump(doc, fh)
        r = self._reverify(bridge, root)
        assert r["verdict"] == "reject"
        assert any(V.G_AGGREGATE in f for f in r["failures"])

    def test_SWAP_a_PATHWAY_CONTEXT_into_target_evidence(self, tmp_path):
        from direct import stage3_bridge as BB
        root, _d, _p, bridge = self._built(tmp_path)
        path = os.path.join(bridge, BB.BRIDGE_FILE)
        doc = json.load(open(path))
        ctx = doc["pathway_contexts"][0]
        ctx["is_a_crispri_target_row"] = True
        ctx["may_be_matched_to_a_drug_as_a_target"] = True
        ctx["arm_value"] = 99
        with open(path, "w") as fh:
            json.dump(_reseal(doc), fh)
        r = self._reverify(bridge, root)
        assert r["verdict"] == "reject"
        assert any(V.G_CTX_FLAGS in f for f in r["failures"])
        assert any(V.G_CTX_ALLOWLIST in f for f in r["failures"])


class TestTheRECEIPTIsAReferentLikeAnyOther:
    """Stage 3 gates on the receipt (W16 --stage2-bridge-receipt). A swapped receipt is a
    swapped release: it can name a different bridge, a different aggregate, or a report that
    never admitted anything — and every hash inside it still agrees with itself."""

    def _built(self, tmp_path):
        from direct import stage3_bridge as BB
        root, d, p = _admitted_release(tmp_path)
        bridge = os.path.join(root, "bridge")
        assert BB.main(["--bundles-root", root, "--bridge-root", bridge, "--verify"]) == 0
        return root, d, bridge

    def test_the_receipt_is_INDEPENDENTLY_verified_and_ADMITS(self, tmp_path):
        root, _d, bridge = self._built(tmp_path)
        rec = V.verify_receipt(bridge, bundles_root=root)
        assert rec["verdict"] == "admit", rec["failures"]
        assert rec["generator_is_not_verifier"] is True

    def test_a_MISSING_receipt_is_REFUSED(self, tmp_path):
        from direct import stage3_bridge as BB
        root, _d, bridge = self._built(tmp_path)
        os.remove(os.path.join(bridge, BB.RECEIPT_FILE))
        rec = V.verify_receipt(bridge, bundles_root=root)
        assert rec["verdict"] == "reject"
        assert any(V.G_RECEIPT_ABSENT in f for f in rec["failures"])

    def test_a_SWAPPED_receipt_naming_a_DIFFERENT_bridge_is_REFUSED(self, tmp_path):
        """The attack W16's gate needs: the bridge is replaced, the receipt still points at
        it by path, and the receipt is resealed so its own hash is valid."""
        from direct import stage3_bridge as BB
        root, _d, bridge = self._built(tmp_path)

        bpath = os.path.join(bridge, BB.BRIDGE_FILE)
        doc = json.load(open(bpath))
        doc["target_rows"][0]["arm_value"] = -0.5          # a different bridge entirely
        with open(bpath, "w") as fh:
            json.dump(_reseal(doc), fh)

        rec = V.verify_receipt(bridge, bundles_root=root)
        assert rec["verdict"] == "reject"
        assert any(V.G_RECEIPT_BINDS in f for f in rec["failures"])
        assert any("a different artifact than the one that is there" in f
                   for f in rec["failures"])

    def test_a_receipt_binding_a_REJECTING_bridge_report_is_REFUSED(self, tmp_path):
        """A receipt is a receipt FOR AN ADMISSION."""
        import hashlib

        from direct import stage3_bridge as BB
        root, _d, bridge = self._built(tmp_path)

        rpath = os.path.join(bridge, BB.BRIDGE_REPORT_FILE)
        with open(rpath, "w") as fh:
            json.dump({"verdict": "reject", "n_failed": 4, "failures": []}, fh,
                      indent=2, sort_keys=True)
        # ...and re-point the receipt at it, honestly, so only the VERDICT is wrong
        recp = os.path.join(bridge, BB.RECEIPT_FILE)
        doc = json.load(open(recp))
        doc["bridge_report"]["raw_sha256"] = _sha(rpath)
        doc["bridge_report"]["canonical_sha256"] = hashlib.sha256(json.dumps(
            json.load(open(rpath)), sort_keys=True, separators=(",", ":"),
            ensure_ascii=True).encode()).hexdigest()
        doc.pop("receipt_sha256")
        doc["receipt_sha256"] = hashlib.sha256(json.dumps(
            doc, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
        with open(recp, "w") as fh:
            json.dump(doc, fh, indent=2, sort_keys=True)

        rec = V.verify_receipt(bridge, bundles_root=root)
        assert rec["verdict"] == "reject"
        assert any(V.G_RECEIPT_ADMITTED in f for f in rec["failures"])

    def test_a_receipt_CLAIMING_the_aggregate_was_RESEALED_is_REFUSED(self, tmp_path):
        import hashlib

        from direct import stage3_bridge as BB
        root, _d, bridge = self._built(tmp_path)
        recp = os.path.join(bridge, BB.RECEIPT_FILE)
        doc = json.load(open(recp))
        doc["aggregate_was_resealed"] = True
        doc.pop("receipt_sha256")
        doc["receipt_sha256"] = hashlib.sha256(json.dumps(
            doc, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
        with open(recp, "w") as fh:
            json.dump(doc, fh, indent=2, sort_keys=True)

        rec = V.verify_receipt(bridge, bundles_root=root)
        assert rec["verdict"] == "reject"
        assert any(V.G_RECEIPT_RESEALED in f for f in rec["failures"])

    def test_a_TAMPERED_receipt_fails_its_OWN_hash(self, tmp_path):
        from direct import stage3_bridge as BB
        root, _d, bridge = self._built(tmp_path)
        recp = os.path.join(bridge, BB.RECEIPT_FILE)
        doc = json.load(open(recp))
        doc["bridge"]["raw_sha256"] = "0" * 64
        with open(recp, "w") as fh:
            json.dump(doc, fh, indent=2, sort_keys=True)

        rec = V.verify_receipt(bridge, bundles_root=root)
        assert rec["verdict"] == "reject"
        assert any(V.G_RECEIPT_SELF_HASH in f for f in rec["failures"])

    def test_the_CLI_verifies_the_receipt_it_just_WROTE(self, tmp_path):
        """generator != verifier, at the process level: the producer writes the receipt, and a
        SEPARATE process re-derives it."""
        from direct import stage3_bridge as BB
        root, _d, _p = _admitted_release(tmp_path)
        bridge = os.path.join(root, "bridge")
        assert BB.main(["--bundles-root", root, "--bridge-root", bridge, "--verify"]) == 0
        # the receipt's report is SEPARATE — it binds the bridge report, so re-writing that
        # report while checking the receipt would invalidate the hash it was built on
        rec = json.load(open(os.path.join(bridge, BB.RECEIPT_REPORT_FILE)))
        assert rec["verdict"] == "admit"
        assert rec["generator_is_not_verifier"] is True


class TestTheWHOLEROWIsTheContract:
    """Selective comparison leaks by construction — it only catches the fields somebody listed.

    Independent replay walked straight through the gaps: target_symbol, target_ensembl,
    program_id and context.condition were ALL admitted after a reseal. Adding four names would
    only move the hole. So the rebuilt row IS the contract: every key, every value, nothing
    extra, nothing missing.
    """

    def _forge(self, tmp_path, mutate):
        from direct import stage3_bridge as BB
        root, d, _p = _admitted_release(tmp_path)
        bridge = os.path.join(root, "bridge")
        assert BB.main(["--bundles-root", root, "--bridge-root", bridge, "--verify"]) == 0
        path = os.path.join(bridge, BB.BRIDGE_FILE)
        doc = json.load(open(path))
        mutate(doc["target_rows"][0])
        with open(path, "w") as fh:
            json.dump(_reseal(doc), fh)
        return V.verify(bridge, bundles_root=root)

    @pytest.mark.parametrize("field,value", [
        ("target_symbol", "WRONG_GENE"),
        ("target_ensembl", "ENSG00000999999"),
        ("target_id_namespace", "gene_symbol"),
        ("program_id", "PRG-OTHER"),
        ("observed_perturbation_modality", "CRISPRa_activation"),
        ("perturbation_target_effect", "target_transcript_increased"),
        ("phenocopy_claim", "equivalence"),
        ("rank", 99),
    ])
    def test_a_RESEALED_row_with_an_ALTERED_field_is_REFUSED(self, tmp_path, field, value):
        report = self._forge(tmp_path, lambda r: r.__setitem__(field, value))
        assert report["verdict"] == "reject"
        assert any(V.G_RECONSTRUCTED in f and field in f for f in report["failures"])

    def test_a_RESEALED_row_with_an_ALTERED_CONTEXT_is_REFUSED(self, tmp_path):
        report = self._forge(tmp_path,
                             lambda r: r.__setitem__("context", {"condition": "Rest"}))
        assert report["verdict"] == "reject"
        assert any(V.G_RECONSTRUCTED in f and "context" in f for f in report["failures"])

    def test_an_EXTRA_field_is_REFUSED(self, tmp_path):
        """A row may not add facts of its own — including a p-value."""
        report = self._forge(tmp_path, lambda r: r.__setitem__("p_value", 0.001))
        assert report["verdict"] == "reject"
        assert any("may not add facts of its own" in f for f in report["failures"])

    def test_a_MISSING_field_is_REFUSED(self, tmp_path):
        report = self._forge(tmp_path, lambda r: r.pop("target_ensembl"))
        assert report["verdict"] == "reject"
        assert any(V.G_RECONSTRUCTED in f and "missing" in f for f in report["failures"])


class TestThePATHWAYProvenanceREBUILDS:
    def test_a_native_0_75_coverage_stays_0_75(self, tmp_path):
        """The native field is `target_source_coverage`. A `.get("coverage")` against these
        bytes returns None on every record, forever, and nothing would ever say so."""
        from direct import stage3_bridge as BB
        root, _d, _p = _admitted_release(tmp_path)
        bridge = os.path.join(root, "bridge")
        assert BB.main(["--bundles-root", root, "--bridge-root", bridge, "--verify"]) == 0

        ctx = json.load(open(os.path.join(bridge, BB.BRIDGE_FILE)))["pathway_contexts"][0]
        assert ctx["target_source_coverage"] == 0.75
        assert ctx["convergence_ref"] == "conv|Stim48hr|GO-BP"
        assert ctx["source"] == "GO-BP"
        assert "coverage" not in ctx          # the name I invented is gone

    @pytest.mark.parametrize("field,value", [
        ("target_source_coverage", 0.99),
        ("convergence_ref", "conv|Rest|Reactome"),
        ("source", "Reactome"),
        ("enrichment_value", 99.0),
    ])
    def test_MISMATCHED_context_provenance_is_REFUSED(self, tmp_path, field, value):
        """A resealed context with a fabricated coverage, convergence_ref or source was
        admitted: only enrichment_value was ever compared."""
        from direct import stage3_bridge as BB
        root, _d, _p = _admitted_release(tmp_path)
        bridge = os.path.join(root, "bridge")
        assert BB.main(["--bundles-root", root, "--bridge-root", bridge, "--verify"]) == 0

        path = os.path.join(bridge, BB.BRIDGE_FILE)
        doc = json.load(open(path))
        doc["pathway_contexts"][0][field] = value
        with open(path, "w") as fh:
            json.dump(_reseal(doc), fh)

        report = V.verify(bridge, bundles_root=root)
        assert report["verdict"] == "reject"
        assert any(V.G_CTX_RECONSTRUCTED in f and field in f for f in report["failures"])

    def test_a_LEADING_EDGE_namespace_SWAPPED_from_ENSG_to_symbol_is_REFUSED(self, tmp_path):
        """It is a valid enum value. It is not THIS target's namespace — and a leading-edge
        gene whose namespace disagrees with its target record is a DIFFERENT GENE."""
        from direct import stage3_bridge as BB
        root, _d, _p = _admitted_release(tmp_path)
        bridge = os.path.join(root, "bridge")
        assert BB.main(["--bundles-root", root, "--bridge-root", bridge, "--verify"]) == 0

        path = os.path.join(bridge, BB.BRIDGE_FILE)
        doc = json.load(open(path))
        le = doc["pathway_contexts"][0]["leading_edge"][0]
        assert le["target_id_namespace"] == "ensembl_gene_id"
        le["target_id_namespace"] = "gene_symbol"          # a valid enum; the wrong gene
        with open(path, "w") as fh:
            json.dump(_reseal(doc), fh)

        report = V.verify(bridge, bundles_root=root)
        assert report["verdict"] == "reject"
        assert any("target_identity.json says" in f for f in report["failures"])


class TestNaNNeverReachesTheBridge:
    """A non-evaluable Direct row carries a NULL value and a NULL rank — the row that says
    'this arm could not score this target'. Through parquet those come back as float('nan'),
    and then json writes the literal `NaN` (not JSON) and NaN != NaN makes the row unequal to
    its own rebuild. The row is REAL and it must bridge cleanly."""

    def test_a_NON_EVALUABLE_row_round_trips_through_parquet_with_NO_NaN_BYTES(self, tmp_path):
        import pandas as pd
        from direct import stage3_bridge as BB
        root, d, _p = _admitted_release(tmp_path)

        # the producer-style unrankable row: evaluable=False, value and rank NULL
        pd.DataFrame([
            {"arm_key": DARM, "program_id": "PRG-1", "desired_change": "increase",
             "condition": "Stim48hr", "target_id": "ENSG00000111111",
             "value": 0.5, "rank": 1, "evaluable": True},
            {"arm_key": DARM, "program_id": "PRG-1", "desired_change": "increase",
             "condition": "Stim48hr", "target_id": "OCLM",
             "value": None, "rank": None, "evaluable": False},
        ]).to_parquet(os.path.join(d, "arms.parquet"))

        # ...and OCLM must be in target_identity.json, or it would drop out of the join
        from direct import target_identity as TI
        ip = os.path.join(d, TI.TARGET_IDENTITY_FILE)
        idoc = json.load(open(ip))
        idoc["records"].append({
            "target_id": "OCLM", "target_id_namespace": "gene_symbol",
            "target_symbol": "OCLM", "target_ensembl": None,
            "observed_perturbation_modality": TI.OBSERVED_PERTURBATION_MODALITY})
        idoc["n_targets"] = 2
        idoc["n_gene_symbol"] = 1
        with open(ip, "w") as fh:
            json.dump(idoc, fh)

        bridge = os.path.join(root, "bridge")
        assert BB.main(["--bundles-root", root, "--bridge-root", bridge, "--verify"]) == 0

        raw = open(os.path.join(bridge, BB.BRIDGE_FILE)).read()
        assert "NaN" not in raw and "Infinity" not in raw     # not JSON, and not a number

        rows = {r["target_id"]: r for r in json.loads(raw)["target_rows"]}
        unrankable = rows["OCLM"]
        assert unrankable["arm_value"] is None      # NULL — never a NaN, and never a zero
        assert unrankable["rank"] is None
        assert unrankable["evaluable"] is False
        assert unrankable["desired_target_modulation"] == "not_evaluated"
        assert unrankable["phenocopy_class"] == "not_evaluable"
        # ...and the row is RETAINED: a dropped row and a row that never existed look the same
        assert len(rows) == 2

        report = json.load(open(os.path.join(bridge, BB.BRIDGE_REPORT_FILE)))
        assert report["verdict"] == "admit", report["failures"]


class TestTheSTALEREPORTAttack:
    """An ADMIT report proves nothing unless it says WHICH BYTES it judged.

    The attack: change the bridge, reseal it, update the receipt's bridge hashes to match the
    new bytes, and leave the earlier ADMIT report untouched. Every hash in the chain agrees
    with itself. The receipt admits — and a fresh bridge verification REJECTS. The report was
    a verdict on bytes that no longer exist.
    """

    def test_the_report_says_WHICH_bridge_bytes_it_judged(self, tmp_path):
        from direct import stage3_bridge as BB
        root, _d, _p = _admitted_release(tmp_path)
        bridge = os.path.join(root, "bridge")
        assert BB.main(["--bundles-root", root, "--bridge-root", bridge, "--verify"]) == 0

        report = json.load(open(os.path.join(bridge, BB.BRIDGE_REPORT_FILE)))
        assert report["judged_bridge"]["raw_sha256"] == _sha(
            os.path.join(bridge, BB.BRIDGE_FILE))

    def test_a_STALE_ADMIT_report_over_NEW_bridge_bytes_is_REFUSED(self, tmp_path):
        import hashlib

        from direct import stage3_bridge as BB
        root, _d, _p = _admitted_release(tmp_path)
        bridge = os.path.join(root, "bridge")
        assert BB.main(["--bundles-root", root, "--bridge-root", bridge, "--verify"]) == 0

        # (1) forge the bridge and reseal it
        bpath = os.path.join(bridge, BB.BRIDGE_FILE)
        doc = json.load(open(bpath))
        doc["target_rows"][0]["arm_value"] = -0.5
        doc["target_rows"][0]["desired_target_modulation"] = "increase"
        doc["target_rows"][0]["phenocopy_class"] = "inhibitor_opposed"
        with open(bpath, "w") as fh:
            json.dump(_reseal(doc), fh)

        # (2) point the receipt at the NEW bridge bytes, honestly, and reseal it.
        #     The earlier ADMIT report is left EXACTLY as it was.
        recp = os.path.join(bridge, BB.RECEIPT_FILE)
        rec = json.load(open(recp))
        rec["bridge"]["raw_sha256"] = _sha(bpath)
        rec["bridge"]["canonical_sha256"] = hashlib.sha256(json.dumps(
            json.load(open(bpath)), sort_keys=True, separators=(",", ":"),
            ensure_ascii=True).encode()).hexdigest()
        rec.pop("receipt_sha256")
        rec["receipt_sha256"] = hashlib.sha256(json.dumps(
            rec, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True).encode()).hexdigest()
        with open(recp, "w") as fh:
            json.dump(rec, fh)

        # every hash agrees with itself — and the receipt must still refuse
        out = V.verify_receipt(bridge, bundles_root=root)
        assert out["verdict"] == "reject"
        assert any(V.G_RECEIPT_STALE in f for f in out["failures"])
        # BOTH proofs fire: the report names other bytes, AND a fresh verification rejects
        assert any("verdict on different bytes" in f for f in out["failures"])
        assert any("no longer verifies" in f for f in out["failures"])

    def test_a_report_that_names_NO_bridge_bytes_is_REFUSED(self, tmp_path):
        import hashlib

        from direct import stage3_bridge as BB
        root, _d, _p = _admitted_release(tmp_path)
        bridge = os.path.join(root, "bridge")
        assert BB.main(["--bundles-root", root, "--bridge-root", bridge, "--verify"]) == 0

        rpath = os.path.join(bridge, BB.BRIDGE_REPORT_FILE)
        report = json.load(open(rpath))
        del report["judged_bridge"]                     # an admission that names no artifact
        with open(rpath, "w") as fh:
            json.dump(report, fh, indent=2, sort_keys=True)

        recp = os.path.join(bridge, BB.RECEIPT_FILE)
        rec = json.load(open(recp))
        rec["bridge_report"]["raw_sha256"] = _sha(rpath)
        rec["bridge_report"]["canonical_sha256"] = hashlib.sha256(json.dumps(
            json.load(open(rpath)), sort_keys=True, separators=(",", ":"),
            ensure_ascii=True).encode()).hexdigest()
        rec.pop("receipt_sha256")
        rec["receipt_sha256"] = hashlib.sha256(json.dumps(
            rec, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True).encode()).hexdigest()
        with open(recp, "w") as fh:
            json.dump(rec, fh)

        out = V.verify_receipt(bridge, bundles_root=root)
        assert out["verdict"] == "reject"
        assert any("can be moved onto any" in f for f in out["failures"])


# --------------------------------------------------------------------------- #
# TEMPORAL: identity is the CANONICAL JOIN across BOTH admitted Direct endpoints.
# --------------------------------------------------------------------------- #
TARM = "temporal|PRG-1|increase|from_condition=Rest|to_condition=Stim48hr"


def _direct_at(root, condition, value=0.5, namespace="ensembl_gene_id", symbol="SYM",
               ensembl="ENSG00000111111"):
    """A Direct endpoint bundle for ONE condition, carrying its target_identity.json."""
    import pandas as pd
    from direct import target_identity as TI

    d = os.path.join(root, "direct", condition)
    os.makedirs(d, exist_ok=True)
    arm = f"direct|PRG-1|increase|condition={condition}"
    with open(os.path.join(d, "arm_bundle.json"), "w") as fh:
        json.dump({"schema_version": "spot.stage02_direct_arm_bundle.v1",
                   "arm_bundle_run_id": f"D-{condition}", "condition": condition}, fh)
    pd.DataFrame([{"arm_key": arm, "program_id": "PRG-1", "desired_change": "increase",
                   "condition": condition, "target_id": "ENSG00000111111",
                   "value": value, "rank": 1, "evaluable": True}]
                 ).to_parquet(os.path.join(d, "arms.parquet"))
    with open(os.path.join(d, TI.TARGET_IDENTITY_FILE), "w") as fh:
        json.dump({"schema_version": TI.SCHEMA_VERSION, "condition": condition,
                   "columns": list(TI.COLUMNS),
                   "observed_perturbation_modality": TI.OBSERVED_PERTURBATION_MODALITY,
                   "modality_rule_id": TI.MODALITY_RULE_ID, "n_targets": 1,
                   "n_ensembl_gene_id": 1, "n_gene_symbol": 0,
                   "records": [{"target_id": "ENSG00000111111",
                                "target_id_namespace": namespace, "target_symbol": symbol,
                                "target_ensembl": ensembl,
                                "observed_perturbation_modality":
                                    TI.OBSERVED_PERTURBATION_MODALITY}]}, fh)
    return d


def _temporal_release(tmp_path, **endpoint_kw):
    """Two admitted Direct endpoints + the temporal bundle that differences them."""
    root = str(tmp_path)
    _direct_at(root, "Rest")
    _direct_at(root, "Stim48hr", **endpoint_kw)

    t = os.path.join(root, "temporal", "Rest__Stim48hr")
    os.makedirs(os.path.join(t, "rankings"), exist_ok=True)
    with open(os.path.join(t, "arm_bundle.json"), "w") as fh:
        json.dump({"schema_version": "spot.stage02_temporal_arm_bundle.v1",
                   "bundle_id": "T-1", "lane": "temporal",
                   "context": {"from_condition": "Rest", "to_condition": "Stim48hr"},
                   # 276a9ad: the identity mirrors are NULL. The bridge never reads them.
                   "base_records": [{"base_key": "PRG-1|ENSG00000111111",
                                     "target_id": "ENSG00000111111",
                                     "target_id_namespace": None, "target_symbol": None,
                                     "target_ensembl": None,
                                     "perturbation_modality": "CRISPRi_knockdown"}]}, fh)
    with open(os.path.join(t, "rankings", "PRG-1__increase.json"), "w") as fh:
        json.dump({"arm_key": TARM,
                   "records": [{"target_id": "ENSG00000111111",
                                "base_key": "PRG-1|ENSG00000111111",
                                "arm_value": 0.5, "evaluable": True, "rank": 1}]}, fh)

    lanes = {la: {"aggregate_disposition": "admitted", "native_verdict": "ADMIT",
                  "native_self_hash": la[0] * 64} for la in ("direct", "temporal")}
    with open(os.path.join(root, "stage2_run_manifest.json"), "w") as fh:
        json.dump({"lane_admissions": lanes,
                   "stage1_v3_release": {"release_canonical_sha256": "s" * 64}}, fh,
                  indent=2, sort_keys=True)
    with open(os.path.join(root, "stage2_aggregate_verification.json"), "w") as fh:
        json.dump({"verdict": "admit", "n_failed": 0}, fh, indent=2, sort_keys=True)
    return root, t


class TestTemporalIdentityIsTheCANONICALEndpointJoin:
    """The native temporal producer (276a9ad) leaves target_symbol, target_ensembl and
    target_id_namespace NULL, and base_records mirror those nulls faithfully. They are not an
    identity source — they are an empty box with the right label on it.

    A temporal arm is a DIFFERENCE BETWEEN TWO DIRECT ENDPOINTS, so its targets are exactly as
    identified as those two endpoints AGREE they are.
    """

    def test_the_NATIVE_276a9ad_bundle_replays_and_gets_a_REAL_identity(self, tmp_path):
        from direct import stage3_bridge as BB
        root, t = _temporal_release(tmp_path)

        # the producer's own mirrors really are null — this is the shape we refuse to trust
        bases = json.load(open(os.path.join(t, "arm_bundle.json")))["base_records"]
        assert bases[0]["target_id_namespace"] is None
        assert bases[0]["target_symbol"] is None

        bridge = os.path.join(root, "bridge")
        assert BB.main(["--bundles-root", root, "--bridge-root", bridge, "--verify"]) == 0

        rows = json.load(open(os.path.join(bridge, BB.BRIDGE_FILE)))["target_rows"]
        temporal = [r for r in rows if r["lane"] == "temporal"]
        assert len(temporal) == 1
        r = temporal[0]
        # ...and the identity is REAL, from the endpoints — not the null mirror
        assert r["target_id_namespace"] == "ensembl_gene_id"
        assert r["target_symbol"] == "SYM"
        assert r["target_ensembl"] == "ENSG00000111111"
        assert r["observed_perturbation_modality"] == "CRISPRi_knockdown"
        assert r["identity_source"] == "target_identity.json"

    def test_it_BINDS_BOTH_endpoint_identity_artifacts_by_hash(self, tmp_path):
        from direct import stage3_bridge as BB
        root, _t = _temporal_release(tmp_path)
        bridge = os.path.join(root, "bridge")
        assert BB.main(["--bundles-root", root, "--bridge-root", bridge, "--verify"]) == 0

        doc = json.load(open(os.path.join(bridge, BB.BRIDGE_FILE)))
        tb = [b for b in doc["bindings"]["native_bundles"].values()
              if b["lane"] == "temporal"][0]
        src = tb["identity_source"]
        assert src["kind"] == "direct_endpoints"
        assert src["trusts_the_temporal_identity_mirrors"] is False
        assert set(src["endpoints"]) == {"Rest", "Stim48hr"}
        for cond in ("Rest", "Stim48hr"):
            want = _sha(os.path.join(root, "direct", cond, "target_identity.json"))
            assert src["endpoints"][cond]["raw_sha256"] == want

    def test_MISMATCHED_endpoint_identity_REFUSES_to_build(self, tmp_path):
        """The two endpoints disagree about who this target is. It is not one target, and a
        difference computed across them is a difference between two different genes."""
        from direct import stage3_bridge as BB
        root, _t = _temporal_release(tmp_path, symbol="A_DIFFERENT_GENE")

        with pytest.raises(BB.BridgeError, match="DISAGREE about its identity"):
            BB.assemble(root, os.path.join(root, "bridge"))

    def test_a_MISMATCH_introduced_AFTER_the_build_is_REFUSED_by_the_verifier(self, tmp_path):
        from direct import stage3_bridge as BB
        root, _t = _temporal_release(tmp_path)
        bridge = os.path.join(root, "bridge")
        assert BB.main(["--bundles-root", root, "--bridge-root", bridge, "--verify"]) == 0

        # somebody edits ONE endpoint's identity afterwards
        ip = os.path.join(root, "direct", "Stim48hr", "target_identity.json")
        doc = json.load(open(ip))
        doc["records"][0]["target_symbol"] = "A_DIFFERENT_GENE"
        with open(ip, "w") as fh:
            json.dump(doc, fh)

        report = V.verify(bridge, bundles_root=root)
        assert report["verdict"] == "reject"
        assert any(V.G_TEMPORAL_IDENTITY in f or V.G_SOURCE_BYTES in f
                   for f in report["failures"])

    def test_a_temporal_target_NEITHER_endpoint_identifies_is_REFUSED(self, tmp_path):
        from direct import stage3_bridge as BB
        root, t = _temporal_release(tmp_path)
        rp = os.path.join(t, "rankings", "PRG-1__increase.json")
        doc = json.load(open(rp))
        doc["records"][0]["target_id"] = "ENSG00000999999"      # in no endpoint's identity
        with open(rp, "w") as fh:
            json.dump(doc, fh)

        with pytest.raises(BB.BridgeError, match="disappear without a trace"):
            BB.assemble(root, os.path.join(root, "bridge"))
