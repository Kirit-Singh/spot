"""The combined-objective firewall: schema-valid is not admitted.

The Stage-3 owner froze the contract (r7, `cb99125…`) with a warning: the document schema is
`additionalProperties: true`, so a bundle can be schema-valid and still carry a smuggled
combined/headline objective. The firewall against one lives in the verifier's recursive
banned-key scan, NOT in the JSON Schema.

Stage 4 never used jsonschema for admission — but it had the same hole by another route, and
these tests exist because it was LIVE, reproduced end to end, not hypothesized:

    `RETIRED_KEYS` guards the promotion lattice. It says nothing about `overall_rank`, and
    `overall_rank` is not canonical content — so the canonical hash and the bundle_id do not
    move when you add it. Re-seal the three hashes the consumer checks and the old consumer
    ADMITTED the bundle, under its own unchanged identity, carrying a cross-arm objective
    Stage 3 refuses to compute.

Every re-seal in these tests is deliberate: an attacker who edits a bundle fixes up the
hashes, and a test that skips the fix-up proves nothing. Forge helpers: `_stage3_forge`.
"""

from __future__ import annotations

import json
import os

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from _stage3_forge import (
    copy_bundle,
    edit_doc,
    reseal_fully,
    reseal_manifest,
)
from analysis.firewall import Rejection
from analysis.stage3_contract_v2 import sha256_file, verify_annotation_bundle
from analysis.stage3_frozen import banned_keys_in


def test_the_clean_pinned_bundle_is_admitted(tmp_path):
    """The floor. If the firewall refuses a clean bundle it is not a firewall, it is a wall."""
    doc, tables = verify_annotation_bundle(copy_bundle(str(tmp_path)))
    assert doc["bundle_id"] == "s3_0b119088734643bf"
    assert doc["artifact_class"] == "analysis"
    assert tables and all(t in tables for t in ("candidates", "target_drug_edges"))


def test_a_resealed_combined_objective_is_refused(tmp_path):
    """THE regression. A fully re-sealed `overall_rank` was ADMITTED before this landed.

    Every hash the consumer checks is repaired, and the bundle keeps its own bundle_id —
    so nothing in the hash chain can catch it. Only the banned-key scan can.
    """
    from analysis.stage3_contract import content_hash

    bundle = copy_bundle(str(tmp_path))
    edit_doc(bundle, lambda d: d.update({"overall_rank": 1}))

    # the bundle is internally consistent: this is not a mangled file, it is a sealed forgery
    with open(os.path.join(bundle, "drug_annotation.json"), encoding="utf-8") as fh:
        doc = json.load(fh)
    assert doc["overall_rank"] == 1
    assert doc["document_sha256"] == content_hash(
        {k: v for k, v in doc.items() if k != "document_sha256"})
    assert doc["bundle_id"] == "s3_0b119088734643bf", "the bundle id must be UNMOVED"

    with pytest.raises(Rejection) as exc:
        verify_annotation_bundle(bundle)
    assert exc.value.code == "stage3_combined_objective_present"
    assert "$.overall_rank" in str(exc.value)


@pytest.mark.parametrize("key", ["combined_score", "headline_arm", "composite_score",
                                 "best_arm", "rank", "pharmacologic_effect"])
def test_every_banned_objective_is_refused_under_any_name(tmp_path, key):
    """A combined objective can always be renamed. The denylist is why that does not help."""
    bundle = copy_bundle(str(tmp_path))
    edit_doc(bundle, lambda d: d.update({key: "x"}))
    with pytest.raises(Rejection) as exc:
        verify_annotation_bundle(bundle)
    assert exc.value.code == "stage3_combined_objective_present"


def test_a_combined_objective_nested_in_a_candidate_is_refused(tmp_path):
    """The scan is recursive. A per-candidate objective is still a cross-arm objective."""
    bundle = copy_bundle(str(tmp_path))

    def mutate(doc):
        # an int, not a float: Stage-3 canonical content carries no floats by construction,
        # so a float would be refused by the hasher before the scan ever ran.
        doc["candidates"][0]["overall_score"] = 1

    edit_doc(bundle, mutate)
    with pytest.raises(Rejection) as exc:
        verify_annotation_bundle(bundle)
    assert exc.value.code == "stage3_combined_objective_present"
    assert "candidates[0].overall_score" in str(exc.value)


def test_a_combined_objective_COLUMN_is_refused(tmp_path):
    """A banned key hides in a table as easily as in a document — and a column reaches the
    rows Stage 4 actually reads.

    Sealed FULLY, table hashes and canonical content included: this is the bundle an upstream
    Stage 3 would emit if it started ranking candidates, not a clumsy tamper. Every hash
    reproduces. Only the column scan is left to catch it.
    """
    bundle = copy_bundle(str(tmp_path))
    path = os.path.join(bundle, "candidates.parquet")
    table = pq.read_table(path)
    table = table.append_column(
        "overall_rank", pa.array(list(range(1, table.num_rows + 1)), pa.int64()))
    pq.write_table(table, path)
    reseal_fully(bundle)

    with pytest.raises(Rejection) as exc:
        verify_annotation_bundle(bundle)
    assert exc.value.code == "stage3_combined_objective_present"
    assert "candidates.overall_rank" in str(exc.value)


def test_a_combined_objective_hidden_in_a_struct_CELL_is_refused(tmp_path):
    """One level down, under an innocent column name.

    `arm_evidence_states` is a list<struct> in the real bundle, so a cross-arm objective can
    ride into Stage 4's rows INSIDE a cell while every column name stays clean. A scan that
    only read column names missed this — proved before the row scan went recursive.
    """
    bundle = copy_bundle(str(tmp_path))
    path = os.path.join(bundle, "candidates.parquet")
    rows = pq.read_table(path).to_pylist()
    rows[0]["arm_evidence_states"] = [
        {**s, "overall_rank": 1} for s in rows[0]["arm_evidence_states"]]
    pq.write_table(pa.Table.from_pylist(rows), path)
    reseal_fully(bundle)

    with pytest.raises(Rejection) as exc:
        verify_annotation_bundle(bundle)
    assert exc.value.code == "stage3_combined_objective_present"
    assert "arm_evidence_states[0].overall_rank" in str(exc.value)


def test_a_combined_objective_in_a_SIGNED_BUT_UNCONSUMED_table_is_refused(tmp_path):
    """The bundle signs 18 parquet tables; Stage 4 reads only 11. An adversarial review
    demonstrated a live bypass: a banned column in one of the other 7 (`cross_arm`) was
    ADMITTED, because those tables were only file-hash-checked, never banned-scanned.

    Every SIGNED table is scanned now. `cross_arm` is not in READ_TABLES and its rows never
    reach Stage 4's computation — but a bundle carrying a cross-arm objective anywhere is a
    bundle Stage 4 refuses, and a sibling consumer that DID read `cross_arm` would otherwise
    read un-firewalled content.
    """
    bundle = copy_bundle(str(tmp_path))
    path = os.path.join(bundle, "cross_arm.parquet")
    table = pq.read_table(path)
    table = table.append_column(
        "overall_rank", pa.array(list(range(1, table.num_rows + 1)), pa.int64()))
    pq.write_table(table, path)
    # re-seal ONLY the file hash + manifest — cross_arm's content hash is not in canonical
    # content, so the document and bundle_id do not move. This is the exact demonstrated attack.
    reseal_manifest(bundle)

    with pytest.raises(Rejection) as exc:
        verify_annotation_bundle(bundle)
    assert exc.value.code == "stage3_combined_objective_present"
    assert "cross_arm.overall_rank" in str(exc.value)


def test_a_combined_objective_COLUMN_on_an_EMPTY_table_is_refused(tmp_path):
    """An empty table has no rows to iterate, so a row-only scan never sees its column names.
    The scan reads the parquet SCHEMA precisely so a zero-row table cannot hide a banned
    column. `pathway_nodes` is empty in the fixture — the demonstrated blind spot."""
    bundle = copy_bundle(str(tmp_path))
    path = os.path.join(bundle, "pathway_nodes.parquet")
    table = pq.read_table(path)
    assert table.num_rows == 0, "this test needs an empty table to be meaningful"
    table = table.append_column("overall_rank", pa.array([], pa.int64()))
    pq.write_table(table, path)
    reseal_manifest(bundle)

    with pytest.raises(Rejection) as exc:
        verify_annotation_bundle(bundle)
    assert exc.value.code == "stage3_combined_objective_present"
    assert "pathway_nodes.overall_rank" in str(exc.value)


def test_a_combined_objective_in_a_SIGNED_EXTRA_JSON_is_refused(tmp_path):
    """Step 3b scans the document + manifest; the table scan covers parquet. A bundle that
    signs a THIRD json file could otherwise smuggle a banned objective in it. Nothing consumes
    such a file today — this is defense-in-depth — but "refused in ANY signed surface" has to
    mean any, including one Stage 4 does not yet read.
    """
    bundle = copy_bundle(str(tmp_path))
    extra = os.path.join(bundle, "extra.json")
    with open(extra, "w", encoding="utf-8") as fh:
        json.dump({"overall_rank": 1}, fh)

    man_path = os.path.join(bundle, "manifest.json")
    with open(man_path, encoding="utf-8") as fh:
        manifest = json.load(fh)
    manifest["files"].append({"file": "extra.json", "file_sha256": sha256_file(extra)})
    with open(man_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
    reseal_manifest(bundle)

    with pytest.raises(Rejection) as exc:
        verify_annotation_bundle(bundle)
    assert exc.value.code == "stage3_combined_objective_present"
    assert "extra.json.overall_rank" in str(exc.value)


def test_stage2_joint_context_is_NOT_banned():
    """The other half of a denylist: it must not refuse what Stage 2 legitimately releases.

    `joint_status` / `pareto_tier` / `joint_ordering_method_id` are typed context, carried
    verbatim. A denylist that ate them would refuse every real Stage-2 bundle.
    """
    assert not banned_keys_in({"stage2_joint_context": {
        "joint_status": "both_arms", "pareto_tier": 3,
        "joint_ordering_method_id": "spot.stage02.pareto.two_arm.v1"}})


def test_this_firewall_suite_never_skips_on_a_bundle():
    """A Stage-3 bundle that fails the firewall must FAIL, never skip."""
    with open(__file__, encoding="utf-8") as fh:
        source = fh.read()
    assert ("pytest" + ".skip(") not in source, (
        "the combined-objective firewall suite regained a skip. A refused bundle FAILS.")
