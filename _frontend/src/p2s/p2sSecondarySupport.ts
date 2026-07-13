/**
 * The Perturb2State SECONDARY-support UI seam.
 *
 * A read-only adapter over `P2S_UI_SUPPORT_PROJECTION.json`. It BINDS support to a target by
 * exact `target_id` on the projection's own `arm_key` (and its exact-negation sibling), exposes
 * a compact reconstruction-support view for the Targets hover/details and a Methods-drawer
 * block, and STRUCTURALLY refuses any p-value / validation / causal / combined / ranking use:
 *
 *   - `loadP2sSecondarySupport` REFUSES a projection that is not `secondary_non_gating`, that
 *     declares itself part of the admitted Direct result, that admits entering primary rank/
 *     order, or that carries any rank / p-value / q-value / FDR / significance / combined /
 *     weighted / causal / validation field. A tampered projection cannot be loaded.
 *   - The adapter offers NO `rank()`, `sort()`, `top()`, `gate()`, or `combine()` — the only
 *     lookup is by `target_id`. There is no surface on which to reorder Direct/Temporal/Pathway.
 *
 * It never reads, writes, or references any Direct/Temporal/Pathway rank or order.
 */
import { P2S_LANE_ROLE, P2S_PROJECTION_SCHEMA } from './types'
import type {
  Direction,
  P2sProjection,
  P2sSupportRow,
  P2sSupportView,
  PrimarySign,
} from './types'

export class P2sSecondarySupportError extends Error {}

const HEX64 = /^[0-9a-f]{64}$/
const HEX40 = /^[0-9a-f]{40}$/
const TOP_KEYS = ['adapter', 'binding', 'columns', 'emitted_utc', 'lane_role', 'n_targets',
  'projection_rows_sha256', 'rows', 'schema_version', 'semantics'] as const
const SEMANTICS_KEYS = ['coefficients_are', 'is_part_of_admitted_direct_result',
  'no_rank_no_pvalue_no_combined_score', 'p2s_fields_enter_primary_rank_or_order', 'row_order',
  'sibling_arm_is_exact_negation'] as const
const ADAPTER_KEYS = ['arm_key', 'condition', 'desired_change', 'display_fields',
  'forbidden_ui_uses', 'join_key', 'program_id', 'robustness_fields',
  'sibling_arm_key'] as const
const BINDING_KEYS = ['arm_key', 'bound_direct_release', 'input_hashes', 'model', 'p2s_run_id',
  'p2s_run_sha256', 'receipt_sha256', 'seed', 'sibling_arm_key', 'source_support_parquet_sha256',
  'source_support_rows_sha256'] as const
const DIRECT_RELEASE_KEYS = ['bundle_run_id', 'release_run_id', 'scorer_view_sha256', 'w10_verdict',
  'w10_verifier_code_sha256', 'w10_verifier_id'] as const
const MODEL_KEYS = ['l1_ratio_grid', 'n_pcs_primary', 'positive', 'random_state', 'upstream_commit',
  'upstream_version'] as const
const INPUT_HASH_KEYS = ['de_main_raw_sha256', 'ntc_h5ad_raw_sha256',
  'stage1_scores_canonical_sha256', 'stage1_scores_raw_sha256'] as const
const ROW_KEYS = ['target_id', 'primary_coefficient', 'primary_abs_coefficient', 'primary_sign',
  'opposed', 'primary_available', 'n_runs', 'sens_log_fc_sign_concordance', 'n_log_fc',
  'sens_pca_off_sign_concordance', 'n_pca_off', 'lodo_sign_concordance', 'n_lodo'] as const
const DISPLAY_FIELDS = ['primary_coefficient', 'primary_sign', 'opposed', 'primary_available'] as const
const ROBUSTNESS_FIELDS = ['sens_log_fc_sign_concordance', 'n_log_fc',
  'sens_pca_off_sign_concordance', 'n_pca_off', 'lodo_sign_concordance', 'n_lodo', 'n_runs'] as const

// Exact schemas protect most of the document. These rules cover the two intentionally extensible
// provenance maps (`model`, `input_hashes`) and catch disguised statistical/ranking surfaces.
function forbiddenDynamicKey(key: string): boolean {
  const k = key.toLowerCase().replace(/[^a-z0-9]/g, '')
  if (/^(p|q)$/.test(k) || /(padj|pval|pvalue|qval|qvalue|fdr|falsediscovery|posteriorprob|nominalp|empiricalp|empiricalq)/.test(k)) return true
  return /(rank|ranking|aggregatescore|compositescore|overallscore|aggregateobjective|combined|balanced|weighted|significance|significant|validat|causal|causality|gating|pareto)/.test(k)
}

function isObject(v: unknown): v is Record<string, unknown> {
  return !!v && typeof v === 'object' && !Array.isArray(v)
}

function exactKeys(v: Record<string, unknown>, expected: readonly string[], path: string): void {
  const got = Object.keys(v).sort()
  const want = [...expected].sort()
  refuse(got.length === want.length && got.every((key, i) => key === want[i]),
    `${path} fields [${got.join(', ')}] do not equal [${want.join(', ')}]`)
}

function exactStrings(v: unknown, expected: readonly string[], path: string): void {
  refuse(Array.isArray(v) && v.length === expected.length &&
    v.every((x, i) => typeof x === 'string' && x === expected[i]),
  `${path} must be exactly [${expected.join(', ')}]`)
}

function nonempty(v: unknown, path: string): string {
  refuse(typeof v === 'string' && v.trim().length > 0, `${path} must be a non-empty string`)
  return v as string
}

function hex64(v: unknown, path: string): string {
  const s = nonempty(v, path)
  refuse(HEX64.test(s), `${path} must be a 64-hex sha256`)
  return s
}

function uint(v: unknown, path: string, positive = false): number {
  refuse(typeof v === 'number' && Number.isSafeInteger(v) && v >= (positive ? 1 : 0),
    `${path} must be a ${positive ? 'positive' : 'non-negative'} integer`)
  return v as number
}

function finiteOrNull(v: unknown, path: string): number | null {
  refuse(v === null || (typeof v === 'number' && Number.isFinite(v)), `${path} must be finite or null`)
  return v as number | null
}

function concordance(v: unknown, denominator: number, coefficient: number | null, path: string): number | null {
  const n = finiteOrNull(v, path)
  // A sign-concordance is undefined for a zero/unavailable primary coefficient even when the
  // sensitivity fit itself exists. The released artifact correctly records those cases as null.
  if (denominator === 0 || coefficient === null || coefficient === 0) {
    refuse(n === null, `${path} must be null when its denominator or primary sign is zero`)
  }
  else refuse(n !== null && n >= 0 && n <= 1, `${path} must be in [0,1] when measured`)
  return n
}

function scanDynamic(v: unknown, path: string): void {
  if (Array.isArray(v)) {
    v.forEach((child, i) => scanDynamic(child, `${path}[${i}]`))
    return
  }
  if (!isObject(v)) {
    if (typeof v === 'string') {
      refuse(!v.startsWith('/') && !/^file:\/\//i.test(v) && !/^[a-z]:[\\/]/i.test(v),
        `${path} carries a machine-local path`)
    }
    return
  }
  for (const [key, child] of Object.entries(v)) {
    refuse(!forbiddenDynamicKey(key), `${path}.${key} is a forbidden statistical/ranking field`)
    scanDynamic(child, `${path}.${key}`)
  }
}

function deepFreeze<T>(value: T): T {
  if (value && typeof value === 'object' && !Object.isFrozen(value)) {
    Object.freeze(value)
    for (const child of Object.values(value as Record<string, unknown>)) deepFreeze(child)
  }
  return value
}

interface DirectArmIdentity { program: string; direction: Direction; condition: string }
function directArmIdentity(key: string, path: string): DirectArmIdentity {
  const parts = key.split('|')
  refuse(parts.length === 4 && parts[0] === 'direct' && parts[1].length > 0 &&
    (parts[2] === 'increase' || parts[2] === 'decrease') && parts[3].length > 0,
  `${path} is not a canonical direct arm key`)
  return { program: parts[1], direction: parts[2] as Direction, condition: parts[3] }
}

function validateRow(v: unknown, index: number): P2sSupportRow {
  const path = `rows[${index}]`
  refuse(isObject(v), `${path} must be an object`)
  const row = v as Record<string, unknown>
  exactKeys(row, ROW_KEYS, path)
  const target = nonempty(row.target_id, `${path}.target_id`)
  refuse(/^ENSG[0-9]{11}$/.test(target), `${path}.target_id must be a canonical Ensembl gene id`)
  const coefficient = finiteOrNull(row.primary_coefficient, `${path}.primary_coefficient`)
  const magnitude = finiteOrNull(row.primary_abs_coefficient, `${path}.primary_abs_coefficient`)
  refuse(typeof row.primary_available === 'boolean', `${path}.primary_available must be boolean`)
  const available = row.primary_available as boolean
  refuse(available === (coefficient !== null), `${path}.primary_available disagrees with coefficient availability`)
  refuse((coefficient === null && magnitude === null) ||
    (coefficient !== null && magnitude !== null && Math.abs(Math.abs(coefficient) - magnitude) <= 1e-12),
  `${path}.primary_abs_coefficient does not equal abs(primary_coefficient)`)
  refuse(row.primary_sign === 'supportive' || row.primary_sign === 'opposed' || row.primary_sign === 'zero',
    `${path}.primary_sign is invalid`)
  const sign = row.primary_sign as PrimarySign
  const expectedSign: PrimarySign = coefficient === null || coefficient === 0
    ? 'zero' : coefficient > 0 ? 'supportive' : 'opposed'
  refuse(sign === expectedSign, `${path}.primary_sign disagrees with primary_coefficient`)
  refuse(typeof row.opposed === 'boolean' && row.opposed === (sign === 'opposed'),
    `${path}.opposed disagrees with primary_sign`)
  const nRuns = uint(row.n_runs, `${path}.n_runs`, true)
  const nLogFc = uint(row.n_log_fc, `${path}.n_log_fc`)
  const nPcaOff = uint(row.n_pca_off, `${path}.n_pca_off`)
  const nLodo = uint(row.n_lodo, `${path}.n_lodo`)
  return {
    target_id: target,
    primary_coefficient: coefficient,
    primary_abs_coefficient: magnitude,
    primary_sign: sign,
    opposed: row.opposed as boolean,
    primary_available: available,
    n_runs: nRuns,
    sens_log_fc_sign_concordance: concordance(row.sens_log_fc_sign_concordance, nLogFc, coefficient,
      `${path}.sens_log_fc_sign_concordance`),
    n_log_fc: nLogFc,
    sens_pca_off_sign_concordance: concordance(row.sens_pca_off_sign_concordance, nPcaOff, coefficient,
      `${path}.sens_pca_off_sign_concordance`),
    n_pca_off: nPcaOff,
    lodo_sign_concordance: concordance(row.lodo_sign_concordance, nLodo, coefficient,
      `${path}.lodo_sign_concordance`),
    n_lodo: nLodo,
  }
}

function refuse(cond: boolean, message: string): void {
  if (!cond) throw new P2sSecondarySupportError(message)
}

function flipSign(sign: PrimarySign): PrimarySign {
  if (sign === 'supportive') return 'opposed'
  if (sign === 'opposed') return 'supportive'
  return 'zero'
}

function negate(v: number | null): number | null {
  if (v === null || v === undefined) return null
  // -0 prints as a different number and asserts a distinction the data does not make
  return v === 0 ? 0 : -v
}

export class P2sSecondarySupport {
  readonly armKey: string
  readonly siblingArmKey: string
  readonly programId: string
  readonly condition: string
  readonly laneRole = P2S_LANE_ROLE
  readonly isPartOfAdmittedDirectResult = false
  readonly entersPrimaryRankOrOrder = false
  readonly binding: P2sProjection['binding']
  readonly nTargets: number

  private readonly byTarget: Map<string, P2sSupportRow>
  private readonly proj: P2sProjection

  private constructor(proj: P2sProjection) {
    this.proj = proj
    this.armKey = proj.adapter.arm_key
    this.siblingArmKey = proj.adapter.sibling_arm_key
    this.programId = proj.adapter.program_id
    this.condition = proj.adapter.condition
    this.binding = proj.binding
    this.nTargets = proj.n_targets
    this.byTarget = new Map(proj.rows.map((r) => [r.target_id, r]))
  }

  /** Load + VALIDATE + guard. Throws `P2sSecondarySupportError` on anything unsafe. */
  static load(raw: unknown): P2sSecondarySupport {
    refuse(isObject(raw), 'projection is not an object')
    exactKeys(raw as Record<string, unknown>, TOP_KEYS, 'projection')
    const p = raw as unknown as P2sProjection
    refuse(p.schema_version === P2S_PROJECTION_SCHEMA,
      `unexpected schema_version ${String(p.schema_version)}`)
    refuse(p.lane_role === P2S_LANE_ROLE,
      `lane_role must be ${P2S_LANE_ROLE}, got ${String(p.lane_role)}`)
    refuse(p.semantics?.is_part_of_admitted_direct_result === false,
      'projection must declare it is NOT part of the admitted Direct result')
    refuse(p.semantics?.p2s_fields_enter_primary_rank_or_order === false,
      'projection must declare its fields do NOT enter primary rank/order')
    refuse(p.semantics?.no_rank_no_pvalue_no_combined_score === true,
      'projection must declare no rank / no p-value / no combined score')
    refuse(p.semantics?.sibling_arm_is_exact_negation === true,
      'projection must declare the sibling arm is the exact negation')
    refuse(isObject(p.semantics), 'projection.semantics must be an object')
    exactKeys(p.semantics as unknown as Record<string, unknown>, SEMANTICS_KEYS, 'projection.semantics')
    refuse(Array.isArray(p.rows), 'projection has no rows')
    refuse(Array.isArray(p.columns), 'projection has no columns')
    exactStrings(p.columns, ROW_KEYS, 'projection.columns')
    refuse(isObject(p.adapter), 'projection.adapter must be an object')
    exactKeys(p.adapter as Record<string, unknown>, ADAPTER_KEYS, 'projection.adapter')
    refuse(p.adapter.join_key === 'target_id', 'projection.adapter.join_key must be target_id')
    exactStrings(p.adapter.display_fields, DISPLAY_FIELDS, 'projection.adapter.display_fields')
    exactStrings(p.adapter.robustness_fields, ROBUSTNESS_FIELDS, 'projection.adapter.robustness_fields')
    refuse(Array.isArray(p.adapter.forbidden_ui_uses) && p.adapter.forbidden_ui_uses.length > 0 &&
      p.adapter.forbidden_ui_uses.every((x) => typeof x === 'string' && x.trim().length > 0),
    'projection.adapter.forbidden_ui_uses must be a non-empty string[]')
    const arm = directArmIdentity(nonempty(p.adapter.arm_key, 'projection.adapter.arm_key'),
      'projection.adapter.arm_key')
    const sibling = directArmIdentity(nonempty(p.adapter.sibling_arm_key,
      'projection.adapter.sibling_arm_key'), 'projection.adapter.sibling_arm_key')
    refuse(arm.program === p.adapter.program_id && arm.condition === p.adapter.condition &&
      arm.direction === p.adapter.desired_change,
    'projection.adapter arm key disagrees with program/condition/direction')
    refuse(sibling.program === arm.program && sibling.condition === arm.condition &&
      sibling.direction !== arm.direction,
    'projection.adapter sibling_arm_key is not the exact opposite direction')

    refuse(isObject(p.binding), 'projection.binding must be an object')
    exactKeys(p.binding as unknown as Record<string, unknown>, BINDING_KEYS, 'projection.binding')
    refuse(p.binding.arm_key === p.adapter.arm_key &&
      p.binding.sibling_arm_key === p.adapter.sibling_arm_key,
    'projection.binding arm keys disagree with projection.adapter')
    hex64(p.binding.receipt_sha256, 'projection.binding.receipt_sha256')
    hex64(p.binding.p2s_run_sha256, 'projection.binding.p2s_run_sha256')
    refuse(p.binding.p2s_run_id === p.binding.p2s_run_sha256.slice(0, 16),
      'projection.binding.p2s_run_id does not derive from p2s_run_sha256')
    hex64(p.binding.source_support_rows_sha256, 'projection.binding.source_support_rows_sha256')
    hex64(p.binding.source_support_parquet_sha256, 'projection.binding.source_support_parquet_sha256')
    uint(p.binding.seed, 'projection.binding.seed')
    refuse(isObject(p.binding.model), 'projection.binding.model must be an object')
    exactKeys(p.binding.model, MODEL_KEYS, 'projection.binding.model')
    scanDynamic(p.binding.model, 'projection.binding.model')
    refuse(HEX40.test(nonempty(p.binding.model.upstream_commit,
      'projection.binding.model.upstream_commit')), 'projection.binding.model.upstream_commit must be full 40-hex')
    nonempty(p.binding.model.upstream_version, 'projection.binding.model.upstream_version')
    refuse(p.binding.model.random_state === p.binding.seed,
      'projection.binding.model.random_state must equal the bound seed')
    refuse(isObject(p.binding.input_hashes), 'projection.binding.input_hashes must be an object')
    exactKeys(p.binding.input_hashes, INPUT_HASH_KEYS, 'projection.binding.input_hashes')
    scanDynamic(p.binding.input_hashes, 'projection.binding.input_hashes')
    for (const key of INPUT_HASH_KEYS) hex64(p.binding.input_hashes[key], `projection.binding.input_hashes.${key}`)
    refuse(isObject(p.binding.bound_direct_release),
      'projection.binding.bound_direct_release must be an object')
    exactKeys(p.binding.bound_direct_release as unknown as Record<string, unknown>, DIRECT_RELEASE_KEYS,
      'projection.binding.bound_direct_release')
    refuse(p.binding.bound_direct_release.w10_verdict === 'ADMIT',
      'projection is not bound to a W10 ADMIT result')
    refuse(p.binding.bound_direct_release.w10_verifier_id ===
      'spot.stage02.direct.arm_bundle.verifier.v1',
    'projection is not bound to the admitted W10 verifier')
    refuse(/^[0-9a-f]{16}$/.test(p.binding.bound_direct_release.release_run_id),
      'projection.binding.bound_direct_release.release_run_id must be 16-hex')
    refuse(/^[0-9a-f]{16}$/.test(p.binding.bound_direct_release.bundle_run_id),
      'projection.binding.bound_direct_release.bundle_run_id must be 16-hex')
    hex64(p.binding.bound_direct_release.w10_verifier_code_sha256,
      'projection.binding.bound_direct_release.w10_verifier_code_sha256')
    hex64(p.binding.bound_direct_release.scorer_view_sha256,
      'projection.binding.bound_direct_release.scorer_view_sha256')

    hex64(p.projection_rows_sha256, 'projection.projection_rows_sha256')
    const rows = p.rows.map((r, i) => validateRow(r, i))
    refuse(uint(p.n_targets, 'projection.n_targets', true) === rows.length,
      'projection.n_targets does not match rows.length')
    const ids = rows.map((r) => r.target_id)
    refuse(new Set(ids).size === ids.length, 'projection has duplicate target_id rows')
    refuse(ids.every((id, i) => i === 0 || ids[i - 1].localeCompare(id) < 0),
      'projection rows are not strictly target_id-ascending')
    // Own the admitted bytes after validation. A caller mutating its original parsed object after load
    // must not change a value already admitted into the UI (TOCTOU fail-closed invariant).
    const admitted = deepFreeze(structuredClone({ ...p, rows }))
    return new P2sSecondarySupport(admitted)
  }

  /** True iff this projection speaks for the given arm (its own arm or its exact-negation sibling). */
  bindsArm(armKey: string): boolean {
    return armKey === this.armKey || armKey === this.siblingArmKey
  }

  private directionFor(armKey: string): Direction | null {
    if (armKey === this.armKey) return this.proj.adapter.desired_change
    if (armKey === this.siblingArmKey) {
      return this.proj.adapter.desired_change === 'increase' ? 'decrease' : 'increase'
    }
    return null
  }

  /**
   * EXACT BINDING: reconstruction support for one target on one arm.
   *
   * Bound by `target_id` on the given `armKey` (must be this projection's arm or its sibling).
   * The stored rows are the `increase` arm; the `decrease` view is the EXACT NEGATION (the two
   * arms are one measurement and a sign — never a re-fit). Returns `null` when the arm is not
   * this projection's, or the target has no support row.
   */
  supportForTarget(targetId: string, armKey: string): P2sSupportView | null {
    const direction = this.directionFor(armKey)
    if (direction === null) return null
    const row = this.byTarget.get(targetId)
    if (!row) return null

    const isStored = direction === this.proj.adapter.desired_change
    const coefficient = isStored ? row.primary_coefficient : negate(row.primary_coefficient)
    const sign = isStored ? row.primary_sign : flipSign(row.primary_sign)
    const opposed = row.primary_sign === 'zero' ? row.opposed : (isStored ? row.opposed : !row.opposed)

    return {
      targetId,
      armKey,
      direction,
      coefficient,
      absCoefficient: row.primary_abs_coefficient, // magnitude is direction-invariant
      sign,
      opposed,
      available: row.primary_available,
      nRuns: row.n_runs,
      robustness: {
        logFcSignConcordance: row.sens_log_fc_sign_concordance,
        nLogFc: row.n_log_fc,
        pcaOffSignConcordance: row.sens_pca_off_sign_concordance,
        nPcaOff: row.n_pca_off,
        lodoSignConcordance: row.lodo_sign_concordance,
        nLodo: row.n_lodo,
      },
    }
  }

  /** The Methods-drawer block: what this lane IS, and the guardrails, straight from the artifact. */
  methodsDrawer() {
    return {
      title: 'Perturb2State reconstruction support (secondary)',
      laneRole: this.laneRole,
      isSecondaryNonGating: true,
      whatItIs: this.proj.semantics.coefficients_are,
      armKey: this.armKey,
      siblingArmKey: this.siblingArmKey,
      program: this.programId,
      condition: this.condition,
      siblingIsExactNegation: this.proj.semantics.sibling_arm_is_exact_negation,
      rowOrder: this.proj.semantics.row_order,
      model: {
        upstream: `${this.binding.model.upstream_version} @ ${this.binding.model.upstream_commit}`,
        seed: this.binding.seed,
      },
      boundDirectRelease: this.binding.bound_direct_release,
      provenance: {
        receiptSha256: this.binding.receipt_sha256,
        p2sRunId: this.binding.p2s_run_id,
        projectionRowsSha256: this.proj.projection_rows_sha256,
      },
      guardrails: [
        'Secondary and NON-GATING: it never enters Direct / Temporal / Pathway rank or order.',
        'Reconstruction support only — NOT a p-value, validation, causal effect, or combined score.',
        ...this.proj.adapter.forbidden_ui_uses.map((u) => `Must not be used for: ${u}.`),
      ],
    }
  }
}

/** Convenience alias — load a raw parsed projection into the guarded adapter. */
export function loadP2sSecondarySupport(raw: unknown): P2sSecondarySupport {
  return P2sSecondarySupport.load(raw)
}
