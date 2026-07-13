// The served Stage-1 distribution must tell ONE story: the release-manifest attestation and the bytes
// actually served cannot disagree. This pins the deploy-time consistency verifier against the EXACT
// audit finding — stage01_release_manifest.json says overlay_release_ok=false / overlay
// release_staging_not_served, while the served page serves+requires stage01_umap_overlay_v3.json.
// The verifier must REJECT that (and pass a consistent tree). It never fabricates or flips the
// attestation — that regeneration is the Stage-1 generator's job; this only refuses to ship a lie.

import { describe, expect, it } from 'vitest';

// Untyped Node ESM deploy tool — imported at runtime; string specifier keeps tsc from resolving it.
interface Verifier {
  OVERLAY_SERVED_FILE: string;
  findServedManifestContradictions: (args: {
    releaseManifest: unknown;
    servedDataFiles: string[];
    pageRequiredFiles?: string[];
    gateStatements?: Array<{ source: string; gates: Record<string, unknown> }>;
  }) => Array<{ source: string; rule: string; message: string }>;
}
async function load(): Promise<Verifier> {
  const modPath: string = '../../../deploy/servedManifestConsistency.mjs';
  return import(modPath) as Promise<Verifier>;
}

/** The real, contradictory release manifest shape (overlay attested un-served). */
function blockedOverlayManifest() {
  return {
    schema: 'spot.stage01_release_manifest.v2',
    release_gates: { overlay_release_ok: false, app_deployment_ready: false },
    not_lockable_reason_codes: ['overlay_release_blocked'],
    artifacts: {
      'stage01_validation.json': { location: 'served', present: true },
      'stage01_umap_overlay.json': { file: 'stage01_umap_overlay_v3.json', location: 'release_staging_not_served', present: true },
    },
  };
}

describe('served manifest consistency — refuse attestation/served-bytes contradictions', () => {
  it('R1+R3: overlay attested un-served but physically served + required → contradictions', async () => {
    const { findServedManifestContradictions, OVERLAY_SERVED_FILE } = await load();
    const c = findServedManifestContradictions({
      releaseManifest: blockedOverlayManifest(),
      servedDataFiles: ['stage01_validation.json', OVERLAY_SERVED_FILE],
      pageRequiredFiles: ['./data/' + OVERLAY_SERVED_FILE, './data/stage01_validation.json'],
    });
    const rules = c.map((x) => x.rule);
    expect(rules).toContain('R1_overlay_gate_vs_reality');
    expect(rules).toContain('R3_staged_artifact_served');
    expect(c.every((x) => x.source === 'stage01_release_manifest.json')).toBe(true);
  });

  it('R2: a served copy disagreeing on a gate value → split-brain contradiction', async () => {
    const { findServedManifestContradictions } = await load();
    const c = findServedManifestContradictions({
      releaseManifest: blockedOverlayManifest(),
      servedDataFiles: ['stage01_validation.json'], // overlay NOT served → R1/R3 clear
      gateStatements: [{ source: 'stage01_current.json', gates: { overlay_release_ok: true, app_deployment_ready: false } }],
    });
    expect(c).toHaveLength(1);
    expect(c[0].rule).toBe('R2_served_gate_agreement');
    expect(c[0].source).toBe('stage01_current.json');
  });

  it('CONSISTENT: overlay released + served, all copies agree → no contradiction', async () => {
    const { findServedManifestContradictions, OVERLAY_SERVED_FILE } = await load();
    const releaseManifest = {
      schema: 'spot.stage01_release_manifest.v2',
      release_gates: { overlay_release_ok: true, app_deployment_ready: false }, // app still honestly gated on 0/33
      not_lockable_reason_codes: [],
      artifacts: {
        'stage01_validation.json': { location: 'served', present: true },
        'stage01_umap_overlay.json': { file: OVERLAY_SERVED_FILE, location: 'served', present: true },
      },
    };
    const c = findServedManifestContradictions({
      releaseManifest,
      servedDataFiles: ['stage01_validation.json', OVERLAY_SERVED_FILE],
      pageRequiredFiles: ['./data/' + OVERLAY_SERVED_FILE],
      gateStatements: [
        { source: 'stage01_current.json', gates: { overlay_release_ok: true, app_deployment_ready: false } },
        { source: 'stage01_validation.json', gates: { overlay_release_ok: true, app_deployment_ready: false } },
      ],
    });
    expect(c).toEqual([]);
  });

  it('CONSISTENT: overlay honestly un-released AND absent from served bytes → no contradiction', async () => {
    const { findServedManifestContradictions } = await load();
    const c = findServedManifestContradictions({
      releaseManifest: blockedOverlayManifest(),
      servedDataFiles: ['stage01_validation.json'], // overlay genuinely not served
    });
    expect(c).toEqual([]);
  });
});
