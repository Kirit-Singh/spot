// Route-aware canvas: each downstream route renders its OWN native path. Stage 3 (Drugs) and Stage 4
// (PK & Safety) must NOT fall through to the Stage-2 gene/pathway tables. A value the artifact does not
// carry stays typed-missing (em-dash / not_evaluated) — never invented, never an inferred negative.

import { cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { renderRouteReal } from '../renderReal';
import type { RealRouteResolution } from '../renderReal';
import type { Stage3UiArtifact } from '../../domain/stage3UiArtifact';
import type { Stage4UiArtifact } from '../../domain/stage4UiArtifact';
import type { JoinedView, ResolvedBundles } from '../../repository/joinResolver';
import type { PathwayArm } from '../../domain/reusableArm';

afterEach(cleanup);

function renderRes(res: RealRouteResolution) {
  return render(<div data-testid="canvas">{renderRouteReal(res)}</div>);
}

function stage3(): Stage3UiArtifact {
  return {
    schema_version: 'spot.ui.stage03_candidates.v2',
    native_schema_version: 'spot.stage03_drug_annotation.v2',
    artifact_class: 'analysis',
    bundle_id: 's3_bundle01',
    canonical_content_sha256: 'a'.repeat(64),
    upstream_stage2_run: 'stage02_run_777',
    candidates: [
      {
        candidate_id: 'cand-1',
        active_moiety_id: 'MOI1',
        preferred_name: 'Examplib',
        identity_status: 'resolved',
        molecule_chembl_ids: ['CHEMBL1', 'CHEMBL2'],
        target_ensembls: ['ENSG1', 'ENSG2'],
        n_edges: 3,
        n_direct_gene_edges: 1,
        max_phase_status: 'stated',
        max_phase_sources: ['4'],
        observed_perturbation_arms: ['arm1'],
        observed_perturbation_support: true,
        mechanism_match_statuses: ['phenocopies_the_perturbation_that_helped'],
        pathway_hypothesis_arms: [],
        stage3_evidence_classes: ['observed_perturbation_target'],
        stage4_assessment_status: 'queued',
        stage4_assessment_reason: null,
        source_record_ids: ['s1'],
      },
    ],
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
    active_view_candidate_ids: ['cand-1'],
    candidates: [
      {
        candidate_id: 'cand-1',
        active_moiety: { active_moiety_name: 'Examplib' },
        compound_ids: { chembl_id: 'CID1' },
        target: 'TARGET1',
        mechanism: 'inhibitor',
        direction_compatibility: 'supported',
        production_eligible: { eligible: true, reason_code: null },
        provenance_chain: [],
        stage3_arm_membership: {},
        in_active_view: true,
        lanes: { delivery: [], cns_mpo: { status: 'complete', total_published: 4.5 }, transporters: {},
          exposure: [], nebpi: [], safety: { rows: [] }, potency: { state: 'not_evaluated' },
          evidence_availability: { brain_exposure: 'not_evaluated' } },
      },
    ],
  };
}

function pathwayArm(key: string): PathwayArm {
  return {
    arm_key: key,
    program_id: 'th17_like',
    desired_change: 'decrease',
    condition: 'Rest',
    source: 'reactome',
    convergence_ref: 'conv|Rest|reactome',
    records: [
      {
        pathway_id: 'R-HSA-1',
        name: 'Signaling X',
        contributing_targets: ['ENSG1'],
        druggable: null,
        enrichment: { arm_headline_rankable: true, arm_coverage_disposition: 'rankable', enrichment_value: 1.2, n_hits_in_ranking: 5, source_coverage: 0.6 },
      },
    ],
  };
}

function pathwayView(): JoinedView {
  return {
    mode: 'same_time_contrast',
    geneArmA: null,
    geneArmB: null,
    pathwayArmA: pathwayArm('pathway|A'),
    pathwayArmB: pathwayArm('pathway|B'),
    pathway_context: 'reactome',
  } as unknown as JoinedView;
}

describe('renderRouteReal — distinct native path per route', () => {
  it('Drugs renders Stage-3 v2 candidate cards (not Stage-2 tables or a candidate ranking)', () => {
    renderRes({ route: 'drugs', artifact: stage3(), admission: 'admitted' });
    const canvas = screen.getByTestId('canvas');
    expect(canvas.querySelector('[data-route="drugs"]')).toBeTruthy();
    expect(within(canvas).getByText('cand-1')).toBeInTheDocument();
    expect(within(canvas).getByText('Examplib')).toBeInTheDocument();
    expect(within(canvas).getByText('stated')).toBeInTheDocument();
    expect(within(canvas).getByText('stage02_run_777')).toBeInTheDocument();
    // NOT the Stage-2 gene / pathway table headers
    expect(within(canvas).queryByText('disposition')).toBeNull();
    expect(within(canvas).queryByText('enrichment')).toBeNull();
    // never manufacture deprecated Stage-3 fields
    expect(canvas.textContent).not.toMatch(/gbm_context|directness|mechanism_direction/i);
    expect(canvas.textContent).not.toMatch(/candidate rank|overall rank|headline/i);
  });

  it('PK & Safety renders Stage-4 lanes; a not-evaluated lane is typed-missing, never safe/brain-penetrant/0', () => {
    renderRes({ route: 'pksafety', artifact: stage4(), admission: 'admitted' });
    const canvas = screen.getByTestId('canvas');
    expect(canvas.querySelector('[data-route="pksafety"]')).toBeTruthy();
    for (const lane of ['delivery', 'cns_mpo', 'transporters', 'exposure', 'nebpi', 'safety', 'potency', 'evidence_availability']) {
      expect(within(canvas).getByText(lane)).toBeInTheDocument();
    }
    // The native potency state is rendered verbatim; empty arrays stay record counts, not negatives.
    expect(within(canvas).getByText('not_evaluated')).toBeInTheDocument();
    expect(within(canvas).getAllByText('0 records').length).toBeGreaterThanOrEqual(3);
    expect(canvas.textContent).not.toMatch(/brain[- ]?penetrant|\bsafe\b/i);
    expect(within(canvas).getByText('production eligible')).toBeInTheDocument();
    expect(within(canvas).queryByText('not eligible')).toBeNull();
  });

  it('renders gene-arm rows VERBATIM — no browser re-sort, re-cap, or pair ranking', () => {
    // records deliberately NOT in rank order; the browser must render them in THIS order (the display
    // projection already applied the cap/sort — the browser is a faithful view, never a re-derivation).
    const arm = {
      arm_key: 'temporal|p|decrease|Rest|Stim48hr', program_id: 'p', desired_change: 'decrease',
      from_condition: 'Rest', to_condition: 'Stim48hr', n_targets: 3, n_evaluable: 3, n_ranked: 3,
      records: [
        { target_id: 'ENSG_C', base_key: 'p|ENSG_C', arm_value: -0.05, evaluable: true, temporal_status: 'evaluable', desired_target_modulation: 'x', rank: 3 },
        { target_id: 'ENSG_A', base_key: 'p|ENSG_A', arm_value: -0.30, evaluable: true, temporal_status: 'evaluable', desired_target_modulation: 'x', rank: 1 },
        { target_id: 'ENSG_B', base_key: 'p|ENSG_B', arm_value: -0.20, evaluable: true, temporal_status: 'evaluable', desired_target_modulation: 'x', rank: 2 },
      ],
    };
    const view = { mode: 'temporal_cross_condition', geneArmA: arm, geneArmB: null, pathwayArmA: null, pathwayArmB: null, pathway_context: 'reactome' } as unknown as JoinedView;
    renderRes({ route: 'targets', view, bundles: { temporal: null } as unknown as ResolvedBundles, admission: 'admitted' });
    const canvas = screen.getByTestId('canvas');
    const dataRows = [...canvas.querySelectorAll('tbody tr')];
    expect(dataRows.length).toBe(3); // no cap — every emitted row rendered
    const ranks = dataRows.map((tr) => tr.querySelector('td')?.textContent); // first column = rank
    expect(ranks).toEqual(['3', '1', '2']); // rendered in RECORDS order, NOT re-sorted to 1,2,3
  });

  it('Pathways renders pathway arms (not gene arms)', () => {
    renderRes({ route: 'pathways', view: pathwayView(), bundles: {} as unknown as ResolvedBundles, admission: 'admitted' });
    const canvas = screen.getByTestId('canvas');
    expect(canvas.querySelector('[data-route="pathways"]')).toBeTruthy();
    expect(within(canvas).getAllByText('Signaling X').length).toBeGreaterThan(0); // one per pathway arm
    expect(within(canvas).getAllByText('pathway').length).toBeGreaterThan(0); // pathway table header
    expect(within(canvas).queryByText('ensembl')).toBeNull(); // NOT the gene table
    expect(within(canvas).queryByText('disposition')).toBeNull();
  });
});
