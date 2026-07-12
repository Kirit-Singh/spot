// Stage-1 v3 browser-loader — migrated from the authoritative reference
// (01_programs/analysis/test_v3_loader_mutation.mjs) and the real 01_page.html loader,
// fixed for the truthful v3 shape: current.schema === spot.stage01_current.v3 and the
// binding block is `measurement_display_release` (was research_preview_v3). Every guard
// rejects BEFORE any score is copied; there is no fallback to v2.

import { sha256Hex } from './canonical';

export const V3_METHOD_ID = 'stage1-continuous-v3.0.1';
export const CURRENT_SCHEMA_V3 = 'spot.stage01_current.v3';
const RESERVED = new Set(['barcode', 'x', 'y', 'donor', 'condition', 'cluster']);
const COORD_KEYS = ['barcode', 'x', 'y'];

export class LoaderError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'LoaderError';
  }
}
const fail = (message: string): never => {
  throw new LoaderError(message);
};

export interface MeasurementDisplayRelease {
  method_version: string;
  registry: { raw_sha256: string };
  overlay: { raw_sha256: string };
  summary: { raw_sha256: string };
  validation_raw_sha256: string;
  base_portable_programs: string[];
}

interface Cur {
  schema?: unknown;
  method_version?: unknown;
  measurement_display_release?: unknown;
}

/** Guard: current pointer is truthful v3 and carries a complete measurement_display_release. */
export function assertCurrentV3(cur: Cur): MeasurementDisplayRelease {
  if (cur.schema !== CURRENT_SCHEMA_V3) fail('current schema != ' + CURRENT_SCHEMA_V3);
  if (cur.method_version !== V3_METHOD_ID) fail('current method != ' + V3_METHOD_ID);
  const mdr = cur.measurement_display_release as MeasurementDisplayRelease | undefined;
  if (
    !mdr || !mdr.registry || !mdr.overlay || !mdr.summary || !mdr.validation_raw_sha256 ||
    !Array.isArray(mdr.base_portable_programs)
  ) {
    fail('measurement_display_release binding incomplete');
  }
  if ((mdr as MeasurementDisplayRelease).method_version !== V3_METHOD_ID) {
    fail('measurement_display_release method != ' + V3_METHOD_ID);
  }
  return mdr as MeasurementDisplayRelease;
}

/**
 * Verify the raw_sha256 bindings of the fetched artifact TEXTS against the
 * measurement_display_release, and re-check the v3 method-version inside summary +
 * validation (catches sha-rebound tampering).
 */
export async function verifyBindings(
  mdr: MeasurementDisplayRelease,
  texts: { registry: string; overlay: string; summary: string; validation: string },
  sha: (t: string) => Promise<string> = sha256Hex,
): Promise<void> {
  if ((await sha(texts.registry)) !== mdr.registry.raw_sha256) fail('registry sha mismatch');
  if ((await sha(texts.overlay)) !== mdr.overlay.raw_sha256) fail('overlay sha mismatch');
  if ((await sha(texts.summary)) !== mdr.summary.raw_sha256) fail('summary sha mismatch');
  if ((await sha(texts.validation)) !== mdr.validation_raw_sha256) fail('validation sha mismatch');
  const summary = JSON.parse(texts.summary);
  if (summary.method_version !== V3_METHOD_ID) fail('summary method != ' + V3_METHOD_ID);
  const validation = JSON.parse(texts.validation);
  if (validation.method_version !== V3_METHOD_ID) fail('validation method != ' + V3_METHOD_ID);
}

interface Cell {
  barcode: string;
  [k: string]: unknown;
}
interface Overlay {
  score_fields: string[];
  cells: Cell[];
}

/**
 * Join v3 scores onto the frozen coordinate shell by EXACT barcode. The declared
 * score_fields must equal the overlay cell columns minus the coordinate keys, must not
 * collide with a reserved seed field, and every seed barcode must be present. Copies
 * ONLY score fields; seed coordinates are preserved. Returns the joined score fields.
 */
export function joinV3Scores(cells: Cell[], overlay: Overlay): string[] {
  const sf = overlay.score_fields ?? [];
  for (const f of sf) if (RESERVED.has(f)) fail('reserved field in score_fields: ' + f);
  if (new Set(sf).size !== sf.length) fail('duplicate score fields');
  const expected = Object.keys(overlay.cells[0]).filter((k) => !COORD_KEYS.includes(k)).sort();
  const declared = [...sf].sort();
  if (declared.length !== expected.length || declared.some((d, i) => d !== expected[i])) {
    fail('score-field set mismatch (declared vs overlay columns)');
  }
  const map = new Map<string, Cell>();
  overlay.cells.forEach((c) => map.set(c.barcode, c));
  if (map.size !== overlay.cells.length) fail('duplicate barcodes in overlay');
  cells.forEach((c) => {
    const s = map.get(c.barcode);
    if (!s) fail('overlay barcode-set mismatch — refusing to join: ' + c.barcode);
    sf.forEach((f) => (c[f] = (s as Cell)[f]));
  });
  return sf;
}

/** Browser orchestrator: fetch + verify + join. `fetchText` fetches a `data/…` path. */
export async function loadV3(fetchText: (path: string) => Promise<string>) {
  const cur = JSON.parse(await fetchText('data/stage01_current.json'));
  const mdr = assertCurrentV3(cur);
  const seed = JSON.parse(await fetchText('data/stage01_umap_seed.json'));
  const texts = {
    registry: await fetchText('data/stage01_program_registry_v3.json'),
    overlay: await fetchText('data/stage01_umap_overlay_v3.json'),
    summary: await fetchText('data/stage01_summary_v3.json'),
    validation: await fetchText('data/stage01_validation.json'),
  };
  await verifyBindings(mdr, texts);
  const overlay: Overlay = JSON.parse(texts.overlay);
  const cells: Cell[] = seed.cells;
  const scoreFields = joinV3Scores(cells, overlay);
  return { cur, mdr, cells, overlay, scoreFields };
}
