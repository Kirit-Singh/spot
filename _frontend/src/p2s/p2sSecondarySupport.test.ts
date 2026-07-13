import { describe, expect, it } from 'vitest'

import { P2sSecondarySupportError, loadP2sSecondarySupport } from './p2sSecondarySupport'
import type { P2sProjection, P2sSupportRow } from './types'

const INC = 'direct|treg_like|increase|Stim48hr'
const DEC = 'direct|treg_like|decrease|Stim48hr'

// Two real-shaped rows: an OPPOSED target (negative increase coefficient) and a SUPPORTIVE one.
const OPPOSED_ROW: P2sSupportRow = {
  target_id: 'ENSG00000000419',
  primary_coefficient: -0.000562, primary_abs_coefficient: 0.000562,
  primary_sign: 'opposed', opposed: true, primary_available: true, n_runs: 7,
  sens_log_fc_sign_concordance: 0.0, n_log_fc: 1,
  sens_pca_off_sign_concordance: 0.0, n_pca_off: 1,
  lodo_sign_concordance: 1.0, n_lodo: 4,
}
const SUPPORTIVE_ROW: P2sSupportRow = {
  target_id: 'ENSG00000000457',
  primary_coefficient: 0.0034, primary_abs_coefficient: 0.0034,
  primary_sign: 'supportive', opposed: false, primary_available: true, n_runs: 7,
  sens_log_fc_sign_concordance: 1.0, n_log_fc: 1,
  sens_pca_off_sign_concordance: 1.0, n_pca_off: 1,
  lodo_sign_concordance: 0.75, n_lodo: 4,
}

function fixture(): P2sProjection {
  // structuredClone so a mutating test cannot pollute the module-level rows shared by others
  return structuredClone(base())
}

function base(): P2sProjection {
  return {
    schema_version: 'spot.stage02.p2s_ui_support_projection.v1',
    emitted_utc: '2026-07-13T18:30:00+00:00',
    lane_role: 'secondary_non_gating',
    semantics: {
      is_part_of_admitted_direct_result: false,
      p2s_fields_enter_primary_rank_or_order: false,
      no_rank_no_pvalue_no_combined_score: true,
      row_order: 'target_id ascending (a neutral key; NOT a rank)',
      coefficients_are: 'reconstruction support; not p-values, validation, or causal effects',
      sibling_arm_is_exact_negation: true,
    },
    adapter: {
      join_key: 'target_id', arm_key: INC, sibling_arm_key: DEC,
      program_id: 'treg_like', desired_change: 'increase', condition: 'Stim48hr',
      display_fields: ['primary_coefficient', 'primary_sign', 'opposed', 'primary_available'],
      robustness_fields: ['sens_log_fc_sign_concordance', 'lodo_sign_concordance'],
      forbidden_ui_uses: ['ranking', 'gating', 'combining with Direct rank/order',
        'presenting as p-value/validation/causal effect'],
    },
    binding: {
      receipt_sha256: '2d96a8a6e6c3baf3d2606d2db0af49620d71106ebd8153f773531270c4cabc80',
      p2s_run_id: 'a8e0e5150e794fb5', p2s_run_sha256: 'deadbeef',
      source_support_rows_sha256: 'abc', source_support_parquet_sha256: 'def',
      arm_key: INC, sibling_arm_key: DEC, seed: 42,
      model: { upstream_commit: '2c2e30959ffa', upstream_version: '0.0.1', random_state: 42 },
      input_hashes: { ntc_h5ad_raw_sha256: '2edc6d31' },
      bound_direct_release: {
        release_run_id: '8faa69d5c54c4895', bundle_run_id: 'bbc582a9c3096f9a',
        w10_verdict: 'ADMIT', w10_verifier_code_sha256: '943d32bd', scorer_view_sha256: '71d7c7d9',
      },
    },
    columns: Object.keys(OPPOSED_ROW),
    n_targets: 2,
    projection_rows_sha256: 'rows-hash',
    rows: [OPPOSED_ROW, SUPPORTIVE_ROW],
  }
}

describe('P2S secondary-support adapter — exact binding', () => {
  it('binds a target by target_id on the projection arm', () => {
    const p2s = loadP2sSecondarySupport(fixture())
    const v = p2s.supportForTarget('ENSG00000000419', INC)!
    expect(v).not.toBeNull()
    expect(v.armKey).toBe(INC)
    expect(v.direction).toBe('increase')
    expect(v.coefficient).toBe(-0.000562)
    expect(v.sign).toBe('opposed')
    expect(v.opposed).toBe(true)
    expect(v.robustness.lodoSignConcordance).toBe(1.0)
    expect(v.nRuns).toBe(7)
  })

  it('returns null for an unknown target and for an arm it does not speak for', () => {
    const p2s = loadP2sSecondarySupport(fixture())
    expect(p2s.supportForTarget('ENSG_NOPE', INC)).toBeNull()
    expect(p2s.supportForTarget('ENSG00000000419', 'direct|th1_like|increase|Stim48hr')).toBeNull()
    expect(p2s.bindsArm(INC)).toBe(true)
    expect(p2s.bindsArm(DEC)).toBe(true)
    expect(p2s.bindsArm('direct|th1_like|increase|Stim48hr')).toBe(false)
  })
})

describe('P2S secondary-support adapter — opposite-direction symmetry', () => {
  it('the decrease view is the EXACT negation of the increase view', () => {
    const p2s = loadP2sSecondarySupport(fixture())
    for (const t of ['ENSG00000000419', 'ENSG00000000457']) {
      const inc = p2s.supportForTarget(t, INC)!
      const dec = p2s.supportForTarget(t, DEC)!
      expect(dec.direction).toBe('decrease')
      expect(dec.coefficient).toBe(-(inc.coefficient as number))          // negated
      expect(dec.absCoefficient).toBe(inc.absCoefficient)                 // magnitude invariant
      expect(dec.opposed).toBe(!inc.opposed)                             // flipped
      expect(dec.sign).toBe(inc.sign === 'supportive' ? 'opposed' : 'supportive')
      expect(dec.robustness).toEqual(inc.robustness)                     // concordances invariant
      expect(dec.nRuns).toBe(inc.nRuns)
    }
  })

  it('a zero coefficient negates to zero and stays unopposed both directions', () => {
    const f = fixture()
    f.rows = [{ ...OPPOSED_ROW, target_id: 'Z', primary_coefficient: 0, primary_abs_coefficient: 0,
      primary_sign: 'zero', opposed: false }]
    const p2s = loadP2sSecondarySupport(f)
    const inc = p2s.supportForTarget('Z', INC)!
    const dec = p2s.supportForTarget('Z', DEC)!
    expect(inc.coefficient).toBe(0)
    expect(dec.coefficient).toBe(0)
    expect(dec.sign).toBe('zero')
    expect(dec.opposed).toBe(false)
  })
})

describe('P2S secondary-support adapter — REFUSES unsafe use', () => {
  it('refuses a non-secondary lane', () => {
    const f = fixture(); f.lane_role = 'primary'
    expect(() => loadP2sSecondarySupport(f)).toThrow(P2sSecondarySupportError)
  })
  it('refuses a projection that claims to be part of the admitted Direct result', () => {
    const f = fixture(); f.semantics.is_part_of_admitted_direct_result = true
    expect(() => loadP2sSecondarySupport(f)).toThrow(/admitted Direct result/)
  })
  it('refuses a projection that admits entering primary rank/order', () => {
    const f = fixture(); f.semantics.p2s_fields_enter_primary_rank_or_order = true
    expect(() => loadP2sSecondarySupport(f)).toThrow(/rank/)
  })
  it('refuses a forbidden column (rank / p-value / combined / …)', () => {
    for (const bad of ['rank', 'p_value', 'combined_score', 'fdr', 'weighted_objective']) {
      const f = fixture(); f.columns = [...f.columns, bad]
      expect(() => loadP2sSecondarySupport(f)).toThrow(/forbidden column/)
    }
  })
  it('refuses a forbidden field smuggled into a row', () => {
    const f = fixture()
    ;(f.rows[0] as unknown as Record<string, unknown>).rank = 1
    expect(() => loadP2sSecondarySupport(f)).toThrow(/forbidden field/)
  })
  it('refuses a projection with no admitted-receipt binding', () => {
    const f = fixture(); f.binding.receipt_sha256 = ''
    expect(() => loadP2sSecondarySupport(f)).toThrow(/admitted receipt/)
  })
})

describe('P2S secondary-support adapter — Methods drawer', () => {
  it('exposes the secondary declaration + guardrails, no rank/score surface', () => {
    const p2s = loadP2sSecondarySupport(fixture())
    const md = p2s.methodsDrawer()
    expect(md.laneRole).toBe('secondary_non_gating')
    expect(md.isSecondaryNonGating).toBe(true)
    expect(md.boundDirectRelease.w10_verdict).toBe('ADMIT')
    expect(md.provenance.receiptSha256).toMatch(/^2d96a8a6/)
    expect(md.guardrails.some((g) => /never enters Direct.*rank/.test(g))).toBe(true)
    // the drawer object exposes no rank/score/p field
    expect(JSON.stringify(md)).not.toMatch(/"(rank|score|p_?value|fdr|combined)"/i)
  })
})
