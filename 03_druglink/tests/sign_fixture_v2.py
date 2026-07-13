"""Shared fixture for the v2 sign-rule suites: the RE-PINNED store and a typed W3 arm.

Every test here is NON-VACUOUS: it asserts the edge/candidate set is NON-EMPTY before trusting
any pass. A suite that silently produced zero edges would agree with every claim ever made.

The typed arm rows below are TEST VECTORS for a deterministic rule — the modality, the namespace,
the modulation token and the phenocopy class exactly as W3 will serialize them. They are NOT
synthesized into an admitted release: the disk-backed loader still REFUSES real Stage-2 bytes
that lack these fields (``test_the_real_native_bytes_refuse_and_yield_zero_edges``), and that
refusal is the contract until W3 regenerates.
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

import pytest

from druglink import edge_build_v2 as eb2
from druglink import modality_v2 as mv2
from druglink import stage2_aggregate as sa
from druglink import universe_rows as ur

NS_ENSEMBL = "ensembl_gene_id"
NS_SYMBOL = "gene_symbol"

# The RE-PINNED admitted store: Stage-2's canonical namespace vocabulary
# (`ensembl_gene_id` / `gene_symbol`), emitted by `druglink.universe_repin` from the store an
# independent verifier admitted. Its rows are the REAL ChEMBL mechanisms, unaltered.
REPINNED_STORE = "/home/tcelab/.cache/spot-stage3-universe-w3tokens/store"

CRISPRI = "CRISPRi_knockdown"
CRISPRA = "CRISPRa_activation"


def load_store() -> ur.AdmittedStore:
    """The re-pinned store's REAL rows, constructed directly.

    `load_store` is the ADMISSION path and it pins the store id an independent verifier signed —
    which still names the pre-repin store, because the re-pinned one has not been re-admitted
    yet. That admission is upstream work in flight, and it is NOT this suite's to grant: moving
    an admission pin to make a test pass is precisely the defect this lane exists to catch.

    So these tests do what `candidates_v2_fixture` already does — construct the store from its
    OWN bytes and test the SIGN RULE against real ChEMBL assertions. Whether the store is
    ADMITTED is a different question, asked by the store's own admission tests.
    """
    rows_path = os.path.join(REPINNED_STORE, "universe_store.rows.json")
    manifest_path = os.path.join(REPINNED_STORE, "universe_manifest.json")
    if not os.path.isfile(rows_path):
        pytest.skip(f"the re-pinned canonical-token store is not on this host ({REPINNED_STORE})")
    with open(rows_path, encoding="utf-8") as fh:
        doc = json.load(fh)
    rows = doc if isinstance(doc, list) else doc["rows"]
    with open(manifest_path, encoding="utf-8") as fh:
        manifest = json.load(fh)

    # The store must already be on the canonical vocabulary. If it is not, the tests below would
    # be asserting the sign rule against an identity space nobody agreed to.
    assert {r["target_id_namespace"] for r in rows} <= {NS_ENSEMBL, NS_SYMBOL}, \
        "the re-pinned store must carry Stage-2's canonical namespace tokens"

    typed = ur.derive_typed_universe(rows)
    return ur.AdmittedStore(
        store_dir=REPINNED_STORE, manifest=manifest, rows=rows,
        eligibility_evidence={}, source_provenance=[],
        licences={ur.LICENSE_NAME: "CC BY-SA 3.0", ur.ATTRIBUTION_NAME: "ChEMBL"},
        typed_universe=typed, typed_universe_sha256=ur.typed_universe_sha256(typed),
        store_binding={"store_id": manifest.get("store_id")},
        _index={(r["target_id_namespace"], r["target_id"]): r for r in rows})


def pick_drug_known(store: ur.AdmittedStore) -> tuple[str, str]:
    """A REAL target the store holds REAL ChEMBL mechanisms for. Non-vacuity depends on it."""
    row = next(r for r in sorted(store.rows, key=lambda r: (r["target_id_namespace"],
                                                            r["target_id"]))
               if r.get("drugs"))
    assert row["drugs"], "the chosen target must genuinely carry drug assertions"
    return str(row["target_id"]), str(row["target_id_namespace"])


# --------------------------------------------------------------------------- #
# A typed arm, exactly as W3 will serialize it.
# --------------------------------------------------------------------------- #
def typed_row(target: tuple[str, str], *, arm_value: Optional[float], evaluable: bool = True,
              rank: Optional[int] = 1, modality: str = CRISPRI,
              modulation: Optional[str] = None, **over: Any) -> dict[str, Any]:
    tid, ns = target
    sign = (mv2.observed_sign_state(arm_value, evaluable=evaluable, origin_is_measured=True)
            if modulation is None else None)
    row = {
        "target_id": tid,
        mv2.FIELD_NAMESPACE: ns,
        mv2.FIELD_MODALITY: modality,
        mv2.FIELD_ARM_VALUE: arm_value,
        mv2.FIELD_EVALUABLE: evaluable,
        "rank": rank,
        # Stage-2's OWN token, consistent with the value it was derived from — the thing Stage 3
        # cross-checks. A test that shipped an inconsistent pair would be testing the gate, and
        # there is a dedicated test for that below.
        mv2.FIELD_MODULATION: (modulation if modulation is not None
                               else mv2.desired_target_modulation(modality, str(sign))),
        mv2.FIELD_PHENOCOPY_CLASS: "transcript_knockdown",
    }
    row.update(over)
    return row


def arm(lane: str, records: list[dict[str, Any]], *, key: str = "A",
        desired_change: str = "increase") -> sa.LoadedArm:
    bundle = sa.AdmittedBundle(
        bundle_key=f"{lane}|Rest", bundle_id=f"B_{lane}", lane=lane, path="d",
        raw_sha256="a" * 64, canonical_sha256="b" * 64, files={}, condition="Rest",
        pathway_source=("GO-BP" if lane == sa.LANE_PATHWAY else None))
    return sa.LoadedArm(
        arm_key=f"{lane}|P0|{desired_change}|{key}", lane=lane, program_id="P0",
        desired_change=desired_change, bundle=bundle,
        ranking={"raw_sha256": "c" * 64, "canonical_sha256": "d" * 64},
        # The NATIVE provenance keys. A null verifier identity is refused (see its own test).
        provenance={"manifest_raw_sha256": "e" * 64, "manifest_canonical_sha256": "f" * 64,
                    "manifest_self_hash": "0" * 64,
                    "aggregate_verifier_id": "spot.stage02.run_manifest.verifier.v1",
                    "aggregate_verdict": "admit", "stage1_release_sha256": "1" * 64},
        records=tuple(records))


def bridge_binding(arms: list[sa.LoadedArm]) -> dict[str, Any]:
    """The BRIDGE these fixture rows were typed by — through the producer's OWN binding shape.

    Every measured row carries a namespace and a modality, and the only place those can come from
    is the bridge. So a fixture aggregate names a bridge too: an emitted bundle that named none
    could be rebuilt from a DIFFERENT admitted bridge and come out byte-identical.
    """
    n = sum(len(a.records) for a in arms if a.lane in sa.MEASURED_LANES)
    return sa.AdmittedBridge(
        bridge_raw_sha256="2" * 64, bridge_canonical_sha256="3" * 64,
        bridge_self_hash="4" * 64, report_raw_sha256="5" * 64, receipt_raw_sha256="6" * 64,
        verifier_id="spot.stage02.stage3_bridge.independent_verifier.v1", verdict="admit",
        n_rows=n, n_pathway_contexts=0, rows_by_arm={},
        rule_id="spot.stage02.stage3_row.direction_and_namespace.v1").binding()


def aggregate(arms: list[sa.LoadedArm]) -> sa.AdmittedAggregate:
    return sa.AdmittedAggregate(
        artifact_class="fixture", manifest_raw_sha256="e" * 64,
        manifest_canonical_sha256="f" * 64, manifest_self_hash="0" * 64,
        verifier_id="spot.stage02.run_manifest.verifier.v1", verdict="admit",
        stage1_release_sha256="1" * 64,
        # AdmittedBundle holds a dict, so it is not hashable: dedupe by KEY, not by set.
        bundles=tuple({a.bundle.bundle_key: a.bundle for a in arms}.values()),
        arms=tuple(arms), program_ids=("P0",), bridge_binding=bridge_binding(arms))


def edges_for(store: ur.AdmittedStore, arms: list[sa.LoadedArm]) -> list[dict[str, Any]]:
    return eb2.build_edges(aggregate(arms), store)["target_drug_edges"]


def by_action(edges: list[dict[str, Any]], action: str) -> list[dict[str, Any]]:
    return [e for e in edges if e["action_type_normalized"] == action]


MEASURED_LANES = (sa.LANE_DIRECT, sa.LANE_TEMPORAL)
