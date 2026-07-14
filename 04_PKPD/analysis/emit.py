"""Emit the Stage-4 artifact set atomically under 04_PKPD/outputs/<scorecard_set_id>/.

Atomic because a half-written scorecard set that still hashes is worse than no
scorecard set: everything is built in a temp directory and swapped into place, so a
reader either sees the complete set or nothing.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from typing import Any

from .canonical import content_sha256, sha256_bytes, sha256_file
from .contracts import STAGE4_METHOD_VERSION
from .emit_rows import (
    _delivery_rows,
    _drug_form_rows,
    _exposure_rows,
    _nebpi_criteria_rows,
    _nebpi_decision_rows,
    _potency_rows,
    _property_rows,
    _pure_input_rows,
    _safety_rows,
    _source_catalog_rows,
)
from .contract_version import ContractVersion
from .evidence_inputs import derived_columns, evidence_input_rows, input_columns
from .firewall import safe_path_component
from .ids import (
    code_tree_sha256,
    derive_scorecard_set_id,
    evidence_inputs_digest,
    source_registry_digest,
)
from .method_config import STAGE4_DIR, MethodBundle
from .pipeline import Stage4Inputs, Stage4Result, build_provenance_chain
from .safety import assert_no_forbidden_fields
from .tables import table_schemas, write_table

# The EXACT allowlist. An extra production-looking file in the directory is a failure,
# not a curiosity: the audit dropped one in and verification still passed.
# v1 is FROZEN: a v1 release has exactly these fifteen tables. It does not gain two empty ones
# because a v2 exists -- an empty `source_acquisition.parquet` in a v1 release would be a claim
# that the release HAS an acquisition manifest and that it is empty, which is false.
TABLE_ARTIFACTS_V1 = (
    # derived lanes
    "delivery_evidence", "transporter_evidence", "exposure_evidence", "safety_evidence",
    "nebpi_decisions", "nebpi_criteria",
    # the canonical input bundle the lanes are reconstructable from
    "contexts", "drug_forms", "property_evidence", "potency_evidence",
    "potency_context_links", "delivery_assignments", "nebpi_observations",
    "search_manifests", "source_catalog",
)
TABLE_ARTIFACTS_V2 = TABLE_ARTIFACTS_V1 + ("fraction_unbound", "source_acquisition")

TABLE_ARTIFACTS = {
    ContractVersion.V1: TABLE_ARTIFACTS_V1,
    ContractVersion.V2: TABLE_ARTIFACTS_V2,
}
JSON_DOCS = ("scorecards.json", "manifest.json", "verification.json", "selection.json")


def artifact_allowlist(version: ContractVersion) -> tuple[str, ...]:
    return tuple(f"{t}.parquet" for t in TABLE_ARTIFACTS[version]) + JSON_DOCS

# A real solver lock: pip-compile --generate-hashes, every distribution pinned by
# sha256, installable with `pip install --require-hashes`. Not a loose requirements list.
class EnvironmentDivergence(RuntimeError):
    """The running environment is not the declared one, so nothing here is reproducible."""


ENV_LOCK_PATH = os.path.join(STAGE4_DIR, "requirements-stage4.lock")
ENV_LOCK_SRC_PATH = os.path.join(STAGE4_DIR, "requirements-stage4.in")

DIRECT_DEPENDENCIES = ("numpy", "pandas", "pyarrow", "pydantic")


def environment_lock() -> dict[str, Any]:
    """The declared lock, plus what is actually running, plus whether they agree.

    scorecard_set_id binds the DECLARED lock hash, so the id is reproducible on any host
    that honours the same lock. The observed runtime is recorded separately and compared,
    because an id that silently absorbed the local interpreter would never be stable.
    """
    with open(ENV_LOCK_PATH, "rb") as fh:
        raw = fh.read()

    import importlib.metadata as md

    observed = {"python": sys.version.split()[0], "platform": platform.system().lower()}
    for pkg in DIRECT_DEPENDENCIES:
        try:
            observed[pkg] = md.version(pkg)
        except md.PackageNotFoundError:  # pragma: no cover - the package is imported below
            observed[pkg] = "not_installed"

    locked = _locked_versions(raw)
    divergent = sorted(
        pkg for pkg in DIRECT_DEPENDENCIES
        if pkg in locked and observed.get(pkg) != locked[pkg]
    )

    return {
        "lock_file": os.path.basename(ENV_LOCK_PATH),
        "lock_kind": "pip-compile --generate-hashes (explicit, sha256-pinned, --require-hashes installable)",
        "lock_sha256": sha256_bytes(raw),
        "production_lockable": True,
        "locked_direct_versions": {k: v for k, v in locked.items() if k in DIRECT_DEPENDENCIES},
        "observed_runtime": observed,
        "observed_matches_lock": not divergent,
        "divergent_packages": divergent,
    }


def _locked_versions(raw: bytes) -> dict[str, str]:
    """Parse `name==version` pins out of the hashed lock."""
    versions: dict[str, str] = {}
    for line in raw.decode("utf-8").splitlines():
        line = line.strip()
        if line.startswith("#") or "==" not in line:
            continue
        name, _, rest = line.partition("==")
        versions[name.strip().lower()] = rest.split()[0].strip().rstrip("\\").strip()
    return versions


# ------------------------------------------------------------------ full-row binding


class FullRowBindingError(RuntimeError):
    """An emitted evidence-input table is not the rows the engine actually consumed."""


def assert_full_row_binding(
    canonical: dict[str, list[dict[str, Any]]],
    table_rows: dict[str, list[dict[str, Any]]],
    version: ContractVersion = ContractVersion.V1,
) -> None:
    """Every emitted column of every consumed row IS the consumed row. No exceptions.

    The re-audit's finding was not "four columns were forgotten" — it was that the comparison
    was a hand-written subset at all, so forgetting a column was a silent, repeatable class of
    bug. This check is generic over the declared column sets:

      * every column emitted for an evidence-input table is classified INPUT or DERIVED, so a
        newly added column cannot escape into the release unbound;
      * the INPUT projection of the emitted rows equals the consumed rows exactly, cell for cell.

    Everything in the INPUT projection feeds `evidence_inputs_sha256` and therefore the
    `scorecard_set_id`, so a change here MUST move the identity — it cannot be resealed away.
    """
    for table, rows in canonical.items():
        declared = set(input_columns(version)[table]) | set(derived_columns(version)[table])
        emitted = table_rows[table]

        schema_cols = set(table_schemas(version)[table].names)
        if schema_cols != declared:
            raise FullRowBindingError(
                f"{table}: the parquet schema and the INPUT|DERIVED declaration disagree "
                f"(schema-only={sorted(schema_cols - declared)}, "
                f"declared-only={sorted(declared - schema_cols)}). An unclassified column is "
                "an unbound column."
            )

        key = input_columns(version)[table][0]
        want = {r[key]: r for r in rows}
        got = {r[key]: {c: r.get(c) for c in input_columns(version)[table]} for r in emitted}
        if want != got:
            missing = sorted(set(want) - set(got))
            extra = sorted(set(got) - set(want))
            changed = sorted(k for k in set(want) & set(got) if want[k] != got[k])
            raise FullRowBindingError(
                f"{table}: the emitted rows are not the consumed rows "
                f"(missing={missing} extra={extra} changed={changed})"
            )


# -------------------------------------------------------------------------- documents


def build_scorecards(scorecard_set_id: str, inputs: Stage4Inputs, result: Stage4Result,
                     method: MethodBundle) -> dict[str, Any]:
    cand_by_id = {c.candidate_id: c for c in inputs.candidate_set.candidates}
    candidates = []
    for cr in result.candidates:
        c = cand_by_id[cr.candidate_id]
        mpo = cr.cns_mpo
        candidates.append(
            {
                "candidate_id": cr.candidate_id,
                "active_moiety": c.active_moiety.model_dump(mode="json"),
                "compound_ids": c.compound_ids.model_dump(mode="json"),
                "target": c.target,
                "mechanism": c.mechanism,
                "namespace": c.namespace.value,
                "direction_compatibility": c.direction_compatibility.value,
                # reason_code only — the sentence it used to carry was bound by nothing, and
                # the code IS reconstructed by the independent verifier (rebuild_eligibility).
                "production_eligible": {
                    "eligible": cr.production_eligible,
                    "reason_code": cr.eligibility_reason_code,
                },
                "lanes": {
                    "delivery": [d.__dict__ for d in cr.delivery],
                    "cns_mpo": {
                        "status": mpo.status,
                        "components": mpo.components,
                        "property_values": mpo.property_values,
                        "total_raw": mpo.total_raw,
                        "total_published": mpo.total_published,
                        # reason_code only. The `detail` sentence was free prose bound by nothing; the
                        # code IS reconstructed, and its sentence lives in METHODS.md.
                        "missing_inputs": [
                            {"property_id": m.property_id, "reason_code": m.reason_code}
                            for m in mpo.missing_inputs
                        ],
                        "input_provenance": mpo.input_provenance,
                        "method_id": mpo.method_id,
                        "method_version": mpo.method_version,
                        "interpretation_guard": method.prose["cns_mpo"]["interpretation_guard"],
                        "warnings": mpo.warnings,
                    },
                    "transporters": cr.transporters,
                    # POTENCY CONTEXT. The exposure lane cites `potency_id`, so a reader could see
                    # WHICH potency underwrote a margin but not WHAT it was — the value, the metric,
                    # the target it was measured against, or the biological context it came from.
                    # A margin whose denominator cannot be inspected is an unbound ratio.
                    #
                    # Direction-aware, and the direction is NOT collapsed: `relation` distinguishes a
                    # point estimate (`=`) from an assay that ran out of range (`>`/`<`), and only an
                    # equality is a magnitude anything may be divided by.
                    "potency": _potency_facet(inputs, c.candidate_id),
                    # EVIDENCE AVAILABILITY. What was actually looked at, per facet. `not_evaluated`
                    # is a first-class answer and it is stated, never left as an empty list a reader
                    # might mistake for a negative result. Absence of an exposure measurement is not
                    # evidence of impermeability, and this is where the artifact says so.
                    "evidence_availability": _availability_facet(inputs, cr, c.candidate_id),
                    "exposure": [
                        {
                            "measurement_id": m.measurement_id,
                            "context_id": m.context_id,
                            "matrix": m.matrix,
                            "enhancement_context": m.enhancement_context,
                            "binding_state": m.binding_state,
                            "detection_status": m.detection_status,
                            "concentration_source_string": m.concentration_source_string,
                            "concentration_canonical_decimal": (
                                m.quantity.canonical_decimal if m.quantity else None),
                            "concentration_units": m.concentration_units,
                            "quantitation_limit_kind": m.quantitation_limit_kind,
                            "quantitation_limit_source_string": m.quantitation_limit_source_string,
                            "quantitation_limit_canonical_decimal": (
                                m.quantitation_limit.canonical_decimal
                                if m.quantitation_limit else None),
                            "quantitation_limit_units": m.quantitation_limit_units,
                            "kp_reported_source_string": m.kp_reported_source_string,
                            "kp_uu_brain_reported_source_string": m.kp_uu_brain_reported_source_string,
                            "margin_status": mg.status,
                            "margin": mg.margin,
                            "margin_canonical_decimal": mg.margin_canonical_decimal,
                            "margin_reason_code": mg.reason_code,
                            "margin_transform": mg.transform,
                            "potency_id": mg.potency_id,
                            "potency_context_link_id": mg.potency_context_link_id,
                            "caveats": mg.caveats,
                        }
                        for m, mg in cr.exposure
                    ],
                    "nebpi": [
                        {
                            "context_id": n.context_id,
                            "nebpi_status": n.nebpi_status,
                            "nebpi_class": n.nebpi_class,
                            "nebpi_primary_gate": n.nebpi_primary_gate,
                            "delivery_requirement": n.delivery_requirement,
                            "criterion_states": n.criterion_states,
                            "branch_proof": [b.__dict__ for b in n.branch_proof],
                            "counterfactual": n.counterfactual,
                            "reason_codes": n.reason_codes,
                            "context_caveats": n.context_caveats,
                            "evidence_observation_ids": n.evidence_observation_ids,
                            "method_id": n.method_id,
                        }
                        for n in cr.nebpi
                    ],
                    "safety": {
                        "rows": [s.model_dump(mode="json") for s in cr.safety_rows],
                        "scenario_matrix": cr.scenario_matrix,
                    },
                },
                "provenance_chain": build_provenance_chain(cr, method.prose),
            }
        )

    doc = {
        "schema_id": method.prose["schema_ids"]["scorecard_set"],
        "scorecard_set_id": scorecard_set_id,
        "stage4_method_version": STAGE4_METHOD_VERSION,
        "upstream": {
            "stage3_schema_id": inputs.candidate_set.schema_id,
            "stage3_run_id": inputs.candidate_set.stage3_run_id,
            "candidate_set_id": inputs.candidate_set.candidate_set_id,
            "candidate_rows_sha256": inputs.candidate_set.candidate_rows_sha256,
            "namespace": inputs.candidate_set.namespace.value,
            "is_fixture": inputs.candidate_set.is_fixture,
            **_stage3_upstream(inputs, method),
        },
        "ordering": {
            "by": "candidate_id",
            "ascending": True,
            "is_ranking": False,
            "note": method.prose["set_level"]["ordering_note"],
        },
        "set_level": {
            "calculator_mixing": result.calculator_mixing,
            "lanes_are_independent": method.prose["set_level"]["lanes_are_independent"],
        },
        "candidates": candidates,
        "guards": [
            method.cns_mpo["prohibited_interpretations"],
            method.nebpi["not_classifiable_rule"]["hard_rules"],
            method.safety_taxonomy["evidence_states"]["hard_rules"],
        ],
    }
    assert_no_forbidden_fields(doc, method.forbidden_fields, "scorecards.json")
    return doc


# The seven facets a Stage-4 candidate must carry, so a reader (and a UI) can see WHAT was
# established and WHAT was never looked at. Enumerated, because a facet nobody named is a facet
# nobody notices is missing.
CANDIDATE_FACETS = (
    "compound_identity",       # active_moiety + compound_ids
    "target_action",           # target + mechanism + direction_compatibility
    "potency_context",         # potency: metric, value, relation, binding state, biological context
    "brain_exposure",          # cns_mpo + exposure + nebpi
    "transporter_liability",   # transporters
    "clinical_label_safety",   # safety
    "evidence_availability",   # what was looked at, and what was not
)


def _potency_facet(inputs: Stage4Inputs, candidate_id: str) -> dict[str, Any]:
    """The potency rows this candidate's margins rest on, inspectable rather than merely cited."""
    rows = [p for p in inputs.potencies if p.candidate_id == candidate_id]
    links = {link.potency_id: link for link in inputs.potency_context_links}
    # `relation` is a v2 COLUMN. At v1 it is not in the emitted table, so putting it in the document
    # would be a value bound by nothing — exactly what `no_unbound_prose` exists to catch.
    v2 = inputs.contract_version is ContractVersion.V2

    return {
        "state": "observed" if rows else "not_evaluated",
        "rows": [
            {
                "potency_id": p.potency_id,
                "metric": p.metric,
                "value_source_string": p.value_source_string,
                "units": p.units,
                # `=` is a magnitude. `>` / `<` / `~` are the source saying the assay ran out of
                # range, and only an equality may be divided by.
                **({"relation": getattr(p, "relation", None)} if v2 else {}),
                "binding_state": p.binding_state,
                "biological_context": p.biological_context,
                "target_context": getattr(p, "target_context", None),
                # A link is the ONLY way a potency measured in one tumour context may be used in
                # another, and it rests on acquired bytes like any other evidence row.
                "context_link_id": getattr(links.get(p.potency_id), "link_id", None),
                "source_record_id": p.provenance.source_record_id,
                "raw_response_sha256": p.provenance.raw_response_sha256,
            }
            for p in sorted(rows, key=lambda r: r.potency_id)
        ],
        # reason_CODE only. A free sentence in the document is bound by nothing — the codebase's
        # existing convention (see `production_eligible`), and `no_unbound_prose` enforces it. The
        # sentence lives in METHODS.md: no potency was acquired, so a margin has no denominator, and
        # one is not invented.
        "not_evaluated_reason_code": None if rows else "no_potency_acquired",
    }


def _availability_facet(inputs: Stage4Inputs, cr: Any, candidate_id: str) -> dict[str, Any]:
    """What was looked at, per facet. An empty lane STATES its emptiness."""
    def _state(rows: Any) -> str:
        return "observed" if rows else "not_evaluated"

    return {
        "compound_identity": "observed",
        "target_action": "observed",
        "potency_context": _state([p for p in inputs.potencies if p.candidate_id == candidate_id]),
        "brain_exposure": _state(cr.exposure),
        "transporter_liability": _state(
            [t for t in inputs.transporters if t.candidate_id == candidate_id]),
        "clinical_label_safety": _state(cr.safety_rows),
        "nebpi_classification": _state([n for n in cr.nebpi if n.nebpi_class]),
        # The guard is a METHOD sentence, not a document one: `not_evaluated` means nobody looked,
        # and it is NOT a negative result. Absence of an exposure measurement is not evidence of
        # impermeability; absence of a labelled finding is not evidence of safety. It lives in
        # METHODS.md and in the method's interpretation guards, both of which ARE bound.
        "guard_code": "not_evaluated_is_not_a_negative_result",
    }


def _stage3_upstream(inputs: Stage4Inputs, method: MethodBundle) -> dict[str, Any]:
    """What the release says about the stage above it. v1 froze a STATUS; v2 binds the RUN.

    v1 copies `method/stage4_prose_v1.json :: stage3_contract_status` verbatim. That file is
    immutable and its bytes are hashed into the identity of every v1 release ever emitted, which
    is correct for a method PARAMETER and wrong for a STATUS: it still says `stage3_frozen: false`
    and pins the r5 contract, and it cannot be corrected without rewriting releases that already
    exist. v1 keeps emitting it anyway — a historical artifact records what was believed when it
    was written, and is not judged against a rule invented afterwards.

    v2 does not inherit it. A current-status field does not belong in immutable method prose at
    all, so v2 serves none; it binds the Stage-3 document THIS RUN actually admitted, taken from
    `Stage3Binding`. Every field below is already inside `scorecard_set_id_inputs` (the id key
    binds the whole binding), so it is anti-tampered and prose-bound for free: rewrite what the
    release says about its upstream and the release id moves. A status blob could never offer
    that, because it described the world rather than the run.
    """
    if inputs.contract_version is not ContractVersion.V2:
        return {"stage3_contract_status": method.prose["stage3_contract_status"]}

    binding = inputs.candidate_set.stage3_binding
    if binding is None:
        # No Stage-3 document came through a door (the engine's own fixtures). Say so; do not
        # imply a provenance that does not exist.
        return {"stage3_admission": {"stage3_document_admitted": False}}

    return {
        "stage3_admission": {
            "stage3_document_admitted": True,
            "stage3_schema_version": binding.stage3_schema_version,
            "stage3_document_id": binding.stage3_document_id,
            "stage3_namespace": binding.stage3_namespace.value,
            "canonical_content_sha256": binding.canonical_content_sha256,
            "document_sha256": binding.document_sha256,
        }
    }


def build_selection(scorecard_set_id: str, inputs: Stage4Inputs, result: Stage4Result,
                    method: MethodBundle) -> dict[str, Any]:
    """The Stage-5 hand-off. This pass emits NO selection, by design.

    Every sentence comes from method/stage4_prose_v1.json — including "Stage 4 does not compute
    a composite score", which is exactly the kind of sentence a resealed release would want to
    quietly delete.
    """
    sel = method.prose["selection"]
    return {
        "schema_id": method.prose["schema_ids"]["selection"],
        "scorecard_set_id": scorecard_set_id,
        "selection_status": sel["selection_status_no_selection"],
        "selected": [],
        "reason": sel["reason_fixture_pass"],
        "selection_basis_when_enabled": {
            "basis": sel["basis_when_enabled"],
            "not_basis": sel["not_basis_when_enabled"],
        },
        "candidates_considered": [
            {
                "candidate_id": cr.candidate_id,
                "production_eligible": cr.production_eligible,
                "eligibility_reason_code": cr.eligibility_reason_code,
                "cns_mpo_status": cr.cns_mpo.status,
                "nebpi_statuses": sorted({n.nebpi_status for n in cr.nebpi}),
            }
            for cr in result.candidates
        ],
        "is_fixture": inputs.candidate_set.is_fixture,
    }


def emit(inputs: Stage4Inputs, result: Stage4Result, method: MethodBundle,
         outputs_root: str) -> tuple[str, dict[str, Any]]:
    """Write the artifact set atomically. -> (output_dir, manifest)."""
    env = environment_lock()
    if not env["observed_matches_lock"]:
        # The audit ran with a declared-divergent runtime and still got a passing
        # verification. A scorecard produced by an environment nobody declared is not
        # reproducible, so it is not emitted at all.
        raise EnvironmentDivergence(
            "refusing to emit: the running environment diverges from the declared lock for "
            f"{env['divergent_packages']}. locked={env['locked_direct_versions']} "
            f"observed={env['observed_runtime']}"
        )

    code_sha, code_files = code_tree_sha256()
    scorecard_set_id, id_key = derive_scorecard_set_id(
        inputs.candidate_set, method, inputs.evidence_lanes(), inputs.sources,
        env["lock_sha256"], inputs.config, code_sha256=code_sha,
    )
    safe_path_component(scorecard_set_id)

    version = inputs.contract_version
    canonical = evidence_input_rows(inputs, version)
    builders = {
        "delivery_evidence": lambda: _delivery_rows(result, inputs),
        "nebpi_decisions": lambda: _nebpi_decision_rows(result),
        "nebpi_criteria": lambda: _nebpi_criteria_rows(result, method),
        "drug_forms": lambda: _drug_form_rows(inputs, result),
        "source_catalog": lambda: _source_catalog_rows(inputs),
        # mixed: the canonical input row + this table's declared derived columns
        "exposure_evidence": lambda: _exposure_rows(inputs, result),
        "safety_evidence": lambda: _safety_rows(inputs, result),
        "property_evidence": lambda: _property_rows(inputs, result),
        "potency_evidence": lambda: _potency_rows(inputs),
        # pure input: the emitted table IS the canonical consumed row, cell for cell
        "contexts": lambda: _pure_input_rows(canonical, "contexts"),
        "transporter_evidence": lambda: _pure_input_rows(canonical, "transporter_evidence"),
        "potency_context_links": lambda: _pure_input_rows(canonical, "potency_context_links"),
        "delivery_assignments": lambda: _pure_input_rows(canonical, "delivery_assignments"),
        "nebpi_observations": lambda: _pure_input_rows(canonical, "nebpi_observations"),
        "search_manifests": lambda: _pure_input_rows(canonical, "search_manifests"),
        # Pure inputs: nothing is derived from an fu row or an acquisition row, so both are
        # bound into identity in full and reconstructed by nobody -- they ARE the evidence.
        "fraction_unbound": lambda: _pure_input_rows(canonical, "fraction_unbound"),
        "source_acquisition": lambda: _pure_input_rows(canonical, "source_acquisition"),
    }

    os.makedirs(outputs_root, exist_ok=True)
    tmp_dir = tempfile.mkdtemp(prefix=f".tmp-{uuid.uuid4().hex[:8]}-", dir=outputs_root)
    try:
        table_rows = {name: builders[name]() for name in TABLE_ARTIFACTS[version]}
        assert_full_row_binding(canonical, table_rows, version)
        artifacts = [
            write_table(name, table_rows[name],
                        os.path.join(tmp_dir, f"{name}.parquet"), version)
            for name in TABLE_ARTIFACTS[version]
        ]

        scorecards = build_scorecards(scorecard_set_id, inputs, result, method)
        selection = build_selection(scorecard_set_id, inputs, result, method)
        for name, doc in (("scorecards.json", scorecards), ("selection.json", selection)):
            path = os.path.join(tmp_dir, name)
            _write_json(path, doc)
            artifacts.append(
                {"filename": name, "rows": None, "columns": None, "dtypes": None,
                 "sort_key": None, "table": None, "content_sha256": content_sha256(doc),
                 "file_sha256": sha256_file(path)}
            )

        manifest = {
            "schema_id": "spot.stage04_manifest.v1",
            "scorecard_set_id": scorecard_set_id,
            "stage4_method_version": STAGE4_METHOD_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),  # excluded from canonical content
            "namespace": inputs.candidate_set.namespace.value,
            "scorecard_set_id_inputs": id_key,
            "upstream": scorecards["upstream"],
            "method_file_sha256": dict(sorted(method.method_file_sha256.items())),
            "method_bundle_sha256": method.bundle_sha256,
            "analysis_code_sha256": code_sha,
            "analysis_code_files": dict(sorted(code_files.items())),
            "source_registry": {
                "source_registry_sha256": source_registry_digest(inputs.sources),
                "sources": [inputs.sources[s].model_dump(mode="json") for s in sorted(inputs.sources)],
            },
            "evidence_inputs_sha256": evidence_inputs_digest(inputs.evidence_lanes()),
            "environment": env,
            # THE METHODS & PROVENANCE DRAWER. Everything a reader needs to re-run this release and
            # to see what every displayed number rests on — assembled here rather than left for a UI
            # to reconstruct, because a drawer that has to guess is a drawer that guesses wrong.
            #
            # `created_at` is the emission time and is already excluded from the identity: a release
            # re-emitted from the same inputs has the same scorecard_set_id and a different clock.
            "reproduce": {
                "command": [
                    "python -m analysis.run_acquire     --stage3-annotation-bundle <S3> "
                    "--run-root <R>",
                    "python -m analysis.run_materialize --stage3-annotation-bundle <S3> "
                    "--run-root <R> --out <B>",
                    "python -m verifier.verify_bundle   <B> --run-root <R>",
                    "python -m analysis.run_stage4      --stage3-annotation-bundle <S3> "
                    "--evidence-bundle <B> --outputs-root outputs --require-external-verifier",
                    f"python -m verifier.verify_stage4   --release outputs/{scorecard_set_id} "
                    "--method method",
                ],
                "verify_sources": "python -m analysis.source_verify --cache-root $SPOT_SOURCE_CACHE",
                "raw_bytes_are_not_bundled": (
                    "Raw public responses are cached OUTSIDE the tree under the run root, addressed "
                    "by SHA-256. Every source below carries its locator, its release and its hash: "
                    "re-fetch and re-hash, do not trust this file."
                ),
                "scorecard_set_id_excludes_the_clock": True,
            },
            "float_rules": {
                "identity": "exact decimal strings (quantity.py); floats are rejected in identity content",
                "publication_rounding": "ROUND_HALF_UP (a frozen implementation rule, not a published one)",
                "nan_inf": "rejected",
            },
            "artifact_allowlist": sorted(artifact_allowlist(version)),
            # Absent means v1. A release written before this field existed IS a v1
            # release, and must stay readable by every later verifier.
            **({"evidence_contract_version": version.value}
               if version != ContractVersion.V1 else {}),
            "artifacts": sorted(artifacts, key=lambda a: a["filename"]),
            "is_fixture": inputs.candidate_set.is_fixture,
        }
        manifest["manifest_content_sha256"] = content_sha256(manifest)
        _write_json(os.path.join(tmp_dir, "manifest.json"), manifest)

        from .verify import verify_outputs  # local import: verify reads the manifest

        verification = verify_outputs(tmp_dir, inputs, method, manifest)
        _write_json(os.path.join(tmp_dir, "verification.json"), verification)

        written = set(os.listdir(tmp_dir))
        missing = sorted(set(artifact_allowlist(version)) - written)
        extra = sorted(written - set(artifact_allowlist(version)))
        if missing or extra:
            raise RuntimeError(f"artifact set does not match the allowlist: missing={missing} extra={extra}")

        final_dir = os.path.join(outputs_root, scorecard_set_id)
        _swap_into_place(tmp_dir, final_dir)
        return final_dir, manifest
    except BaseException:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise


def _write_json(path: str, doc: Any) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        fh.write("\n")


def _swap_into_place(tmp_dir: str, final_dir: str) -> None:
    """A reader sees either the previous complete set or the new complete set."""
    backup = None
    if os.path.exists(final_dir):
        backup = f"{final_dir}.superseded-{uuid.uuid4().hex[:8]}"
        os.rename(final_dir, backup)
    try:
        os.rename(tmp_dir, final_dir)
    except BaseException:
        if backup:
            os.rename(backup, final_dir)
        raise
    if backup:
        shutil.rmtree(backup, ignore_errors=True)
