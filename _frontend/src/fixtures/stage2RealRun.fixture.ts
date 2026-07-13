// Synthetic Stage-2 REAL-RUN artifact fixtures — schema/shape fixtures only (no real data).
//
// These mirror the AUTHORITATIVE serializations:
//   · screen.parquet   — FLAT rows (spot.stage02_screen.v1) carrying the real column set,
//                        incl. machine columns (delta_*, *_zscore, balanced_skew, support_*)
//                        the UI must PROJECT AWAY.
//   · temporal.parquet — FLAT rows with per-arm DiD + both endpoints AND the methods-only
//                        `batch_partially_confounded` field + reliability metric (projected
//                        away, never a reason to reject) + a stray `combined_temporal_score`
//                        (proves no combined column is ever surfaced).
//   · pathway.json     — records[].enrichment.{away_from_A,toward_b} + a machine field.
//
// The embedded selection is a NON-Treg pair (Th17-like → Th1-like) so the UI proves it
// supports arbitrary programs/directions, not a hardcoded Treg contrast. Temporal uses a
// DIFFERENT-timepoint pair (Rest → Stim48hr) — a batch_partially_confounded case.

import { fixtureProvenance } from './synthetic';

/** Non-Treg v1 selection embedded in the Stage-2 artifacts (fixture namespace). */
export const nonTregSelectionRaw = {
  schema_version: 'spot.stage01_selection.v1',
  namespace: 'fixture',
  production_gate_passed: false,
  source: 'local_demo_bridge',
  question_id: 'QUESTION_NONTREG_01',
  selection_id: 'SELECTION_NONTREG_01',
  contrast_id: 'fixture-nontreg-contrast-01',
  program_a: { program_id: 'th17_like', score_field: 'th17_like_score', display_label: 'Th17-like', direction: 'low' },
  program_b: { program_id: 'th1_like', score_field: 'th1_like_score', display_label: 'Th1-like', direction: 'high' },
  analysis_condition: 'Rest',
  dataset_id: 'FIXTURE_DATASET',
  donor_scope: 'all',
  artifact_status: 'fixture · production_eligible=false',
};

function prov(slug: string, seed: string, methodId: string, schemaVersion: string) {
  return {
    ...fixtureProvenance({
      stage: 'stage02',
      slug,
      seed,
      methodId,
      sources: [{ label: 'Reactome', record_id: 'R-FIX-0000', url: null, detail: 'Synthetic (fixture)' }],
      upstream: { stage: 'stage01', slug: 'demo_selection', seed: 'a1b1c1d1' },
    }),
    schema_version: schemaVersion,
  };
}

/** One flat screen row carrying the real column set incl. machine columns to be projected away. */
function screenRow(over: Record<string, unknown>) {
  return {
    schema_version: 'spot.stage02_screen.v1',
    contrast_id: 'fixture-nontreg-contrast-01',
    run_id: 'fixture-nontreg-contrast-01',
    source_row_id: 'srcrow-fixture-0',
    condition: 'Rest',
    // machine / provenance columns the UI must NOT surface:
    n_cells_target: 240,
    n_donors_effective: 4,
    n_guides: 4,
    qc_ontarget_effect_size: -1.2,
    qc_low_target_expression: false,
    qc_target_baseMean: 33.1,
    mask_resolved: true,
    mask_gene_count: 3,
    delta_A: -0.61,
    delta_B: 0.4,
    balanced_skew: 0.9, // combined/diagnostic axis — must be projected away
    away_from_A_zscore: -2.1,
    toward_b_zscore: 1.3,
    balanced_skew_zscore: 1.9,
    support_state: 'within_dataset_replicated',
    evidence_tier: 'tier_1',
    desired_target_modulation: 'repress',
    crispri_modality: 'CRISPRi',
    inference_status: 'not_calibrated',
    ...over,
  };
}

// ── screen.parquet (flat) ──
export const directScreenFixtureRaw = {
  provenance: prov('demo_direct_screen', 'd1d1d1d1', 'target_masked_direct_screen.fixture', 'spot.stage02_screen.v1'),
  selection: nonTregSelectionRaw,
  condition: 'Rest',
  rows: [
    screenRow({
      target_ensembl: 'ENSG00000000001',
      target_symbol: 'GENE_A',
      qc_ontarget_significant: true,
      eligibility_state: 'eligible',
      direction_class: 'aligned_both',
      rank: 1,
      away_from_A: -0.52,
      toward_b: 0.31,
    }),
    screenRow({
      target_ensembl: 'ENSG00000000002',
      target_symbol: 'GENE_B',
      qc_ontarget_significant: true,
      eligibility_state: 'eligible',
      direction_class: 'aligned_away_a_only',
      rank: 2,
      away_from_A: -0.44,
      toward_b: null, // arm not evaluated at this condition
    }),
    screenRow({
      target_ensembl: 'ENSG00000000003',
      target_symbol: null,
      qc_ontarget_significant: false,
      eligibility_state: 'ineligible_ontarget_not_significant',
      direction_class: 'not_evaluated',
      rank: null,
      away_from_A: null,
      toward_b: null,
    }),
  ],
};

// ── temporal.parquet (flat, DiD + both endpoints + methods-only batch machine fields) ──
function temporalRow(over: Record<string, unknown>) {
  return {
    schema_version: 'spot.stage02_temporal.v1',
    method_version: 'stage2-temporal-cross-condition-v1-did-on-program-projections',
    inference_status: 'not_calibrated',
    // methods-only machine fields — projected away, NEVER rendered, NEVER a reason to reject:
    batch_partially_confounded: true,
    batch_reliability_metric: 0.42,
    interaction_std_program: 0.47,
    combined_temporal_score: 0.7, // stray combined column — must never be surfaced
    ...over,
  };
}

export const temporalDiDFixtureRaw = {
  provenance: prov('demo_temporal', 'd2d2d2d2', 'temporal_did_population.fixture', 'spot.stage02_temporal.v1'),
  selection: { ...nonTregSelectionRaw, analysis_condition: 'Stim48hr' },
  from_condition: 'Rest',
  to_condition: 'Stim48hr',
  analysis_mode: 'temporal_cross_condition',
  rows: [
    temporalRow({
      target_ensembl: 'ENSG00000000001',
      target_symbol: 'GENE_A',
      away_from_A_did: -0.12,
      toward_b_did: 0.05,
      away_from_A_from: -0.52,
      away_from_A_to: -0.64,
      toward_b_from: 0.31,
      toward_b_to: 0.36,
      present_from: true,
      present_to: true,
    }),
    temporalRow({
      target_ensembl: 'ENSG00000000004',
      target_symbol: 'GENE_D',
      away_from_A_did: null,
      toward_b_did: null,
      away_from_A_from: -0.2,
      away_from_A_to: null,
      toward_b_from: 0.1,
      toward_b_to: null,
      present_from: true,
      present_to: false, // union row: absent at the `to` endpoint
    }),
  ],
};

// ── pathway.json (records[].enrichment.{away_from_A,toward_b}) ──
export const pathwayConvergenceFixtureRaw = {
  provenance: prov('demo_pathway', 'd3d3d3d3', 'target_ranked_pathway_convergence.fixture', 'spot.stage02_pathway.v1'),
  selection: nonTregSelectionRaw,
  condition: 'Rest',
  gene_set_source: 'reactome',
  records: [
    {
      pathway_id: 'R-HSA-FIX01',
      name: 'Synthetic convergent signature 01',
      contributing_targets: ['ENSG00000000001', 'ENSG00000000002'],
      druggable: true,
      method: 'Reactome overrepresentation (target-ranked)', // machine field, projected away
      source_hash: 'fixturehashpathway01', // machine field, projected away
      enrichment: {
        away_from_A: {
          arm_coverage_disposition: 'rankable',
          arm_headline_rankable: true,
          enrichment_value: 2.1,
          n_hits_in_ranking: 4,
          source_coverage: 0.66,
        },
        toward_b: {
          arm_coverage_disposition: 'descriptive_only_thin_arm',
          arm_headline_rankable: false,
          enrichment_value: 1.4,
          n_hits_in_ranking: 2,
          source_coverage: 0.33,
        },
      },
    },
    {
      pathway_id: 'R-HSA-FIX02',
      name: 'Synthetic convergent signature 02',
      contributing_targets: ['ENSG00000000001'],
      druggable: false,
      method: 'Reactome overrepresentation (target-ranked)',
      source_hash: 'fixturehashpathway02',
      enrichment: {
        away_from_A: {
          arm_coverage_disposition: 'descriptive_only_low_source_coverage',
          arm_headline_rankable: false,
          enrichment_value: null,
          n_hits_in_ranking: 1,
          source_coverage: 0.2,
        },
        toward_b: {
          arm_coverage_disposition: 'undefined',
          arm_headline_rankable: false,
          enrichment_value: null,
          n_hits_in_ranking: 0,
          source_coverage: 0.0,
        },
      },
    },
  ],
};
