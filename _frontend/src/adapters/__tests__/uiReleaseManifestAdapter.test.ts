// Fail-closed admitted-artifact binding: the UI release manifest W1 packages after a real run must
// (a) content-address against its pinned hash, (b) match the code-bound stage_label + method_id,
// (c) carry an EXPLICIT admitted verifier token, and (d) be complete. Any failure → reject (unbound).
// mergeAdmittedManifest overlays the admitted run onto the static route definition (isRunBound=true).

import { describe, it, expect } from 'vitest';
import {
  parseUiReleaseManifest,
  mergeAdmittedManifest,
  packageUiReleaseManifest,
} from '../uiReleaseManifestAdapter';
import { UI_RELEASE_SCHEMA_VERSION } from '../../domain/uiReleaseManifest';
import type { UiReleaseManifest } from '../../domain/uiReleaseManifest';
import { AdapterError } from '../errors';
import { canonicalJson, sha256Hex } from '../../stage1/canonical';
import { buildStageMethodsManifest } from '../../mpa/stageMethods';
import { isRunBound } from '../../shell/ProvenanceDrawer';

const TARGETS_METHOD_ID =
  'spot.stage02.direct.masked_program_projection · spot.stage02.pareto.two_arm.v1 · spot.stage02.temporal_cross_condition.v1';

function valid(over: Partial<UiReleaseManifest> = {}): UiReleaseManifest {
  return {
    schema_version: UI_RELEASE_SCHEMA_VERSION,
    stage_label: 'Targets',
    method_id: TARGETS_METHOD_ID,
    release_revision: 'spot.stage02.direct@rev1',
    raw_sha256: 'a'.repeat(64),
    canonical_sha256: 'b'.repeat(64),
    method_code_sha256: 'c'.repeat(64),
    environment: 'conda:stage2@lock-9f1',
    last_run_utc: '2026-07-13T04:00:00Z',
    generator_status: 'generated',
    verifier_status: 'admitted',
    reproduce_command: 'cd 02_geneskew && python -m analysis.direct.run_arms --condition Rest --out-root $OUT',
    cs_notebook_url: 'https://science.example.org/notebooks/stage02-abc',
    artifact_paths: ['out/arms/bundle.json'],
    source_artifact_ids: ['marson2025_gwcd4_perturbseq@c355f535'],
    ...over,
  };
}
const hashOf = (m: unknown) => sha256Hex(canonicalJson(m));

describe('parseUiReleaseManifest — valid round-trip', () => {
  it('a complete, admitted, hash-matched manifest parses and round-trips through the W1 packager', async () => {
    const { manifest, content_hash } = await packageUiReleaseManifest(valid());
    expect(content_hash).toMatch(/^[0-9a-f]{64}$/);
    const parsed = await parseUiReleaseManifest(manifest, content_hash, 'Targets', TARGETS_METHOD_ID);
    expect(parsed.verifier_status).toBe('admitted');
    expect(parsed.artifact_paths).toEqual(['out/arms/bundle.json']);
  });
});

describe('parseUiReleaseManifest — FAIL CLOSED', () => {
  it('rejects a one-byte mutation against the pinned hash (content_hash_mismatch)', async () => {
    const m = valid();
    const pinned = await hashOf(m);
    const mutated = { ...m, environment: m.environment + '.' };
    await expect(parseUiReleaseManifest(mutated, pinned, 'Targets', TARGETS_METHOD_ID)).rejects.toMatchObject({
      code: 'content_hash_mismatch',
    });
  });

  it('rejects an unknown schema_version', async () => {
    const m = { ...valid(), schema_version: 'spot.ui_release_manifest.v2' } as unknown as UiReleaseManifest;
    await expect(parseUiReleaseManifest(m, await hashOf(m), 'Targets', TARGETS_METHOD_ID)).rejects.toMatchObject({
      code: 'unknown_schema_version',
    });
  });

  it('rejects a manifest bound to the wrong stage (stage_label_mismatch)', async () => {
    const m = valid({ stage_label: 'Drugs' });
    await expect(parseUiReleaseManifest(m, await hashOf(m), 'Targets', TARGETS_METHOD_ID)).rejects.toMatchObject({
      code: 'stage_label_mismatch',
    });
  });

  it('rejects a manifest bound to the wrong method (method_id_mismatch)', async () => {
    const m = valid({ method_id: 'spot.stage02_screen.v3' });
    await expect(parseUiReleaseManifest(m, await hashOf(m), 'Targets', TARGETS_METHOD_ID)).rejects.toMatchObject({
      code: 'method_id_mismatch',
    });
  });

  it('rejects every non-admitted verifier token (verifier_not_admitted)', async () => {
    // Substring traps ("not passed" ⊃ "pass", "unverified" ⊃ "verified") and empty all reject.
    for (const bad of ['failed', 'refused', 'pending', 'not passed', 'pending independent verification', 'unverified', '']) {
      const m = valid({ verifier_status: bad });
      await expect(parseUiReleaseManifest(m, await hashOf(m), 'Targets', TARGETS_METHOD_ID)).rejects.toMatchObject({
        code: 'verifier_not_admitted',
      });
    }
  });

  it('rejects an INCOMPLETE run (empty required field OR empty artifact_paths)', async () => {
    const missingEnv = valid({ environment: '' });
    await expect(parseUiReleaseManifest(missingEnv, await hashOf(missingEnv), 'Targets', TARGETS_METHOD_ID)).rejects.toMatchObject({
      code: 'incomplete_admitted_run',
    });
    const noArtifacts = valid({ artifact_paths: [] });
    await expect(parseUiReleaseManifest(noArtifacts, await hashOf(noArtifacts), 'Targets', TARGETS_METHOD_ID)).rejects.toMatchObject({
      code: 'incomplete_admitted_run',
    });
  });

  it('the W1 packager itself refuses to hand over an incomplete / non-admitted manifest', async () => {
    await expect(packageUiReleaseManifest(valid({ verifier_status: 'pending' }))).rejects.toBeInstanceOf(AdapterError);
    await expect(packageUiReleaseManifest(valid({ last_run_utc: '' }))).rejects.toBeInstanceOf(AdapterError);
  });
});

describe('mergeAdmittedManifest — overlays the admitted run onto the STATIC route definition', () => {
  it('binds a complete run (isRunBound → true): definition preserved, run fields + source IDs bound', async () => {
    const staticDef = await buildStageMethodsManifest('targets');
    expect(isRunBound(staticDef.methods, staticDef.provenance)).toBe(false); // static = unbound

    const admitted = valid();
    const merged = mergeAdmittedManifest(staticDef, admitted);

    // definition prose preserved verbatim
    expect(merged.methods.method_id).toBe(staticDef.methods.method_id);
    expect(merged.methods.estimand).toBe(staticDef.methods.estimand);
    // admitted run fields bound
    expect(merged.methods.method_code_sha256).toBe(admitted.method_code_sha256);
    expect(merged.methods.environment).toBe(admitted.environment);
    expect(merged.methods.last_run_utc).toBe(admitted.last_run_utc);
    expect(merged.methods.reproduce_command).toBe(admitted.reproduce_command);
    expect(merged.provenance.release_revision).toBe(admitted.release_revision);
    expect(merged.provenance.raw_sha256).toBe(admitted.raw_sha256);
    expect(merged.provenance.canonical_sha256).toBe(admitted.canonical_sha256);
    expect(merged.provenance.verifier_status).toBe('admitted');
    expect(merged.provenance.cs_notebook_url).toBe(admitted.cs_notebook_url);
    expect(merged.provenance.artifact_paths).toEqual(admitted.artifact_paths);
    // preserved source artifact IDs appended to the source chain (never dropped)
    expect(merged.provenance.source_chain.some((s) => s.record_id === 'marson2025_gwcd4_perturbseq@c355f535')).toBe(true);
    // and the merged manifest now binds a COMPLETE admitted-run identity
    expect(isRunBound(merged.methods, merged.provenance)).toBe(true);
  });

  it('a merged manifest with a non-admitted verifier is NOT run-bound (fail-closed at render)', async () => {
    const staticDef = await buildStageMethodsManifest('drugs');
    // mergeAdmittedManifest trusts a validated input; isRunBound is the render-time backstop.
    const merged = mergeAdmittedManifest(staticDef, valid({ stage_label: 'Drugs', method_id: staticDef.methods.method_id!, verifier_status: 'failed' }));
    expect(isRunBound(merged.methods, merged.provenance)).toBe(false);
  });
});
