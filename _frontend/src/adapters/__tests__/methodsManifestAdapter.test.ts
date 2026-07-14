// Contract tests for the content-addressed per-stage Methods & Provenance manifest adapter.
//
// Proves the MAJOR-5 repair: a real manifest populates EVERY drawer row (data/input, estimand,
// masks/QC, method+code hash, env, last-run UTC, reproduce command, release, generator/verifier,
// notebook URL, artifact paths, and per-source URL + license + retrieval + raw/canonical hashes)
// — nothing hard-nulled, nothing invented. The artifact is bound by a content hash: mutating any
// byte and passing the OLD bound hash fails closed at a named gate. A genuinely-absent optional
// field stays null. A Claude-Science session/frame id is NEVER promoted into cs_notebook_url.

import { describe, expect, it } from 'vitest';
import { AdapterError } from '../errors';
import { parseStageMethodsManifest } from '../methodsManifestAdapter';
import { canonicalJson, sha256Hex } from '../../stage1/canonical';

/** The exact binding: sha256 over the canonical manifest bytes (same fns the adapter uses). */
const hashOf = (v: unknown): Promise<string> => sha256Hex(canonicalJson(v));

/** A full REAL Stage-2 manifest with every drawer field + two source-chain entries. */
function fullManifest(): Record<string, any> {
  return {
    stage_label: 'Targets',
    methods: {
      data_input: 'GWCD4i perturb-seq: 41,234 primary CD4 T cells across 33 guide conditions',
      source_tissue:
        'Primary human CD4 T cells (Marson GWCD4i) — one experimental source, across donor/stimulation conditions.',
      estimand: 'Per-gene log2 fold-change of program score; arms = away_from_A and toward_b (independent)',
      masks_qc: 'min 200 cells/guide; mito < 10%; scrublet-filtered doublets; guides with <2 donors dropped',
      upstream_model: 'spot.stage01_selection.v3 program contrast (Th17-like vs Th1-like @ Rest)',
      limitations: [
        'One in-vitro CD4 dataset; needs cross-donor / cross-tissue confirmation.',
        'Guide-level population effect; not lineage-resolved.',
      ],
      method_id: 'spot.stage02.direct_screen',
      method_code_sha256: 'a1b2c3d4e5f60718293a4b5c6d7e8f90112233445566778899aabbccddeeff00',
      environment: 'conda:spot-stage2 (solver-locked) env-lock:7f3c9a2e',
      last_run_utc: '2026-07-11T18:32:04Z',
      reproduce_command: 'spot run stage02 --selection sel_abc --config cfg_direct --seed 7',
    },
    provenance: {
      release_revision: 'spot@v2.3.1+gbm.7',
      raw_sha256: '1111111111111111111111111111111111111111111111111111111111111111',
      canonical_sha256: '2222222222222222222222222222222222222222222222222222222222222222',
      generator_status: 'generated 2026-07-11T18:32:04Z (green)',
      verifier_status: 'independently verified 2026-07-11T19:02:11Z (green)',
      cs_notebook_url: 'https://science.example.org/notebooks/stage02-abc',
      // A session/frame id is carried for auditability but is NOT a URL and must never
      // become cs_notebook_url.
      cs_session: { session_ref: 'sess-9f2', frame_ref: 'frame-77c1' },
      artifact_paths: [
        '02_geneskew/outputs/screen.parquet',
        '02_geneskew/outputs/screen.provenance.json',
      ],
      source_chain: [
        {
          label: 'Marson GWCD4i',
          record_id: 'GSE190604',
          url: 'https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE190604',
          license: 'CC-BY 4.0',
          retrieval_utc: '2026-07-01T09:00:00Z',
          raw_sha256: '3333333333333333333333333333333333333333333333333333333333333333',
          canonical_sha256: '4444444444444444444444444444444444444444444444444444444444444444',
        },
        {
          label: 'Ensembl',
          record_id: 'release-110',
          url: 'https://ensembl.org',
          license: 'Apache-2.0 / no-restriction',
          retrieval_utc: '2026-07-02T12:00:00Z',
          raw_sha256: '5555555555555555555555555555555555555555555555555555555555555555',
          canonical_sha256: '6666666666666666666666666666666666666666666666666666666666666666',
        },
      ],
    },
  };
}

/** Assert a promise rejects with an AdapterError carrying the given code (mirrors firewall.test). */
async function expectRejectCode(p: Promise<unknown>, code: string): Promise<void> {
  try {
    await p;
    throw new Error('expected rejection but the promise resolved');
  } catch (e) {
    expect(e).toBeInstanceOf(AdapterError);
    expect((e as AdapterError).code).toBe(code);
  }
}

describe('parseStageMethodsManifest — content-addressed real manifest', () => {
  it('populates EVERY drawer field from the manifest (nothing hard-nulled, nothing invented)', async () => {
    const m = fullManifest();
    const h = await hashOf(m);
    const parsed = await parseStageMethodsManifest(m, h, 'Targets');

    expect(parsed.stage_label).toBe('Targets');

    // Methods block — every row present.
    expect(parsed.methods.data_input).toBe(m.methods.data_input);
    expect(parsed.methods.source_tissue).toBe(m.methods.source_tissue);
    expect(parsed.methods.estimand).toBe(m.methods.estimand);
    expect(parsed.methods.masks_qc).toBe(m.methods.masks_qc);
    expect(parsed.methods.upstream_model).toBe(m.methods.upstream_model);
    expect(parsed.methods.limitations).toEqual(m.methods.limitations);
    expect(parsed.methods.method_id).toBe(m.methods.method_id);
    expect(parsed.methods.method_code_sha256).toBe(m.methods.method_code_sha256);
    expect(parsed.methods.environment).toBe(m.methods.environment);
    expect(parsed.methods.last_run_utc).toBe(m.methods.last_run_utc);
    expect(parsed.methods.reproduce_command).toBe(m.methods.reproduce_command);

    // Provenance block — every row present.
    expect(parsed.provenance.release_revision).toBe(m.provenance.release_revision);
    expect(parsed.provenance.raw_sha256).toBe(m.provenance.raw_sha256);
    expect(parsed.provenance.canonical_sha256).toBe(m.provenance.canonical_sha256);
    expect(parsed.provenance.generator_status).toBe(m.provenance.generator_status);
    expect(parsed.provenance.verifier_status).toBe(m.provenance.verifier_status);
    expect(parsed.provenance.cs_notebook_url).toBe(m.provenance.cs_notebook_url);
    expect(parsed.provenance.artifact_paths).toEqual(m.provenance.artifact_paths);

    // Per-source chain — url + license + retrieval + raw/canonical hashes on each entry.
    expect(parsed.provenance.source_chain).toHaveLength(2);
    const [s0, s1] = parsed.provenance.source_chain;
    expect(s0.label).toBe('Marson GWCD4i');
    expect(s0.record_id).toBe('GSE190604');
    expect(s0.url).toBe(m.provenance.source_chain[0].url);
    expect(s0.license).toBe('CC-BY 4.0');
    expect(s0.retrieval_utc).toBe('2026-07-01T09:00:00Z');
    expect(s0.raw_sha256).toBe(m.provenance.source_chain[0].raw_sha256);
    expect(s0.canonical_sha256).toBe(m.provenance.source_chain[0].canonical_sha256);
    expect(s1.label).toBe('Ensembl');
    expect(s1.license).toBe('Apache-2.0 / no-restriction');
    expect(s1.canonical_sha256).toBe(m.provenance.source_chain[1].canonical_sha256);
  });

  it('admits the manifest only against its own recomputed content hash', async () => {
    const m = fullManifest();
    const h = await hashOf(m);
    await expect(parseStageMethodsManifest(m, h, 'Targets')).resolves.toBeTruthy();
    // any other bound hash → rejected
    await expectRejectCode(
      parseStageMethodsManifest(m, '0'.repeat(64), 'Targets'),
      'content_hash_mismatch',
    );
  });

  it('is FAIL-CLOSED: mutate the bytes but pass the OLD bound hash → rejected at a named gate', async () => {
    const base = fullManifest();
    const h = await hashOf(base); // hash of the ORIGINAL bytes, bound in code

    // Independently mutate each bound datum; every one invalidates the whole manifest. Each
    // mutated value is itself well-formed (valid 64-hex where a hash), proving it is the CONTENT
    // BINDING — not shape validation — that catches the tamper.
    const mutations: Array<(m: Record<string, any>) => void> = [
      (m) => { m.provenance.source_chain[0].raw_sha256 = 'f'.repeat(64); },
      (m) => { m.provenance.source_chain[0].canonical_sha256 = 'e'.repeat(64); },
      (m) => { m.provenance.source_chain[1].raw_sha256 = 'd'.repeat(64); },
      (m) => { m.provenance.raw_sha256 = 'c'.repeat(64); },
      (m) => { m.provenance.canonical_sha256 = 'b'.repeat(64); },
      (m) => { m.methods.method_code_sha256 = 'a'.repeat(64); },
      (m) => { m.provenance.release_revision = 'spot@v9.9.9'; },
      (m) => { m.provenance.source_chain[0].retrieval_utc = '2020-01-01T00:00:00Z'; },
      (m) => { m.provenance.source_chain[0].license = 'proprietary'; },
      (m) => { m.provenance.source_chain[0].url = 'https://evil.example'; },
      (m) => { m.methods.last_run_utc = '1999-01-01T00:00:00Z'; },
      (m) => { m.methods.reproduce_command = 'rm -rf /'; },
    ];

    for (const mutate of mutations) {
      const tampered = structuredClone(base);
      mutate(tampered);
      await expectRejectCode(parseStageMethodsManifest(tampered, h, 'Targets'), 'content_hash_mismatch');
    }

    // Sanity: rebinding to the tampered bytes' own hash admits — proving it is the binding,
    // not the shape, that gates.
    const tampered = structuredClone(base);
    tampered.provenance.release_revision = 'spot@v9.9.9';
    const h2 = await hashOf(tampered);
    await expect(parseStageMethodsManifest(tampered, h2, 'Targets')).resolves.toBeTruthy();
  });

  it('leaves a genuinely-absent optional field null (never fabricated from a fixture)', async () => {
    const m = fullManifest();
    delete m.methods.estimand;
    delete m.methods.reproduce_command;
    delete m.methods.last_run_utc;
    delete m.provenance.release_revision;
    delete m.provenance.verifier_status;
    delete m.provenance.source_chain[1].license;
    delete m.provenance.source_chain[1].retrieval_utc;
    const h = await hashOf(m);
    const parsed = await parseStageMethodsManifest(m, h, 'Targets');

    expect(parsed.methods.estimand).toBeNull();
    expect(parsed.methods.reproduce_command).toBeNull();
    expect(parsed.methods.last_run_utc).toBeNull();
    expect(parsed.provenance.release_revision).toBeNull();
    expect(parsed.provenance.verifier_status).toBeNull();
    expect(parsed.provenance.source_chain[1].license).toBeNull();
    expect(parsed.provenance.source_chain[1].retrieval_utc).toBeNull();
    // a field the manifest DID supply is still populated
    expect(parsed.provenance.source_chain[1].canonical_sha256).toBe(
      '6666666666666666666666666666666666666666666666666666666666666666',
    );
  });

  it('falls back to the deterministic stage source-tissue fact only when the manifest omits it', async () => {
    const m = fullManifest();
    delete m.methods.source_tissue;
    const h = await hashOf(m);
    const parsed = await parseStageMethodsManifest(m, h, 'Targets');
    // source-backed, keyed on the stage — not a per-run invention
    expect(parsed.methods.source_tissue).toContain('Primary human CD4 T cells');
  });

  it('NEVER promotes a session/frame id into cs_notebook_url', async () => {
    const m = fullManifest();
    delete m.provenance.cs_notebook_url; // frame/session id still present in cs_session
    expect(m.provenance.cs_session.frame_ref).toBe('frame-77c1');
    const h = await hashOf(m);
    const parsed = await parseStageMethodsManifest(m, h, 'Targets');
    expect(parsed.provenance.cs_notebook_url).toBeNull();
  });

  it('emits cs_notebook_url ONLY from the explicit notebook url field', async () => {
    const m = fullManifest();
    const h = await hashOf(m);
    const parsed = await parseStageMethodsManifest(m, h, 'Targets');
    expect(parsed.provenance.cs_notebook_url).toBe('https://science.example.org/notebooks/stage02-abc');
  });

  it('rejects a manifest whose declared stage disagrees with the code-bound stage', async () => {
    const m = fullManifest(); // declares stage_label: 'Targets'
    const h = await hashOf(m); // correct content hash — so only the stage firewall can fire
    await expectRejectCode(parseStageMethodsManifest(m, h, 'Drug link'), 'stage_label_mismatch');
  });

  it('rejects a non-object manifest as malformed', async () => {
    await expectRejectCode(parseStageMethodsManifest(null, '0'.repeat(64), 'Targets'), 'malformed');
    await expectRejectCode(parseStageMethodsManifest('nope', '0'.repeat(64), 'Targets'), 'malformed');
  });
});
