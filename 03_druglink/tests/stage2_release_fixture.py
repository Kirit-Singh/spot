"""Sealed NON-PRODUCTION Stage-2 aggregate releases, shared by the aggregate tests.

Every release built here declares ``artifact_class="fixture"`` unless a caller overrides it,
so it is refused by the analysis path and can never be laundered into a real run. It exists
to exercise admission PLUMBING: no drug is named, no target is ranked, no science asserted.
"""
from __future__ import annotations

import hashlib
import json
import os


from druglink import stage2_aggregate as sa
from druglink.hashing import content_hash

PROGRAMS = tuple(f"FIXTURE_PROG_{i:02d}" for i in range(sa.N_PROGRAMS))
TARGETS = ("FIXTURE_TGT_00", "FIXTURE_TGT_01", "FIXTURE_TGT_02")
INDEPENDENT = "spot.stage02.aggregate.independent_verifier.v1"
MANIFEST_SCHEMA = "spot.stage02_aggregate_run_manifest.v1"
REPORT_SCHEMA = "spot.stage02_aggregate_verification.v1"


def _hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# A sealed, NON-PRODUCTION 15-bundle release. Synthetic programs, synthetic targets.
# --------------------------------------------------------------------------- #
def _base_records(lane: str) -> list[dict]:
    out = []
    for prog in PROGRAMS:
        for tgt in TARGETS:
            base = {"base_key": f"{prog}|{tgt}", "program_id": prog, "target_id": tgt,
                    "target_id_namespace": "fixture", "target_symbol": f"SYM_{tgt[-2:]}",
                    "target_ensembl": f"ENSGT{tgt[-2:]}", "evaluable": True}
            if lane == sa.LANE_TEMPORAL:
                base["from_released_estimate_id"] = f"{tgt}|from"
                base["to_released_estimate_id"] = f"{tgt}|to"
            else:
                base["released_estimate_id"] = f"{tgt}|est"
            out.append(base)
    return out


def _records(lane: str, prog: str, source: str | None) -> list[dict]:
    rows = []
    for i, tgt in enumerate(TARGETS):
        if lane == sa.LANE_PATHWAY:
            # An inferred pathway node: nobody perturbed it, so it carries no value and
            # no rank. Null stays null.
            rows.append({"target_id": tgt, "target_id_namespace": "fixture",
                         "set_id": f"{source}:FIXTURE_SET_{i}", "arm_value": None,
                         "rank": None, "evaluable": False})
        else:
            rows.append({"base_key": f"{prog}|{tgt}", "target_id": tgt,
                         "arm_value": 0.5 + i / 10,
                         # the third target is UNRANKED — it must arrive as null, never 0
                         "rank": None if i == 2 else i + 1,
                         "evaluable": i != 2,
                         "desired_target_modulation": "supports_target_inhibition"})
    return rows


def _bundle_doc(key: str, lane: str, ctx: dict) -> dict:
    arms = []
    for prog in PROGRAMS:
        for change in sa.DESIRED_CHANGES:
            arm_key = f"{key}|{prog}|{change}"
            arms.append({
                "arm_key": arm_key, "program_id": prog, "desired_change": change,
                "ranking": {"path": f"rankings/{prog}__{change}.json",
                            "raw_sha256": _hex(f"raw|{arm_key}"),
                            "canonical_sha256": _hex(f"canon|{arm_key}")},
                "records": _records(lane, prog, ctx.get("pathway_source"))})
    doc = {"schema_version": f"spot.stage02_{lane}_arm_bundle.v1",
           "artifact_class": "fixture", "bundle_key": key, "lane": lane,
           "context": dict(ctx), "arms": arms}
    if lane != sa.LANE_PATHWAY:
        doc["base_records"] = _base_records(lane)
    return doc


def _contexts() -> list[tuple[str, str, dict]]:
    out = [(f"{sa.LANE_DIRECT}|{c}", sa.LANE_DIRECT, {"condition": c})
           for c in sa.CONDITIONS]
    out += [(f"{sa.LANE_TEMPORAL}|{a}|{b}", sa.LANE_TEMPORAL,
             {"from_condition": a, "to_condition": b})
            for a, b in sa.ordered_condition_pairs()]
    out += [(f"{sa.LANE_PATHWAY}|{c}|{s}", sa.LANE_PATHWAY,
             {"condition": c, "pathway_source": s})
            for c in sa.CONDITIONS for s in sa.PATHWAY_SOURCES]
    return out


def build_release(root, *, mutate_bundles=None, mutate_inventory=None,
                  mutate_manifest=None, mutate_after_seal=None, mutate_report=None,
                  artifact_class="fixture", mutate_disk=None):
    """Write a sealed NON-PRODUCTION release; return the four admission paths."""
    root = str(root)
    bundles_root = os.path.join(root, "bundles")
    docs = {key: _bundle_doc(key, lane, ctx) for key, lane, ctx in _contexts()}
    if mutate_bundles:
        mutate_bundles(docs)

    inventory = []
    for key, lane, ctx in _contexts():
        rel = os.path.join(lane, key.replace("|", "__") + ".json")
        full = os.path.join(bundles_root, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        payload = json.dumps(docs[key], sort_keys=True, separators=(",", ":"))
        with open(full, "w", encoding="utf-8") as fh:
            fh.write(payload)
        inventory.append({"bundle_key": key, "lane": lane, "path": rel,
                          "raw_sha256": hashlib.sha256(payload.encode()).hexdigest(),
                          "canonical_sha256": content_hash(
                              json.loads(json.dumps(docs[key]), parse_float=str)),
                          **ctx})
    if mutate_inventory:
        mutate_inventory(inventory)

    stage1_path = os.path.join(root, "stage1_release.json")
    with open(stage1_path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"release_id": "fixture_stage1_v3", "programs": list(PROGRAMS)},
                            sort_keys=True))

    manifest = {
        "schema_version": MANIFEST_SCHEMA,
        "artifact_class": artifact_class,
        "generated_at": "2026-07-13T00:00:00Z",
        "stage1_release": {"release_id": "fixture_stage1_v3",
                           "raw_sha256": sa.file_sha256(stage1_path)},
        "inventory": inventory,
    }
    if mutate_manifest:
        mutate_manifest(manifest)
    manifest[sa.SELF_HASH_FIELD] = sa.manifest_self_hash(manifest)
    if mutate_after_seal:
        mutate_after_seal(manifest)

    manifest_path = os.path.join(root, "aggregate_run_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(manifest, sort_keys=True))

    report = {"schema_version": REPORT_SCHEMA, "verifier_id": INDEPENDENT,
              "verdict": sa.ADMIT,
              "admits": {"manifest_raw_sha256": sa.file_sha256(manifest_path),
                         "manifest_canonical_sha256": content_hash(manifest)}}
    if mutate_report:
        mutate_report(report)
    report_path = os.path.join(root, "aggregate_verification.json")
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(report, sort_keys=True))

    paths = {"manifest_path": manifest_path, "report_path": report_path,
             "bundles_root": bundles_root, "stage1_release_path": stage1_path}
    if mutate_disk:
        mutate_disk(paths)
    return paths


def _gate(exc) -> str:
    return str(exc.value)


