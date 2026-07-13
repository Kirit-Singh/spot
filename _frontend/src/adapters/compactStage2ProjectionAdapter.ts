// Strict parser for W3's selection-independent compact Stage-2 projection. It accepts the exact
// producer contract only, binds the producer self hash, validates every capped-prefix count,
// and rejects unknown/combined/p/q fields. It never derives a ranking or fills a missing value.

import type {
  CompactDisplayVerificationReceipt,
  CompactLane,
  CompactPathwayArm,
  CompactPathwayRow,
  CompactSourceBundleBinding,
  CompactStage2Arm,
  CompactStage2Projection,
  CompactTargetArm,
  CompactTargetRow,
} from '../domain/compactStage2Projection';
import {
  COMPACT_STAGE2_METHOD,
  COMPACT_STAGE2_SCHEMA,
  COMPACT_STAGE2_VERIFIER,
} from '../domain/compactStage2Projection';
import { fail } from './errors';
import { arr, bool, enumOf, isObject, num, str } from './guards';

const HEX64 = /^[0-9a-f]{64}$/;
const LANES = ['direct', 'temporal', 'pathway'] as const;
const TARGET_KEYS = ['arm_key', 'cap', 'context', 'is_a_prefix', 'lane', 'n_emitted',
  'n_evaluable', 'n_ranked', 'n_rows_total', 'rows', 'source_bundle'] as const;
const PATHWAY_KEYS = ['arm_key', 'cap', 'context', 'coverage_disposition_counts', 'is_a_prefix',
  'lane', 'n_emitted', 'n_sets_total', 'n_with_coverage', 'row_order', 'rows', 'rows_are_ranked',
  'source_bundle', 'why_not_ranked'] as const;
const TOP_KEYS = ['analysis_mode', 'arms', 'authoritative_artifacts_are_the_native_ones', 'bindings',
  'cap_policy', 'combined_objective', 'cross_arm_score_or_order', 'method_version', 'n_arms',
  'projection_sha256', 'schema_version', 'selection_id', 'selection_independent'] as const;
const CAP_KEYS = ['cap_policy_id', 'chosen_before_inspecting_any_value',
  'combined_or_pair_ranking_emitted', 'configurable_from_the_ui', 'configurable_only_by',
  'cross_arm_order_emitted', 'method_version', 'caps', 'pathway_rule', 'target_rule'] as const;

function exactKeys(v: Record<string, unknown>, expected: readonly string[], path: string): void {
  const got = Object.keys(v).sort();
  const want = [...expected].sort();
  if (got.length !== want.length || got.some((k, i) => k !== want[i])) {
    fail('malformed', `${path} fields [${got.join(', ')}] do not equal [${want.join(', ')}]`);
  }
}
function hex64(v: unknown, path: string): string {
  const s = str(v, path);
  if (!HEX64.test(s)) fail('missing_hash', `${path} must be a 64-hex sha256`);
  return s;
}
function nonempty(v: unknown, path: string): string {
  const s = str(v, path);
  if (!s.trim()) fail('malformed', `${path} is empty`);
  return s;
}
function uint(v: unknown, path: string): number {
  const n = num(v, path);
  if (!Number.isSafeInteger(n) || n < 0) fail('malformed', `${path} must be a non-negative integer`);
  return n;
}
function nullableNum(v: unknown, path: string): number | null {
  if (v === null) return null;
  return num(v, path);
}
function nullableStr(v: unknown, path: string): string | null {
  if (v === null) return null;
  return str(v, path);
}

function targetRow(v: unknown, path: string): CompactTargetRow {
  if (!isObject(v)) fail('malformed', `${path} must be an object`);
  exactKeys(v, ['arm_value', 'rank', 'target_id'], path);
  const rank = uint(v.rank, `${path}.rank`);
  if (rank < 1) fail('malformed', `${path}.rank must be >= 1`);
  return { target_id: nonempty(v.target_id, `${path}.target_id`), rank, arm_value: nullableNum(v.arm_value, `${path}.arm_value`) };
}

function pathwayRow(v: unknown, path: string): CompactPathwayRow {
  if (!isObject(v)) fail('malformed', `${path} must be an object`);
  exactKeys(v, ['enrichment_value', 'global_coverage_disposition', 'n_leading_edge', 'peak_rank',
    'set_id', 'target_source_coverage'], path);
  const nLeading = v.n_leading_edge === null ? null : uint(v.n_leading_edge, `${path}.n_leading_edge`);
  const peak = v.peak_rank === null ? null : uint(v.peak_rank, `${path}.peak_rank`);
  return {
    set_id: nonempty(v.set_id, `${path}.set_id`),
    enrichment_value: nullableNum(v.enrichment_value, `${path}.enrichment_value`),
    target_source_coverage: nullableNum(v.target_source_coverage, `${path}.target_source_coverage`),
    global_coverage_disposition: nullableStr(v.global_coverage_disposition, `${path}.global_coverage_disposition`),
    n_leading_edge: nLeading,
    peak_rank: peak,
  };
}

function context(v: unknown, lane: CompactLane, path: string): CompactTargetArm['context'] | CompactPathwayArm['context'] {
  if (!isObject(v)) fail('malformed', `${path} must be an object`);
  if (lane === 'direct') {
    exactKeys(v, ['condition'], path);
    return { condition: nonempty(v.condition, `${path}.condition`) };
  }
  if (lane === 'temporal') {
    exactKeys(v, ['from_condition', 'to_condition'], path);
    const from = nonempty(v.from_condition, `${path}.from_condition`);
    const to = nonempty(v.to_condition, `${path}.to_condition`);
    if (from === to) fail('malformed', `${path} temporal endpoints must differ`);
    return { from_condition: from, to_condition: to };
  }
  exactKeys(v, ['condition', 'gene_set_source'], path);
  return {
    condition: nonempty(v.condition, `${path}.condition`),
    gene_set_source: nonempty(v.gene_set_source, `${path}.gene_set_source`),
  };
}

function validateArmKey(armKey: string, lane: CompactLane, ctx: CompactTargetArm['context'] | CompactPathwayArm['context'], path: string): void {
  const parts = armKey.split('|');
  const expectedLength = lane === 'direct' ? 4 : 5;
  if (parts.length !== expectedLength || parts[0] !== lane || !parts[1] || !['increase', 'decrease'].includes(parts[2])) {
    fail('arm_key_mismatch', `${path} is not a canonical ${lane} reusable-arm key`);
  }
  if (lane === 'direct' && (!('condition' in ctx) || parts[3] !== ctx.condition)) {
    fail('arm_key_mismatch', `${path} condition disagrees with context`);
  }
  if (lane === 'temporal' && (!('from_condition' in ctx) || parts[3] !== ctx.from_condition || parts[4] !== ctx.to_condition)) {
    fail('arm_key_mismatch', `${path} endpoints disagree with context`);
  }
  if (lane === 'pathway' && (!('condition' in ctx) || !('gene_set_source' in ctx) || parts[3] !== ctx.condition || parts[4] !== ctx.gene_set_source)) {
    fail('arm_key_mismatch', `${path} pathway context disagrees with key`);
  }
}

function targetArm(v: Record<string, unknown>, lane: 'direct' | 'temporal', mapKey: string, path: string): CompactTargetArm {
  exactKeys(v, TARGET_KEYS, path);
  const armKey = nonempty(v.arm_key, `${path}.arm_key`);
  if (armKey !== mapKey) fail('arm_key_mismatch', `${path}.arm_key differs from its map key`);
  const ctx = context(v.context, lane, `${path}.context`) as CompactTargetArm['context'];
  validateArmKey(armKey, lane, ctx, `${path}.arm_key`);
  const rows = arr(v.rows, `${path}.rows`).map((r, i) => targetRow(r, `${path}.rows[${i}]`));
  const n_rows_total = uint(v.n_rows_total, `${path}.n_rows_total`);
  const n_evaluable = uint(v.n_evaluable, `${path}.n_evaluable`);
  const n_ranked = uint(v.n_ranked, `${path}.n_ranked`);
  const n_emitted = uint(v.n_emitted, `${path}.n_emitted`);
  const cap = uint(v.cap, `${path}.cap`);
  const is_a_prefix = bool(v.is_a_prefix, `${path}.is_a_prefix`);
  if (cap !== 100 || rows.length !== n_emitted || n_emitted !== Math.min(n_ranked, cap) ||
      n_ranked > n_evaluable || n_evaluable > n_rows_total) {
    fail('malformed', `${path} target prefix counts/cap are inconsistent`);
  }
  if (is_a_prefix !== (n_emitted < n_ranked)) fail('malformed', `${path}.is_a_prefix disagrees with counts`);
  const ranks = rows.map((r) => r.rank);
  if (new Set(ranks).size !== ranks.length || ranks.some((r, i) => i > 0 && r <= ranks[i - 1])) {
    fail('malformed', `${path}.rows are not in unique ascending native rank order`);
  }
  return { lane, arm_key: armKey, context: ctx, source_bundle: nonempty(v.source_bundle, `${path}.source_bundle`),
    n_rows_total, n_evaluable, n_ranked, n_emitted, cap, is_a_prefix, rows };
}

function pathwayArm(v: Record<string, unknown>, mapKey: string, path: string): CompactPathwayArm {
  exactKeys(v, PATHWAY_KEYS, path);
  const armKey = nonempty(v.arm_key, `${path}.arm_key`);
  if (armKey !== mapKey) fail('arm_key_mismatch', `${path}.arm_key differs from its map key`);
  const ctx = context(v.context, 'pathway', `${path}.context`) as CompactPathwayArm['context'];
  validateArmKey(armKey, 'pathway', ctx, `${path}.arm_key`);
  const rows = arr(v.rows, `${path}.rows`).map((r, i) => pathwayRow(r, `${path}.rows[${i}]`));
  const n_sets_total = uint(v.n_sets_total, `${path}.n_sets_total`);
  const n_with_coverage = uint(v.n_with_coverage, `${path}.n_with_coverage`);
  const n_emitted = uint(v.n_emitted, `${path}.n_emitted`);
  const cap = uint(v.cap, `${path}.cap`);
  const is_a_prefix = bool(v.is_a_prefix, `${path}.is_a_prefix`);
  if (cap !== 50 || rows.length !== n_emitted || n_emitted !== Math.min(n_sets_total, cap) ||
      n_with_coverage > n_sets_total) {
    fail('malformed', `${path} pathway prefix counts/cap are inconsistent`);
  }
  if (is_a_prefix !== (n_emitted < n_sets_total)) fail('malformed', `${path}.is_a_prefix disagrees with counts`);
  if (str(v.row_order, `${path}.row_order`) !== 'native_producer_emission_order' || bool(v.rows_are_ranked, `${path}.rows_are_ranked`) !== false) {
    fail('malformed', `${path} must preserve unranked native producer emission order`);
  }
  if (!isObject(v.coverage_disposition_counts)) fail('malformed', `${path}.coverage_disposition_counts must be an object`);
  const counts: Record<string, number> = {};
  for (const [k, value] of Object.entries(v.coverage_disposition_counts)) counts[k] = uint(value, `${path}.coverage_disposition_counts.${k}`);
  if (Object.values(counts).reduce((a, b) => a + b, 0) !== n_sets_total) fail('malformed', `${path} coverage counts do not cover every set`);
  return { lane: 'pathway', arm_key: armKey, context: ctx, source_bundle: nonempty(v.source_bundle, `${path}.source_bundle`),
    n_sets_total, n_with_coverage, coverage_disposition_counts: counts, n_emitted, cap, is_a_prefix,
    row_order: 'native_producer_emission_order', rows_are_ranked: false,
    why_not_ranked: nonempty(v.why_not_ranked, `${path}.why_not_ranked`), rows };
}

function sourceBindings(v: unknown): { native_bundles: Record<string, CompactSourceBundleBinding> } {
  if (!isObject(v)) fail('malformed', 'bindings must be an object');
  exactKeys(v, ['native_bundles'], 'bindings');
  if (!isObject(v.native_bundles)) fail('malformed', 'bindings.native_bundles must be an object');
  const native_bundles: Record<string, CompactSourceBundleBinding> = {};
  for (const [rel, raw] of Object.entries(v.native_bundles)) {
    if (!rel || rel.startsWith('/') || rel.includes('..')) fail('malformed', `native bundle path ${rel} is unsafe`);
    if (!isObject(raw)) fail('malformed', `bindings.native_bundles.${rel} must be an object`);
    exactKeys(raw, ['bundle_id', 'files', 'lane'], `bindings.native_bundles.${rel}`);
    const lane = enumOf(raw.lane, LANES, `bindings.native_bundles.${rel}.lane`);
    if (!isObject(raw.files)) fail('malformed', `bindings.native_bundles.${rel}.files must be an object`);
    const files: Record<string, { raw_sha256: string }> = {};
    for (const [name, entry] of Object.entries(raw.files)) {
      if (!name || name.startsWith('/') || name.includes('..')) fail('malformed', `native source file ${name} is unsafe`);
      if (!isObject(entry)) fail('malformed', `native source ${rel}/${name} must be an object`);
      exactKeys(entry, ['raw_sha256'], `bindings.native_bundles.${rel}.files.${name}`);
      files[name] = { raw_sha256: hex64(entry.raw_sha256, `bindings.native_bundles.${rel}.files.${name}.raw_sha256`) };
    }
    if (Object.keys(files).length === 0) fail('malformed', `bindings.native_bundles.${rel}.files is empty`);
    native_bundles[rel] = { lane, bundle_id: nonempty(raw.bundle_id, `bindings.native_bundles.${rel}.bundle_id`), files };
  }
  return { native_bundles };
}

function validateCapPolicy(v: unknown): void {
  if (!isObject(v)) fail('malformed', 'cap_policy must be an object');
  exactKeys(v, CAP_KEYS, 'cap_policy');
  if (str(v.cap_policy_id, 'cap_policy.cap_policy_id') !== 'spot.stage02.display_projection.first_n_native_order.v1' ||
      str(v.method_version, 'cap_policy.method_version') !== COMPACT_STAGE2_METHOD) fail('malformed', 'cap policy identity mismatch');
  if (!isObject(v.caps)) fail('malformed', 'cap_policy.caps must be an object');
  exactKeys(v.caps, ['direct', 'pathway', 'temporal'], 'cap_policy.caps');
  if (uint(v.caps.direct, 'cap_policy.caps.direct') !== 100 || uint(v.caps.temporal, 'cap_policy.caps.temporal') !== 100 || uint(v.caps.pathway, 'cap_policy.caps.pathway') !== 50) fail('malformed', 'cap policy values changed');
  if (bool(v.chosen_before_inspecting_any_value, 'cap_policy.chosen_before_inspecting_any_value') !== true ||
      bool(v.configurable_from_the_ui, 'cap_policy.configurable_from_the_ui') !== false ||
      bool(v.cross_arm_order_emitted, 'cap_policy.cross_arm_order_emitted') !== false ||
      bool(v.combined_or_pair_ranking_emitted, 'cap_policy.combined_or_pair_ranking_emitted') !== false) fail('malformed', 'cap policy admits a mutable/combined order');
  nonempty(v.configurable_only_by, 'cap_policy.configurable_only_by');
  nonempty(v.target_rule, 'cap_policy.target_rule');
  nonempty(v.pathway_rule, 'cap_policy.pathway_rule');
}

/** Parse the exact compact projection and bind its producer self-hash to release metadata. */
export async function parseCompactStage2Projection(raw: unknown, expectedSelfHash?: string): Promise<CompactStage2Projection> {
  if (!isObject(raw)) fail('malformed', 'compact Stage-2 projection must be an object');
  exactKeys(raw, TOP_KEYS, 'projection');
  if (str(raw.schema_version, 'schema_version') !== COMPACT_STAGE2_SCHEMA || str(raw.method_version, 'method_version') !== COMPACT_STAGE2_METHOD) fail('unknown_schema_version', 'compact projection schema/method mismatch');
  if (raw.selection_independent !== true || raw.selection_id !== null || raw.analysis_mode !== null) fail('malformed', 'compact projection must be selection-independent');
  if (raw.combined_objective !== null || raw.cross_arm_score_or_order !== null) fail('stale_combined_field', 'compact projection carries a combined/cross-arm value');
  if (raw.authoritative_artifacts_are_the_native_ones !== true) fail('malformed', 'native artifacts must remain authoritative');
  validateCapPolicy(raw.cap_policy);
  const bindings = sourceBindings(raw.bindings);
  if (!isObject(raw.arms)) fail('malformed', 'arms must be an object');
  const arms: Record<string, CompactStage2Arm> = {};
  for (const [key, value] of Object.entries(raw.arms)) {
    if (!isObject(value)) fail('malformed', `arms.${key} must be an object`);
    const lane = enumOf(value.lane, LANES, `arms.${key}.lane`);
    const arm = lane === 'pathway' ? pathwayArm(value, key, `arms.${key}`) : targetArm(value, lane, key, `arms.${key}`);
    const source = bindings.native_bundles[arm.source_bundle];
    if (!source || source.lane !== lane) fail('content_hash_mismatch', `arms.${key}.source_bundle is absent or has the wrong lane`);
    arms[key] = arm;
  }
  const n_arms = uint(raw.n_arms, 'n_arms');
  if (Object.keys(arms).length !== n_arms) fail('malformed', 'n_arms does not match arms map');
  // The loader independently hashes the exact served bytes and its parsed canonical content. This
  // producer self-hash uses Python JSON number semantics (1.0 remains distinct from 1), which a browser
  // JSON.parse cannot reconstruct; bind it to the admitted metadata + generator≠verifier receipt rather
  // than pretending a lossy JavaScript reserialization is an independent reproduction.
  const declared = hex64(raw.projection_sha256, 'projection_sha256');
  if (expectedSelfHash && declared !== expectedSelfHash) fail('content_hash_mismatch', 'projection self hash does not match release metadata');
  return { schema_version: COMPACT_STAGE2_SCHEMA, method_version: COMPACT_STAGE2_METHOD,
    selection_independent: true, authoritative_artifacts_are_the_native_ones: true,
    projection_sha256: declared, n_arms, arms, bindings };
}

/** The exact projection identity a receipt must admit — n_arms alone is deliberately insufficient. */
export interface CompactReceiptExpectation {
  n_arms: number;
  projection_raw_sha256: string;
  projection_canonical_sha256: string;
  projection_self_sha256: string;
}

/**
 * Strictly admit the independent display-projection receipt after its bytes were hash-checked. Beyond the
 * verdict + exact-arm count, this enforces the W3 exact-SUBJECT binding: the receipt must name the EXACT
 * projection it verified (raw/canonical/self sha) plus the admitted per-lane native receipts + inventory.
 * A receipt that admits by arm count alone (no `subject`, or a `subject` binding different projection
 * bytes) is REFUSED — so the real-data loader fails closed until W3 emits receipts carrying this subject.
 */
export function parseCompactDisplayReceipt(raw: unknown, expected: CompactReceiptExpectation): CompactDisplayVerificationReceipt {
  if (!isObject(raw)) fail('malformed', 'display-projection verification receipt must be an object');
  exactKeys(raw, ['admitted_inputs', 'failures', 'generator_is_not_verifier', 'n_arms', 'n_failed',
    'rebuilt_from_admitted_native_bytes', 'subject', 'verdict', 'verifier_id'], 'display_receipt');
  if (str(raw.verifier_id, 'display_receipt.verifier_id') !== COMPACT_STAGE2_VERIFIER ||
      raw.generator_is_not_verifier !== true || raw.rebuilt_from_admitted_native_bytes !== true ||
      raw.verdict !== 'admit' || uint(raw.n_failed, 'display_receipt.n_failed') !== 0 ||
      uint(raw.n_arms, 'display_receipt.n_arms') !== expected.n_arms || arr(raw.failures, 'display_receipt.failures').length !== 0) {
    fail('verifier_not_admitted', 'independent display-projection receipt did not admit these exact arms');
  }
  // W3 exact-subject binding: the receipt must name the EXACT projection it verified, not just a count.
  // A matching n_arms on different projection bytes is refused here (closes the same-n_arms weakness).
  const subject = raw.subject;
  if (!isObject(subject)) fail('verifier_not_admitted', 'display receipt has no exact projection-subject binding (n_arms alone is not accepted)');
  exactKeys(subject, ['projection_canonical_sha256', 'projection_file', 'projection_raw_sha256',
    'projection_self_sha256_declared', 'projection_self_sha256_recomputed', 'self_hash_agrees'], 'display_receipt.subject');
  str(subject.projection_file, 'display_receipt.subject.projection_file');
  const declaredSelf = hex64(subject.projection_self_sha256_declared, 'display_receipt.subject.projection_self_sha256_declared');
  const recomputedSelf = hex64(subject.projection_self_sha256_recomputed, 'display_receipt.subject.projection_self_sha256_recomputed');
  if (hex64(subject.projection_raw_sha256, 'display_receipt.subject.projection_raw_sha256') !== expected.projection_raw_sha256 ||
      hex64(subject.projection_canonical_sha256, 'display_receipt.subject.projection_canonical_sha256') !== expected.projection_canonical_sha256 ||
      declaredSelf !== expected.projection_self_sha256) {
    fail('verifier_not_admitted', 'display receipt subject binds a different projection than the served bytes');
  }
  // the verifier must have independently CONFIRMED the projection's own self-hash (declared == recomputed)
  if (subject.self_hash_agrees !== true || declaredSelf !== recomputedSelf) {
    fail('verifier_not_admitted', 'display receipt subject self-hash does not agree with the verifier recompute');
  }
  // the per-lane external admission evidence the view was rebuilt from must be present + non-empty
  if (!isObject(raw.admitted_inputs) || Object.keys(raw.admitted_inputs).length === 0) {
    fail('verifier_not_admitted', 'display receipt carries no admitted native-input evidence');
  }
  return raw as unknown as CompactDisplayVerificationReceipt;
}
