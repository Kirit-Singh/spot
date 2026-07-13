// UI readiness audit — pins the three pre-real-artifact invariants for every Stage 2/3/4 route:
//   (1) no placeholder/demo scientific value can be mistaken for a real result — the unbound canvas
//       shows ZERO fabricated rows and none of the synthetic fixture tokens (GENE_A, COMPOUND_A, …);
//   (2) each route has a clean NEUTRAL empty/loading state — a compact pending panel, no banner, no
//       editorial caveat block, no numbers;
//   (3) the ONE header Methods & provenance drawer is route-specific and RENDERS the run fields the
//       final package supplies — run timestamp, source/code hashes, rerun command, CS notebook link.
// Visual design is unchanged; these are assertions only.

import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { StageIsland } from '../StageIsland';
import type { RealRouteResolution } from '../renderReal';
import type { PageKey } from '../pages';
import type { JoinedView, ResolvedBundles } from '../../repository/joinResolver';
import type { Stage3UiArtifact } from '../../domain/stage3UiArtifact';
import type { Stage4UiArtifact } from '../../domain/stage4UiArtifact';
import type { StageMethodsManifest } from '../../domain/methodsManifest';
import type { UiReleaseManifest } from '../../domain/uiReleaseManifest';
import { mergeAdmittedManifest } from '../../adapters/uiReleaseManifestAdapter';
import { buildStageMethodsManifest } from '../stageMethods';

afterEach(cleanup);

const ROUTES: [PageKey, string][] = [
  ['targets', 'Targets'],
  ['pathways', 'Pathways'],
  ['drugs', 'Drugs'],
  ['pksafety', 'PK & Safety'],
];

// Synthetic fixture tokens that must NEVER surface as if they were real results.
const FIXTURE_TOKENS = /GENE_[A-Z]|COMPOUND_[A-Z]|\bfixture\b|\bdemo\b|research_only|GBM context/i;

// ── Invariants 1 + 2: clean neutral empty/loading state, no demo numbers ──
describe('every Stage 2/3/4 route has a clean neutral empty/loading state (no demo numbers)', () => {
  it.each(ROUTES)('%s: neutral pending panel, zero fabricated rows, no fixture tokens, no banner/editorial', async (page, label) => {
    window.history.pushState({}, '', '/02_page.html'); // production, no demo
    render(<StageIsland page={page} subtitle={label} />); // no loadRealArtifact → unbound
    const main = screen.getByRole('main');

    // loading → resolved-empty: the neutral pending panel is present throughout (no numbers, no rows)
    await waitFor(() => expect(within(main).getByText(/pending independent admission/i)).toBeInTheDocument());
    expect(within(main).getByText(/not generated|resolving/i)).toBeInTheDocument();

    // zero fabricated data rows on the canvas (no table that could be mistaken for results)
    expect(main.querySelectorAll('table tbody tr, [role="row"]').length).toBe(0);
    // no synthetic fixture tokens anywhere in the canvas
    expect(main.textContent || '').not.toMatch(FIXTURE_TOKENS);
    // no banner / alert / editorial caveat chrome
    expect(main.querySelector('[role="banner"], [role="alert"]')).toBeNull();
    expect(within(main).queryByText(/caveat|editorial|disclaimer|note:/i)).toBeNull();
    // methods prose stays out of the canvas (it lives only in the drawer)
    expect(within(main).queryByText(/Methods & provenance/i)).toBeNull();
    expect(within(main).queryByText(/Estimand/i)).toBeNull();
  });
});

// ── Invariant 3: the drawer is route-specific and renders every run field the package supplies ──
function boundManifestWith(page: PageKey, run: { last_run_utc: string; method_code_sha256: string; raw_sha256: string; canonical_sha256: string; reproduce_command: string; cs_notebook_url: string }): Promise<StageMethodsManifest> {
  return buildStageMethodsManifest(page).then((staticDef) => {
    const admitted: UiReleaseManifest = {
      schema_version: 'spot.ui_release_manifest.v1',
      stage_label: staticDef.stage_label,
      method_id: staticDef.methods.method_id!,
      release_revision: 'rev-1',
      raw_sha256: run.raw_sha256,
      canonical_sha256: run.canonical_sha256,
      method_code_sha256: run.method_code_sha256,
      environment: 'conda@env1',
      last_run_utc: run.last_run_utc,
      generator_status: 'generated',
      verifier_status: 'admitted',
      reproduce_command: run.reproduce_command,
      cs_notebook_url: run.cs_notebook_url,
      artifact_paths: ['results/x.json'],
      source_artifact_ids: ['src-1'],
    };
    return mergeAdmittedManifest(staticDef, admitted);
  });
}

const geneView = { mode: 'within_condition', geneArmA: null, geneArmB: null, pathwayArmA: null, pathwayArmB: null, pathway_context: 'reactome' } as unknown as JoinedView;
const bundles = {} as unknown as ResolvedBundles;
const stage3: Stage3UiArtifact = { schema_version: 'spot.stage03_drug_annotation.v1', bundle_id: 's3_b1', manifest_sha256: 'a'.repeat(64), upstream_stage2_run: 'run_1', candidates: [] };
const stage4: Stage4UiArtifact = { schema_version: 'spot.stage04_scorecards.v1', scorecard_set_id: 's4_1', stage4_method_version: 'stage4-evidence-v2', upstream_stage3_bundle: 's3_b1', candidates: [] };

async function boundResolution(page: PageKey): Promise<RealRouteResolution> {
  const manifest = await boundManifestWith(page, {
    last_run_utc: '2026-07-13T04:05:06Z',
    method_code_sha256: 'c'.repeat(64),
    raw_sha256: 'a'.repeat(64),
    canonical_sha256: 'b'.repeat(64),
    reproduce_command: `spot repro ${page}`,
    cs_notebook_url: 'https://example.org/cs/notebook/run-1',
  });
  if (page === 'drugs') return { route: 'drugs', artifact: stage3, admission: 'admitted', manifest };
  if (page === 'pksafety') return { route: 'pksafety', artifact: stage4, admission: 'admitted', manifest };
  return { route: page as 'targets' | 'pathways', view: geneView, bundles, admission: 'admitted', manifest };
}

describe('drawer is route-specific and ready to consume the final package run fields', () => {
  it.each(ROUTES)('%s: run timestamp + source/code hashes + rerun command + CS notebook all render', async (page, label) => {
    window.history.pushState({}, '', '/02_page.html');
    const resolution = await boundResolution(page);
    render(<StageIsland page={page} subtitle={label} loadRealArtifact={() => resolution} />);

    // wait for the admitted resolution, then open the ONE drawer
    await waitFor(() => expect(document.querySelector('main [data-route]')).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: /Methods & provenance/i }));
    const dialog = screen.getByRole('dialog');

    // route-specific
    expect(dialog.querySelector('[data-stage-label]')?.textContent).toBe(label);

    // run timestamp
    expect(within(dialog).getByText('2026-07-13T04:05:06Z')).toBeInTheDocument();
    // source + code hashes (raw / canonical / code sha256)
    expect(within(dialog).getByText('a'.repeat(64))).toBeInTheDocument();
    expect(within(dialog).getByText('b'.repeat(64))).toBeInTheDocument();
    expect(within(dialog).getByText('c'.repeat(64))).toBeInTheDocument();
    // rerun command
    expect(within(dialog).getByText(new RegExp(`spot repro ${page}`))).toBeInTheDocument();
    // Claude Science notebook link (external provenance link, not an in-app page)
    const nb = [...dialog.querySelectorAll('a[href]')].find((a) => (a.getAttribute('href') || '').includes('example.org/cs/notebook'));
    expect(nb?.getAttribute('target')).toBe('_blank');
    expect(nb?.getAttribute('rel')).toContain('noopener');
  });
});
