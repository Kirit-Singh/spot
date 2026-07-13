#!/usr/bin/env node
// Offline DETERMINISTIC UI-projection packager. Given an admitted-run pack spec (compact route
// projections already mapped from the native Stage-3/4 bundles and W3's admitted compact Stage-2
// projection, plus each route's admitted RECEIPT
// fields), it emits the served results/ tree: the compact route projections, the four
// spot.ui_release_manifest.v1 manifests, and results/current.json with a complete content-addressed
// inventory. It NEVER invents rows or run metadata — every run field (reproduce command, run UTC,
// generator/verifier status, release + artifact hashes, environment, artifact paths, CS notebook URL)
// is an INPUT from the admitted receipt, and the packager REFUSES if a required field is missing or the
// verifier is not an admitted token. content_hash / projection_content_hash use the SAME canonical JSON
// + sha256 the browser recomputes, so the emitted tree round-trips through the fail-closed browser loader.
//
// `pack(spec)` returns the virtual tree in-memory (results-relative path → text) for tests; the CLI
// wrapper writes it to disk. It writes NOTHING unless invoked with a real spec + output dir.
//
// Stage-2 row mapping is intentionally OUT OF SCOPE here: W3 emits the exact
// spot.stage02_display_projection.v2 document and its generator≠verifier receipt. This packager
// preserves those bytes as a compact served artifact and binds them into results/current.json.

import { createHash } from 'node:crypto';
import { readFileSync, mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';

// ── canonical JSON + sha256 — byte-exact replicas of _frontend/src/stage1/canonical.ts ──
function ensureAsciiString(s) {
  return JSON.stringify(s).replace(/[-￿]/g, (c) => '\\u' + c.charCodeAt(0).toString(16).padStart(4, '0'));
}
export function canonicalJson(value) {
  if (value === null) return 'null';
  const t = typeof value;
  if (t === 'boolean') return value ? 'true' : 'false';
  if (t === 'number') {
    if (!Number.isFinite(value)) throw new Error('canonicalJson: NaN/Infinity not allowed');
    return JSON.stringify(value);
  }
  if (t === 'string') return ensureAsciiString(value);
  if (Array.isArray(value)) return '[' + value.map(canonicalJson).join(',') + ']';
  if (t === 'object') {
    const keys = Object.keys(value).sort();
    return '{' + keys.map((k) => ensureAsciiString(k) + ':' + canonicalJson(value[k])).join(',') + '}';
  }
  throw new Error('canonicalJson: unserializable value of type ' + t);
}
const sha256Hex = (text) => createHash('sha256').update(text, 'utf8').digest('hex');
const canonicalHash = (obj) => sha256Hex(canonicalJson(obj));

// ── code-bound route table — stage_label + method_id MUST match _frontend/src/mpa/stageMethods.ts;
//    the browser firewall rejects any manifest whose values differ (the round-trip test guards this). ──
const ROUTES = {
  targets: {
    stage_label: 'Targets',
    method_id: 'spot.stage02.direct.masked_program_projection · spot.stage02.pareto.two_arm.v1 · spot.stage02.temporal_cross_condition.v1',
    projection_path: 'stage02/stage2_display_projection.json',
    projection_schema: 'spot.stage02_display_projection.v2',
  },
  pathways: {
    stage_label: 'Pathways',
    method_id: 'spot.stage02.pathway.ranked_arm_enrichment.v2 · spot.stage02.pathway.signature_convergence.v2',
    projection_path: 'stage02/stage2_display_projection.json',
    projection_schema: 'spot.stage02_display_projection.v2',
  },
  drugs: {
    stage_label: 'Drugs',
    method_id: 'stage3-druglink reusable-arm candidates · native schema spot.stage03_drug_annotation.v2 · browser projection spot.ui.stage03_candidates.v2',
    projection_path: 'stage03/drugs.ui.json',
    projection_schema: 'spot.ui_projection.drugs.v1',
  },
  pksafety: {
    stage_label: 'PK & Safety',
    method_id: 'stage4-evidence-v2 · cns_mpo_wager2010_v1 · nebpi_source_framing_v2 · safety_taxonomy_v2',
    projection_path: 'stage04/pksafety.ui.json',
    projection_schema: 'spot.ui_projection.stage2.v1', // overwritten per-route below (drugs/pksafety differ)
  },
};
ROUTES.pksafety.projection_schema = 'spot.ui_projection.pksafety.v1';

const ADMITTED_VERIFIER = new Set(['admit', 'admitted', 'pass', 'passed', 'verified', 'ok']);
const HEX64 = /^[0-9a-f]{64}$/;
const UI_RELEASE_SCHEMA = 'spot.ui_release_manifest.v1';
const STAGE2_METHOD = 'spot.stage02.display_projection.v2';
const STAGE2_VERIFIER = 'spot.stage02.display_projection.independent_verifier.v1';
const STAGE2_RECEIPT_PATH = 'stage02/display_projection.verification.json';
const P2S_PROJECTION_PATH = 'stage02/p2s_secondary_support.json';
const P2S_VERIFICATION_PATH = 'stage02/p2s_secondary_support.verification.json';
const P2S_SCHEMA = 'spot.stage02.p2s_ui_support_projection.v1';
const P2S_VERIFICATION_SCHEMA = 'spot.stage02.p2s_ui_projection_verification.v3';
const P2S_RELEASE_SCHEMA = 'spot.ui_p2s_secondary_release.v1';
const RELEASE_CONDITIONS = ['Rest', 'Stim8hr', 'Stim48hr'];
const PATHWAY_SOURCES = ['reactome', 'go_bp'];
const STAGE2_TOP_KEYS = ['analysis_mode', 'arms', 'authoritative_artifacts_are_the_native_ones',
  'bindings', 'cap_policy', 'combined_objective', 'cross_arm_score_or_order', 'method_version',
  'n_arms', 'projection_sha256', 'schema_version', 'selection_id', 'selection_independent'];
const STAGE2_RECEIPT_KEYS = ['admitted_inputs', 'failures', 'generator_is_not_verifier', 'n_arms', 'n_failed',
  'rebuilt_from_admitted_native_bytes', 'subject', 'verdict', 'verifier_id'];
// W3 exact admission subject (verify_display_projection.py): binds the EXACT projection the receipt
// verified — raw/canonical hashes + the projection's declared vs recomputed self-hash + their agreement.
const STAGE2_SUBJECT_KEYS = ['projection_canonical_sha256', 'projection_file', 'projection_raw_sha256',
  'projection_self_sha256_declared', 'projection_self_sha256_recomputed', 'self_hash_agrees'];
const P2S_TOP_KEYS = ['adapter', 'binding', 'columns', 'emitted_utc', 'lane_role', 'n_targets',
  'projection_rows_sha256', 'rows', 'schema_version', 'semantics'];
const P2S_VERIFICATION_KEYS = ['all_mutations_fail_closed', 'bound_direct_bundle_run_id',
  'clean_projection_admitted', 'clean_projection_failures', 'emitted_utc', 'generator',
  'firewall_false_positives_on_legit_keys', 'firewall_token_coverage',
  'firewall_token_coverage_complete', 'mutation_tests', 'n_mutations',
  'no_machine_local_path_proven', 'projection_identical_to_v2',
  'projection_canonical_rows_sha256', 'projection_raw_file_sha256', 'receipt_sha256',
  'schema_version', 'supersedes', 'verifier', 'verifier_is_independent_of_generator', 'verifies',
  'w10_verdict', 'w10_verifier_code_sha256'];
const P2S_COVERAGE_TOKENS = ['aggregate', 'aggregate_score', 'causal', 'combined',
  'combined_score', 'discovery', 'empirical_p_value', 'empirical_q_value', 'false_discovery',
  'false_discovery_rate', 'fdr', 'gating', 'nominal_p', 'overall_rank', 'p', 'p_adj',
  'p_value', 'padj', 'padjusted', 'pareto', 'pval', 'pvalue', 'q', 'q_adj', 'q_value',
  'qadj', 'qval', 'qvalue', 'rank', 'score', 'significance', 'validate', 'validation',
  'weighted', 'weighted_score'];
const P2S_SUPERSEDED_RECEIPT = 'p2s-ui-seam-handoff-v2/P2S_UI_PROJECTION_VERIFICATION.json';
const P2S_MUTATIONS = ['abs_broken', 'admits_entering_rank', 'arm_key_non_canonical',
  'binding_aggregate_score_key', 'claims_part_of_direct', 'concordance_for_zero_sign',
  'denominators_broken', 'disguised_rank_key_overall_rank', 'extra_binding_key_combined_score',
  'join_key_rank', 'lane_not_secondary', 'machine_path_in_binding', 'machine_path_mnt',
  'n_targets_wrong', 'non_finite_coef', 'opposed_flipped', 'row_causal_key',
  'row_combined_key', 'row_empirical_p_value_key', 'row_false_discovery_rate_key',
  'row_fdr_key', 'row_padj_key', 'row_qval_key', 'row_validation_key', 'row_weighted_key',
  'rows_unsorted', 'sibling_not_exact_negation', 'sibling_same_direction',
  'sign_not_sign_of_coef', 'tampered_row_hash', 'tampered_w10_verdict',
  'target_id_not_unique', 'wrong_bundle'].sort();
const P2S_ROW_KEYS = ['target_id', 'primary_coefficient', 'primary_abs_coefficient', 'primary_sign',
  'opposed', 'primary_available', 'n_runs', 'sens_log_fc_sign_concordance', 'n_log_fc',
  'sens_pca_off_sign_concordance', 'n_pca_off', 'lodo_sign_concordance', 'n_lodo'];

function fail(msg) {
  throw new Error('pack: ' + msg);
}
function exactKeys(obj, expected, path) {
  const got = Object.keys(obj).sort();
  const want = [...expected].sort();
  if (got.length !== want.length || got.some((key, i) => key !== want[i])) {
    fail(`${path} has fields [${got.join(', ')}], expected [${want.join(', ')}]`);
  }
}
function rejectStage2ScientificKeys(value, path) {
  if (Array.isArray(value)) return value.forEach((item, i) => rejectStage2ScientificKeys(item, `${path}[${i}]`));
  if (!value || typeof value !== 'object') return;
  for (const [key, child] of Object.entries(value)) {
    const normalized = key.toLowerCase().replace(/[^a-z0-9]/g, '');
    if (/^(p|pval|pvalue|q|qval|qvalue|fdr|nominalp|empiricalpvalue|empiricalqvalue|combinedscore|balancedscore|balancedskew|weightedscore|overallrank|pairrank|headlinerank)$/.test(normalized)) {
      fail(`${path}.${key} is forbidden in the compact Stage-2 projection`);
    }
    rejectStage2ScientificKeys(child, `${path}.${key}`);
  }
}

function rejectP2sDynamic(value, path) {
  if (Array.isArray(value)) return value.forEach((item, i) => rejectP2sDynamic(item, `${path}[${i}]`));
  if (typeof value === 'string') {
    if (value.startsWith('/') || /^file:\/\//i.test(value) || /^[a-z]:[\\/]/i.test(value)) {
      fail(`${path} carries a machine-local path`);
    }
    return;
  }
  if (!value || typeof value !== 'object') return;
  for (const [key, child] of Object.entries(value)) {
    const k = key.toLowerCase().replace(/[^a-z0-9]/g, '');
    if (/^(p|q)$/.test(k) || /(padj|pval|pvalue|qval|qvalue|fdr|falsediscovery|posteriorprob|nominalp|empiricalp|empiricalq|rank|aggregatescore|compositescore|overallscore|combined|balanced|weighted|significan|validat|causal|pareto)/.test(k)) {
      fail(`${path}.${key} is forbidden in P2S dynamic provenance`);
    }
    rejectP2sDynamic(child, `${path}.${key}`);
  }
}
function reqStr(receipt, key, route) {
  const v = receipt ? receipt[key] : undefined;
  if (typeof v !== 'string' || v.trim() === '') fail(`${route} receipt.${key} must be a non-empty string (never invented)`);
  return v;
}
function reqHex(receipt, key, route) {
  const v = reqStr(receipt, key, route);
  if (!HEX64.test(v)) fail(`${route} receipt.${key} must be a 64-hex sha256`);
  return v;
}
function reqStrList(receipt, key, route, min) {
  const v = receipt ? receipt[key] : undefined;
  if (!Array.isArray(v) || v.some((x) => typeof x !== 'string')) fail(`${route} receipt.${key} must be a string[]`);
  if (v.length < min) fail(`${route} receipt.${key} must have >= ${min} entr${min === 1 ? 'y' : 'ies'}`);
  return v;
}

/** Build a spot.ui_release_manifest.v1 from the code-bound identity + the admitted receipt (no invention). */
function buildManifest(route, def, receipt) {
  const verifier = reqStr(receipt, 'verifier_status', route);
  if (!ADMITTED_VERIFIER.has(verifier.trim().toLowerCase())) {
    fail(`${route} receipt.verifier_status "${verifier}" is not an admitted token — refusing to package a non-admitted run`);
  }
  if (!receipt || !('cs_notebook_url' in receipt)) fail(`${route} receipt.cs_notebook_url must be present (string URL or null; never invented)`);
  const notebook = receipt.cs_notebook_url;
  if (notebook !== null && typeof notebook !== 'string') fail(`${route} receipt.cs_notebook_url must be a string or null`);
  return {
    schema_version: UI_RELEASE_SCHEMA,
    stage_label: def.stage_label,
    method_id: def.method_id,
    release_revision: reqStr(receipt, 'release_revision', route),
    raw_sha256: reqHex(receipt, 'raw_sha256', route),
    canonical_sha256: reqHex(receipt, 'canonical_sha256', route),
    method_code_sha256: reqHex(receipt, 'method_code_sha256', route),
    environment: reqStr(receipt, 'environment', route),
    last_run_utc: reqStr(receipt, 'last_run_utc', route),
    generator_status: reqStr(receipt, 'generator_status', route),
    verifier_status: verifier,
    reproduce_command: reqStr(receipt, 'reproduce_command', route),
    cs_notebook_url: notebook,
    artifact_paths: reqStrList(receipt, 'artifact_paths', route, 1),
    source_artifact_ids: reqStrList(receipt, 'source_artifact_ids', route, 0),
  };
}

function validateProjectionEnvelope(route, def, projection) {
  if (!projection || typeof projection !== 'object' || Array.isArray(projection)) fail(`${route} projection must be an object`);
  if (projection.schema_version !== def.projection_schema) fail(`${route} projection.schema_version must be ${def.projection_schema}`);
  if (route === 'targets' || route === 'pathways') {
    exactKeys(projection, STAGE2_TOP_KEYS, `${route} projection`);
    if (projection.method_version !== STAGE2_METHOD || projection.selection_independent !== true ||
        projection.selection_id !== null || projection.analysis_mode !== null ||
        projection.combined_objective !== null || projection.cross_arm_score_or_order !== null ||
        projection.authoritative_artifacts_are_the_native_ones !== true || !HEX64.test(projection.projection_sha256)) {
      fail(`${route} compact Stage-2 projection identity/firewall is malformed`);
    }
    if (!projection.arms || typeof projection.arms !== 'object' || Array.isArray(projection.arms) ||
        !Number.isSafeInteger(projection.n_arms) || projection.n_arms !== Object.keys(projection.arms).length) {
      fail(`${route} compact Stage-2 projection arm count is malformed`);
    }
    rejectStage2ScientificKeys(projection.arms, `${route} projection.arms`);
    return;
  }
  if (projection.route !== route) fail(`${route} projection.route must be "${route}"`);
}

function requireBinding(b) {
  if (!b || typeof b !== 'object') fail('spec.stage1_binding is required');
  if (typeof b.release_method_version !== 'string' || b.release_method_version.trim() === '') fail('stage1_binding.release_method_version required');
  if (typeof b.registry_scorer_view_sha256 !== 'string' || !HEX64.test(b.registry_scorer_view_sha256)) fail('stage1_binding.registry_scorer_view_sha256 must be 64-hex');
  // 539431d release identity — carried into current.json so the browser can pin-verify it (schema-file
  // raw sha from release components.selection_schema_v3 + the release self-hash). Both required, 64-hex.
  if (typeof b.selection_schema_raw_sha256 !== 'string' || !HEX64.test(b.selection_schema_raw_sha256)) fail('stage1_binding.selection_schema_raw_sha256 must be 64-hex');
  if (typeof b.release_self_sha256 !== 'string' || !HEX64.test(b.release_self_sha256)) fail('stage1_binding.release_self_sha256 must be 64-hex');
  return {
    release_method_version: b.release_method_version,
    registry_scorer_view_sha256: b.registry_scorer_view_sha256,
    selection_schema_raw_sha256: b.selection_schema_raw_sha256,
    release_self_sha256: b.release_self_sha256,
  };
}


// ── NATIVE → COMPACT projection derivation ──────────────────────────────────────────────────────
// Stage-2 rows are already projected and independently verified by W3; this file never re-maps
// them. Stage-3/4 adapters remain strict on required ids + types and preserve typed absence.
function nObj(v, path) { if (!v || typeof v !== 'object' || Array.isArray(v)) fail(`${path} must be an object`); return v; }
function nStr(v, path) { if (typeof v !== 'string' || v.trim() === '') fail(`${path} must be a non-empty string`); return v; }
function nBool(v, path) { if (typeof v !== 'boolean') fail(`${path} must be boolean`); return v; }
function nHex(v, path) { const s = nStr(v, path); if (!HEX64.test(s)) fail(`${path} must be 64-hex`); return s; }
function nOptStr(v, path) { if (v === undefined || v === null) return null; if (typeof v !== 'string') fail(`${path} must be a string or null`); return v; }
function nStrList(v, path) { if (v === undefined || v === null) return []; if (!Array.isArray(v) || v.some((x) => typeof x !== 'string')) fail(`${path} must be a string[]`); return v; }
function nArr(v, path) { if (!Array.isArray(v)) fail(`${path} must be an array`); return v; }
function nCountMap(v, path) {
  nObj(v, path); const out = {};
  for (const [key, value] of Object.entries(v)) {
    if (!Number.isSafeInteger(value) || value < 0) fail(`${path}.${key} must be a non-negative integer`);
    out[key] = value;
  }
  return out;
}

// Stage-3 v2 native drug_annotation → compact Drugs projection (fields per §7 "Required Stage-3 UI model").
function nativeToDrugsProjection(nat) {
  nObj(nat, 'drugs native');
  if (nat.schema_version !== 'spot.stage03_drug_annotation.v2') fail('drugs native.schema_version must be spot.stage03_drug_annotation.v2');
  if (nat.artifact_class !== 'analysis') fail('drugs native.artifact_class must be analysis (fixture/research artifacts are refused)');
  if (nat.p_q_fdr_permitted !== false || nat.candidate_rank_permitted !== false ||
      nat.combined_objective_permitted !== false || nat.headline_arm_permitted !== false) {
    fail('drugs native permits an inferential/ranked/combined claim the browser contract forbids');
  }
  const aggregate = nObj(nat.stage2_aggregate, 'drugs native.stage2_aggregate');
  const upstreamStage2 = nHex(aggregate.manifest_self_hash, 'drugs native.stage2_aggregate.manifest_self_hash');
  const candidates = nArr(nat.candidates, 'drugs native.candidates').map((c, i) => {
    const p = `drugs native.candidates[${i}]`;
    nObj(c, p);
    const byOrigin = nCountMap(c.n_edges_by_origin, `${p}.n_edges_by_origin`);
    return {
      candidate_id: nStr(c.candidate_id, `${p}.candidate_id`),
      active_moiety_id: nOptStr(c.active_moiety_id, `${p}.active_moiety_id`),
      preferred_name: nOptStr(c.preferred_name, `${p}.preferred_name`),
      identity_status: nOptStr(c.identity_status, `${p}.identity_status`),
      molecule_chembl_ids: nStrList(c.molecule_chembl_ids, `${p}.molecule_chembl_ids`),
      target_ensembls: nStrList(c.target_ids, `${p}.target_ids`),
      n_edges: Object.values(byOrigin).reduce((sum, value) => sum + value, 0),
      n_direct_gene_edges: byOrigin.direct_target ?? 0,
      max_phase_status: nOptStr(c.max_phase_status, `${p}.max_phase_status`),
      max_phase_sources: nStrList(c.max_phase_sources, `${p}.max_phase_sources`),
      observed_perturbation_arms: nStrList(c.observed_perturbation_arm_keys, `${p}.observed_perturbation_arm_keys`),
      observed_perturbation_support: nBool(c.observed_perturbation_support, `${p}.observed_perturbation_support`),
      mechanism_match_statuses: nStrList(c.mechanism_match_statuses, `${p}.mechanism_match_statuses`),
      pathway_hypothesis_arms: nStrList(c.pathway_hypothesis_arm_keys, `${p}.pathway_hypothesis_arm_keys`),
      stage3_evidence_classes: nStrList(c.stage3_evidence_classes, `${p}.stage3_evidence_classes`),
      stage4_assessment_status: nOptStr(c.stage4_assessment_status, `${p}.stage4_assessment_status`),
      stage4_assessment_reason: nOptStr(c.stage4_assessment_reason, `${p}.stage4_assessment_reason`),
      source_record_ids: nStrList(c.source_record_ids, `${p}.source_record_ids`),
    };
  });
  return {
    schema_version: 'spot.ui_projection.drugs.v1', route: 'drugs',
    artifact: {
      schema_version: 'spot.ui.stage03_candidates.v2',
      native_schema_version: 'spot.stage03_drug_annotation.v2',
      artifact_class: 'analysis',
      bundle_id: nStr(nat.bundle_id, 'drugs native.bundle_id'),
      canonical_content_sha256: nHex(nat.canonical_content_sha256, 'drugs native.canonical_content_sha256'),
      upstream_stage2_run: upstreamStage2,
      candidates,
    },
  };
}

// Stage-4's native browser projection is ALREADY browser-safe. Preserve every nested object and
// null exactly; only add the compact envelope + the explicit chain id copied from native upstream.
function nativeToPkSafetyProjection(nat) {
  nObj(nat, 'pksafety native');
  if (nat.schema_id !== 'spot.stage04_browser_projection.v1') fail('pksafety native.schema_id must be spot.stage04_browser_projection.v1');
  if (nat.store_is_selection_independent !== true || nat.is_ranking !== false) fail('pksafety native must be selection-independent and non-ranking');
  const upstream = nObj(nat.upstream, 'pksafety native.upstream');
  if (upstream.namespace !== 'production' || upstream.is_fixture !== false) fail('pksafety native upstream is not admitted production');
  const upstreamStage3 = nStr(upstream.candidate_set_id, 'pksafety native.upstream.candidate_set_id');
  nArr(nat.candidates, 'pksafety native.candidates').forEach((c, i) => {
    const p = `pksafety native.candidates[${i}]`;
    nObj(c, p); nStr(c.candidate_id, `${p}.candidate_id`); nObj(c.lanes, `${p}.lanes`);
  });
  return {
    schema_version: 'spot.ui_projection.pksafety.v1', route: 'pksafety',
    artifact: {
      ...nat,
      schema_version: nat.schema_id,
      upstream_stage3_bundle: upstreamStage3,
    },
  };
}

function exactList(v, expected, path) {
  const got = nStrList(v, path);
  if (got.length !== expected.length || got.some((x, i) => x !== expected[i])) {
    fail(`${path} must be exactly [${expected.join(', ')}]`);
  }
  return got;
}

function compactStage2Input(routeInput) {
  nObj(routeInput, 'stage2 route');
  // W3 writes SORTED PYTHON JSON bytes; the subject raw hash is over that EXACT file. We accept those
  // verbatim bytes, parse ONLY for validation, and serve the original text unchanged (re-serializing
  // would change float formatting / key order / newlines and break the raw-hash + subject binding).
  const projectionText = nStr(routeInput.projection_text, 'stage2 route.projection_text');
  let projection;
  try { projection = JSON.parse(projectionText); } catch { fail('stage2 route.projection_text is not valid JSON'); }
  if (!projection || typeof projection !== 'object' || Array.isArray(projection)) {
    fail('stage2 route.projection_text must decode to an object');
  }
  const displayReceipt = nObj(routeInput.display_verifier_receipt,
    'stage2 route.display_verifier_receipt');
  exactKeys(displayReceipt, STAGE2_RECEIPT_KEYS, 'stage2 route.display_verifier_receipt');
  const subject = nObj(displayReceipt.subject, 'stage2 route.display_verifier_receipt.subject');
  exactKeys(subject, STAGE2_SUBJECT_KEYS, 'stage2 route.display_verifier_receipt.subject');
  for (const h of ['projection_raw_sha256', 'projection_canonical_sha256', 'projection_self_sha256_declared', 'projection_self_sha256_recomputed']) {
    if (!HEX64.test(subject[h])) fail(`stage2 display receipt subject.${h} must be a 64-hex sha256`);
  }
  if (subject.self_hash_agrees !== true || subject.projection_self_sha256_declared !== subject.projection_self_sha256_recomputed) {
    fail('stage2 display receipt subject self-hash does not agree with the verifier recompute');
  }
  const admittedInputs = nObj(displayReceipt.admitted_inputs, 'stage2 route.display_verifier_receipt.admitted_inputs');
  if (Object.keys(admittedInputs).length === 0) fail('stage2 display receipt admitted_inputs must be non-empty');
  const release = nObj(routeInput.compact_release, 'stage2 route.compact_release');
  const displayReleaseId = nStr(release.display_release_id,
    'stage2 route.compact_release.display_release_id');
  const releaseConditions = exactList(release.release_conditions, RELEASE_CONDITIONS,
    'stage2 route.compact_release.release_conditions');
  const pathwaySources = exactList(release.pathway_sources, PATHWAY_SOURCES,
    'stage2 route.compact_release.pathway_sources');
  const activeSource = nStr(release.active_pathway_source,
    'stage2 route.compact_release.active_pathway_source');
  if (!pathwaySources.includes(activeSource)) fail('stage2 active_pathway_source is not released');
  if (displayReceipt.verifier_id !== STAGE2_VERIFIER ||
      displayReceipt.generator_is_not_verifier !== true ||
      displayReceipt.rebuilt_from_admitted_native_bytes !== true ||
      displayReceipt.verdict !== 'admit' || displayReceipt.n_failed !== 0 ||
      !Array.isArray(displayReceipt.failures) || displayReceipt.failures.length !== 0 ||
      displayReceipt.n_arms !== projection.n_arms) {
    fail('stage2 independent display-verifier receipt is not admitted for this projection');
  }
  return { projection, projectionText, displayReceipt, displayReleaseId, releaseConditions, pathwaySources, activeSource };
}

function canonicalDirectArm(key, path) {
  const parts = nStr(key, path).split('|');
  if (parts.length !== 4 || parts[0] !== 'direct' || !parts[1] ||
      !['increase', 'decrease'].includes(parts[2]) || !parts[3]) {
    fail(`${path} is not a canonical Direct arm key`);
  }
  return { program: parts[1], direction: parts[2], condition: parts[3] };
}

/** Exact v3-only receipt assertions, exported so the packager's release boundary has a direct test. */
export function validateP2sV3ReceiptAttestations(verification) {
  nObj(verification, 'targets P2S verification');
  exactKeys(verification, P2S_VERIFICATION_KEYS, 'targets P2S verification');
  if (verification.projection_identical_to_v2 !== true ||
      verification.firewall_token_coverage_complete !== true ||
      !Array.isArray(verification.firewall_false_positives_on_legit_keys) ||
      verification.firewall_false_positives_on_legit_keys.length !== 0) {
    fail('targets P2S verification does not attest unchanged projection bytes and complete clean field coverage');
  }
  if (verification.supersedes !== P2S_SUPERSEDED_RECEIPT ||
      verification.supersedes.startsWith('/') || verification.supersedes.split('/').includes('..')) {
    fail('targets P2S verification supersedes path is not the admitted relative v2 receipt');
  }
  const coverage = nObj(verification.firewall_token_coverage,
    'targets P2S verification.firewall_token_coverage');
  exactKeys(coverage, P2S_COVERAGE_TOKENS,
    'targets P2S verification.firewall_token_coverage');
  if (P2S_COVERAGE_TOKENS.some((token) => coverage[token] !== true)) {
    fail('targets P2S verification field coverage is incomplete');
  }
}

/** Strictly admit + bind the optional P2S sidecar before it can enter the served results tree. */
function p2sSecondaryInput(routeInput, directProjection) {
  const hasProjection = routeInput.p2s_projection_text !== undefined;
  const hasReceipt = routeInput.p2s_verifier_receipt_text !== undefined;
  if (!hasProjection && !hasReceipt) return null;
  if (!hasProjection || !hasReceipt) fail('targets P2S projection and verifier receipt must both be present');
  const projectionText = nStr(routeInput.p2s_projection_text, 'targets.p2s_projection_text');
  const verificationText = nStr(routeInput.p2s_verifier_receipt_text,
    'targets.p2s_verifier_receipt_text');
  let projection, verification;
  try { projection = JSON.parse(projectionText); } catch { fail('targets P2S projection is not valid JSON'); }
  try { verification = JSON.parse(verificationText); } catch { fail('targets P2S verification is not valid JSON'); }
  nObj(projection, 'targets P2S projection');
  nObj(verification, 'targets P2S verification');
  exactKeys(projection, P2S_TOP_KEYS, 'targets P2S projection');
  validateP2sV3ReceiptAttestations(verification);
  if (projection.schema_version !== P2S_SCHEMA || projection.lane_role !== 'secondary_non_gating') {
    fail('targets P2S projection schema/lane is not admitted');
  }
  const semantics = nObj(projection.semantics, 'targets P2S projection.semantics');
  if (semantics.is_part_of_admitted_direct_result !== false ||
      semantics.p2s_fields_enter_primary_rank_or_order !== false ||
      semantics.no_rank_no_pvalue_no_combined_score !== true ||
      semantics.sibling_arm_is_exact_negation !== true) {
    fail('targets P2S projection weakens the non-gating/no-statistic firewall');
  }
  const adapter = nObj(projection.adapter, 'targets P2S projection.adapter');
  exactKeys(adapter, ['arm_key', 'condition', 'desired_change', 'display_fields',
    'forbidden_ui_uses', 'join_key', 'program_id', 'robustness_fields', 'sibling_arm_key'],
  'targets P2S projection.adapter');
  if (adapter.join_key !== 'target_id') fail('targets P2S adapter join_key must be target_id');
  const arm = canonicalDirectArm(adapter.arm_key, 'targets P2S adapter.arm_key');
  const sibling = canonicalDirectArm(adapter.sibling_arm_key, 'targets P2S adapter.sibling_arm_key');
  if (arm.program !== adapter.program_id || arm.condition !== adapter.condition ||
      arm.direction !== adapter.desired_change || sibling.program !== arm.program ||
      sibling.condition !== arm.condition || sibling.direction === arm.direction) {
    fail('targets P2S adapter arm/sibling identity is inconsistent');
  }
  const binding = nObj(projection.binding, 'targets P2S projection.binding');
  exactKeys(binding, ['arm_key', 'bound_direct_release', 'input_hashes', 'model', 'p2s_run_id',
    'p2s_run_sha256', 'receipt_sha256', 'seed', 'sibling_arm_key',
    'source_support_parquet_sha256', 'source_support_rows_sha256'], 'targets P2S projection.binding');
  if (binding.arm_key !== adapter.arm_key || binding.sibling_arm_key !== adapter.sibling_arm_key ||
      !HEX64.test(binding.p2s_run_sha256) || binding.p2s_run_id !== binding.p2s_run_sha256.slice(0, 16) ||
      !HEX64.test(binding.receipt_sha256)) fail('targets P2S binding identity is malformed');
  const direct = nObj(binding.bound_direct_release, 'targets P2S bound_direct_release');
  exactKeys(direct, ['bundle_run_id', 'release_run_id', 'scorer_view_sha256', 'w10_verdict',
    'w10_verifier_code_sha256', 'w10_verifier_id'], 'targets P2S bound_direct_release');
  if (direct.w10_verdict !== 'ADMIT' ||
      direct.w10_verifier_id !== 'spot.stage02.direct.arm_bundle.verifier.v1' ||
      !HEX64.test(direct.w10_verifier_code_sha256) || !HEX64.test(direct.scorer_view_sha256)) {
    fail('targets P2S is not bound to admitted W10 Direct evidence');
  }
  exactKeys(nObj(binding.model, 'targets P2S binding.model'),
    ['l1_ratio_grid', 'n_pcs_primary', 'positive', 'random_state', 'upstream_commit', 'upstream_version'],
  'targets P2S binding.model');
  exactKeys(nObj(binding.input_hashes, 'targets P2S binding.input_hashes'),
    ['de_main_raw_sha256', 'ntc_h5ad_raw_sha256', 'stage1_scores_canonical_sha256',
      'stage1_scores_raw_sha256'], 'targets P2S binding.input_hashes');
  rejectP2sDynamic(binding.model, 'targets P2S binding.model');
  rejectP2sDynamic(binding.input_hashes, 'targets P2S binding.input_hashes');
  for (const value of Object.values(binding.input_hashes)) if (!HEX64.test(value)) {
    fail('targets P2S input hash is not 64-hex');
  }
  exactList(projection.columns, P2S_ROW_KEYS, 'targets P2S projection.columns');
  const rows = nArr(projection.rows, 'targets P2S projection.rows');
  if (!Number.isSafeInteger(projection.n_targets) || projection.n_targets < 1 ||
      projection.n_targets !== rows.length || !HEX64.test(projection.projection_rows_sha256)) {
    fail('targets P2S projection row count/hash is malformed');
  }
  const ids = rows.map((row, i) => {
    nObj(row, `targets P2S rows[${i}]`); exactKeys(row, P2S_ROW_KEYS, `targets P2S rows[${i}]`);
    const id = nStr(row.target_id, `targets P2S rows[${i}].target_id`);
    if (!/^ENSG[0-9]{11}$/.test(id)) fail(`targets P2S rows[${i}].target_id is not canonical Ensembl`);
    return id;
  });
  if (new Set(ids).size !== ids.length || ids.some((id, i) => i > 0 && ids[i - 1].localeCompare(id) >= 0)) {
    fail('targets P2S target ids are duplicate or not ascending');
  }

  if (verification.schema_version !== P2S_VERIFICATION_SCHEMA ||
      verification.verifies !== 'P2S_UI_SUPPORT_PROJECTION.json' ||
      verification.generator !== 'emit_projection_v2.py' || verification.verifier !== 'verify_projection_v3.py' ||
      verification.verifier_is_independent_of_generator !== true ||
      verification.clean_projection_admitted !== true || verification.all_mutations_fail_closed !== true ||
      verification.no_machine_local_path_proven !== true ||
      !Array.isArray(verification.clean_projection_failures) || verification.clean_projection_failures.length !== 0 ||
      verification.projection_raw_file_sha256 !== sha256Hex(projectionText) ||
      verification.projection_canonical_rows_sha256 !== projection.projection_rows_sha256 ||
      verification.bound_direct_bundle_run_id !== direct.bundle_run_id ||
      verification.w10_verdict !== 'ADMIT' ||
      verification.w10_verifier_code_sha256 !== direct.w10_verifier_code_sha256) {
    fail('targets P2S independent receipt does not admit these exact bytes/bindings');
  }
  const mutations = nArr(verification.mutation_tests, 'targets P2S verification.mutation_tests')
    .map((item, i) => { nObj(item, `targets P2S mutation[${i}]`);
      exactKeys(item, ['attack', 'rejected'], `targets P2S mutation[${i}]`);
      if (item.rejected !== true) fail(`targets P2S mutation[${i}] did not fail closed`);
      return nStr(item.attack, `targets P2S mutation[${i}].attack`); }).sort();
  if (verification.n_mutations !== P2S_MUTATIONS.length || mutations.length !== P2S_MUTATIONS.length ||
      mutations.some((name, i) => name !== P2S_MUTATIONS[i])) {
    fail('targets P2S mutation battery is incomplete or substituted');
  }
  if (!HEX64.test(verification.receipt_sha256)) fail('targets P2S receipt self hash is malformed');
  const receiptBody = { ...verification }; delete receiptBody.receipt_sha256;
  if (canonicalHash(receiptBody) !== verification.receipt_sha256) {
    fail('targets P2S receipt self hash does not re-derive');
  }

  const expectedBundle = `direct/${direct.bundle_run_id}`;
  const directArm = directProjection.arms?.[adapter.arm_key];
  const directSibling = directProjection.arms?.[adapter.sibling_arm_key];
  if (!directArm || !directSibling || directArm.lane !== 'direct' || directSibling.lane !== 'direct' ||
      directArm.source_bundle !== expectedBundle || directSibling.source_bundle !== expectedBundle ||
      directProjection.bindings?.native_bundles?.[expectedBundle]?.lane !== 'direct' ||
      directArm.n_evaluable !== projection.n_targets || directSibling.n_evaluable !== projection.n_targets) {
    fail('targets P2S sidecar does not bind the exact admitted Direct bundle/arms/count');
  }
  return { projection, projectionText, verification, verificationText, sourceBundle: expectedBundle };
}

/** Accumulate the admitted cross-stage chain ids from each route's derived projection. */
function collectChain(route, projection, ids, displayReleaseId = null) {
  if (route === 'targets' || route === 'pathways') {
    if (ids.stage2_display_release_id !== null && ids.stage2_display_release_id !== displayReleaseId) {
      fail(`chain: stage-2 display_release_id differs across routes ("${ids.stage2_display_release_id}" vs "${displayReleaseId}")`);
    }
    ids.stage2_display_release_id = displayReleaseId;
  } else if (route === 'drugs') {
    ids.stage3_bundle_id = projection.artifact.bundle_id;
    ids._drugsUpstream = projection.artifact.upstream_stage2_run;
  } else if (route === 'pksafety') {
    ids.stage4_scorecard_set_id = projection.artifact.scorecard_set_id;
    ids._pksafetyUpstream = projection.artifact.upstream_stage3_bundle;
  }
}

/** Enforce cross-stage consistency (admitted receipt over data from another run/bundle → refuse). */
function finalizeChain(ids, nRoutes) {
  if (ids._drugsUpstream !== null && ids._drugsUpstream !== ids.stage2_run_id) {
    fail(`chain: drugs upstream_stage2_run "${ids._drugsUpstream}" != stage-2 run_id "${ids.stage2_run_id}"`);
  }
  if (ids._pksafetyUpstream !== null && ids._pksafetyUpstream !== ids.stage3_bundle_id) {
    fail(`chain: pksafety upstream_stage3_bundle "${ids._pksafetyUpstream}" != stage-3 bundle_id "${ids.stage3_bundle_id}"`);
  }
  if (nRoutes > 0 && ids.stage2_display_release_id === null) {
    fail('chain: a bound release requires a Stage-2 route (targets/pathways) to anchor stage2_display_release_id');
  }
  return { stage2_display_release_id: ids.stage2_display_release_id, stage2_run_id: ids.stage2_run_id,
    stage3_bundle_id: ids.stage3_bundle_id, stage4_scorecard_set_id: ids.stage4_scorecard_set_id };
}

/** Derive the compact route projection from that route's admitted NATIVE bundle(s). */
export function deriveCompactProjection(route, native) {
  if (native === undefined || native === null) {
    fail(`${route} native input required — the packager derives compact projections from admitted native bundles, never hand-authored rows`);
  }
  if (route === 'targets' || route === 'pathways') {
    fail(`${route} consumes W3's admitted compact projection via route.projection; it never derives Stage-2 rows`);
  }
  if (route === 'drugs') return nativeToDrugsProjection(native);
  if (route === 'pksafety') return nativeToPkSafetyProjection(native);
  return fail(`unknown route "${route}"`);
}

/**
 * Assemble the virtual served results/ tree from a pack spec. Stage-2 supplies W3's admitted compact
 * projection + independent receipt + explicit release order/source/run identity; Stage-3/4 supply their
 * native bundle. Returns { tree, current } (results-relative path → text).
 */
export function pack(spec) {
  if (!spec || typeof spec !== 'object') fail('spec must be an object');
  const stage1_binding = requireBinding(spec.stage1_binding);
  const routesIn = spec.routes && typeof spec.routes === 'object' ? spec.routes : {};

  const tree = {}; // results-relative path → text (pretty JSON; hashes are over the canonical form / raw bytes)
  const routes = {};
  const declaredStage2RunId = spec.stage2_run_id == null ? null : nStr(spec.stage2_run_id,
    'spec.stage2_run_id');
  const chainIds = { stage2_display_release_id: null, stage2_run_id: declaredStage2RunId, stage3_bundle_id: null,
    stage4_scorecard_set_id: null, _drugsUpstream: null, _pksafetyUpstream: null };
  for (const route of Object.keys(routesIn)) {
    const def = ROUTES[route];
    if (!def) fail(`unknown route "${route}"`);
    const routeInput = routesIn[route] || {};
    const { native, receipt } = routeInput;
    const isStage2 = route === 'targets' || route === 'pathways';
    const compact = isStage2 ? compactStage2Input(routeInput) : null;
    const projection = compact ? compact.projection : deriveCompactProjection(route, native);
    if (route !== 'targets' && (routeInput.p2s_projection_text !== undefined ||
        routeInput.p2s_verifier_receipt_text !== undefined)) {
      fail(`${route} cannot carry the Targets-only P2S secondary sidecar`);
    }
    const p2s = route === 'targets' && compact ? p2sSecondaryInput(routeInput, projection) : null;
    validateProjectionEnvelope(route, def, projection);
    collectChain(route, projection, chainIds, compact?.displayReleaseId ?? null);

    // Compact Stage-2 serves W3's EXACT projection bytes VERBATIM (never re-serialized); derived
    // Stage-3/4 projections have no external raw text and are serialized here.
    const projectionText = compact ? compact.projectionText : JSON.stringify(projection, null, 2);
    if (def.projection_path in tree && tree[def.projection_path] !== projectionText) {
      fail(`${route} projection disagrees with the already-packaged shared Stage-2 projection`);
    }
    tree[def.projection_path] = projectionText;
    const projection_content_hash = canonicalHash(projection);

    const manifest = buildManifest(route, def, receipt);
    const manifest_path = `manifests/${route}.ui_release.json`;
    tree[manifest_path] = JSON.stringify(manifest, null, 2);
    const content_hash = canonicalHash(manifest);

    let compact_stage2 = null;
    let p2s_secondary = null;
    if (compact) {
      const displayReceiptText = JSON.stringify(compact.displayReceipt, null, 2);
      if (STAGE2_RECEIPT_PATH in tree && tree[STAGE2_RECEIPT_PATH] !== displayReceiptText) {
        fail(`${route} verifier receipt disagrees with the already-packaged Stage-2 receipt`);
      }
      tree[STAGE2_RECEIPT_PATH] = displayReceiptText;
      // W3 exact-subject binding: refuse to package a receipt whose subject admits DIFFERENT projection
      // bytes than the ones being served (closes the same-n_arms weakness at package time, not just load).
      const subj = compact.displayReceipt.subject;
      if (subj.projection_raw_sha256 !== sha256Hex(projectionText) ||
          subj.projection_canonical_sha256 !== projection_content_hash ||
          subj.projection_self_sha256_declared !== projection.projection_sha256) {
        fail(`${route} display receipt subject binds a different projection than the packaged bytes`);
      }
      compact_stage2 = {
        schema_version: 'spot.ui_compact_stage2_release.v1',
        display_release_id: compact.displayReleaseId,
        release_conditions: compact.releaseConditions,
        pathway_sources: compact.pathwaySources,
        active_pathway_source: compact.activeSource,
        projection_raw_sha256: sha256Hex(projectionText),
        projection_canonical_sha256: projection_content_hash,
        projection_self_sha256: projection.projection_sha256,
        independent_verifier: {
          verifier_id: STAGE2_VERIFIER,
          receipt_path: STAGE2_RECEIPT_PATH,
          receipt_raw_sha256: sha256Hex(displayReceiptText),
          receipt_canonical_sha256: canonicalHash(compact.displayReceipt),
        },
      };
      const priorStage2 = routes.targets?.compact_stage2 ?? routes.pathways?.compact_stage2;
      if (priorStage2 && canonicalJson(priorStage2) !== canonicalJson(compact_stage2)) {
        fail(`${route} compact Stage-2 release metadata disagrees across targets/pathways`);
      }
    }
    if (p2s) {
      tree[P2S_PROJECTION_PATH] = p2s.projectionText;
      tree[P2S_VERIFICATION_PATH] = p2s.verificationText;
      p2s_secondary = {
        schema_version: P2S_RELEASE_SCHEMA,
        projection_path: P2S_PROJECTION_PATH,
        projection_raw_sha256: sha256Hex(p2s.projectionText),
        projection_canonical_sha256: canonicalHash(p2s.projection),
        projection_rows_sha256: p2s.projection.projection_rows_sha256,
        verification_path: P2S_VERIFICATION_PATH,
        verification_raw_sha256: sha256Hex(p2s.verificationText),
        verification_canonical_sha256: canonicalHash(p2s.verification),
        verification_self_sha256: p2s.verification.receipt_sha256,
        receipt_sha256: p2s.projection.binding.receipt_sha256,
        p2s_run_sha256: p2s.projection.binding.p2s_run_sha256,
        arm_key: p2s.projection.adapter.arm_key,
        sibling_arm_key: p2s.projection.adapter.sibling_arm_key,
        source_bundle: p2s.sourceBundle,
      };
    }
    routes[route] = { manifest_path, content_hash, projection_path: def.projection_path,
      projection_content_hash, compact_stage2, p2s_secondary };
  }

  // inventory: EVERY emitted file (results-relative), raw-file-bytes sha256, sorted — excludes current.json.
  const inventory = Object.keys(tree).sort().map((path) => ({ path, sha256: sha256Hex(tree[path]) }));
  const chain = finalizeChain(chainIds, Object.keys(routes).length);
  const current = { schema: 'spot.ui_results_current.v1', stage1_binding, chain, routes, inventory };
  tree['current.json'] = JSON.stringify(current, null, 2);
  return { tree, current };
}

/**
 * CLI convenience for large, byte-bound Stage-2 artifacts. A small run spec may name the exact W3
 * projection and receipt files instead of embedding a multi-megabyte JSON string. Paths are resolved
 * relative to the spec file; the projection is read as TEXT and passed through verbatim.
 */
export function hydrateStage2FileInputs(spec, baseDir, readText = (path) => readFileSync(path, 'utf8')) {
  if (!spec || typeof spec !== 'object' || !spec.routes || typeof spec.routes !== 'object') return spec;
  for (const route of ['targets', 'pathways']) {
    const input = spec.routes[route];
    if (!input || typeof input !== 'object') continue;
    if (input.projection_text === undefined && typeof input.projection_file === 'string') {
      input.projection_text = readText(resolve(baseDir, input.projection_file));
    }
    if (input.display_verifier_receipt === undefined && typeof input.display_verifier_receipt_file === 'string') {
      input.display_verifier_receipt = JSON.parse(readText(resolve(baseDir, input.display_verifier_receipt_file)));
    }
    if (route === 'targets' && input.p2s_projection_text === undefined &&
        typeof input.p2s_projection_file === 'string') {
      input.p2s_projection_text = readText(resolve(baseDir, input.p2s_projection_file));
    }
    if (route === 'targets' && input.p2s_verifier_receipt_text === undefined &&
        typeof input.p2s_verifier_receipt_file === 'string') {
      input.p2s_verifier_receipt_text = readText(resolve(baseDir, input.p2s_verifier_receipt_file));
    }
  }
  return spec;
}

// ── CLI: write the tree to <out_results_dir>. Only runs when invoked explicitly with a real spec. ──
function main() {
  const [specPath, outDir] = process.argv.slice(2);
  if (!specPath || !outDir) {
    console.error('usage: pack_ui_projections.mjs <spec.json> <out_results_dir>');
    process.exit(2);
  }
  const spec = hydrateStage2FileInputs(JSON.parse(readFileSync(specPath, 'utf8')), dirname(resolve(specPath)));
  const { tree } = pack(spec);
  for (const [rel, text] of Object.entries(tree)) {
    const dst = join(outDir, rel);
    mkdirSync(dirname(dst), { recursive: true });
    writeFileSync(dst, text);
  }
  console.log(`wrote ${Object.keys(tree).length} file(s) under ${outDir} (results/ tree)`);
}

if (import.meta.url === `file://${process.argv[1]}`) main();
