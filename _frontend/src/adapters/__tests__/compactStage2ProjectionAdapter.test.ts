import { describe, expect, it } from 'vitest';
import { parseCompactDisplayReceipt, parseCompactStage2Projection } from '../compactStage2ProjectionAdapter';
import { canonicalJson, sha256Hex } from '../../stage1/canonical';
import { compactProjectionRaw, compactReceipt } from '../../test/compactStage2';

async function reseal(doc: Record<string, unknown>) {
  const body = { ...doc };
  delete body.projection_sha256;
  doc.projection_sha256 = await sha256Hex(canonicalJson(body));
}

describe('CompactStage2Projection — exact W3 producer contract', () => {
  it('parses the complete selection-independent capped projection and its independent receipt', async () => {
    const raw = await compactProjectionRaw();
    const parsed = await parseCompactStage2Projection(raw, raw.projection_sha256);
    expect(parsed.schema_version).toBe('spot.stage02_display_projection.v1');
    expect(parsed.n_arms).toBe(Object.keys(parsed.arms).length);
    expect(parseCompactDisplayReceipt(await compactReceipt(parsed.n_arms), parsed.n_arms).verdict).toBe('admit');
  });

  it('rejects a mismatched projection self hash, even when the surrounding shape is valid', async () => {
    const raw = await compactProjectionRaw();
    const admitted = raw.projection_sha256;
    raw.projection_sha256 = '0'.repeat(64);
    await expect(parseCompactStage2Projection(raw, admitted)).rejects.toThrow(/self hash/);
  });

  it('rejects an unknown row field, including nested p/q and combined values', async () => {
    for (const key of ['p_value', 'qval', 'fdr', 'combined_score', 'balanced_skew']) {
      const raw = await compactProjectionRaw();
      const arm = Object.values(raw.arms)[0] as { rows: Record<string, unknown>[] };
      arm.rows[0][key] = 0.01;
      await reseal(raw);
      await expect(parseCompactStage2Projection(raw)).rejects.toThrow(/fields|combined/);
    }
  });

  it('allows only the producer null sentinels for combined/cross-arm output', async () => {
    const raw = await compactProjectionRaw();
    (raw as Record<string, unknown>).combined_objective = 0.5;
    await reseal(raw);
    await expect(parseCompactStage2Projection(raw)).rejects.toThrow(/combined|cross-arm/);
  });

  it('rejects a hidden prefix/count mismatch and a source-bundle lane mismatch', async () => {
    const raw = await compactProjectionRaw();
    const key = Object.keys(raw.arms).find((k) => k.startsWith('direct|'))!;
    (raw.arms[key] as Record<string, unknown>).n_ranked = 1;
    await reseal(raw);
    await expect(parseCompactStage2Projection(raw)).rejects.toThrow(/counts/);

    const raw2 = await compactProjectionRaw();
    const key2 = Object.keys(raw2.arms).find((k) => k.startsWith('direct|'))!;
    const arm2 = raw2.arms[key2] as { source_bundle: string };
    (raw2.bindings.native_bundles[arm2.source_bundle] as Record<string, unknown>).lane = 'pathway';
    await reseal(raw2);
    await expect(parseCompactStage2Projection(raw2)).rejects.toThrow(/wrong lane/);
  });

  it('rejects a receipt with a wrong arm count, verifier, verdict, or nonempty failures', async () => {
    const receipt = await compactReceipt(60);
    expect(() => parseCompactDisplayReceipt({ ...receipt, n_arms: 59 }, 60)).toThrow(/did not admit/);
    expect(() => parseCompactDisplayReceipt({ ...receipt, verifier_id: 'other' }, 60)).toThrow(/did not admit/);
    expect(() => parseCompactDisplayReceipt({ ...receipt, verdict: 'reject', n_failed: 1, failures: ['x'] }, 60)).toThrow(/did not admit/);
  });
});
