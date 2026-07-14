// Synthetic Stage-2 target set — DEMO data (fixture namespace, production_eligible=false).
//
// Renders only behind the explicit demo gate; never on the default canvas. Demonstrates
// every joint status (both_arms / a_only / b_only / opposed / not_evaluated), Pareto
// tiers, marker-breadth diagnostics, and convergent pathway nodes. All ids synthetic.

import { selectionFixtureRaw } from './selection.fixture';
import { fixtureProvenance } from './synthetic';

const REACTOME = {
  label: 'Reactome',
  record_id: 'R-FIX-0000',
  url: null,
  detail: 'Synthetic descriptive overrepresentation record (fixture)',
};
const DEPMAP = {
  label: 'DepMap',
  record_id: 'DEPMAP-FIX-0000',
  url: null,
  detail: 'Synthetic essentiality annotation (fixture)',
};

function armNotEvaluated(reason: string) {
  return { evaluated: false, reason, effect: null, rank: null, coverage: null };
}

function breadth(supporting_markers: number, single_marker_driven: boolean, detail: string | null = null) {
  return { supporting_markers, single_marker_driven, detail };
}

function evidence(overrides: Record<string, unknown> = {}) {
  return {
    guides: [
      { guide_id: 'GUIDE_1', effect: -0.41, sign_agrees: true },
      { guide_id: 'GUIDE_2', effect: -0.33, sign_agrees: true },
    ],
    donor_support: { effective_n: 4, denominator: 'NTC guides at CONDITION_01', pair_discordance: false },
    on_target_detected: true,
    perturb2state: 'direct_only',
    depmap: { status: 'non_essential', detail: 'synthetic' },
    support_status: 'screen_only',
    source_links: [
      { label: 'stage02_screen (fixture)', url: null, detail: 'row for this gene (synthetic)' },
    ],
    ...overrides,
  };
}

export const stage2FixtureRaw = {
  provenance: fixtureProvenance({
    stage: 'stage02',
    slug: 'demo_lever_set',
    seed: 'a2b2c2d2',
    methodId: 'target_masked_measured_effect_screen.fixture',
    sources: [REACTOME, DEPMAP],
    upstream: { stage: 'stage01', slug: 'demo_selection', seed: 'a1b1c1d1' },
  }),
  selection: selectionFixtureRaw,
  tested_family_size: 128,
  significance_calibrated: false,
  joint_ordering_method_id: 'pareto_joint_order.fixture.v1',
  levers: [
    {
      gene_id: 'GENE_A',
      ensembl_id: 'ENSGFIX00000000A',
      arms: {
        away_from_A: { evaluated: true, reason: null, effect: -0.52, rank: 1, coverage: 0.88 },
        toward_B: { evaluated: true, reason: null, effect: 0.31, rank: 2, coverage: 0.61 },
      },
      joint_status: 'both_arms',
      pareto_tier: 1,
      marker_breadth: breadth(6, false, 'broad marker support (synthetic)'),
      evidence: evidence({ support_status: 'within_dataset_replicated' }),
    },
    {
      gene_id: 'GENE_B',
      ensembl_id: 'ENSGFIX00000000B',
      arms: {
        away_from_A: { evaluated: true, reason: null, effect: -0.44, rank: 2, coverage: 0.79 },
        toward_B: armNotEvaluated('B pole unrepresented at CONDITION_01 (G-frac gate not passed)'),
      },
      joint_status: 'a_only',
      pareto_tier: 1,
      marker_breadth: breadth(1, true, 'single-marker driven (synthetic)'),
      evidence: evidence({ perturb2state: 'perturb2state_supported' }),
    },
    {
      gene_id: 'GENE_C',
      ensembl_id: 'ENSGFIX00000000C',
      arms: {
        away_from_A: { evaluated: true, reason: null, effect: -0.29, rank: 3, coverage: 0.72 },
        toward_B: { evaluated: true, reason: null, effect: -0.18, rank: 4, coverage: 0.55 },
      },
      joint_status: 'opposed',
      pareto_tier: 3,
      marker_breadth: breadth(3, false),
      evidence: evidence({
        support_status: 'confounded',
        donor_support: { effective_n: 4, denominator: 'NTC guides at CONDITION_01', pair_discordance: true },
      }),
    },
    {
      gene_id: 'GENE_D',
      ensembl_id: null,
      arms: {
        away_from_A: armNotEvaluated('insufficient target-cell count (below frozen minimum)'),
        toward_B: { evaluated: true, reason: null, effect: 0.22, rank: 1, coverage: 0.5 },
      },
      joint_status: 'b_only',
      pareto_tier: 2,
      marker_breadth: breadth(2, false),
      evidence: evidence({
        on_target_detected: null,
        support_status: 'underpowered',
        depmap: { status: 'not_evaluated', detail: null },
      }),
    },
    {
      gene_id: 'GENE_E',
      ensembl_id: 'ENSGFIX00000000E',
      arms: {
        away_from_A: armNotEvaluated('no statistically detectable on-target repression under source analysis'),
        toward_B: armNotEvaluated('B pole unrepresented at CONDITION_01 (G-frac gate not passed)'),
      },
      joint_status: 'not_evaluated',
      pareto_tier: null,
      marker_breadth: breadth(0, false),
      evidence: evidence({
        on_target_detected: false,
        support_status: 'underpowered',
        guides: [{ guide_id: 'GUIDE_1', effect: null, sign_agrees: null }],
        perturb2state: 'not_evaluated',
      }),
    },
    {
      gene_id: 'GENE_F',
      ensembl_id: 'ENSGFIX00000000F',
      arms: {
        away_from_A: { evaluated: true, reason: null, effect: -0.21, rank: 4, coverage: 0.64 },
        toward_B: armNotEvaluated('B pole unrepresented at CONDITION_01 (G-frac gate not passed)'),
      },
      joint_status: 'a_only',
      pareto_tier: 2,
      marker_breadth: breadth(1, true, 'single-marker driven (synthetic)'),
      evidence: evidence({ perturb2state: 'perturb2state_discordant' }),
    },
  ],
  pathways: [
    {
      pathway_id: 'PATHWAY_01',
      name: 'Synthetic convergent signature 01',
      contributing_targets: ['GENE_A', 'GENE_B', 'GENE_F'],
      arm_support: 'a',
      enrichment: 2.1,
      druggable: true,
      method: 'Reactome overrepresentation',
      source_hash: 'fixturehashpathway01',
    },
    {
      pathway_id: 'PATHWAY_02',
      name: 'Synthetic convergent signature 02',
      contributing_targets: ['GENE_A', 'GENE_D'],
      arm_support: 'both',
      enrichment: null,
      druggable: false,
      method: 'Reactome overrepresentation',
      source_hash: 'fixturehashpathway02',
    },
  ],
};
