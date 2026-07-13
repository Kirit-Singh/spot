import { describe, expect, it } from 'vitest'

import type { CompactStage2Projection } from '../domain/compactStage2Projection'
import { canonicalJson, sha256Hex } from '../stage1/canonical'
import { loadAdmittedP2sSecondary } from './p2sAdmission'
import type { P2sProjection, P2sProjectionVerification, P2sSecondaryReleaseMetadata } from './types'

const INC = 'direct|treg_like|increase|Stim48hr'
const DEC = 'direct|treg_like|decrease|Stim48hr'
const BUNDLE_ID = 'bbc582a9c3096f9a'
const H = 'a'.repeat(64)
const ATTACKS = ['abs_broken', 'admits_entering_rank', 'arm_key_non_canonical',
  'binding_aggregate_score_key', 'claims_part_of_direct', 'concordance_for_zero_sign',
  'denominators_broken', 'disguised_rank_key_overall_rank', 'extra_binding_key_combined_score',
  'join_key_rank', 'lane_not_secondary', 'machine_path_in_binding', 'machine_path_mnt',
  'n_targets_wrong', 'non_finite_coef', 'opposed_flipped', 'row_causal_key',
  'row_combined_key', 'row_empirical_p_value_key', 'row_false_discovery_rate_key',
  'row_fdr_key', 'row_padj_key', 'row_qval_key', 'row_validation_key', 'row_weighted_key',
  'rows_unsorted', 'sibling_not_exact_negation', 'sibling_same_direction',
  'sign_not_sign_of_coef', 'tampered_row_hash', 'tampered_w10_verdict',
  'target_id_not_unique', 'wrong_bundle']
const COVERAGE = Object.fromEntries(['aggregate', 'aggregate_score', 'causal', 'combined',
  'combined_score', 'discovery', 'empirical_p_value', 'empirical_q_value', 'false_discovery',
  'false_discovery_rate', 'fdr', 'gating', 'nominal_p', 'overall_rank', 'p', 'p_adj',
  'p_value', 'padj', 'padjusted', 'pareto', 'pval', 'pvalue', 'q', 'q_adj', 'q_value',
  'qadj', 'qval', 'qvalue', 'rank', 'score', 'significance', 'validate', 'validation',
  'weighted', 'weighted_score'].map((token) => [token, true]))

function projection(): P2sProjection {
  const rows = [{
    target_id: 'ENSG00000000419', primary_coefficient: -0.1, primary_abs_coefficient: 0.1,
    primary_sign: 'opposed' as const, opposed: true, primary_available: true, n_runs: 7,
    sens_log_fc_sign_concordance: 0, n_log_fc: 1, sens_pca_off_sign_concordance: 0,
    n_pca_off: 1, lodo_sign_concordance: 1, n_lodo: 4,
  }]
  return {
    schema_version: 'spot.stage02.p2s_ui_support_projection.v1', emitted_utc: '2026-07-13T18:00:00Z',
    lane_role: 'secondary_non_gating',
    semantics: { is_part_of_admitted_direct_result: false,
      p2s_fields_enter_primary_rank_or_order: false, no_rank_no_pvalue_no_combined_score: true,
      row_order: 'target_id ascending (a neutral key; NOT a rank)',
      coefficients_are: 'conditional reconstruction weights', sibling_arm_is_exact_negation: true },
    adapter: { join_key: 'target_id', arm_key: INC, sibling_arm_key: DEC, program_id: 'treg_like',
      desired_change: 'increase', condition: 'Stim48hr',
      display_fields: ['primary_coefficient', 'primary_sign', 'opposed', 'primary_available'],
      robustness_fields: ['sens_log_fc_sign_concordance', 'n_log_fc',
        'sens_pca_off_sign_concordance', 'n_pca_off', 'lodo_sign_concordance', 'n_lodo', 'n_runs'],
      forbidden_ui_uses: ['ranking', 'gating'] },
    binding: { receipt_sha256: H, p2s_run_id: H.slice(0, 16), p2s_run_sha256: H,
      source_support_rows_sha256: H, source_support_parquet_sha256: H,
      arm_key: INC, sibling_arm_key: DEC, seed: 42,
      model: { upstream_commit: '2c2e30959ffafadecc6af5d4d7b5bde868ab5313',
        upstream_version: '0.0.1', random_state: 42, l1_ratio_grid: [0.1], n_pcs_primary: 50,
        positive: false }, input_hashes: { de_main_raw_sha256: H, ntc_h5ad_raw_sha256: H,
        stage1_scores_canonical_sha256: H, stage1_scores_raw_sha256: H },
      bound_direct_release: { release_run_id: '8faa69d5c54c4895', bundle_run_id: BUNDLE_ID,
        w10_verdict: 'ADMIT', w10_verifier_id: 'spot.stage02.direct.arm_bundle.verifier.v1',
        w10_verifier_code_sha256: H, scorer_view_sha256: H } },
    columns: Object.keys(rows[0]), n_targets: 1, projection_rows_sha256: H, rows,
  }
}

function direct(n = 1): CompactStage2Projection {
  const value = {
    arms: {
      [INC]: { lane: 'direct', source_bundle: `direct/${BUNDLE_ID}`, n_evaluable: n,
        rows: [{ target_id: 'ENSG00000000419' }] },
      [DEC]: { lane: 'direct', source_bundle: `direct/${BUNDLE_ID}`, n_evaluable: n,
        rows: [{ target_id: 'ENSG00000000419' }] },
    },
    bindings: {
      native_bundles: { [`direct/${BUNDLE_ID}`]: { lane: 'direct' } },
    },
  }
  return value as unknown as CompactStage2Projection
}

async function release() {
  const proj = projection()
  const projectionText = JSON.stringify(proj)
  const receiptBase = { schema_version: 'spot.stage02.p2s_ui_projection_verification.v3',
    verifies: 'P2S_UI_SUPPORT_PROJECTION.json', generator: 'emit_projection_v2.py',
    verifier: 'verify_projection_v3.py', verifier_is_independent_of_generator: true,
    projection_raw_file_sha256: await sha256Hex(projectionText),
    projection_canonical_rows_sha256: H, clean_projection_admitted: true,
    clean_projection_failures: [], no_machine_local_path_proven: true,
    projection_identical_to_v2: true, firewall_token_coverage_complete: true,
    firewall_false_positives_on_legit_keys: [], firewall_token_coverage: COVERAGE,
    supersedes: 'p2s-ui-seam-handoff-v2/P2S_UI_PROJECTION_VERIFICATION.json',
    bound_direct_bundle_run_id: BUNDLE_ID, w10_verdict: 'ADMIT',
    w10_verifier_code_sha256: H,
    mutation_tests: ATTACKS.map((attack) => ({ attack, rejected: true as const })),
    n_mutations: ATTACKS.length, all_mutations_fail_closed: true,
    emitted_utc: '2026-07-13T18:10:00Z' }
  const receipt = { ...receiptBase,
    receipt_sha256: await sha256Hex(canonicalJson(receiptBase)) } as P2sProjectionVerification
  const verificationText = JSON.stringify(receipt)
  const meta: P2sSecondaryReleaseMetadata = {
    schema_version: 'spot.ui_p2s_secondary_release.v1', projection_path: 'stage02/p2s.json',
    projection_raw_sha256: await sha256Hex(projectionText),
    projection_canonical_sha256: await sha256Hex(canonicalJson(proj)), projection_rows_sha256: H,
    verification_path: 'stage02/p2s.verification.json',
    verification_raw_sha256: await sha256Hex(verificationText),
    verification_canonical_sha256: await sha256Hex(canonicalJson(receipt)),
    verification_self_sha256: receipt.receipt_sha256, receipt_sha256: H,
    p2s_run_sha256: H, arm_key: INC, sibling_arm_key: DEC,
    source_bundle: `direct/${BUNDLE_ID}`,
  }
  const files = new Map([['results/stage02/p2s.json', projectionText],
    ['results/stage02/p2s.verification.json', verificationText]])
  return { meta, proj, receipt, files, fetchText: async (path: string) => {
    const value = files.get(path); if (value === undefined) throw new Error('404'); return value
  } }
}

describe('content-addressed P2S secondary admission', () => {
  it('binds exact projection/receipt bytes to the exact Direct bundle and arms', async () => {
    const r = await release()
    const admitted = await loadAdmittedP2sSecondary(r.meta, r.fetchText, direct())
    expect(admitted.support.supportForTarget('ENSG00000000419', INC)?.coefficient).toBe(-0.1)
    expect(admitted.support.supportForTarget('ENSG00000000419', DEC)?.coefficient).toBe(0.1)
  })

  it('rejects raw/canonical/self-hash drift', async () => {
    const raw = await release(); raw.files.set('results/stage02/p2s.json', JSON.stringify({ ...raw.proj, emitted_utc: 'changed' }))
    await expect(loadAdmittedP2sSecondary(raw.meta, raw.fetchText, direct())).rejects.toThrow(/raw hash/)

    const self = await release(); self.meta.verification_self_sha256 = '0'.repeat(64)
    await expect(loadAdmittedP2sSecondary(self.meta, self.fetchText, direct())).rejects.toThrow(/self hash/)
  })

  it('rejects a missing/wrong Direct bundle, arm, or target count', async () => {
    const wrongBundle = await release(); wrongBundle.meta.source_bundle = 'direct/0000000000000000'
    await expect(loadAdmittedP2sSecondary(wrongBundle.meta, wrongBundle.fetchText, direct())).rejects.toThrow(/source bundle/)

    const missing = await release(); const d = direct(); delete (d.arms as Record<string, unknown>)[DEC]
    await expect(loadAdmittedP2sSecondary(missing.meta, missing.fetchText, d)).rejects.toThrow(/absent/)

    const count = await release()
    await expect(loadAdmittedP2sSecondary(count.meta, count.fetchText, direct(2))).rejects.toThrow(/target count/)
  })

  it('requires the complete v3 field-coverage attestation and sanitized supersedes path', async () => {
    const incomplete = await release()
    const changed = structuredClone(incomplete.receipt) as unknown as Record<string, unknown>
    const coverage = { ...(changed.firewall_token_coverage as Record<string, boolean>) }
    coverage.qval = false
    changed.firewall_token_coverage = coverage
    const body = { ...changed }; delete body.receipt_sha256
    changed.receipt_sha256 = await sha256Hex(canonicalJson(body))
    const text = JSON.stringify(changed)
    incomplete.files.set('results/stage02/p2s.verification.json', text)
    incomplete.meta.verification_raw_sha256 = await sha256Hex(text)
    incomplete.meta.verification_canonical_sha256 = await sha256Hex(canonicalJson(changed))
    incomplete.meta.verification_self_sha256 = changed.receipt_sha256 as string
    await expect(loadAdmittedP2sSecondary(incomplete.meta, incomplete.fetchText, direct()))
      .rejects.toThrow(/coverage is incomplete/)

    const path = await release()
    const pathReceipt = structuredClone(path.receipt) as unknown as Record<string, unknown>
    pathReceipt.supersedes = '/home/user/private/receipt.json'
    const pathBody = { ...pathReceipt }; delete pathBody.receipt_sha256
    pathReceipt.receipt_sha256 = await sha256Hex(canonicalJson(pathBody))
    const pathText = JSON.stringify(pathReceipt)
    path.files.set('results/stage02/p2s.verification.json', pathText)
    path.meta.verification_raw_sha256 = await sha256Hex(pathText)
    path.meta.verification_canonical_sha256 = await sha256Hex(canonicalJson(pathReceipt))
    path.meta.verification_self_sha256 = pathReceipt.receipt_sha256 as string
    await expect(loadAdmittedP2sSecondary(path.meta, path.fetchText, direct()))
      .rejects.toThrow(/supersedes path/)
  })
})
