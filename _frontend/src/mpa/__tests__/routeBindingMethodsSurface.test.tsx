// Sole-methods-surface invariant for the BOUND real-artifact path. When a route binds an admitted
// artifact (a merged ui_release manifest + a native projection), the ONE header "Methods & provenance"
// slide-out stays the only primary methods surface: exactly one invoker, both methods + provenance
// sections, route-specific content, the bound run rows (reproduce command), and NO anchor to a
// standalone in-app methods/notebook/trace page — a real external cs_notebook_url is an allowed
// target=_blank provenance link, not an in-app destination. Methods prose never leaks onto the canvas.
//
// Companion to drawerSoleMethodsSurface.test.tsx (which covers the UNBOUND/pending state).

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

const NOTEBOOK_URL = 'https://example.org/cs/notebook/run-1';

// The drawerSoleMethodsSurface rule: a href is a forbidden in-app methods destination only when it is
// NOT external and points at a methods/notebook/trace/provenance page. External URLs are allowed.
function isStandaloneMethodsHref(href: string): boolean {
  if (/^(https?:\/\/|mailto:)/i.test(href)) return false;
  if (href === '/data/stage01_release_manifest.json') return false;
  return /(notebook|trace|methods|provenance)/i.test(href);
}

/** A merged, run-bound manifest for a route (static definition + an admitted run overlay). */
async function boundManifest(page: PageKey): Promise<StageMethodsManifest> {
  const staticDef = await buildStageMethodsManifest(page);
  const admitted: UiReleaseManifest = {
    schema_version: 'spot.ui_release_manifest.v1',
    stage_label: staticDef.stage_label,
    method_id: staticDef.methods.method_id!,
    release_revision: 'rev-1',
    raw_sha256: 'a'.repeat(64),
    canonical_sha256: 'b'.repeat(64),
    method_code_sha256: 'c'.repeat(64),
    environment: 'conda@env1',
    last_run_utc: '2026-07-13T00:00:00Z',
    generator_status: 'generated',
    verifier_status: 'admitted',
    reproduce_command: `spot repro ${page}`,
    cs_notebook_url: NOTEBOOK_URL,
    artifact_paths: ['results/x.json'],
    source_artifact_ids: ['src-1'],
  };
  return mergeAdmittedManifest(staticDef, admitted);
}

const geneView = {
  mode: 'same_time_contrast',
  geneArmA: null,
  geneArmB: null,
  pathwayArmA: null,
  pathwayArmB: null,
  pathway_context: 'reactome',
} as unknown as JoinedView;
const bundles = {} as unknown as ResolvedBundles;

function stage3(): Stage3UiArtifact {
  return {
    schema_version: 'spot.ui.stage03_candidates.v2', native_schema_version: 'spot.stage03_drug_annotation.v2', artifact_class: 'analysis',
    bundle_id: 's3_bundle01',
    canonical_content_sha256: 'a'.repeat(64),
    upstream_stage2_run: 'stage02_run_777',
    candidates: [],
  };
}
function stage4(): Stage4UiArtifact {
  return {
    schema_version: 'spot.stage04_browser_projection.v1',
    scorecard_set_id: 's4_set01',
    upstream_stage3_bundle: 's3_bundle01',
    upstream: { candidate_set_id: 's3_bundle01', namespace: 'production', is_fixture: false },
    store_is_selection_independent: true,
    is_ranking: false,
    ordering: { by: 'candidate_id' },
    guards: [],
    active_selection_view: null,
    active_view_candidate_ids: [],
    candidates: [],
  };
}

async function resolutionFor(page: PageKey): Promise<RealRouteResolution> {
  const manifest = await boundManifest(page);
  switch (page) {
    case 'targets':
      return { route: 'targets', view: geneView, bundles, admission: 'admitted', manifest };
    case 'pathways':
      return { route: 'pathways', view: geneView, bundles, admission: 'admitted', manifest };
    case 'drugs':
      return { route: 'drugs', artifact: stage3(), admission: 'admitted', manifest };
    default:
      return { route: 'pksafety', artifact: stage4(), admission: 'admitted', manifest };
  }
}

const ROUTES: [PageKey, string][] = [
  ['targets', 'Targets'],
  ['pathways', 'Pathways'],
  ['drugs', 'Drugs'],
  ['pksafety', 'PK & Safety'],
];

describe('BOUND real-artifact path — sole methods surface holds on every route', () => {
  it.each(ROUTES)('%s: one drawer, route-specific bound methods+provenance, no standalone-methods link, clean canvas', async (page, label) => {
    window.history.pushState({}, '', '/02_page.html'); // production, no demo
    const resolution = await resolutionFor(page);
    render(<StageIsland page={page} subtitle={label} loadRealArtifact={() => resolution} />);

    // the admitted artifact resolves → the route's OWN native canvas renders (proves the bound path)
    const main = document.querySelector('main')!;
    await waitFor(() => expect(main.querySelector(`[data-route="${page}"]`)).toBeTruthy());

    // (1) exactly ONE primary methods surface; no separate methods/notebook/trace nav
    const invokers = screen.getAllByRole('button', { name: /Methods & provenance/i });
    expect(invokers).toHaveLength(1);
    fireEvent.click(invokers[0]);
    const dialog = screen.getByRole('dialog');

    // (2) route-specific, BOTH sections in the ONE slide-out
    expect(dialog.querySelector('[data-stage-label]')?.textContent).toBe(label);
    expect(dialog.querySelector('[data-section="methods"]')).toBeTruthy();
    expect(dialog.querySelector('[data-section="provenance"]')).toBeTruthy();

    // (3) the BOUND run rows are shown (reproduce command bound to THIS route)
    expect(within(dialog).getByText(new RegExp(`spot repro ${page}`))).toBeInTheDocument();

    // (4) no anchor to a standalone in-app methods/notebook/trace page; the external CS notebook URL is
    //     an allowed target=_blank provenance link (not an in-app destination)
    const anchors = [...dialog.querySelectorAll('a[href]')];
    expect(anchors.map((a) => a.getAttribute('href') || '').filter(isStandaloneMethodsHref)).toEqual([]);
    const notebook = anchors.find((a) => (a.getAttribute('href') || '').includes('example.org/cs/notebook'));
    expect(notebook?.getAttribute('target')).toBe('_blank');
    expect(notebook?.getAttribute('rel')).toContain('noopener');

    // (5) methods prose stays in the drawer, never on the canvas
    expect(within(main).queryByText(/Methods & provenance/i)).toBeNull();
    expect(within(main).queryByText(/Estimand/i)).toBeNull();
    expect(within(main).queryByText(/Masks \/ QC/i)).toBeNull();
    expect(within(main).queryByText(new RegExp(`spot repro ${page}`))).toBeNull();
  });
});
