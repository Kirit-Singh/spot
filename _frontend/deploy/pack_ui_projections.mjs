#!/usr/bin/env node
// Offline DETERMINISTIC UI-projection packager. Given an admitted-run pack spec (compact route
// projections already mapped from the native Stage-2/3/4 bundles, plus each route's admitted RECEIPT
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
// Native→compact field mapping is intentionally OUT OF SCOPE here (see
// docs W1/W6/W16 handoff): W1/W6 supply compact projections that pass the browser's strict adapters;
// this packager is the deterministic assembly + content-addressing + manifest/receipt binding step.

import { createHash } from 'node:crypto';
import { readFileSync, mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';

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
    projection_path: 'stage02/targets.ui.json',
    projection_schema: 'spot.ui_projection.stage2.v1',
  },
  pathways: {
    stage_label: 'Pathways',
    method_id: 'spot.stage02.pathway.ranked_arm_enrichment.v2 · spot.stage02.pathway.signature_convergence.v2',
    projection_path: 'stage02/pathways.ui.json',
    projection_schema: 'spot.ui_projection.stage2.v1',
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

function fail(msg) {
  throw new Error('pack: ' + msg);
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
// The packager DERIVES the four compact route projections from the admitted native bundles; compact
// rows are never hand-authored. These adapters are STRICT on required ids + types and LENIENT on
// absence (a missing optional value stays null / [] — "missing stays missing", never invented). The
// native FIELD NAMES below follow the current handoff (§6 Stage-2, §7 Stage-3 v2, §8 Stage-4);
// PIN THEM against the final producer schemas when W16 (Stage-2), W6 (Stage-3 v2) and W1 (Stage-4)
// publish — the mapping is the intended pinning point, not a guess to ship blind.
function nObj(v, path) { if (!v || typeof v !== 'object' || Array.isArray(v)) fail(`${path} must be an object`); return v; }
function nStr(v, path) { if (typeof v !== 'string' || v.trim() === '') fail(`${path} must be a non-empty string`); return v; }
function nOptStr(v, path) { if (v === undefined || v === null) return null; if (typeof v !== 'string') fail(`${path} must be a string or null`); return v; }
function nOptNum(v, path) { if (v === undefined || v === null) return null; if (typeof v !== 'number' || !Number.isFinite(v)) fail(`${path} must be a finite number or null`); return v; }
function nOptBool(v, path) { if (v === undefined || v === null) return null; if (typeof v !== 'boolean') fail(`${path} must be a boolean or null`); return v; }
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

// Stage-4 native scorecards → compact PK & Safety projection (fields per §8 "Required Stage-4 UI model").
const S4_LANES = ['delivery', 'cns_mpo', 'transporters', 'exposure', 'nebpi', 'safety'];
function nativeToPkSafetyProjection(nat) {
  nObj(nat, 'pksafety native');
  const candidates = nArr(nat.candidates, 'pksafety native.candidates').map((c, i) => {
    const p = `pksafety native.candidates[${i}]`;
    nObj(c, p);
    const lanesRaw = c.lanes && typeof c.lanes === 'object' && !Array.isArray(c.lanes) ? c.lanes : {};
    const lanes = {};
    for (const l of S4_LANES) lanes[l] = nOptStr(lanesRaw[l], `${p}.lanes.${l}`);
    return {
      candidate_id: nStr(c.candidate_id, `${p}.candidate_id`),
      active_moiety: nOptStr(c.active_moiety, `${p}.active_moiety`),
      compound_ids: nStrList(c.compound_ids, `${p}.compound_ids`),
      target: nOptStr(c.target, `${p}.target`),
      mechanism: nOptStr(c.mechanism, `${p}.mechanism`),
      production_eligible: nOptBool(c.production_eligible, `${p}.production_eligible`),
      production_eligible_reason: nOptStr(c.production_eligible_reason, `${p}.production_eligible_reason`),
      lanes,
    };
  });
  return {
    schema_version: 'spot.ui_projection.pksafety.v1', route: 'pksafety',
    artifact: {
      schema_version: 'spot.stage04_scorecards.v1',
      scorecard_set_id: nStr(nat.scorecard_set_id, 'pksafety native.scorecard_set_id'),
      stage4_method_version: nStr(nat.stage4_method_version, 'pksafety native.stage4_method_version'),
      upstream_stage3_bundle: nStr(nat.upstream_stage3_bundle, 'pksafety native.upstream_stage3_bundle'),
      candidates,
    },
  };
}

// Stage-2 native aggregate → compact projection. Converts native base_records[]/arms[] (arrays, §6)
// into objects keyed by base_key/arm_key WITHOUT changing any value (deterministic reserialization).
function arrToObj(arr, keyField, path) {
  if (arr === undefined || arr === null) return {};
  const obj = {};
  nArr(arr, path).forEach((e, i) => {
    nObj(e, `${path}[${i}]`);
    obj[nStr(e[keyField], `${path}[${i}].${keyField}`)] = e;
  });
  return obj;
}
function nativeToStage2Bundle(nat, path) {
  if (nat === undefined || nat === null) return null;
  nObj(nat, path);
  const out = { ...nat };
  if ('base_records' in nat) out.base_records = arrToObj(nat.base_records, 'base_key', `${path}.base_records`);
  if ('arms' in nat) out.arms = arrToObj(nat.arms, 'arm_key', `${path}.arms`);
  return out; // arm.records stays a native array (the browser NativeTemporalArm expects an array)
}
function mapNativeBundles(nat, path) {
  if (nat === undefined || nat === null) return {};
  nObj(nat, path);
  const out = {};
  for (const k of Object.keys(nat)) out[k] = nativeToStage2Bundle(nat[k], `${path}.${k}`);
  return out;
}
// Pack-time completeness: the COMPLETE generic release must carry every Direct condition bundle, every
// ORDERED temporal pair, and every (condition, source) pathway bundle — refuse to emit an incomplete one.
function assertStage2Complete(conds, sources, direct, temporal, pathway) {
  for (const c of conds) if (!(c in direct)) fail(`stage-2 incomplete: missing Direct bundle for condition "${c}"`);
  for (const from of conds) for (const to of conds) {
    if (from !== to && !(`${from}__${to}` in temporal)) fail(`stage-2 incomplete: missing temporal bundle "${from}__${to}"`);
  }
  for (const c of conds) for (const s of sources) if (!(`${c}|${s}` in pathway)) fail(`stage-2 incomplete: missing pathway bundle "${c}|${s}"`);
}
function nativeToStage2Projection(nat, route) {
  nObj(nat, 'stage2 native aggregate');
  const release_conditions = nStrList(nat.release_conditions, 'stage2 native.release_conditions');
  const pathway_sources = nStrList(nat.pathway_sources, 'stage2 native.pathway_sources');
  const pathway_source = nStr(nat.pathway_source, 'stage2 native.pathway_source');
  const directByCondition = mapNativeBundles(nat.directByCondition, 'stage2 native.directByCondition');
  const temporalByPair = mapNativeBundles(nat.temporalByPair, 'stage2 native.temporalByPair');
  const pathwayByContext = mapNativeBundles(nat.pathwayByContext, 'stage2 native.pathwayByContext');
  assertStage2Complete(release_conditions, pathway_sources, directByCondition, temporalByPair, pathwayByContext);
  return {
    schema_version: 'spot.ui_projection.stage2.v1', route,
    run_id: nStr(nat.run_id, 'stage2 native.run_id'),
    // no top-level analysis_mode — the all-arm release serves both within + temporal; the active
    // selection decides at join time.
    release_conditions, pathway_sources, pathway_source,
    directByCondition, temporalByPair, pathwayByContext,
  };
}

/** Accumulate the admitted cross-stage chain ids from each route's derived projection. */
function collectChain(route, projection, ids) {
  if (route === 'targets' || route === 'pathways') {
    if (ids.stage2_run_id !== null && ids.stage2_run_id !== projection.run_id) {
      fail(`chain: stage-2 run_id differs across routes ("${ids.stage2_run_id}" vs "${projection.run_id}")`);
    }
    ids.stage2_run_id = projection.run_id;
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
  if (nRoutes > 0 && ids.stage2_run_id === null) {
    fail('chain: a bound release requires a Stage-2 route (targets/pathways) to anchor stage2_run_id');
  }
  return { stage2_run_id: ids.stage2_run_id, stage3_bundle_id: ids.stage3_bundle_id, stage4_scorecard_set_id: ids.stage4_scorecard_set_id };
}

/** Derive the compact route projection from that route's admitted NATIVE bundle(s). */
export function deriveCompactProjection(route, native) {
  if (native === undefined || native === null) {
    fail(`${route} native input required — the packager derives compact projections from admitted native bundles, never hand-authored rows`);
  }
  if (route === 'targets' || route === 'pathways') return nativeToStage2Projection(native, route);
  if (route === 'drugs') return nativeToDrugsProjection(native);
  if (route === 'pksafety') return nativeToPkSafetyProjection(native);
  return fail(`unknown route "${route}"`);
}

/**
 * Assemble the virtual served results/ tree from a pack spec. Each route supplies its admitted NATIVE
 * bundle + admitted RECEIPT; the packager DERIVES the compact projection, then content-addresses +
 * packages. Returns { tree, current } (results-relative path → text). A route absent from spec.routes is
 * not emitted (unbound). Throws on any malformed native input / missing receipt field / non-admitted verifier.
 */
export function pack(spec) {
  if (!spec || typeof spec !== 'object') fail('spec must be an object');
  const stage1_binding = requireBinding(spec.stage1_binding);
  const routesIn = spec.routes && typeof spec.routes === 'object' ? spec.routes : {};

  const tree = {}; // results-relative path → text (pretty JSON; hashes are over the canonical form / raw bytes)
  const routes = {};
  const chainIds = { stage2_run_id: null, stage3_bundle_id: null, stage4_scorecard_set_id: null, _drugsUpstream: null, _pksafetyUpstream: null };
  for (const route of Object.keys(routesIn)) {
    const def = ROUTES[route];
    if (!def) fail(`unknown route "${route}"`);
    const { native, receipt } = routesIn[route] || {};
    const projection = deriveCompactProjection(route, native); // derived from native — never hand-authored
    validateProjectionEnvelope(route, def, projection);
    collectChain(route, projection, chainIds);

    tree[def.projection_path] = JSON.stringify(projection, null, 2);
    const projection_content_hash = canonicalHash(projection);

    const manifest = buildManifest(route, def, receipt);
    const manifest_path = `manifests/${route}.ui_release.json`;
    tree[manifest_path] = JSON.stringify(manifest, null, 2);
    const content_hash = canonicalHash(manifest);

    routes[route] = { manifest_path, content_hash, projection_path: def.projection_path, projection_content_hash };
  }

  // inventory: EVERY emitted file (results-relative), raw-file-bytes sha256, sorted — excludes current.json.
  const inventory = Object.keys(tree).sort().map((path) => ({ path, sha256: sha256Hex(tree[path]) }));
  const chain = finalizeChain(chainIds, Object.keys(routes).length);
  const current = { schema: 'spot.ui_results_current.v1', stage1_binding, chain, routes, inventory };
  tree['current.json'] = JSON.stringify(current, null, 2);
  return { tree, current };
}

// ── CLI: write the tree to <out_results_dir>. Only runs when invoked explicitly with a real spec. ──
function main() {
  const [specPath, outDir] = process.argv.slice(2);
  if (!specPath || !outDir) {
    console.error('usage: pack_ui_projections.mjs <spec.json> <out_results_dir>');
    process.exit(2);
  }
  const spec = JSON.parse(readFileSync(specPath, 'utf8'));
  const { tree } = pack(spec);
  for (const [rel, text] of Object.entries(tree)) {
    const dst = join(outDir, rel);
    mkdirSync(dirname(dst), { recursive: true });
    writeFileSync(dst, text);
  }
  console.log(`wrote ${Object.keys(tree).length} file(s) under ${outDir} (results/ tree)`);
}

if (import.meta.url === `file://${process.argv[1]}`) main();
