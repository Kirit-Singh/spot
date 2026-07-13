// results/current.json is the single mutable downstream pointer. It is FAIL-CLOSED: a non-object,
// unknown schema, missing/short Stage-1 binding, unknown route key, non-64-hex hash, or half-bound
// projection is rejected. An empty `routes` (all routes unbound) is valid — that is the pre-run state.

import { describe, expect, it } from 'vitest';
import { parseUiResultsCurrent } from '../uiResultsCurrentAdapter';
import { AdapterError } from '../errors';

const H = 'a'.repeat(64);
const BINDING = { release_method_version: 'stage1-continuous-v3.0.1', registry_scorer_view_sha256: H };
const ENTRY = { manifest_path: 'results/manifests/targets.ui_release.json', content_hash: H, projection_path: null, projection_content_hash: null };

describe('parseUiResultsCurrent — fail-closed downstream pointer', () => {
  it('accepts a valid pointer and preserves route entries', () => {
    const c = parseUiResultsCurrent({ schema: 'spot.ui_results_current.v1', stage1_binding: BINDING, routes: { targets: ENTRY } });
    expect(c.schema).toBe('spot.ui_results_current.v1');
    expect(c.stage1_binding.registry_scorer_view_sha256).toBe(H);
    expect(c.routes.targets?.content_hash).toBe(H);
    expect(c.routes.targets?.projection_path).toBeNull();
  });

  it('an empty routes object is valid (all routes unbound — the pre-run state)', () => {
    const c = parseUiResultsCurrent({ schema: 'spot.ui_results_current.v1', stage1_binding: BINDING, routes: {} });
    expect(c.routes).toEqual({});
  });

  it('accepts a fully-bound projection (path + hash together)', () => {
    const entry = { ...ENTRY, projection_path: 'results/stage02/release.json', projection_content_hash: H };
    const c = parseUiResultsCurrent({ schema: 'spot.ui_results_current.v1', stage1_binding: BINDING, routes: { targets: entry } });
    expect(c.routes.targets?.projection_path).toBe('results/stage02/release.json');
  });

  it('rejects a non-object', () => {
    expect(() => parseUiResultsCurrent(null)).toThrow(AdapterError);
    expect(() => parseUiResultsCurrent('x')).toThrow(AdapterError);
  });

  it('rejects an unknown schema', () => {
    expect(() => parseUiResultsCurrent({ schema: 'spot.ui_results_current.v2', stage1_binding: BINDING, routes: {} })).toThrow(/unknown_schema_version|expected/);
  });

  it('rejects a missing / malformed stage1_binding', () => {
    expect(() => parseUiResultsCurrent({ schema: 'spot.ui_results_current.v1', routes: {} })).toThrow(AdapterError);
    expect(() => parseUiResultsCurrent({ schema: 'spot.ui_results_current.v1', stage1_binding: { release_method_version: 'v', registry_scorer_view_sha256: 'short' }, routes: {} })).toThrow(AdapterError);
  });

  it('rejects an unknown route key', () => {
    expect(() => parseUiResultsCurrent({ schema: 'spot.ui_results_current.v1', stage1_binding: BINDING, routes: { bogus: ENTRY } })).toThrow(AdapterError);
  });

  it('rejects a route content_hash that is not 64-hex', () => {
    const entry = { ...ENTRY, content_hash: 'not-a-hash' };
    expect(() => parseUiResultsCurrent({ schema: 'spot.ui_results_current.v1', stage1_binding: BINDING, routes: { drugs: entry } })).toThrow(AdapterError);
  });

  it('rejects a HALF-bound projection (path without hash, or hash without path)', () => {
    const halfA = { ...ENTRY, projection_path: 'results/stage02/x.json', projection_content_hash: null };
    const halfB = { ...ENTRY, projection_path: null, projection_content_hash: H };
    expect(() => parseUiResultsCurrent({ schema: 'spot.ui_results_current.v1', stage1_binding: BINDING, routes: { targets: halfA } })).toThrow(AdapterError);
    expect(() => parseUiResultsCurrent({ schema: 'spot.ui_results_current.v1', stage1_binding: BINDING, routes: { targets: halfB } })).toThrow(AdapterError);
  });
});
