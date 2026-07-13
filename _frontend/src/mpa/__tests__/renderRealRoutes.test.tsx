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
    schema_version: 'spot.stage03_drug_annotation.v1',
    bundle_id: 's3_bundle01',
    manifest_sha256: 'a'.repeat(64),
    upstream_stage2_run: 'stage02_run_777',
    candidates: [
      {
        candidate_id: 'cand-1',
        active_moiety_id: 'MOI1',
        preferred_name: 'Examplib',
        identity_status: 'resolved',
        form_ids: ['F1', 'F2'],
        target_ensembls: ['ENSG1', 'ENSG2'],
        n_edges: 3,
        n_direct_gene_edges: 1,
        development_state_aggregate: 'approved',
        n_potency_rows: 0,
        potency_state: null, // → typed em-dash
        observed_perturbation_arms: ['arm1'],
        inverse_direction_support: 'supported',
        pathway_hypothesis_arms: [],
        stage3_evidence_classes: ['observed_perturbation_target'],
        disease_context_review_status: 'reviewed',
        disease_context_review_result: 'eligible',
        stage4_assessment_status: 'queued',
        source_record_ids: ['s1'],
      },
    ],
  };
}

function stage4(): Stage4UiArtifact {
  return {
    schema_version: 'spot.stage04_scorecards.v1',
    scorecard_set_id: 's4_set01',
    stage4_method_version: 'stage4-evidence-v2',
    upstream_stage3_bundle: 's3_bundle01',
    candidates: [
      {
        candidate_id: 'cand-1',
        active_moiety: 'Examplib',
        compound_ids: ['CID1'],
        target: 'TARGET1',
        mechanism: 'inhibitor',
        production_eligible: null, // → eligibility not_evaluated, never "not eligible"
        production_eligible_reason: null,
        lanes: { delivery: 'oral', cns_mpo: '4.5', transporters: null, exposure: null, nebpi: 'context_specific', safety: null },
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
  it('Drugs renders Stage-3 cards (not Stage-2 tables); a null field is a typed em-dash; no deprecated fields', () => {
    renderRes({ route: 'drugs', artifact: stage3(), admission: 'admitted' });
    const canvas = screen.getByTestId('canvas');
    expect(canvas.querySelector('[data-route="drugs"]')).toBeTruthy();
    expect(within(canvas).getByText('cand-1')).toBeInTheDocument();
    expect(within(canvas).getByText('Examplib')).toBeInTheDocument();
    expect(within(canvas).getByText('approved')).toBeInTheDocument();
    expect(within(canvas).getByText('stage02_run_777')).toBeInTheDocument();
    // NOT the Stage-2 gene / pathway table headers
    expect(within(canvas).queryByText('disposition')).toBeNull();
    expect(within(canvas).queryByText('enrichment')).toBeNull();
    // never manufacture deprecated Stage-3 fields
    expect(canvas.textContent).not.toMatch(/gbm_context|directness|mechanism_direction/i);
    // the null potency_state renders as a compact em-dash
    expect(canvas.textContent).toContain('—');
  });

  it('PK & Safety renders Stage-4 lanes; a not-evaluated lane is typed-missing, never safe/brain-penetrant/0', () => {
    renderRes({ route: 'pksafety', artifact: stage4(), admission: 'admitted' });
    const canvas = screen.getByTestId('canvas');
    expect(canvas.querySelector('[data-route="pksafety"]')).toBeTruthy();
    for (const lane of ['delivery', 'cns_mpo', 'transporters', 'exposure', 'nebpi', 'safety']) {
      expect(within(canvas).getByText(lane)).toBeInTheDocument();
    }
    // three null lanes (transporters/exposure/safety) → not_evaluated; never an inferred negative
    expect(within(canvas).getAllByText('not_evaluated').length).toBeGreaterThanOrEqual(3);
    expect(canvas.textContent).not.toMatch(/brain[- ]?penetrant|\bsafe\b/i);
    // eligibility null → not_evaluated pill, never "not eligible"; NEBPI keeps context specificity
    expect(within(canvas).getByText(/eligibility not_evaluated/i)).toBeInTheDocument();
    expect(within(canvas).queryByText('not eligible')).toBeNull();
    expect(within(canvas).getByText('context_specific')).toBeInTheDocument();
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
