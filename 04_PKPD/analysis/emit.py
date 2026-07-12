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
from .evidence_inputs import DERIVED_COLUMNS, INPUT_COLUMNS, evidence_input_rows
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
from .tables import TABLE_SCHEMAS, write_table

# The EXACT allowlist. An extra production-looking file in the directory is a failure,
# not a curiosity: the audit dropped one in and verification still passed.
TABLE_ARTIFACTS = (
    # derived lanes
    "delivery_evidence", "transporter_evidence", "exposure_evidence", "safety_evidence",
    "nebpi_decisions", "nebpi_criteria",
    # the canonical input bundle the lanes are reconstructable from
    "contexts", "drug_forms", "property_evidence", "potency_evidence",
    "potency_context_links", "delivery_assignments", "nebpi_observations",
    "search_manifests", "source_catalog",
)
JSON_DOCS = ("scorecards.json", "manifest.json", "verification.json", "selection.json")
ARTIFACTS = tuple(f"{t}.parquet" for t in TABLE_ARTIFACTS) + JSON_DOCS

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
        declared = set(INPUT_COLUMNS[table]) | set(DERIVED_COLUMNS[table])
        emitted = table_rows[table]

        schema_cols = set(TABLE_SCHEMAS[table].names)
        if schema_cols != declared:
            raise FullRowBindingError(
                f"{table}: the parquet schema and the INPUT|DERIVED declaration disagree "
                f"(schema-only={sorted(schema_cols - declared)}, "
                f"declared-only={sorted(declared - schema_cols)}). An unclassified column is "
                "an unbound column."
            )

        key = INPUT_COLUMNS[table][0]
        want = {r[key]: r for r in rows}
        got = {r[key]: {c: r.get(c) for c in INPUT_COLUMNS[table]} for r in emitted}
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
            "stage3_contract_status": method.prose["stage3_contract_status"],
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

    canonical = evidence_input_rows(inputs)
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
    }

    os.makedirs(outputs_root, exist_ok=True)
    tmp_dir = tempfile.mkdtemp(prefix=f".tmp-{uuid.uuid4().hex[:8]}-", dir=outputs_root)
    try:
        table_rows = {name: builders[name]() for name in TABLE_ARTIFACTS}
        assert_full_row_binding(canonical, table_rows)
        artifacts = [
            write_table(name, table_rows[name], os.path.join(tmp_dir, f"{name}.parquet"))
            for name in TABLE_ARTIFACTS
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
            "float_rules": {
                "identity": "exact decimal strings (quantity.py); floats are rejected in identity content",
                "publication_rounding": "ROUND_HALF_UP (a frozen implementation rule, not a published one)",
                "nan_inf": "rejected",
            },
            "artifact_allowlist": sorted(ARTIFACTS),
            "artifacts": sorted(artifacts, key=lambda a: a["filename"]),
            "is_fixture": inputs.candidate_set.is_fixture,
        }
        manifest["manifest_content_sha256"] = content_sha256(manifest)
        _write_json(os.path.join(tmp_dir, "manifest.json"), manifest)

        from .verify import verify_outputs  # local import: verify reads the manifest

        verification = verify_outputs(tmp_dir, inputs, method, manifest)
        _write_json(os.path.join(tmp_dir, "verification.json"), verification)

        written = set(os.listdir(tmp_dir))
        missing = sorted(set(ARTIFACTS) - written)
        extra = sorted(written - set(ARTIFACTS))
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
