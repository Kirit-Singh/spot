// The browser consumes W3's compact display projection and verifies its method-versioned per-arm
// cap/policy, source hashes, counts, and native-row-equality receipt against the exact rows it will
// render — failing closed on any mismatch. It applies NO further sort/cap/pair-ranking of its own.

import { describe, expect, it } from 'vitest';
import { verifyDisplayProjection } from '../displayProjectionAdapter';
import { AdapterError } from '../errors';
import { canonicalJson, sha256Hex } from '../../stage1/canonical';

const ROWS = [
  { target: 'ENSG1', effect: -0.2, rank: 1 },
  { target: 'ENSG2', effect: -0.1, rank: 2 },
];

async function validPolicy(rows: unknown[] = ROWS, over: Record<string, unknown> = {}) {
  const receipt = await sha256Hex(canonicalJson(rows));
  return {
    projection_method_version: 'spot.stage02.display_projection.v1',
    per_arm_cap: 25,
    projection_policy: 'top_n_by_native_rank_no_recompute',
    counts: { n_total: 100, n_evaluable: 40, n_emitted: rows.length },
    source_raw_sha256: 'a'.repeat(64),
    source_canonical_sha256: 'b'.repeat(64),
    native_row_equality_receipt: receipt,
    artifact_download_refs: ['results/stage02/direct/Rest.parquet'],
    ...over,
  };
}

describe('verifyDisplayProjection — W3 compact display policy + native-row receipt (fail-closed)', () => {
  it('accepts a valid policy whose receipt matches the exact emitted rows', async () => {
    const p = await verifyDisplayProjection(await validPolicy(), ROWS);
    expect(p.per_arm_cap).toBe(25);
    expect(p.counts.n_emitted).toBe(2);
    expect(p.artifact_download_refs.length).toBe(1);
  });
  it('fails closed on an UNVERSIONED projection method', async () => {
    await expect(verifyDisplayProjection(await validPolicy(ROWS, { projection_method_version: 'x' }), ROWS)).rejects.toBeInstanceOf(AdapterError);
  });
  it('fails closed when n_emitted exceeds the per-arm cap', async () => {
    await expect(verifyDisplayProjection(await validPolicy(ROWS, { per_arm_cap: 1 }), ROWS)).rejects.toThrow(/exceeds per_arm_cap/);
  });
  it('fails closed on non-monotonic counts (emitted > evaluable)', async () => {
    await expect(verifyDisplayProjection(await validPolicy(ROWS, { counts: { n_total: 100, n_evaluable: 1, n_emitted: 2 } }), ROWS)).rejects.toThrow(/n_emitted <= n_evaluable/);
  });
  it('fails closed when n_emitted != the rows the browser would render (no client cap/expand)', async () => {
    await expect(verifyDisplayProjection(await validPolicy(ROWS, { counts: { n_total: 100, n_evaluable: 40, n_emitted: 5 } }), ROWS)).rejects.toThrow(/no browser cap\/expand/);
  });
  it('fails closed when the native-row-equality receipt does not match (tampered/reordered rows)', async () => {
    const policy = await validPolicy(ROWS); // receipt bound to ROWS
    const tampered = [{ ...ROWS[0], effect: -0.99 }, ROWS[1]];
    await expect(verifyDisplayProjection(policy, tampered)).rejects.toThrow(/receipt mismatch/);
  });
  it('fails closed without an authoritative downloadable artifact ref', async () => {
    await expect(verifyDisplayProjection(await validPolicy(ROWS, { artifact_download_refs: [] }), ROWS)).rejects.toThrow(/artifact_download_refs/);
  });
  it('fails closed on a missing/short source hash', async () => {
    await expect(verifyDisplayProjection(await validPolicy(ROWS, { source_raw_sha256: 'short' }), ROWS)).rejects.toBeInstanceOf(AdapterError);
  });
});
