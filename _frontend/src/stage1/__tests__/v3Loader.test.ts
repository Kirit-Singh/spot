import { describe, expect, it } from 'vitest';
import { sha256Hex } from '../canonical';
import { assertCurrentV3, joinV3Scores, verifyBindings, loadV3, LoaderError } from '../v3Loader';

const V3 = 'stage1-continuous-v3.0.1';

// Minimal synthetic file set with correct raw_sha256 bindings (no dependency on the 40k artifacts).
async function makeFiles() {
  const registry = JSON.stringify({ schema_version: 'spot.stage01_program_registry.v3', method_version: V3 });
  const overlay = JSON.stringify({
    schema: 'spot.stage01_umap_overlay.v3',
    method_version: V3,
    n_cells: 2,
    score_fields: ['treg_like_score', 'th1_like_score'],
    cells: [
      { barcode: 'BC1', x: 0.1, y: 0.2, treg_like_score: 0.5, th1_like_score: -0.3 },
      { barcode: 'BC2', x: 0.3, y: 0.4, treg_like_score: 0.1, th1_like_score: 0.2 },
    ],
  });
  const summary = JSON.stringify({ schema: 'spot.stage01_summary.v3', method_version: V3 });
  const validation = JSON.stringify({ schema: 'spot.stage01_validation.v1', method_version: V3 });
  const seed = JSON.stringify({ cells: [{ barcode: 'BC1', x: 0.1, y: 0.2 }, { barcode: 'BC2', x: 0.3, y: 0.4 }] });
  const current = JSON.stringify({
    schema: 'spot.stage01_current.v3',
    method_version: V3,
    measurement_display_release: {
      method_version: V3,
      registry: { raw_sha256: await sha256Hex(registry) },
      overlay: { raw_sha256: await sha256Hex(overlay) },
      summary: { raw_sha256: await sha256Hex(summary) },
      validation_raw_sha256: await sha256Hex(validation),
      base_portable_programs: ['treg_like'],
    },
  });
  return { current, registry, overlay, summary, validation, seed };
}

function env(files: Record<string, string>) {
  const map: Record<string, string> = {
    'data/stage01_current.json': files.current,
    'data/stage01_umap_seed.json': files.seed,
    'data/stage01_program_registry_v3.json': files.registry,
    'data/stage01_umap_overlay_v3.json': files.overlay,
    'data/stage01_summary_v3.json': files.summary,
    'data/stage01_validation.json': files.validation,
  };
  return (p: string) => (p in map ? Promise.resolve(map[p]) : Promise.reject(new Error('unexpected fetch ' + p)));
}

async function expectReject(fn: () => Promise<unknown>, match: RegExp) {
  await expect(fn()).rejects.toThrow(match);
}

describe('v3 loader — clean load + join', () => {
  it('resolves a clean v3 load and joins the score fields by barcode', async () => {
    const files = await makeFiles();
    const r = await loadV3(env(files));
    expect(r.cur.schema).toBe('spot.stage01_current.v3');
    expect(r.scoreFields.sort()).toEqual(['th1_like_score', 'treg_like_score']);
    expect(r.cells[0].treg_like_score).toBe(0.5); // joined from overlay
    expect(r.cells[0].x).toBe(0.1); // seed coordinate preserved
  });
});

describe('v3 loader — guards reject before any score copy', () => {
  it('rejects a stale non-v3 (v2) current.schema', async () => {
    const files = await makeFiles();
    files.current = JSON.stringify({ ...JSON.parse(files.current), schema: 'spot.stage01_current.v2' });
    await expectReject(() => loadV3(env(files)), /current schema/);
  });

  it('rejects a tampered current.method_version', () => {
    expect(() => assertCurrentV3({ schema: 'spot.stage01_current.v3', method_version: 'v9.9.9' })).toThrow(/current method/);
  });

  it('rejects a research_preview_v3-shaped current (no measurement_display_release)', () => {
    expect(() => assertCurrentV3({ schema: 'spot.stage01_current.v3', method_version: V3, research_preview_v3: {} } as never))
      .toThrow(/measurement_display_release binding incomplete/);
  });

  it('rejects a bad registry raw-sha binding', async () => {
    const files = await makeFiles();
    files.registry = files.registry.replace('v3', 'v3 ');
    await expectReject(() => loadV3(env(files)), /registry sha mismatch/);
  });

  it('rejects a sha-rebound tampered summary.method_version', async () => {
    const files = await makeFiles();
    const summary = JSON.stringify({ schema: 'spot.stage01_summary.v3', method_version: 'v9.9.9' });
    const cur = JSON.parse(files.current);
    cur.measurement_display_release.summary.raw_sha256 = await sha256Hex(summary);
    files.summary = summary;
    files.current = JSON.stringify(cur);
    await expectReject(() => loadV3(env(files)), /summary method/);
  });
});

describe('v3 loader — joinV3Scores field-set gate', () => {
  const cells = [{ barcode: 'BC1', x: 0, y: 0, a_score: 1, b_score: 2 }];
  const overlay = { score_fields: ['a_score', 'b_score'], cells: [{ barcode: 'BC1', x: 0, y: 0, a_score: 1, b_score: 2 }] };

  it('rejects a reserved field injected into score_fields', () => {
    expect(() => joinV3Scores(structuredClone(cells), { ...overlay, score_fields: ['a_score', 'donor'] } as never)).toThrow(/reserved field/);
  });
  it('rejects an omitted expected score field', () => {
    expect(() => joinV3Scores(structuredClone(cells), { ...overlay, score_fields: ['a_score'] } as never)).toThrow(/score-field set mismatch/);
  });
  it('rejects an unknown score field', () => {
    expect(() => joinV3Scores(structuredClone(cells), { ...overlay, score_fields: ['a_score', 'b_score', 'bogus'] } as never)).toThrow(/score-field set mismatch/);
  });
  it('is a LoaderError', () => {
    try { assertCurrentV3({ schema: 'x' }); } catch (e) { expect(e).toBeInstanceOf(LoaderError); }
  });

  it('verifyBindings validates all four artifact texts', async () => {
    const files = await makeFiles();
    const mdr = assertCurrentV3(JSON.parse(files.current));
    await expect(verifyBindings(mdr, { registry: files.registry, overlay: files.overlay, summary: files.summary, validation: files.validation })).resolves.toBeUndefined();
  });
});
