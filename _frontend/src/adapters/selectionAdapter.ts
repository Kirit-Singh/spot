// Adapter for the Stage-1 selection contract (spot.stage01_selection.v1).

import type { Namespace } from '../domain/common';
import type {
  ProgramDirection,
  ProgramPole,
  Stage1Bindings,
  StageSelection,
} from '../domain/selection';
import { fail } from './errors';
import { bool, enumOf, isObject, namespaceOf, optHex, optStr, str } from './guards';

export const KNOWN_SELECTION_VERSIONS = ['spot.stage01_selection.v1'] as const;

function pole(v: unknown, path: string): ProgramPole {
  if (!isObject(v)) fail('malformed', `${path} program pole is required`);
  return {
    program_id: str(v.program_id, `${path}.program_id`),
    score_field: str(v.score_field, `${path}.score_field`),
    display_label: str(v.display_label, `${path}.display_label`),
    direction: enumOf<ProgramDirection>(v.direction, ['high', 'low'], `${path}.direction`),
  };
}

/**
 * Optional v3 Stage-1 bridge bindings, read from the top level of the selection.
 * Validated (hex digests) and preserved when present; returns null when the bridge
 * supplied none of them (fixture / older selections).
 */
function stage1Bindings(raw: Record<string, unknown>): Stage1Bindings | null {
  const bindings: Stage1Bindings = {
    stage1_method_version: optStr(raw.stage1_method_version, 'selection.stage1_method_version'),
    program_registry_raw_sha256: optHex(
      raw.program_registry_raw_sha256,
      'selection.program_registry_raw_sha256',
    ),
    program_registry_sha256: optHex(raw.program_registry_sha256, 'selection.program_registry_sha256'),
    validation_raw_sha256: optHex(raw.validation_raw_sha256, 'selection.validation_raw_sha256'),
    v3_overlay_raw_sha256: optHex(raw.v3_overlay_raw_sha256, 'selection.v3_overlay_raw_sha256'),
    v3_summary_raw_sha256: optHex(raw.v3_summary_raw_sha256, 'selection.v3_summary_raw_sha256'),
    source_h5ad_sha256: optHex(raw.source_h5ad_sha256, 'selection.source_h5ad_sha256'),
  };
  const anyPresent = Object.values(bindings).some((v) => v !== null);
  return anyPresent ? bindings : null;
}

export function parseSelection(raw: unknown, expected: Namespace): StageSelection {
  if (!isObject(raw)) fail('malformed', 'selection must be an object');

  const schema_version = str(raw.schema_version, 'selection.schema_version');
  if (!(KNOWN_SELECTION_VERSIONS as readonly string[]).includes(schema_version)) {
    fail('unknown_schema_version', `selection.schema_version "${schema_version}" is not accepted`);
  }

  const namespace = namespaceOf(raw.namespace, 'selection.namespace');
  if (namespace !== expected) {
    fail(
      'namespace_mismatch',
      `selection.namespace "${namespace}" does not match code-bound "${expected}"`,
    );
  }

  const production_gate_passed = bool(raw.production_gate_passed, 'selection.production_gate_passed');
  if (production_gate_passed && namespace !== 'production') {
    fail(
      'illegal_production_claim',
      `selection is ${namespace} but claims production_gate_passed=true`,
    );
  }

  return {
    schema_version,
    namespace,
    production_gate_passed,
    source: str(raw.source, 'selection.source'),
    question_id: str(raw.question_id, 'selection.question_id'),
    selection_id: str(raw.selection_id, 'selection.selection_id'),
    contrast_id: str(raw.contrast_id, 'selection.contrast_id'),
    program_a: pole(raw.program_a, 'selection.program_a'),
    program_b: pole(raw.program_b, 'selection.program_b'),
    analysis_condition: str(raw.analysis_condition, 'selection.analysis_condition'),
    dataset_id: str(raw.dataset_id, 'selection.dataset_id'),
    donor_scope: str(raw.donor_scope, 'selection.donor_scope'),
    artifact_status: str(raw.artifact_status, 'selection.artifact_status'),
    stage1_bindings: stage1Bindings(raw),
  };
}
