import type { CompactStage2Projection } from '../domain/compactStage2Projection'
import type { StageMethodsManifest } from '../domain/methodsManifest'
import { canonicalJson, sha256Hex } from '../stage1/canonical'
import { loadP2sSecondarySupport, P2sSecondarySupport } from './p2sSecondarySupport'
import {
  P2S_RELEASE_SCHEMA,
  P2S_VERIFICATION_SCHEMA,
  type P2sProjection,
  type P2sProjectionVerification,
  type P2sSecondaryReleaseMetadata,
} from './types'

const RESULTS_ROOT = 'results/'
const HEX64 = /^[0-9a-f]{64}$/
const VERIFICATION_KEYS = ['all_mutations_fail_closed', 'bound_direct_bundle_run_id',
  'clean_projection_admitted', 'clean_projection_failures', 'emitted_utc', 'generator',
  'firewall_false_positives_on_legit_keys', 'firewall_token_coverage',
  'firewall_token_coverage_complete', 'mutation_tests', 'n_mutations',
  'no_machine_local_path_proven', 'projection_identical_to_v2',
  'projection_canonical_rows_sha256', 'projection_raw_file_sha256', 'receipt_sha256',
  'schema_version', 'supersedes', 'verifier', 'verifier_is_independent_of_generator', 'verifies',
  'w10_verdict', 'w10_verifier_code_sha256'] as const
const REQUIRED_COVERAGE_TOKENS = ['aggregate', 'aggregate_score', 'causal', 'combined',
  'combined_score', 'discovery', 'empirical_p_value', 'empirical_q_value', 'false_discovery',
  'false_discovery_rate', 'fdr', 'gating', 'nominal_p', 'overall_rank', 'p', 'p_adj',
  'p_value', 'padj', 'padjusted', 'pareto', 'pval', 'pvalue', 'q', 'q_adj', 'q_value',
  'qadj', 'qval', 'qvalue', 'rank', 'score', 'significance', 'validate', 'validation',
  'weighted', 'weighted_score'] as const
const SUPERSEDED_RECEIPT = 'p2s-ui-seam-handoff-v2/P2S_UI_PROJECTION_VERIFICATION.json'
const REQUIRED_MUTATIONS = ['abs_broken', 'admits_entering_rank', 'arm_key_non_canonical',
  'binding_aggregate_score_key', 'claims_part_of_direct', 'concordance_for_zero_sign',
  'denominators_broken', 'disguised_rank_key_overall_rank',
  'extra_binding_key_combined_score', 'join_key_rank', 'lane_not_secondary',
  'machine_path_in_binding', 'machine_path_mnt', 'n_targets_wrong', 'non_finite_coef',
  'opposed_flipped', 'row_causal_key', 'row_combined_key', 'row_empirical_p_value_key',
  'row_false_discovery_rate_key', 'row_fdr_key', 'row_padj_key', 'row_qval_key',
  'row_validation_key', 'row_weighted_key', 'rows_unsorted', 'sibling_not_exact_negation',
  'sibling_same_direction', 'sign_not_sign_of_coef', 'tampered_row_hash',
  'tampered_w10_verdict', 'target_id_not_unique', 'wrong_bundle'] as const

export class P2sAdmissionError extends Error {}

function refuse(cond: boolean, message: string): void {
  if (!cond) throw new P2sAdmissionError(message)
}

function object(v: unknown, path: string): Record<string, unknown> {
  refuse(!!v && typeof v === 'object' && !Array.isArray(v), `${path} must be an object`)
  return v as Record<string, unknown>
}

function exactKeys(v: Record<string, unknown>, expected: readonly string[], path: string): void {
  const got = Object.keys(v).sort()
  const want = [...expected].sort()
  refuse(got.length === want.length && got.every((key, i) => key === want[i]),
    `${path} fields do not equal the admitted schema`)
}

async function canonicalHash(v: unknown): Promise<string> {
  return sha256Hex(canonicalJson(v))
}

async function parseVerification(raw: unknown, meta: P2sSecondaryReleaseMetadata,
  projection: P2sProjection): Promise<P2sProjectionVerification> {
  const receipt = object(raw, 'P2S verification')
  exactKeys(receipt, VERIFICATION_KEYS, 'P2S verification')
  refuse(receipt.schema_version === P2S_VERIFICATION_SCHEMA,
    'P2S verification schema is not admitted')
  refuse(receipt.verifies === 'P2S_UI_SUPPORT_PROJECTION.json',
    'P2S verification names a different projection')
  refuse(receipt.generator === 'emit_projection_v2.py' && receipt.verifier === 'verify_projection_v3.py' &&
    receipt.verifier_is_independent_of_generator === true && receipt.clean_projection_admitted === true &&
    receipt.no_machine_local_path_proven === true && receipt.all_mutations_fail_closed === true &&
    Array.isArray(receipt.clean_projection_failures) && receipt.clean_projection_failures.length === 0,
  'P2S verification is not an independent all-pass receipt')
  refuse(receipt.projection_identical_to_v2 === true &&
    receipt.firewall_token_coverage_complete === true &&
    Array.isArray(receipt.firewall_false_positives_on_legit_keys) &&
    receipt.firewall_false_positives_on_legit_keys.length === 0,
  'P2S verification does not attest an unchanged projection and complete clean field coverage')
  const coverage = object(receipt.firewall_token_coverage, 'P2S verification.firewall_token_coverage')
  exactKeys(coverage, REQUIRED_COVERAGE_TOKENS,
    'P2S verification.firewall_token_coverage')
  refuse(REQUIRED_COVERAGE_TOKENS.every((token) => coverage[token] === true),
    'P2S verification field coverage is incomplete')
  refuse(receipt.supersedes === SUPERSEDED_RECEIPT &&
    !String(receipt.supersedes).startsWith('/') &&
    !String(receipt.supersedes).split('/').includes('..'),
  'P2S verification supersedes path is not the admitted relative v2 receipt')
  refuse(receipt.projection_raw_file_sha256 === meta.projection_raw_sha256 &&
    receipt.projection_canonical_rows_sha256 === meta.projection_rows_sha256 &&
    receipt.projection_canonical_rows_sha256 === projection.projection_rows_sha256,
  'P2S verification binds different projection bytes/rows')
  refuse(receipt.bound_direct_bundle_run_id === projection.binding.bound_direct_release.bundle_run_id &&
    receipt.w10_verdict === 'ADMIT' &&
    receipt.w10_verifier_code_sha256 === projection.binding.bound_direct_release.w10_verifier_code_sha256,
  'P2S verification binds different Direct/W10 evidence')
  refuse(Array.isArray(receipt.mutation_tests) && receipt.n_mutations === REQUIRED_MUTATIONS.length &&
    receipt.mutation_tests.length === REQUIRED_MUTATIONS.length,
  'P2S verification mutation battery count is incomplete')
  const attacks = (receipt.mutation_tests as unknown[]).map((item, i) => {
    const attack = object(item, `P2S verification.mutation_tests[${i}]`)
    exactKeys(attack, ['attack', 'rejected'], `P2S verification.mutation_tests[${i}]`)
    refuse(typeof attack.attack === 'string' && attack.rejected === true,
      `P2S verification.mutation_tests[${i}] did not fail closed`)
    return attack.attack as string
  }).sort()
  refuse(attacks.length === new Set(attacks).size &&
    attacks.every((name, i) => name === [...REQUIRED_MUTATIONS].sort()[i]),
  'P2S verification mutation battery names are incomplete or substituted')
  const declared = receipt.receipt_sha256
  refuse(typeof declared === 'string' && HEX64.test(declared),
    'P2S verification self hash is malformed')
  const body = { ...receipt }
  delete body.receipt_sha256
  refuse(await canonicalHash(body) === declared && declared === meta.verification_self_sha256,
    'P2S verification self hash does not re-derive')
  return receipt as unknown as P2sProjectionVerification
}

export interface AdmittedP2sSecondary {
  support: P2sSecondarySupport
  metadata: P2sSecondaryReleaseMetadata
  verification: P2sProjectionVerification
}

/**
 * Re-hash and admit the secondary projection, then bind it to the exact Direct native bundle already
 * present in the independently-admitted compact Stage-2 release. It returns null nowhere: callers
 * catch any refusal and omit the optional secondary lane while keeping Direct untouched.
 */
export async function loadAdmittedP2sSecondary(
  meta: P2sSecondaryReleaseMetadata,
  fetchText: (path: string) => Promise<string>,
  directProjection: CompactStage2Projection,
): Promise<AdmittedP2sSecondary> {
  refuse(meta.schema_version === P2S_RELEASE_SCHEMA, 'P2S release metadata schema is not admitted')
  const projectionText = await fetchText(`${RESULTS_ROOT}${meta.projection_path}`)
  refuse(await sha256Hex(projectionText) === meta.projection_raw_sha256,
    'P2S projection raw hash mismatch')
  const projectionRaw = JSON.parse(projectionText) as unknown
  refuse(await canonicalHash(projectionRaw) === meta.projection_canonical_sha256,
    'P2S projection canonical hash mismatch')
  const support = loadP2sSecondarySupport(projectionRaw)
  const projection = projectionRaw as P2sProjection
  // Numeric lexical forms (notably 1.0 and -0.0) are not preserved by JSON.parse in a browser,
  // so a browser cannot honestly reproduce the Python producer's row-canonicalization. The raw
  // projection hash fixes every byte; the independent receipt and projection both bind the same
  // producer-canonical row hash. Re-deriving a different JavaScript hash would be false assurance.
  refuse(projection.projection_rows_sha256 === meta.projection_rows_sha256,
  'P2S projection row hash mismatch')

  const verificationText = await fetchText(`${RESULTS_ROOT}${meta.verification_path}`)
  refuse(await sha256Hex(verificationText) === meta.verification_raw_sha256,
    'P2S verification raw hash mismatch')
  const verificationRaw = JSON.parse(verificationText) as unknown
  refuse(await canonicalHash(verificationRaw) === meta.verification_canonical_sha256,
    'P2S verification canonical hash mismatch')
  const verification = await parseVerification(verificationRaw, meta, projection)

  refuse(meta.receipt_sha256 === support.binding.receipt_sha256 &&
    meta.p2s_run_sha256 === support.binding.p2s_run_sha256 &&
    meta.arm_key === support.armKey && meta.sibling_arm_key === support.siblingArmKey,
  'P2S results/current binding disagrees with the admitted projection')
  const expectedBundle = `direct/${support.binding.bound_direct_release.bundle_run_id}`
  refuse(meta.source_bundle === expectedBundle,
    'P2S results/current source bundle disagrees with its Direct binding')
  const arm = directProjection.arms[support.armKey]
  const sibling = directProjection.arms[support.siblingArmKey]
  refuse(!!arm && arm.lane === 'direct' && !!sibling && sibling.lane === 'direct',
    'P2S arms are absent from the admitted Direct display release')
  if (!arm || arm.lane !== 'direct' || !sibling || sibling.lane !== 'direct') {
    throw new P2sAdmissionError('unreachable Direct arm narrowing failure')
  }
  refuse(arm.source_bundle === expectedBundle && sibling.source_bundle === expectedBundle &&
    directProjection.bindings.native_bundles[expectedBundle]?.lane === 'direct',
  'P2S source bundle is not the admitted Direct source for both arms')
  refuse(arm.n_evaluable === support.nTargets && sibling.n_evaluable === support.nTargets,
    'P2S target count does not match the bound Direct arms')
  refuse(arm.rows.every((row) => support.supportForTarget(row.target_id, support.armKey) !== null) &&
    sibling.rows.every((row) => support.supportForTarget(row.target_id, support.siblingArmKey) !== null),
  'P2S projection does not cover an emitted target in its bound Direct arms')
  return { support, metadata: structuredClone(meta), verification }
}

/** Add the admitted secondary lane to the existing Targets drawer; nothing is added to the canvas. */
export function withP2sSecondaryMethods(
  manifest: StageMethodsManifest,
  admitted: AdmittedP2sSecondary,
): StageMethodsManifest {
  const { support, metadata } = admitted
  const upstream = manifest.methods.upstream_model ?? ''
  const boundText = `Bound Perturb2State secondary projection: ${support.binding.p2s_run_id}; ` +
    `${support.armKey} with exact-negation sibling ${support.siblingArmKey}; conditional ` +
    `reconstruction weights only, secondary_non_gating; Direct bundle ` +
    `${support.binding.bound_direct_release.bundle_run_id}, W10 ${support.binding.bound_direct_release.w10_verdict}; ` +
    `training receipt ${support.binding.receipt_sha256}; rows ${metadata.projection_rows_sha256}; ` +
    `independent projection receipt ${metadata.verification_self_sha256}.`
  const source = {
    label: 'Perturb2State secondary reconstruction-support projection',
    record_id: `${support.binding.p2s_run_id} · ${support.armKey}`,
    url: `https://github.com/emdann/pert2state_model/tree/${support.binding.model.upstream_commit}`,
    license: 'MIT',
    retrieval_utc: null,
    raw_sha256: metadata.projection_raw_sha256,
    canonical_sha256: metadata.projection_canonical_sha256,
  }
  return {
    ...manifest,
    methods: {
      ...manifest.methods,
      upstream_model: [upstream, boundText].filter(Boolean).join(' '),
      limitations: [...manifest.methods.limitations,
        'Perturb2State coefficients are reconstruction support only; they do not alter Direct ordering or gates.'],
    },
    provenance: {
      ...manifest.provenance,
      artifact_paths: [...new Set([...manifest.provenance.artifact_paths,
        `results/${metadata.projection_path}`, `results/${metadata.verification_path}`])],
      source_chain: [...manifest.provenance.source_chain, source],
    },
  }
}
