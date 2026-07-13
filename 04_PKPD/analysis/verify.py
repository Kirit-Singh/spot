"""Emit-time verification.

Two halves, deliberately:

  * the checks that need the ORIGINAL INPUTS — re-deriving the scorecard_set_id, the
    method/source/evidence digests, and recomputing the Stage-3 candidate row hash rather
    than trusting the one the artifact declares;
  * the RECONSTRUCTION, which is delegated to `verifier/` — a separately implemented
    package that imports none of this code and rebuilds every derived claim from the
    emitted tables alone.

Scope is explicit. Called without inputs/method, this returns `partial`, not an
unqualified `pass`: the audit found that a verifier which cannot see the inputs was
still reporting success.
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

import pyarrow.parquet as pq

from .evidence_inputs import evidence_input_rows, input_columns
from .firewall import compute_candidate_rows_sha256
from .ids import (
    code_tree_sha256,
    derive_scorecard_set_id,
    evidence_inputs_digest,
    source_registry_digest,
)
from .method_config import METHOD_DIR, MethodBundle
from .pipeline import Stage4Inputs, provenance_bindings

# The bound input tables, and the function that flattens each input record to the row the
# emitted parquet must contain. Reconstructed from the INPUTS — the standalone verifier
# reconstructs the same bindings from the emitted tables, and the two never read each
# other's answer.
UNACQUIRED = "not_acquired"


def _check(checks: list[dict[str, Any]], check_id: str, ok: bool, detail: str) -> None:
    checks.append({"check_id": check_id, "status": "pass" if ok else "fail", "detail": detail})


def _source_binding_failures(inputs: Stage4Inputs) -> list[str]:
    """Every cited source exists, was acquired, and hashes to what the row declares.

    Re-derived here from the input records. `check_referential_integrity` runs the same rule
    at input time and REFUSES; this is the emit-time restatement, so a caller that reached
    `emit()` without going through the pipeline (or that mutated inputs after it) cannot
    write an artifact whose evidence rests on bytes nobody has.
    """
    bad: list[str] = []
    for owner, prov in provenance_bindings(inputs):
        rec = inputs.sources.get(prov.source_record_id)
        if rec is None:
            bad.append(f"{owner}: source {prov.source_record_id!r} is not in the registry")
        elif rec.source_class == UNACQUIRED:
            bad.append(f"{owner}: source {prov.source_record_id!r} was never acquired")
        elif rec.raw_sha256 != prov.raw_response_sha256:
            bad.append(f"{owner}: declares {prov.raw_response_sha256!r}, source hashes to "
                       f"{rec.raw_sha256!r}")
    return sorted(bad)


def _emitted_rows_match_inputs(out_dir: str, inputs: Stage4Inputs) -> list[str]:
    """Every emitted column of every consumed evidence-input row IS the consumed row.

    GENERIC over the declared column sets (`evidence_inputs.py`) — never a hand-picked
    subset. The re-audit rewrote a negative search's `search_scope`, `source`,
    `executed_date` and `extraction_transform` in a resealed release and both verifiers
    passed, because the comparison here listed six columns and the table had fourteen. The
    class of bug was the list; there is no list now.

    An extra row, a missing row, or ANY changed bound cell in any evidence-input table means
    the release is not the run — so it is stale, not merely different.
    """
    canonical = evidence_input_rows(inputs, inputs.contract_version)
    problems: list[str] = []

    for table, want_rows in canonical.items():
        path = os.path.join(out_dir, f"{table}.parquet")
        if not os.path.exists(path):
            problems.append(f"{table}: not emitted")
            continue

        cols = input_columns(inputs.contract_version)[table]
        on_disk = pq.read_table(path).to_pylist()
        missing_cols = [c for c in cols if on_disk and c not in on_disk[0]]
        if missing_cols:
            problems.append(f"{table}: the release omits bound column(s) {missing_cols}")
            continue

        key = cols[0]
        want = {r[key]: r for r in want_rows}
        got = {r[key]: {c: _norm(r.get(c)) for c in cols} for r in on_disk}
        want = {k: {c: _norm(v.get(c)) for c in cols} for k, v in want.items()}

        for k in sorted(set(want) - set(got)):
            problems.append(f"{table}: consumed row {k!r} is absent from the release")
        for k in sorted(set(got) - set(want)):
            problems.append(f"{table}: row {k!r} is in the release but was never consumed")
        for k in sorted(set(want) & set(got)):
            diffs = {c: (want[k][c], got[k][c]) for c in cols if want[k][c] != got[k][c]}
            if diffs:
                problems.append(
                    f"{table}: row {k!r} differs from the row the engine consumed "
                    f"(column: consumed -> emitted) {diffs}")
    return problems


def _norm(v: Any) -> Any:
    """Parquet round-trips a list as a list and a tuple as a list; compare like for like."""
    if isinstance(v, tuple):
        return list(v)
    return v


def verify_outputs(
    out_dir: str,
    inputs: Optional[Stage4Inputs],
    method: Optional[MethodBundle],
    manifest: dict[str, Any],
    method_dir: str = METHOD_DIR,
) -> dict[str, Any]:
    """Independent reconstruction + the input-bound identity checks."""
    from verifier.checks import verify_release  # separate package; imports no analysis code

    report = verify_release(out_dir, method_dir)
    checks: list[dict[str, Any]] = list(report["checks"])

    if inputs is None or method is None:
        return {
            **report,
            "scope": "partial_no_inputs",
            "scope_note": (
                "The original inputs and method bundle were not supplied, so the "
                "scorecard_set_id could not be re-derived from them. Reconstruction from the "
                "emitted tables did run. This is NOT a full verification."
            ),
            "checks": sorted(checks, key=lambda c: c["check_id"]),
        }

    env_lock = manifest["environment"]["lock_sha256"]
    code_sha, _files = code_tree_sha256()
    recomputed_id, key = derive_scorecard_set_id(
        inputs.candidate_set, method, inputs.evidence_lanes(), inputs.sources,
        env_lock, inputs.config, code_sha256=code_sha,
    )
    _check(checks, "scorecard_set_id_rederived",
           recomputed_id == manifest["scorecard_set_id"],
           f"declared={manifest['scorecard_set_id']} recomputed={recomputed_id}")
    _check(checks, "method_file_sha256_unchanged",
           dict(method.method_file_sha256) == dict(manifest["method_file_sha256"]),
           "method/*.json file hashes match the manifest")
    _check(checks, "analysis_code_sha256_unchanged",
           code_sha == manifest.get("analysis_code_sha256"),
           "the analysis tree hashes to what the manifest recorded")
    _check(checks, "source_registry_sha256_unchanged",
           source_registry_digest(inputs.sources)
           == manifest["source_registry"]["source_registry_sha256"],
           "the full source provenance class matches the manifest")
    _check(checks, "evidence_inputs_sha256_unchanged",
           evidence_inputs_digest(inputs.evidence_lanes()) == manifest["evidence_inputs_sha256"],
           "every evidence input row (incl. potency-context links) matches the manifest")

    # The input-side half of the provenance binding. The standalone verifier re-derives the
    # same bindings from the emitted tables and the source catalog; this one re-derives them
    # from the input records. Two reconstructions, two data sources, and neither consults the
    # other's verdict — a generator that reported "bound: true" would satisfy neither.
    unbound = _source_binding_failures(inputs)
    _check(checks, "input_rows_bound_to_acquired_sources", not unbound,
           "every potency-context link, delivery assignment, search manifest and evidence row "
           f"cites a registered, acquired source whose bytes hash to its claim: {unbound}")

    drift = _emitted_rows_match_inputs(out_dir, inputs)
    _check(checks, "bound_input_tables_emitted_exactly", not drift,
           "the links, assignments and search manifests on disk are exactly the ones the "
           f"engine consumed: {drift}")

    # Never trust the DECLARED Stage-3 row hash: recompute it from the rows.
    recomputed_rows = compute_candidate_rows_sha256(inputs.candidate_set.candidates)
    _check(checks, "stage3_candidate_rows_recomputed",
           recomputed_rows == inputs.candidate_set.candidate_rows_sha256
           == manifest["upstream"]["candidate_rows_sha256"],
           f"declared={inputs.candidate_set.candidate_rows_sha256} recomputed={recomputed_rows}")

    # The Stage-3 artifact this run claims to descend from.
    binding = inputs.candidate_set.stage3_binding
    _check(checks, "stage3_binding_present_or_internal_fixture",
           binding is not None or inputs.candidate_set.is_fixture,
           "a non-fixture run must name the Stage-3 document it was adapted from")

    failed = [c for c in checks if c["status"] == "fail"]
    return {
        **report,
        "scope": "full_reconstruction_and_identity",
        "status": "fail" if failed else "pass",
        "n_checks": len(checks),
        "n_failed": len(failed),
        "checks": sorted(checks, key=lambda c: c["check_id"]),
    }


def verify_output_dir(out_dir: str, inputs: Optional[Stage4Inputs] = None,
                      method: Optional[MethodBundle] = None) -> dict[str, Any]:
    """Re-verify a written scorecard set from disk."""
    with open(os.path.join(out_dir, "manifest.json"), encoding="utf-8") as fh:
        manifest = json.load(fh)
    return verify_outputs(out_dir, inputs, method, manifest)
