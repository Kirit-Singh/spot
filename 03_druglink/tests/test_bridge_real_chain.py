"""The REAL Stage-2 bridge chain on disk, run through the real consumer.

WHAT THIS CHAIN IS, EXACTLY. It is the bytes Stage-2's real CLIs emitted — real schema, real
hashes, a real separate verifier's report, a real receipt. It is NOT a production result: its
bundle ids are ``FIXTURE-*`` and its gene sets are ``FIXTURE-SET-*``. So it proves the PLUMBING —
that the consumer parses, re-hashes and cross-binds the genuine artifact shape — and it may never
be reported as a Stage-3 finding.

IT IS ALSO EXPECTED TO REFUSE UPSTREAM, and that refusal is the point of the second test. Its
pathway bundles index 20 arm keys in the manifest but ship none in their ``arm_bundle.json``, so
``admit_aggregate`` refuses at ``the_manifests_arm_index_disagrees_with_the_bundles_bytes`` /
``the_release_does_not_resolve_its_full_arm_topology`` — before the bridge is ever opened. That is
the aggregate gate working. This test PINS that refusal rather than weakening the gate to get a
green tick out of a stale release.

Skips when the chain is not on this host: it is a local read-only copy, not a repo artifact.
"""
from __future__ import annotations

import json
import os

import pytest

from druglink import stage2_aggregate as sa
from druglink import stage2_bridge as sb
from druglink.hashing import file_sha256
from druglink.stage2_contract import stage2_content_sha256

CHAIN = os.environ.get(
    "SPOT_W3_CHAIN",
    os.path.expanduser("~/.spot-runs/stage3-universe-20260713/w3_v3_chain/bundles"))

BRIDGE = os.path.join(CHAIN, "stage3_bridge.json")
REPORT = os.path.join(CHAIN, "stage3_bridge_verification.json")
RECEIPT = os.path.join(CHAIN, "stage2_stage3_receipt.json")
MANIFEST = os.path.join(CHAIN, "stage2_run_manifest.json")
AGG_REPORT = os.path.join(CHAIN, "stage2_aggregate_verification.json")

pytestmark = pytest.mark.skipif(
    not os.path.isfile(BRIDGE),
    reason=f"the real W3 chain is not on this host ({CHAIN})")


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def test_the_real_bridge_recomputes_every_hash_the_chain_claims():
    """Recompute every digest from the bytes. Trust none of the text claims."""
    bridge, report, receipt = _load(BRIDGE), _load(REPORT), _load(RECEIPT)

    bridge_raw = file_sha256(BRIDGE)
    bridge_canonical = stage2_content_sha256(bridge)

    # 1. the bridge recomputes its OWN identity
    assert sb.bridge_self_hash(bridge) == bridge["bridge_sha256"] == \
        "6fd1bc7d6fe4940062a97df340c78ba662d7222e2e21787d4c0ea722b6e63a17"
    assert bridge_raw == \
        "871b37e7b26943eb9abdff0b7f06464be06f48cd027d9561a01ac7b903041f5e"

    # 2. the SEPARATE report judged THESE bytes
    assert report["verifier_id"] == sb.BRIDGE_VERIFIER_ID
    assert report["generator_is_not_verifier"] is True
    assert report["verdict"] == sa.ADMIT and report["n_failed"] == 0
    assert report["reconstructs_from_admitted_native_bytes"] is True
    assert report["judged_bridge"]["raw_sha256"] == bridge_raw
    assert report["judged_bridge"]["canonical_sha256"] == bridge_canonical

    # 3. the RECEIPT binds the bridge AND its report, by raw AND canonical bytes
    assert sb.receipt_self_hash(receipt) == receipt["receipt_sha256"]
    assert receipt["bridge"]["raw_sha256"] == bridge_raw
    assert receipt["bridge"]["canonical_sha256"] == bridge_canonical
    assert receipt["bridge_report"]["raw_sha256"] == file_sha256(REPORT)

    # 4. the aggregate it stands on
    assert receipt["aggregate"]["manifest"]["raw_sha256"] == file_sha256(MANIFEST)
    assert receipt["aggregate"]["report"]["raw_sha256"] == file_sha256(AGG_REPORT)

    # 5. A PRODUCER DOES NOT ADMIT ITSELF — and the real one says so.
    assert bridge["self_admitted"] is False and bridge["admitted"] is False
    assert bridge["verdict"] == "pending_independent_verification"

    # 6. the shape the consumer types the native rows with
    assert bridge["n_target_rows"] == len(bridge["target_rows"]) == 2160
    assert bridge["n_pathway_contexts"] == len(bridge["pathway_contexts"]) == 240
    assert {r["lane"] for r in bridge["target_rows"]} == {"direct", "temporal"}
    assert all(c["is_a_crispri_target_row"] is False for c in bridge["pathway_contexts"])
    assert all(c["may_be_matched_to_a_drug_as_a_target"] is False
               for c in bridge["pathway_contexts"])


def test_the_real_chain_refuses_UPSTREAM_at_the_aggregate_gate():
    """PINNED, NOT WORKED AROUND. This chain's pathway bundles index 20 arm keys and ship none,
    so the AGGREGATE gate refuses it before the bridge is ever opened.

    That is the gate doing its job on a stale release. The fix is a complete Stage-2 release, not
    a weaker Stage-3 gate — so this test exists to make any future weakening of it fail loudly.
    """
    with pytest.raises(sa.Stage2AggregateError) as exc:
        sa.admit_aggregate(manifest_path=MANIFEST, report_path=AGG_REPORT,
                           bundles_root=CHAIN,
                           stage1_release_path=os.path.join(
                               os.path.dirname(CHAIN), "release_root",
                               "stage01_v3_release.json"),
                           artifact_class="fixture")
    message = str(exc.value)
    assert ("arm_index_disagrees" in message or "full_arm_topology" in message
            or "incomplete" in message.lower()), message
