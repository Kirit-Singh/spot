import type { CompactStage2ReleaseMetadata } from '../domain/compactStage2Projection';
import { canonicalJson, sha256Hex } from '../stage1/canonical';
import { directArmKey, pathwayArmKey, temporalArmKey } from '../repository/armKey';

export const CONDITIONS = ['Rest', 'Stim8hr', 'Stim48hr'] as const;
export const SOURCES = ['reactome', 'go_bp'] as const;
export const PROGRAMS = ['prog_alpha', 'prog_beta'] as const;
export const CHANGES = ['increase', 'decrease'] as const;

const sourceHash = (seed: string) => (seed.length % 16).toString(16).repeat(64);

export async function compactProjectionRaw() {
  const arms: Record<string, unknown> = {};
  const native_bundles: Record<string, unknown> = {};
  for (const condition of CONDITIONS) {
    const rel = `direct/${condition}`;
    native_bundles[rel] = { lane: 'direct', bundle_id: `D-${condition}`, files: { 'arms.parquet': { raw_sha256: sourceHash(`d${condition.length}`) } } };
    for (const program of PROGRAMS) for (const change of CHANGES) {
      const key = directArmKey(program, change, condition);
      arms[key] = {
        lane: 'direct', arm_key: key, context: { condition }, source_bundle: rel,
        n_rows_total: 3, n_evaluable: 2, n_ranked: 2, n_emitted: 2, cap: 100,
        is_a_prefix: false,
        rows: [{ target_id: `${program}-${change}-1`, rank: 1, arm_value: 0.5 }, { target_id: `${program}-${change}-2`, rank: 2, arm_value: null }],
      };
    }
  }
  for (const from of CONDITIONS) for (const to of CONDITIONS) if (from !== to) {
    const rel = `temporal/${from}__${to}`;
    native_bundles[rel] = { lane: 'temporal', bundle_id: `T-${from}-${to}`, files: { 'rankings/arms.json': { raw_sha256: sourceHash(`t${from.length}${to.length}`) } } };
    for (const program of PROGRAMS) for (const change of CHANGES) {
      const key = temporalArmKey(program, change, from, to);
      arms[key] = {
        lane: 'temporal', arm_key: key, context: { from_condition: from, to_condition: to }, source_bundle: rel,
        n_rows_total: 2, n_evaluable: 2, n_ranked: 2, n_emitted: 2, cap: 100,
        is_a_prefix: false,
        rows: [{ target_id: `${program}-${from}-${to}-1`, rank: 1, arm_value: -0.25 }, { target_id: `${program}-${from}-${to}-2`, rank: 2, arm_value: 0.1 }],
      };
    }
  }
  for (const condition of CONDITIONS) for (const source of SOURCES) {
    const rel = `pathway/${condition}__${source}`;
    native_bundles[rel] = { lane: 'pathway', bundle_id: `P-${condition}-${source}`, files: { 'arm_bundle.json': { raw_sha256: sourceHash(`p${condition.length}${source.length}`) } } };
    for (const program of PROGRAMS) for (const change of CHANGES) {
      const key = pathwayArmKey(program, change, condition, source);
      const rows = Array.from({ length: 50 }, (_, i) => i === 0
        ? { set_id: `${source}:1`, enrichment_value: 1.2, target_source_coverage: 0.7,
          global_coverage_disposition: 'covered', n_leading_edge: 3, peak_rank: 4 }
        : { set_id: `${source}:${i + 1}`, enrichment_value: null, target_source_coverage: null,
          global_coverage_disposition: null, n_leading_edge: null, peak_rank: null });
      arms[key] = {
        lane: 'pathway', arm_key: key, context: { condition, gene_set_source: source }, source_bundle: rel,
        n_sets_total: 51, n_with_coverage: 1, coverage_disposition_counts: { covered: 1, under_covered: 50 },
        n_emitted: 50, cap: 50, is_a_prefix: true, row_order: 'native_producer_emission_order', rows_are_ranked: false,
        why_not_ranked: 'the native pathway record carries no rank; enrichment_value is not a set ranking',
        rows,
      };
    }
  }
  const body = {
    schema_version: 'spot.stage02_display_projection.v1', method_version: 'spot.stage02.display_projection.v1',
    cap_policy: {
      cap_policy_id: 'spot.stage02.display_projection.first_n_native_order.v1',
      method_version: 'spot.stage02.display_projection.v1', caps: { direct: 100, temporal: 100, pathway: 50 },
      chosen_before_inspecting_any_value: true, configurable_from_the_ui: false,
      configurable_only_by: 'a method-version change', target_rule: 'first N native-ranked rows',
      pathway_rule: 'first N producer-emitted rows', cross_arm_order_emitted: false,
      combined_or_pair_ranking_emitted: false,
    },
    selection_independent: true, selection_id: null, analysis_mode: null,
    combined_objective: null, cross_arm_score_or_order: null,
    authoritative_artifacts_are_the_native_ones: true,
    bindings: { native_bundles }, n_arms: Object.keys(arms).length, arms,
  };
  return { ...body, projection_sha256: await sha256Hex(canonicalJson(body)) };
}

/** The pre-W3, n_arms-only receipt (NO exact-subject binding) — used by fail-closed tests: the strict
 *  adapter/loader must REFUSE it. Do not use on the binding path. */
export async function compactReceipt(n_arms: number) {
  return {
    verifier_id: 'spot.stage02.display_projection.independent_verifier.v1',
    generator_is_not_verifier: true, rebuilt_from_admitted_native_bytes: true,
    n_arms, n_failed: 0, failures: [], verdict: 'admit',
  };
}

/** The real W3 admitted receipt (verify_display_projection.py shape): the exact projection-subject
 *  binding (raw hash over the SERVED bytes `rawText`, canonical hash, declared+recomputed self-hash that
 *  agree) + non-empty per-lane admitted_inputs. `rawText` MUST be the exact bytes served for the subject
 *  raw hash to match — pass the same text used as projection_text. Use on the binding path. */
export async function compactReceiptAdmitted(
  projection: { n_arms: number; projection_sha256: string },
  rawText?: string,
) {
  const raw = rawText ?? JSON.stringify(projection);
  return {
    ...(await compactReceipt(projection.n_arms)),
    subject: {
      projection_file: 'stage2_display_projection.json',
      projection_raw_sha256: await sha256Hex(raw),
      projection_canonical_sha256: await sha256Hex(canonicalJson(projection)),
      projection_self_sha256_declared: projection.projection_sha256,
      projection_self_sha256_recomputed: projection.projection_sha256,
      self_hash_agrees: true,
    },
    admitted_inputs: {
      'direct:Rest': { admission_file: 'w10_admission_Rest.json', report_sha256: 'a'.repeat(64),
        n_gates: 5, n_arms_verified: 1, recompute_mode: 'full' },
    },
  };
}

export async function compactMetadata(projection: unknown, receipt: unknown): Promise<CompactStage2ReleaseMetadata> {
  const projectionText = JSON.stringify(projection);
  const receiptText = JSON.stringify(receipt);
  return {
    schema_version: 'spot.ui_compact_stage2_release.v1', display_release_id: 'stage2-display-1',
    release_conditions: [...CONDITIONS], pathway_sources: [...SOURCES], active_pathway_source: 'reactome',
    projection_raw_sha256: await sha256Hex(projectionText),
    projection_canonical_sha256: await sha256Hex(canonicalJson(projection)),
    projection_self_sha256: (projection as { projection_sha256: string }).projection_sha256,
    independent_verifier: {
      verifier_id: 'spot.stage02.display_projection.independent_verifier.v1',
      receipt_path: 'stage02/display_projection.verification.json',
      receipt_raw_sha256: await sha256Hex(receiptText),
      receipt_canonical_sha256: await sha256Hex(canonicalJson(receipt)),
    },
  };
}
