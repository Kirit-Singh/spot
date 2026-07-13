import { describe, expect, it } from 'vitest';
import { parseCompactDisplayReceipt, parseCompactStage2Projection } from '../compactStage2ProjectionAdapter';
import { canonicalJson, sha256Hex } from '../../stage1/canonical';
import { compactProjectionRaw, compactReceipt, compactReceiptAdmitted } from '../../test/compactStage2';

async function reseal(doc: Record<string, unknown>) {
  const body = { ...doc };
  delete body.projection_sha256;
  doc.projection_sha256 = await sha256Hex(canonicalJson(body));
}

/** The exact projection identity the receipt must admit (mirrors the loader's expectation). */
async function expectationFor(proj: { n_arms: number; projection_sha256: string }) {
  return {
    n_arms: proj.n_arms,
    projection_raw_sha256: await sha256Hex(JSON.stringify(proj)),
    projection_canonical_sha256: await sha256Hex(canonicalJson(proj)),
    projection_self_sha256: proj.projection_sha256,
  };
}

describe('CompactStage2Projection — exact W3 producer contract', () => {
  it('parses the complete selection-independent capped projection and its independent receipt', async () => {
    const raw = await compactProjectionRaw();
    const parsed = await parseCompactStage2Projection(raw, raw.projection_sha256);
    expect(parsed.schema_version).toBe('spot.stage02_display_projection.v2');
    expect(parsed.bindings.symbol_crosswalk.n_one_to_one).toBe(10_282);
    expect(parsed.n_arms).toBe(Object.keys(parsed.arms).length);
    const admitted = await compactReceiptAdmitted(raw);
    expect(parseCompactDisplayReceipt(admitted, await expectationFor(raw)).verdict).toBe('admit');
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

  it('fails closed when the frozen symbol crosswalk binding is missing or mutated', async () => {
    const missing = await compactProjectionRaw();
    delete (missing.bindings as Record<string, unknown>).symbol_crosswalk;
    await reseal(missing);
    await expect(parseCompactStage2Projection(missing)).rejects.toThrow(/symbol_crosswalk|bindings/);

    const mutated = await compactProjectionRaw();
    mutated.bindings.symbol_crosswalk.raw_sha256 = '0'.repeat(64);
    await reseal(mutated);
    await expect(parseCompactStage2Projection(mutated)).rejects.toThrow(/crosswalk hash/);
  });

  it('rejects a receipt with a wrong arm count, verifier, verdict, or nonempty failures', async () => {
    const raw = await compactProjectionRaw();
    const exp = await expectationFor(raw);
    const receipt = await compactReceiptAdmitted(raw);
    expect(() => parseCompactDisplayReceipt({ ...receipt, n_arms: exp.n_arms - 1 }, exp)).toThrow(/did not admit/);
    expect(() => parseCompactDisplayReceipt({ ...receipt, verifier_id: 'other' }, exp)).toThrow(/did not admit/);
    expect(() => parseCompactDisplayReceipt({ ...receipt, verdict: 'reject', n_failed: 1, failures: ['x'] }, exp)).toThrow(/did not admit/);
  });

  it('FAILS CLOSED on a receipt that admits by arm count alone (no exact-subject binding)', async () => {
    const raw = await compactProjectionRaw();
    const exp = await expectationFor(raw);
    const nArmsOnly = await compactReceipt(raw.n_arms); // the pre-W3, n_arms-only receipt — no `subject`
    expect(() => parseCompactDisplayReceipt(nArmsOnly, exp)).toThrow();
  });

  it('FAILS CLOSED on a subject that binds a different projection than the served bytes', async () => {
    const raw = await compactProjectionRaw();
    const exp = await expectationFor(raw);
    const admitted = await compactReceiptAdmitted(raw);
    const wrongRaw = { ...admitted, subject: { ...admitted.subject, projection_raw_sha256: '0'.repeat(64) } };
    expect(() => parseCompactDisplayReceipt(wrongRaw, exp)).toThrow(/different projection/);
    const wrongSelf = { ...admitted, subject: { ...admitted.subject, projection_self_sha256_declared: '0'.repeat(64) } };
    expect(() => parseCompactDisplayReceipt(wrongSelf, exp)).toThrow(/different projection/);
  });
});
