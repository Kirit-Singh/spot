// Fail-closed production adapter for the AUTHORITATIVE Stage-1 v3 selection contract
// `spot.stage01_selection.v3`. This replaces reliance on the legacy v1 `parseSelection`:
// it NEVER trusts the artifact. A named schema gate refuses anything that is not v3 (so a
// v1 selection is rejected outright), then `verifySelectionV3` INDEPENDENTLY recomputes
// selection_id / selection_full_sha256 / full_contract_content_sha256 and re-derives the
// routing decision — throwing SelectionError on any forgery, hash mismatch, mode/estimator
// mismatch, or pole-identity mismatch. Only a fully verified contract is projected into the
// typed SelectionV3 the UI consumes.

import { SelectionError, verifySelectionV3 } from '../stage1/selectionV3';

export interface SelectionV3Pole {
  program_id: string;
  direction: 'high' | 'low';
}

export interface SelectionV3 {
  selection_id: string;
  analysis_mode: 'within_condition' | 'temporal_cross_condition';
  execution_status: 'ready' | 'refused' | 'awaiting_estimator';
  estimator_id: string;
  estimator_status: 'available' | 'not_implemented';
  A: SelectionV3Pole;
  B: SelectionV3Pole;
  conditions: string[]; // 1 within / 2 ordered temporal
  registry_scorer_view_sha256: string;
  source_h5ad_sha256: string;
  selection_full_sha256: string;
  full_contract_content_sha256: string;
  raw: Record<string, unknown>;
}

function asObject(v: unknown, path: string): Record<string, unknown> {
  if (typeof v !== 'object' || v === null || Array.isArray(v)) {
    throw new SelectionError('malformed', `${path} must be an object`);
  }
  return v as Record<string, unknown>;
}

function asString(v: unknown, path: string): string {
  if (typeof v !== 'string') throw new SelectionError('malformed', `${path} must be a string`);
  return v;
}

function asDirection(v: unknown, path: string): 'high' | 'low' {
  const s = asString(v, path);
  if (s !== 'high' && s !== 'low') {
    throw new SelectionError('bad_enum', `${path} "${s}" not in high|low`);
  }
  return s;
}

function asEstimatorStatus(v: unknown, path: string): 'available' | 'not_implemented' {
  const s = asString(v, path);
  if (s !== 'available' && s !== 'not_implemented') {
    throw new SelectionError('bad_enum', `${path} "${s}" not in available|not_implemented`);
  }
  return s;
}

/**
 * Parse a Stage-1 v3 selection contract, fail-closed.
 *
 * Async because verification hash-recomputes via {@link verifySelectionV3}. Throws
 * {@link SelectionError} on a v1/legacy/unknown schema (`bad_schema_version`), a forged
 * hash, or a mode/estimator/pole mismatch. Returns the projected {@link SelectionV3} only
 * for a contract that passes independent verification.
 */
export async function parseSelectionV3(raw: unknown): Promise<SelectionV3> {
  // ── NAMED schema gate (fail-closed) ──
  // Refuse anything that is not the authoritative v3 contract BEFORE any other work, so a
  // legacy v1 selection (or a forged/unknown schema tag) can never reach the verifier.
  if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) {
    throw new SelectionError('malformed', 'selection must be an object');
  }
  const top = raw as Record<string, unknown>;
  if (top.schema_version !== 'spot.stage01_selection.v3') {
    throw new SelectionError(
      'bad_schema_version',
      `schema_version "${String(top.schema_version)}" != spot.stage01_selection.v3`,
    );
  }

  // ── independent verification: recomputes every hash + re-derives routing, throws on any
  //    forgery or mismatch. We only project fields it has already validated. ──
  const verified = await verifySelectionV3(top);
  const source = verified.raw;

  const cc = asObject(source.canonical_content, 'canonical_content');
  const ccA = asObject(cc.A, 'canonical_content.A');
  const ccB = asObject(cc.B, 'canonical_content.B');

  const conditionsRaw = cc.conditions;
  if (!Array.isArray(conditionsRaw)) {
    throw new SelectionError('malformed', 'canonical_content.conditions must be an array');
  }

  return {
    selection_id: verified.selection_id,
    analysis_mode: verified.analysis_mode,
    execution_status: verified.execution_status,
    estimator_id: asString(source.estimator_id, 'estimator_id'),
    estimator_status: asEstimatorStatus(source.estimator_status, 'estimator_status'),
    A: {
      program_id: asString(ccA.program_id, 'canonical_content.A.program_id'),
      direction: asDirection(ccA.direction, 'canonical_content.A.direction'),
    },
    B: {
      program_id: asString(ccB.program_id, 'canonical_content.B.program_id'),
      direction: asDirection(ccB.direction, 'canonical_content.B.direction'),
    },
    conditions: conditionsRaw.map((c, i) => asString(c, `canonical_content.conditions[${i}]`)),
    registry_scorer_view_sha256: asString(
      cc.registry_scorer_view_sha256,
      'canonical_content.registry_scorer_view_sha256',
    ),
    source_h5ad_sha256: asString(cc.source_h5ad_sha256, 'canonical_content.source_h5ad_sha256'),
    selection_full_sha256: asString(source.selection_full_sha256, 'selection_full_sha256'),
    full_contract_content_sha256: asString(
      source.full_contract_content_sha256,
      'full_contract_content_sha256',
    ),
    raw: source,
  };
}
