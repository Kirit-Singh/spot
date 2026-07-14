// Synthetic Stage-1 selection for the local demo bridge.
//
// This is a VALID selection-shaped object but it did NOT pass the live production
// Stage-1 gate: namespace=fixture, production_gate_passed=false, source=local_demo_bridge.

export const selectionFixtureRaw = {
  schema_version: 'spot.stage01_selection.v1',
  namespace: 'fixture',
  production_gate_passed: false,
  source: 'local_demo_bridge',
  question_id: 'QUESTION_DEMO_01',
  selection_id: 'SELECTION_DEMO_01',
  contrast_id: 'fixture-demo-contrast-01',
  program_a: {
    program_id: 'PROGRAM_A',
    score_field: 'program_a_score',
    display_label: 'Program A (regulatory-like)',
    direction: 'low',
  },
  program_b: {
    program_id: 'PROGRAM_B',
    score_field: 'program_b_score',
    display_label: 'Program B (inflammatory-like)',
    direction: 'high',
  },
  analysis_condition: 'CONDITION_01',
  dataset_id: 'FIXTURE_DATASET',
  donor_scope: 'all',
  artifact_status: 'fixture · production_eligible=false',
};
