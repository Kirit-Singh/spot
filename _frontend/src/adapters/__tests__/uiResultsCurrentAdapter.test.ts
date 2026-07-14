// results/current.json is the single mutable downstream pointer. It is FAIL-CLOSED: a non-object,
// unknown schema, missing/short Stage-1 binding, unknown route key, non-64-hex hash, or half-bound
// projection is rejected. An empty `routes` (all routes unbound) is valid — that is the pre-run state.

import { describe, expect, it } from 'vitest';
import { parseUiResultsCurrent } from '../uiResultsCurrentAdapter';
import { AdapterError } from '../errors';

const H = 'a'.repeat(64);
const BINDING = {
  release_method_version: 'stage1-continuous-v3.0.1',
  registry_scorer_view_sha256: H,
  selection_schema_raw_sha256: 'b'.repeat(64),
  release_self_sha256: 'c'.repeat(64),
};
const CHAIN = { stage2_display_release_id: 'display_1', stage2_run_id: null,
  stage3_bundle_id: null, stage4_scorecard_set_id: null };
const ENTRY = { manifest_path: 'results/manifests/targets.ui_release.json', content_hash: H, projection_path: null, projection_content_hash: null, compact_stage2: null };
const COMPACT = {
  schema_version: 'spot.ui_compact_stage2_release.v1', display_release_id: 'display_1',
  release_conditions: ['Rest', 'Stim8hr', 'Stim48hr'], pathway_sources: ['go_bp'], active_pathway_source: 'go_bp',
  projection_raw_sha256: 'd'.repeat(64), projection_canonical_sha256: H, projection_self_sha256: 'e'.repeat(64),
  independent_verifier: {
    verifier_id: 'spot.stage02.display_projection.independent_verifier.v1',
    receipt_path: 'stage02/display.verify.json', receipt_raw_sha256: 'f'.repeat(64), receipt_canonical_sha256: '1'.repeat(64),
  },
};

describe('parseUiResultsCurrent — fail-closed downstream pointer', () => {
  it('accepts a valid pointer and preserves route entries', () => {
    const c = parseUiResultsCurrent({ schema: 'spot.ui_results_current.v1', stage1_binding: BINDING, chain: CHAIN, routes: { targets: ENTRY } });
    expect(c.schema).toBe('spot.ui_results_current.v1');
    expect(c.stage1_binding.registry_scorer_view_sha256).toBe(H);
    expect(c.routes.targets?.content_hash).toBe(H);
    expect(c.routes.targets?.projection_path).toBeNull();
  });

  it('an empty routes object is valid (all routes unbound — the pre-run state)', () => {
    const c = parseUiResultsCurrent({ schema: 'spot.ui_results_current.v1', stage1_binding: BINDING, chain: CHAIN, routes: {} });
    expect(c.routes).toEqual({});
  });

  it('accepts a fully-bound projection (path + hash together)', () => {
    const entry = { ...ENTRY, projection_path: 'stage02/release.json', projection_content_hash: H, compact_stage2: COMPACT };
    const c = parseUiResultsCurrent({ schema: 'spot.ui_results_current.v1', stage1_binding: BINDING, chain: CHAIN, routes: { targets: entry } });
    expect(c.routes.targets?.projection_path).toBe('stage02/release.json');
  });

  it('rejects a non-object', () => {
    expect(() => parseUiResultsCurrent(null)).toThrow(AdapterError);
    expect(() => parseUiResultsCurrent('x')).toThrow(AdapterError);
  });

  it('rejects an unknown schema', () => {
    expect(() => parseUiResultsCurrent({ schema: 'spot.ui_results_current.v2', stage1_binding: BINDING, chain: CHAIN, routes: {} })).toThrow(/unknown_schema_version|expected/);
  });

  it('rejects a missing / malformed stage1_binding', () => {
    expect(() => parseUiResultsCurrent({ schema: 'spot.ui_results_current.v1', routes: {} })).toThrow(AdapterError);
    expect(() => parseUiResultsCurrent({ schema: 'spot.ui_results_current.v1', stage1_binding: { release_method_version: 'v', registry_scorer_view_sha256: 'short' }, routes: {} })).toThrow(AdapterError);
    // the 539431d release-identity hashes are required + 64-hex (shape); absent/short → rejected
    const noSchemaRaw = { release_method_version: 'v', registry_scorer_view_sha256: H, release_self_sha256: 'c'.repeat(64) };
    expect(() => parseUiResultsCurrent({ schema: 'spot.ui_results_current.v1', stage1_binding: noSchemaRaw, chain: CHAIN, routes: {} })).toThrow(AdapterError);
    const shortReleaseSelf = { ...BINDING, release_self_sha256: 'deadbeef' };
    expect(() => parseUiResultsCurrent({ schema: 'spot.ui_results_current.v1', stage1_binding: shortReleaseSelf, chain: CHAIN, routes: {} })).toThrow(AdapterError);
  });

  it('rejects a missing display release id while allowing the production run id to remain null', () => {
    expect(() => parseUiResultsCurrent({ schema: 'spot.ui_results_current.v1', stage1_binding: BINDING, routes: {} })).toThrow(AdapterError);
    expect(() => parseUiResultsCurrent({ schema: 'spot.ui_results_current.v1', stage1_binding: BINDING, chain: { stage3_bundle_id: null, stage4_scorecard_set_id: null }, routes: {} })).toThrow(AdapterError);
  });

  it('rejects an unknown route key', () => {
    expect(() => parseUiResultsCurrent({ schema: 'spot.ui_results_current.v1', stage1_binding: BINDING, chain: CHAIN, routes: { bogus: ENTRY } })).toThrow(AdapterError);
  });

  it('rejects a route content_hash that is not 64-hex', () => {
    const entry = { ...ENTRY, content_hash: 'not-a-hash' };
    expect(() => parseUiResultsCurrent({ schema: 'spot.ui_results_current.v1', stage1_binding: BINDING, chain: CHAIN, routes: { drugs: entry } })).toThrow(AdapterError);
  });

  it('rejects a HALF-bound projection (path without hash, or hash without path)', () => {
    const halfA = { ...ENTRY, projection_path: 'results/stage02/x.json', projection_content_hash: null };
    const halfB = { ...ENTRY, projection_path: null, projection_content_hash: H };
    expect(() => parseUiResultsCurrent({ schema: 'spot.ui_results_current.v1', stage1_binding: BINDING, chain: CHAIN, routes: { targets: halfA } })).toThrow(AdapterError);
    expect(() => parseUiResultsCurrent({ schema: 'spot.ui_results_current.v1', stage1_binding: BINDING, chain: CHAIN, routes: { targets: halfB } })).toThrow(AdapterError);
  });

  it('requires exact compact release metadata for bound Stage-2 routes and cross-checks run/hash', () => {
    const base = { ...ENTRY, projection_path: 'stage02/release.json', projection_content_hash: H };
    expect(() => parseUiResultsCurrent({ schema: 'spot.ui_results_current.v1', stage1_binding: BINDING, chain: CHAIN, routes: { targets: base } })).toThrow(/compact_stage2/);
    expect(() => parseUiResultsCurrent({ schema: 'spot.ui_results_current.v1', stage1_binding: BINDING, chain: CHAIN, routes: { targets: { ...base, compact_stage2: { ...COMPACT, display_release_id: 'other' } } } })).toThrow(/display_release_id/);
    expect(() => parseUiResultsCurrent({ schema: 'spot.ui_results_current.v1', stage1_binding: BINDING, chain: CHAIN, routes: { targets: { ...base, compact_stage2: { ...COMPACT, projection_canonical_sha256: '2'.repeat(64) } } } })).toThrow(/canonical hash/);
  });

  it('rejects reordered release metadata and compact metadata on Stage-3/4 routes', () => {
    const base = { ...ENTRY, projection_path: 'stage02/release.json', projection_content_hash: H };
    expect(() => parseUiResultsCurrent({ schema: 'spot.ui_results_current.v1', stage1_binding: BINDING, chain: CHAIN, routes: { pathways: { ...base, compact_stage2: { ...COMPACT, release_conditions: ['Stim8hr', 'Rest', 'Stim48hr'] } } } })).toThrow(/exactly/);
    expect(() => parseUiResultsCurrent({ schema: 'spot.ui_results_current.v1', stage1_binding: BINDING, chain: CHAIN, routes: { drugs: { ...base, compact_stage2: COMPACT } } })).toThrow(/only valid/);
  });

  it('rejects unknown compact metadata and verifier fields', () => {
    const base = { ...ENTRY, projection_path: 'stage02/release.json', projection_content_hash: H };
    expect(() => parseUiResultsCurrent({ schema: 'spot.ui_results_current.v1', stage1_binding: BINDING, chain: CHAIN, routes: {
      targets: { ...base, compact_stage2: { ...COMPACT, inferred_order: ['Rest'] } },
    } })).toThrow(/fields/);
    expect(() => parseUiResultsCurrent({ schema: 'spot.ui_results_current.v1', stage1_binding: BINDING, chain: CHAIN, routes: {
      targets: { ...base, compact_stage2: { ...COMPACT, independent_verifier: { ...COMPACT.independent_verifier, verdict: 'admit' } } },
    } })).toThrow(/fields/);
  });

  it('rejects different compact release metadata across targets and pathways', () => {
    const base = { ...ENTRY, projection_path: 'stage02/release.json', projection_content_hash: H };
    expect(() => parseUiResultsCurrent({ schema: 'spot.ui_results_current.v1', stage1_binding: BINDING, chain: CHAIN, routes: {
      targets: { ...base, compact_stage2: COMPACT },
      // GO-BP-only leaves active_pathway_source with a single legal value, so the cross-route
      // agreement gate is exercised on a field that CAN still legitimately differ.
      pathways: { ...base, compact_stage2: { ...COMPACT, projection_raw_sha256: 'b'.repeat(64) } },
    } })).toThrow(/metadata disagree/);
  });
});
