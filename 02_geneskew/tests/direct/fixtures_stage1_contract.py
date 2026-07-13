"""The AUTHORITATIVE Stage-1 contract bytes, materialised from git — never from a host path.

WHY THIS FILE EXISTS
--------------------
The Stage-2 gate-B tests used to read the v3 schema from a path on ONE developer's machine::

    /home/tcelab/.spot-runs/20260712T021343Z/stage1-ui-contract/spot.stage01_selection.v3.schema.json

That file holds the STALE schema (``f4c2c2cc…``). So the gate validated every contract
against a schema nobody could audit, that no commit records, and that had already been
superseded — and the tests were GREEN the whole time. A pin whose bytes live outside the
repository is not a pin: it is whatever that host happens to contain today.

So the contract is staged out of GIT, at an exact commit, and its bytes are checked against
the hashes an INDEPENDENT Stage-1 audit published. When the ref is not fetched the tests
SKIP loudly — they never quietly pass against something else.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile

import pytest

# The repaired authoritative Stage-1 contract. Fetch with:
#   git fetch origin stage1-temporal-estimator-repair
STAGE1_COMMIT = "539431dd8d87a3d763fb69ab44ed44bc98631d5a"

# What the INDEPENDENT Stage-1 audit published. Asserted against the real bytes below, so a
# drift on either side is a loud failure rather than a quiet re-attribution.
SCHEMA_SHA256 = "f8104283d7139ed47059978751dbed33e8426c920ba0d8086082eda9c43f4c1d"
RELEASE_RAW_SHA256 = "0c336546db10746bba1569ccc6bef7dedf9679effd24e17d0c07a5ab04dbef73"
RELEASE_SELF_SHA256 = "2262430931707552f4414808be3d6734fa3c7287748ec23339ce3ef498224b11"
TEMPORAL_METHOD_SHA256 = \
    "343f20db53aed3f34f45f6c4adebc2cdf26985ab179b7df264dbd0d02587c4b5"

# The schema Stage-2 pinned BEFORE this repair. Kept by name so the stale-schema attack can
# be written as an attack, rather than as a hash nobody recognises.
STALE_SCHEMA_SHA256 = "f4c2c2cc83b739ffba48286e22a7471cb5f83f0ff15e06f2bb377817382ad8e8"

BRIDGE = "01_programs/analysis/stage2_bridge"
SCHEMA_REL = f"{BRIDGE}/schemas/spot.stage01_selection.v3.schema.json"
RELEASE_REL = f"{BRIDGE}/release/stage01_v3_release.json"

# The producer's OWN fixtures. These are the ground truth for the question_id recipe: their
# ids were computed by Stage-1's code, not by ours, so re-deriving them here is an
# INDEPENDENT check rather than our hasher agreeing with itself.
PRODUCER_FIXTURES = {
    "within_ready": f"{BRIDGE}/fixtures/stage01_selection_within_ready_example.json",
    "within_refused": f"{BRIDGE}/fixtures/stage01_selection_within_refused_example.json",
    "temporal_ready": f"{BRIDGE}/fixtures/stage01_selection_temporal_ready_example.json",
}

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

_CACHE: dict[str, str] = {}


def _show(rel_path: str) -> bytes:
    """The exact bytes of one path at STAGE1_COMMIT. Skips when the ref is not fetched."""
    try:
        return subprocess.run(
            ["git", "-C", REPO, "show", f"{STAGE1_COMMIT}:{rel_path}"],
            capture_output=True, check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        # allow_module_level: the schema path is resolved at IMPORT time (it is the pin the
        # module is skipped on), and a bare skip() outside a test is an error, not a skip.
        pytest.skip(f"Stage-1 {STAGE1_COMMIT[:7]} is not fetched in this worktree "
                    "(git fetch origin stage1-temporal-estimator-repair)",
                    allow_module_level=True)


def _staged(rel_path: str) -> str:
    """Materialise one contract file into a process-wide temp dir, once."""
    if rel_path not in _CACHE:
        blob = _show(rel_path)
        root = _CACHE.setdefault("__root__", tempfile.mkdtemp(prefix="stage1-contract-"))
        dest = os.path.join(root, os.path.basename(rel_path))
        with open(dest, "wb") as fh:
            fh.write(blob)
        _CACHE[rel_path] = dest
    return _CACHE[rel_path]


def schema_path() -> str:
    """The pinned f810 selection schema, on disk. Its BYTES are what the gate checks."""
    return _staged(SCHEMA_REL)


def producer_fixture(name: str) -> dict:
    """One contract STAGE-1 ITSELF emitted — ids included, computed by its code."""
    with open(_staged(PRODUCER_FIXTURES[name])) as fh:
        return json.load(fh)


def stage_release(root: str) -> str:
    """Materialise the authoritative release + every served component under ``root``."""
    dest = os.path.join(root, RELEASE_REL)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    blob = _show(RELEASE_REL)
    with open(dest, "wb") as fh:
        fh.write(blob)

    for comp in json.loads(blob)["components"].values():
        path = comp.get("path")
        if not path:
            continue                       # declared, not served (the scores parquet)
        out = os.path.join(root, path)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "wb") as fh:
            fh.write(_show(path))
    return dest


# --------------------------------------------------------------------------- #
# THE RECIPE, RE-IMPLEMENTED INDEPENDENTLY.
#
# This is deliberately NOT ``stage1_v3.derive_question_id``. A test that computed the
# expected id with the very function under test would prove only that the function equals
# itself. So the recipe is spelled out here from Stage-1's published text — literal
# ``json.dumps``, literal ``hashlib`` — and the gate has to agree with THIS.
#
#   question_id = sha256(canonical_json({
#       "A": {program_id, direction, condition: conditions[0]},
#       "B": {program_id, direction, condition: conditions[-1]},
#       "analysis_mode": mode}))[:16]
#
#   canonical_json = json.dumps(sort_keys=True, separators=(",",":"), ensure_ascii=True)
#
# (`jq -cS | sha256sum` is exercised as a THIRD, out-of-process oracle in the tests.)
# --------------------------------------------------------------------------- #
def independent_question_id(a, dir_a, b, dir_b, conditions, mode) -> str:
    content = {
        "A": {"program_id": a, "direction": dir_a, "condition": conditions[0]},
        "B": {"program_id": b, "direction": dir_b, "condition": conditions[-1]},
        "analysis_mode": mode,
    }
    blob = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


# away_from_A(high) DECREASES the program; toward_B(high) INCREASES it. The same pole means
# OPPOSITE perturbations depending on the role, which is why an arm is keyed on the desired
# change and never on the pole. (Stage-1 `arm_keys.desired_change`.)
DESIRED_CHANGE = {("away_from_A", "high"): "decrease", ("away_from_A", "low"): "increase",
                  ("toward_B", "high"): "increase", ("toward_B", "low"): "decrease"}


def _arm_ref(role, program_id, direction, condition, mode, conditions) -> dict:
    dc = DESIRED_CHANGE[(role, direction)]
    ref = {"role": role, "program_id": program_id, "pole_direction": direction,
           "desired_change": dc, "condition": condition,
           "direct_arm_key": f"{program_id}|{dc}|{condition}",
           "pathway_arm_key_base": f"{program_id}|{dc}|{condition}"}
    if mode == "temporal_cross_condition":
        ref["temporal_arm_key"] = \
            f"{program_id}|{dc}|{conditions[0]}|{conditions[-1]}"
    return ref


def complete(doc: dict, temporal_method_sha256: str = TEMPORAL_METHOD_SHA256) -> dict:
    """Add the blocks the f810 schema REQUIRES: question_id, arms, estimator.

    The v3 schema is ``additionalProperties: false`` and requires all three. A builder that
    omits them emits a contract Stage-1 could never have produced — so every fixture goes
    through here, and a caller that sets one explicitly keeps its own value (that is how the
    forgery paths are written).
    """
    c = doc["canonical_content"]
    mode = c["analysis_mode"]
    conds = list(c["conditions"])
    a, dir_a = c["A"]["program_id"], c["A"]["direction"]
    b, dir_b = c["B"]["program_id"], c["B"]["direction"]

    doc.setdefault("question_id",
                   independent_question_id(a, dir_a, b, dir_b, conds, mode))
    doc.setdefault("arms", {
        "away_from_A": _arm_ref("away_from_A", a, dir_a, conds[0], mode, conds),
        "toward_B": _arm_ref("toward_B", b, dir_b, conds[-1], mode, conds),
    })
    if "estimator" not in doc:
        est = {"estimator_id": doc["estimator_id"], "analysis_mode": mode,
               "n_conditions": len(conds), "status": doc["estimator_status"]}
        if mode == "temporal_cross_condition" and doc["estimator_status"] == "available":
            est.update({
                "method_id": "spot.stage02.temporal_cross_condition.v1",
                "method_version":
                    "stage2-temporal-cross-condition-v1-did-on-program-projections",
                "estimand_id": "spot.stage02.temporal.estimand."
                               "population_program_projection_shift.v1",
                "estimand_level": "population",
                "estimand_is_per_cell_fate": False,
                "inference_status": "not_calibrated",
                "method_sha256": temporal_method_sha256,
            })
        doc["estimator"] = est
    return doc
