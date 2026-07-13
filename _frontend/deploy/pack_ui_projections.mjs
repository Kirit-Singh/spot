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
// spot.stage02_display_projection.v1 document and its generator≠verifier receipt. This packager
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
    projection_schema: 'spot.stage02_display_projection.v1',
  },
  pathways: {
    stage_label: 'Pathways',
    method_id: 'spot.stage02.pathway.ranked_arm_enrichment.v2 · spot.stage02.pathway.signature_convergence.v2',
    projection_path: 'stage02/stage2_display_projection.json',
    projection_schema: 'spot.stage02_display_projection.v1',
  },
  drugs: {
    stage_label: 'Drugs',
    method_id: 'stage3-druglink-v4-workflow-states · schema spot.stage03_drug_annotation.v1',
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
const STAGE2_METHOD = 'spot.stage02.display_projection.v1';
const STAGE2_VERIFIER = 'spot.stage02.display_projection.independent_verifier.v1';
const STAGE2_RECEIPT_PATH = 'stage02/display_projection.verification.json';
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
function nOptStr(v, path) { if (v === undefined || v === null) return null; if (typeof v !== 'string') fail(`${path} must be a string or null`); return v; }
function nOptNum(v, path) { if (v === undefined || v === null) return null; if (typeof v !== 'number' || !Number.isFinite(v)) fail(`${path} must be a finite number or null`); return v; }
function nStrList(v, path) { if (v === undefined || v === null) return []; if (!Array.isArray(v) || v.some((x) => typeof x !== 'string')) fail(`${path} must be a string[]`); return v; }
function nArr(v, path) { if (!Array.isArray(v)) fail(`${path} must be an array`); return v; }

// Stage-3 v2 native drug_annotation → compact Drugs projection (fields per §7 "Required Stage-3 UI model").
function nativeToDrugsProjection(nat) {
  nObj(nat, 'drugs native');
  const candidates = nArr(nat.candidates, 'drugs native.candidates').map((c, i) => {
    const p = `drugs native.candidates[${i}]`;
    nObj(c, p);
    return {
      candidate_id: nStr(c.candidate_id, `${p}.candidate_id`),
      active_moiety_id: nOptStr(c.active_moiety_id, `${p}.active_moiety_id`),
      preferred_name: nOptStr(c.preferred_name, `${p}.preferred_name`),
      identity_status: nOptStr(c.identity_status, `${p}.identity_status`),
      form_ids: nStrList(c.form_ids, `${p}.form_ids`),
      target_ensembls: nStrList(c.target_ensembls, `${p}.target_ensembls`),
      n_edges: nOptNum(c.n_edges, `${p}.n_edges`),
      n_direct_gene_edges: nOptNum(c.n_direct_gene_edges, `${p}.n_direct_gene_edges`),
      development_state_aggregate: nOptStr(c.development_state_aggregate, `${p}.development_state_aggregate`),
      n_potency_rows: nOptNum(c.n_potency_rows, `${p}.n_potency_rows`),
      potency_state: nOptStr(c.potency_state, `${p}.potency_state`),
      observed_perturbation_arms: nStrList(c.observed_perturbation_arms, `${p}.observed_perturbation_arms`),
      inverse_direction_support: nOptStr(c.inverse_direction_support, `${p}.inverse_direction_support`),
      pathway_hypothesis_arms: nStrList(c.pathway_hypothesis_arms, `${p}.pathway_hypothesis_arms`),
      stage3_evidence_classes: nStrList(c.stage3_evidence_classes, `${p}.stage3_evidence_classes`),
      disease_context_review_status: nOptStr(c.disease_context_review_status, `${p}.disease_context_review_status`),
      disease_context_review_result: nOptStr(c.disease_context_review_result, `${p}.disease_context_review_result`),
      stage4_assessment_status: nOptStr(c.stage4_assessment_status, `${p}.stage4_assessment_status`),
      source_record_ids: nStrList(c.source_record_ids, `${p}.source_record_ids`),
    };
  });
  return {
    schema_version: 'spot.ui_projection.drugs.v1', route: 'drugs',
    artifact: {
      schema_version: 'spot.stage03_drug_annotation.v1',
      bundle_id: nStr(nat.bundle_id, 'drugs native.bundle_id'),
      manifest_sha256: nStr(nat.manifest_sha256, 'drugs native.manifest_sha256'),
      upstream_stage2_run: nStr(nat.upstream_stage2_run, 'drugs native.upstream_stage2_run'),
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
    routes[route] = { manifest_path, content_hash, projection_path: def.projection_path,
      projection_content_hash, compact_stage2 };
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
