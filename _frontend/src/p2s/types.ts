/**
 * Types for the Perturb2State (P2S) SECONDARY reconstruction-support projection.
 *
 * These mirror `P2S_UI_SUPPORT_PROJECTION.json` (schema
 * `spot.stage02.p2s_ui_support_projection.v1`) exactly. The projection is SECONDARY and
 * NON-GATING: it carries reconstruction-support coefficients only — never a rank, a p-value,
 * a combined/weighted score, a validation claim, or a causal effect. The types deliberately
 * expose no rank/order field, so the UI cannot render one from this data.
 */

export const P2S_PROJECTION_SCHEMA = 'spot.stage02.p2s_ui_support_projection.v1'
export const P2S_LANE_ROLE = 'secondary_non_gating'

export type PrimarySign = 'supportive' | 'opposed' | 'zero'
export type Direction = 'increase' | 'decrease'

/** One target's compact reconstruction-support view (as stored — the INCREASE arm). */
export interface P2sSupportRow {
  target_id: string
  primary_coefficient: number | null
  primary_abs_coefficient: number | null
  primary_sign: PrimarySign
  opposed: boolean
  primary_available: boolean
  n_runs: number
  sens_log_fc_sign_concordance: number | null
  n_log_fc: number
  sens_pca_off_sign_concordance: number | null
  n_pca_off: number
  lodo_sign_concordance: number | null
  n_lodo: number
}

/** The provenance the projection binds — read-only ids/hashes, surfaced in the Methods drawer. */
export interface P2sBinding {
  receipt_sha256: string
  p2s_run_id: string
  p2s_run_sha256: string
  source_support_rows_sha256: string
  source_support_parquet_sha256: string
  arm_key: string
  sibling_arm_key: string
  seed: number
  model: {
    l1_ratio_grid?: number[]
    random_state?: number
    positive?: boolean
    n_pcs?: number
    upstream_commit: string
    upstream_version: string
    [k: string]: unknown
  }
  input_hashes: Record<string, unknown>
  bound_direct_release: {
    release_run_id: string
    bundle_run_id: string
    w10_verdict: string
    w10_verifier_code_sha256: string
    scorer_view_sha256: string
  }
}

export interface P2sProjection {
  schema_version: string
  emitted_utc: string
  lane_role: string
  semantics: {
    is_part_of_admitted_direct_result: boolean
    p2s_fields_enter_primary_rank_or_order: boolean
    no_rank_no_pvalue_no_combined_score: boolean
    row_order: string
    coefficients_are: string
    sibling_arm_is_exact_negation: boolean
  }
  adapter: {
    join_key: string
    arm_key: string
    sibling_arm_key: string
    program_id: string
    desired_change: Direction
    condition: string
    display_fields: string[]
    robustness_fields: string[]
    forbidden_ui_uses: string[]
    [k: string]: unknown
  }
  binding: P2sBinding
  columns: string[]
  n_targets: number
  projection_rows_sha256: string
  rows: P2sSupportRow[]
}

/** A per-(target, direction) view the UI renders. Note: NO rank, NO score, NO p-value. */
export interface P2sSupportView {
  targetId: string
  armKey: string
  direction: Direction
  /** signed reconstruction-support coefficient for this direction */
  coefficient: number | null
  absCoefficient: number | null
  sign: PrimarySign
  /** the perturbation OPPOSES the desired direction (a supportive/opposed label, not a verdict) */
  opposed: boolean
  available: boolean
  nRuns: number
  robustness: {
    logFcSignConcordance: number | null
    nLogFc: number
    pcaOffSignConcordance: number | null
    nPcaOff: number
    lodoSignConcordance: number | null
    nLodo: number
  }
}
