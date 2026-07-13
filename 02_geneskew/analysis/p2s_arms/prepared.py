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
# Only the id and non-scientific provenance are excluded from the self-id. artifact_sha256 is
# INCLUDED: a run whose id did not cover the matrix hashes could have its matrices swapped
# (update the manifest's artifact_sha256, re-derive the id) and still self-verify. The
# producer computes the id AFTER hashing the files, folding them in.
_SELF_ID_EXCLUDED = ("p2s_inputs_run_id", "created_at", "argv")

# THE A-vs-B BINDING KEY SET. Every one of these authoritative Direct fields must be PRESENT
# and NONEMPTY on BOTH sides — the manifest's ``direct_binding`` (A, the bundle the inputs
# were prepared from) and the run's current W10 admission (B) — and A must EQUAL B. A missing
# field is NOT a pass: a fail-open comparison (skip when either side is absent) is exactly how
# matrices prepared from bundle A run under bundle B's provenance. Bundle identity, the WHOLE
# artifact-map fingerprint, the arm rows, the scorer view, and BOTH identity hashes are all
# bound — the whole of what W10 pinned, not a subset.
_AB_BINDING_KEYS = (
    "arm_bundle_run_id",
    "arm_bundle_run_sha256",
    "arm_rows_sha256",
    "scorer_view_sha256",
    "direct_bundle_artifact_map_sha256",
    "target_identity_admitted_sha256",
    "target_identity_canonical_sha256",
)


def _check_direct_binding_A_equals_B(m: dict[str, Any], admitted: dict[str, Any]) -> None:
    """The prepared-from bundle (A) must be, field for field, the admitted bundle (B).

    Presence is REQUIRED, not fail-open. The comparison covers exactly ``_AB_BINDING_KEYS``:
    every key must be present and nonempty on both sides, and A must equal B. A run whose
    inputs were prepared from a different admitted bundle is refused before a number is fit.
    """
    db = m.get("direct_binding")
    if not isinstance(db, dict) or not db:
        raise D.RefusalError(
            D.REFUSE_PREPARED_PIN_DRIFT,
            "the prepared manifest carries no direct_binding block, so there is nothing "
            "saying WHICH admitted Direct bundle its matrices were built from. An absent "
            "binding is a refusal, never a reason to skip the cross-check")

    for key in _AB_BINDING_KEYS:
        a, b = db.get(key), admitted.get(key)
        if not a or not b:
            raise D.RefusalError(
                D.REFUSE_PREPARED_PIN_DRIFT,
                f"the Direct binding field {key!r} is absent or empty on the prepared side "
                f"({str(a)[:12]!r}) or the admitted side ({str(b)[:12]!r}). Every binding "
                "field must be present and nonempty on both sides; a hole here is how a swap "
                "slips past a comparison that only fires when both values happen to exist")
        if a != b:
            raise D.RefusalError(
                D.REFUSE_PREPARED_PIN_DRIFT,
                f"the prepared inputs were built from a Direct bundle whose {key} is "
                f"{str(a)[:12]}..., but the run is admitting a bundle whose {key} is "
                f"{str(b)[:12]}.... Matrices from one admitted bundle may not run under "
                "another's provenance")


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


def load_and_verify(inputs_dir: str, *, condition: str, lane: str,
                    admitted: dict[str, Any] | None = None) -> dict[str, Any]:
    """Re-hash every matrix, compare bound identities to CODE LITERALS, re-derive the self id.

    ``admitted`` is the run's CURRENT W10 admission. When given, the manifest's Direct binding
    (bundle A the inputs were prepared from) must equal the currently admitted bundle (B).
    Otherwise matrices prepared from admitted bundle A could run while provenance binds B.
    """
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

    # THE RAW PUBLIC INPUTS, compared to CODE-PINNED bytes. The manifest carries its own
    # observed hashes; comparing them to the pins in THIS lane's code (not to the manifest's
    # copy of the pins) is what refuses a set of matrices prepared from a re-pinned or swapped
    # NTC/DE readout. A forger can reseal the manifest's internal pins; the literal is not in it.
    raw = m.get("raw_input_sha256") or {}
    _require(raw.get("ntc_h5ad"), _literal("NTC_H5AD_SHA256"), "raw NTC h5ad")
    _require(raw.get("de_main"), _literal("DE_MAIN_SHA256"), "raw DE readout")

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

    # A-vs-B: the bundle the inputs were prepared from (A, recorded in the manifest's
    # direct_binding) must be EXACTLY the bundle now admitted for this run (B).
    if admitted is not None:
        _check_direct_binding_A_equals_B(m, admitted)

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
