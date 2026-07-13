"""VERIFY THE PREPARED INPUTS against CODE LITERALS before a number is computed from them.

The producer does not read ``cells.npz`` / ``effects.npz`` / ``masks.parquet`` /
``eligible.parquet`` on trust. It reads ``p2s_inputs.json`` — the manifest ``prepare_inputs``
wrote — and RE-HASHES every matrix against the ``artifact_sha256`` it recorded.

THE ATTACK THIS CLOSES (audit)
------------------------------
Comparing a manifest's observed hash to a ``*_pinned`` value CARRIED IN THE SAME MANIFEST is
circular: a forger edits both, recomputes the artifact hashes, recomputes the self id, and
the manifest is internally consistent. So this module compares the bound identities to
CODE/CONFIG LITERALS — the raw and canonical Stage-1 score hashes, the public source, and the
two environment locks — which a forged manifest cannot change because they are not in it. It
also RE-DERIVES the manifest's self id (``p2s_inputs_run_id``) and binds the verified id into
the run output, so a run cannot be re-attributed to a prepared set it was not built from.
"""
from __future__ import annotations

import json
import os
from typing import Any

from . import config, w10
from . import disposition as D

MANIFEST_FILE = "p2s_inputs.json"
MATRIX_FILES = ("cells.npz", "effects.npz", "masks.parquet", "eligible.parquet")

# The keys prepare_inputs adds to the binding AFTER hashing it into the self id. Stripped
# before re-deriving, so the id is taken over exactly what it was taken over.
_SELF_ID_EXCLUDED = ("p2s_inputs_run_id", "created_at", "argv", "artifact_sha256")


def _literal(name: str) -> str:
    """A hard identity, read from config at call time (so a test can pin the fixture value)."""
    return getattr(config, name)


def _require(got: Any, literal: str, what: str) -> None:
    """The bound value must equal the CODE LITERAL. Not the manifest's own copy of it."""
    if got != literal:
        raise D.RefusalError(
            D.REFUSE_PREPARED_PIN_DRIFT,
            f"the prepared {what} is {str(got)[:16]}..., not the code-pinned "
            f"{str(literal)[:16]}.... A manifest can reseal its own internal pins; it cannot "
            "change the literal in this lane's code")


def load_and_verify(inputs_dir: str, *, condition: str, lane: str) -> dict[str, Any]:
    """Re-hash every matrix, compare bound identities to CODE LITERALS, re-derive the self id."""
    manifest_path = os.path.join(inputs_dir, MANIFEST_FILE)
    if not os.path.isdir(inputs_dir) or not os.path.exists(manifest_path):
        raise D.RefusalError(
            D.REFUSE_PREPARED_MANIFEST_MISSING,
            f"--inputs {inputs_dir!r} carries no {MANIFEST_FILE}. The producer runs only from "
            "inputs prepared by `python -m p2s_arms.prepare_inputs`; it does not read raw "
            "matrices on trust")
    with open(manifest_path) as fh:
        m = json.load(fh)

    # 1. SUBSTITUTION. Every matrix must hash to what the manifest recorded.
    recorded = m.get("artifact_sha256") or {}
    swapped = []
    for name in MATRIX_FILES:
        path = os.path.join(inputs_dir, name)
        if not os.path.exists(path):
            swapped.append(f"{name} (absent)")
            continue
        got = w10.file_sha256(path)
        if recorded.get(name) != got:
            swapped.append(f"{name} (manifest {str(recorded.get(name))[:12]}..., on disk "
                           f"{got[:12]}...)")
    if swapped:
        raise D.RefusalError(
            D.REFUSE_PREPARED_FILE_SUBSTITUTED,
            f"{len(swapped)} prepared matrix/matrices do not hash to the manifest: "
            f"{swapped[:3]}. A file swapped for another keeps its name; only the hash tells")

    # 2. THE SELF ID, RE-DERIVED. A manifest whose id does not follow its content was edited.
    binding = {k: v for k, v in m.items() if k not in _SELF_ID_EXCLUDED}
    derived_id = w10.content_sha256(binding)[:config.RUN_ID_LEN]
    if derived_id != m.get("p2s_inputs_run_id"):
        raise D.RefusalError(
            D.REFUSE_PREPARED_PIN_DRIFT,
            f"the prepared manifest's self id {str(m.get('p2s_inputs_run_id'))[:12]}... does "
            f"not follow its content (re-derives to {derived_id[:12]}...). It was edited after "
            "it was written")

    # 3. THE BOUND IDENTITIES, compared to CODE LITERALS — not to values inside the manifest.
    sc = m.get("stage1_scores") or {}
    _require(sc.get("raw_sha256"), _literal("STAGE1_SCORES_RAW_SHA256"),
             "stage1 scores raw sha256")
    _require(sc.get("canonical_scores_sha256"),
             _literal("STAGE1_SCORES_CANONICAL_SHA256"), "stage1 scores canonical sha256")

    src = m.get("public_source") or {}
    _require(src.get("ntc"), _literal("NTC_HF_SOURCE"), "public NTC source")
    _require(src.get("revision"), _literal("NTC_HF_REVISION"), "public NTC revision")

    locks = m.get("environment_locks") or {}
    _require(locks.get("direct_solver_lock_sha256"),
             _literal("PINNED_SOLVER_LOCK_SHA256"), "Direct solver lock")
    _require(locks.get("p2s_runtime_lock_sha256"),
             _literal("P2S_RUNTIME_LOCK_SHA256"), "P2S runtime lock")

    # 4. THE CONDITION and LANE the inputs were built for.
    if str(m.get("condition")) != condition:
        raise D.RefusalError(
            D.REFUSE_PREPARED_CONDITION,
            f"the prepared inputs are for condition {m.get('condition')!r}, not {condition!r}")
    if lane in config.RELEASE_LANES and m.get("lane") != lane:
        raise D.RefusalError(
            D.REFUSE_PREPARED_LANE,
            f"the prepared inputs were built in the {m.get('lane')!r} lane, and this is a "
            f"{lane!r} run")

    return {
        "manifest": m,
        "paths": {"cells": os.path.join(inputs_dir, "cells.npz"),
                  "effects": os.path.join(inputs_dir, "effects.npz"),
                  "masks": os.path.join(inputs_dir, "masks.parquet"),
                  "eligible": os.path.join(inputs_dir, "eligible.parquet")},
        "p2s_inputs_run_id": derived_id,          # the RE-DERIVED id, not the claimed one
        "condition": m.get("condition"),
        "stage1_scores": sc,
        "environment_locks": locks,
        "gene_namespace": m.get("gene_namespace") or {},
        "compared_to_code_literals": True,
        "self_id_rederived": True,
        "artifact_sha256_verified": True,
    }
