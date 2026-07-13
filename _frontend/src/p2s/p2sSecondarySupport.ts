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

// Any field name containing one of these is refused at load: this data may never be used as a
// statistic, a verdict, a combined objective, or a rank. `coefficient`/`concordance` are NOT
// here — they are the reconstruction-support values themselves.
const FORBIDDEN_FIELD = /rank|p_?value|q_?val|fdr|significance|combined|weighted|causal|validation|gating|pareto/i

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
    const p = raw as P2sProjection
    refuse(!!p && typeof p === 'object', 'projection is not an object')
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
    refuse(Array.isArray(p.rows), 'projection has no rows')
    refuse(Array.isArray(p.columns), 'projection has no columns')

    // STRUCTURAL REFUSAL: no column and no row key may name a statistic/verdict/rank.
    const cols = p.columns.filter((c) => FORBIDDEN_FIELD.test(c))
    refuse(cols.length === 0, `projection carries forbidden column(s): ${cols.join(', ')}`)
    const rowKeys = new Set<string>()
    for (const r of p.rows) for (const k of Object.keys(r)) rowKeys.add(k)
    const badKeys = [...rowKeys].filter((k) => FORBIDDEN_FIELD.test(k))
    refuse(badKeys.length === 0, `projection rows carry forbidden field(s): ${badKeys.join(', ')}`)

    refuse(!!p.adapter?.arm_key && !!p.adapter?.sibling_arm_key,
      'projection is missing its arm_key / sibling_arm_key binding')
    refuse(!!p.binding?.receipt_sha256, 'projection is not bound to an admitted receipt')
    return new P2sSecondarySupport(p)
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
