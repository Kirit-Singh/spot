// Consumer for W5's NATIVE reusable-temporal-arm bundle (spot.stage02_temporal_arm_bundle.v1).
// Aligned to the exact shipped producer shape (not the prior memo). Fail-closed on schema,
// arm_key, base_key referential integrity, modulation vocabulary, and ranking-ref shape;
// allowlist-and-project everything else (never rejects a verified artifact for extra fields).
//
// EXTERNAL ADMISSION PENDING: W5 currently self-signs its verification report with W11's
// independent id, and W11 cannot yet open W5's bytes (native audit). So this consumer marks
// external admission `pending` and must be revalidated against W11's final admitted bytes.

import type { Namespace } from '../domain/common';
import type {
  NativeTemporalArm,
  NativeTemporalArmBundle,
  NativeTemporalArmRecord,
  NativeTemporalBaseRecord,
  NativeTemporalRankingRef,
  TemporalModulation,
} from '../domain/nativeTemporalArm';
import { TEMPORAL_MODULATIONS, TEMPORAL_INDEPENDENT_VERIFIER_ID } from '../domain/nativeTemporalArm';
import type { DesiredChange } from '../domain/reusableArm';
import { temporalArmKey } from '../repository/armKey';
import { fail } from './errors';
import { arr, bool, enumOf, isObject, num, optBool, optNum, optStr, provenance, str } from './guards';

export const NATIVE_TEMPORAL_BUNDLE_SCHEMA = 'spot.stage02_temporal_arm_bundle.v1';

function baseRecord(v: unknown, path: string): NativeTemporalBaseRecord {
  if (!isObject(v)) fail('malformed', `${path} base record is required`);
  return {
    base_key: str(v.base_key, `${path}.base_key`),
    program_id: str(v.program_id, `${path}.program_id`),
    target_id: str(v.target_id, `${path}.target_id`),
    target_symbol: optStr(v.target_symbol, `${path}.target_symbol`),
    target_ensembl: optStr(v.target_ensembl, `${path}.target_ensembl`),
    target_id_namespace: optStr(v.target_id_namespace, `${path}.target_id_namespace`),
    perturbation_modality: optStr(v.perturbation_modality, `${path}.perturbation_modality`),
    from_condition: str(v.from_condition, `${path}.from_condition`),
    to_condition: str(v.to_condition, `${path}.to_condition`),
    temporal_status: optStr(v.temporal_status, `${path}.temporal_status`),
    evaluable: optBool(v.evaluable, `${path}.evaluable`),
    base_delta: optNum(v.base_delta, `${path}.base_delta`),
  };
}

function armRecord(v: unknown, path: string, baseKeys: Set<string>): NativeTemporalArmRecord {
  if (!isObject(v)) fail('malformed', `${path} arm record is required`);
  const base_key = str(v.base_key, `${path}.base_key`);
  // referential integrity: the row joins to a base record by base_key (never by symbol)
  if (!baseKeys.has(base_key)) {
    fail('malformed', `${path}.base_key "${base_key}" has no matching base_records entry`);
  }
  return {
    target_id: str(v.target_id, `${path}.target_id`),
    base_key,
    arm_value: optNum(v.arm_value, `${path}.arm_value`),
    evaluable: bool(v.evaluable, `${path}.evaluable`),
    temporal_status: str(v.temporal_status, `${path}.temporal_status`),
    desired_target_modulation: enumOf<TemporalModulation>(
      v.desired_target_modulation,
      TEMPORAL_MODULATIONS,
      `${path}.desired_target_modulation`,
    ),
    rank: optNum(v.rank, `${path}.rank`), // RETAINED even when null (unrankable rows kept)
  };
}

function rankingRef(v: unknown, path: string): NativeTemporalRankingRef {
  if (!isObject(v)) fail('malformed', `${path}.ranking is required`);
  return {
    path: str(v.path, `${path}.ranking.path`),
    raw_sha256: str(v.raw_sha256, `${path}.ranking.raw_sha256`),
    canonical_sha256: str(v.canonical_sha256, `${path}.ranking.canonical_sha256`),
  };
}

function arm(v: unknown, path: string, from: string, to: string, baseKeys: Set<string>): NativeTemporalArm {
  if (!isObject(v)) fail('malformed', `${path} arm is required`);
  const program_id = str(v.program_id, `${path}.program_id`);
  const desired_change = enumOf<DesiredChange>(v.desired_change, ['increase', 'decrease'], `${path}.desired_change`);
  const arm_key = str(v.arm_key, `${path}.arm_key`);
  // arm_key must equal the canonical key derived from the BUNDLE's ordered pair
  if (arm_key !== temporalArmKey(program_id, desired_change, from, to)) {
    fail('arm_key_mismatch', `${path}.arm_key "${arm_key}" != canonical temporal key`);
  }
  return {
    arm_key,
    program_id,
    desired_change,
    from_condition: str(v.from_condition, `${path}.from_condition`),
    to_condition: str(v.to_condition, `${path}.to_condition`),
    n_targets: num(v.n_targets, `${path}.n_targets`),
    n_evaluable: num(v.n_evaluable, `${path}.n_evaluable`),
    n_ranked: num(v.n_ranked, `${path}.n_ranked`),
    records: arr(v.records, `${path}.records`).map((r, i) => armRecord(r, `${path}.records[${i}]`, baseKeys)),
    ranking: rankingRef(v.ranking, path),
  };
}

export function parseNativeTemporalArmBundle(raw: unknown, expected: Namespace): NativeTemporalArmBundle {
  if (!isObject(raw)) fail('malformed', 'native temporal arm bundle must be an object');
  if (raw.schema_version !== NATIVE_TEMPORAL_BUNDLE_SCHEMA) {
    fail('unknown_schema_version', `schema_version "${String(raw.schema_version)}" != ${NATIVE_TEMPORAL_BUNDLE_SCHEMA}`);
  }
  if (raw.analysis_mode !== 'temporal_cross_condition') {
    fail('malformed', `analysis_mode "${String(raw.analysis_mode)}" != temporal_cross_condition`);
  }
  const prov = provenance(raw.provenance, 'temporalArmBundle.provenance', expected, 'stage02', [
    // the bundle's provenance file carries its own stage-02 schema; accept the known versions
    'spot.stage02_temporal_provenance.v1',
    'spot.stage02_gene_lever_set.v1',
  ]);
  const from_condition = str(raw.from_condition, 'temporalArmBundle.from_condition');
  const to_condition = str(raw.to_condition, 'temporalArmBundle.to_condition');

  const baseRaw = raw.base_records;
  if (!isObject(baseRaw)) fail('malformed', 'temporalArmBundle.base_records is required');
  const base_records: Record<string, NativeTemporalBaseRecord> = {};
  for (const k of Object.keys(baseRaw)) base_records[k] = baseRecord(baseRaw[k], `base_records.${k}`);
  const baseKeys = new Set(Object.keys(base_records));

  const armsRaw = raw.arms;
  if (!isObject(armsRaw)) fail('malformed', 'temporalArmBundle.arms is required');
  const arms: Record<string, NativeTemporalArm> = {};
  for (const k of Object.keys(armsRaw)) {
    const a = arm(armsRaw[k], `arms.${k}`, from_condition, to_condition, baseKeys);
    if (k !== a.arm_key) fail('arm_key_mismatch', `arms map key "${k}" != arm_key "${a.arm_key}"`);
    arms[k] = a;
  }

  return {
    schema_version: NATIVE_TEMPORAL_BUNDLE_SCHEMA,
    lane: 'temporal',
    analysis_mode: 'temporal_cross_condition',
    from_condition,
    to_condition,
    bundle_id: str(raw.bundle_id, 'temporalArmBundle.bundle_id'),
    base_records,
    arms,
    verification_ref: str(raw.verification_ref, 'temporalArmBundle.verification_ref'),
    provenance: prov,
  };
}

/** Resolve a reusable temporal arm by (program_id, desired_change) via its canonical key. */
export function getNativeTemporalArm(
  b: NativeTemporalArmBundle,
  program_id: string,
  change: DesiredChange,
): NativeTemporalArm | null {
  return b.arms[temporalArmKey(program_id, change, b.from_condition, b.to_condition)] ?? null;
}

/** Immutable identity for an arm record — joined by base_key, never by symbol. */
export function nativeTemporalIdentity(
  b: NativeTemporalArmBundle,
  record: NativeTemporalArmRecord,
): { target_id: string; target_ensembl: string | null; target_symbol: string | null } {
  const rec = b.base_records[record.base_key];
  if (!rec) return { target_id: record.target_id, target_ensembl: null, target_symbol: null };
  return { target_id: rec.target_id, target_ensembl: rec.target_ensembl, target_symbol: rec.target_symbol };
}

/** External admission is PENDING until W11 admits W5's bytes with its own report. */
export function nativeTemporalAdmission(b: NativeTemporalArmBundle): {
  verifier_id: string;
  matches_independent_id: boolean;
  external_admission: 'pending';
} {
  return {
    verifier_id: b.verification_ref,
    matches_independent_id: b.verification_ref === TEMPORAL_INDEPENDENT_VERIFIER_ID,
    external_admission: 'pending',
  };
}
