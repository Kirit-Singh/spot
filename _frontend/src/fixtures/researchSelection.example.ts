// A valid `spot.stage01_selection.v1` object as the Stage-1 research bridge would
// write it to localStorage: namespace research_only, production_gate_passed=false,
// source stage01_research_bridge, an ordered A→B program pair, one condition, and
// stable ids. It carries NO combined objective. Used by ingestion tests and by the
// browser-QA injection snippet. This is a real research SELECTION (unscored), not a
// synthetic fixture RESULT.

export const researchSelectionExampleRaw = {
  schema_version: 'spot.stage01_selection.v1',
  namespace: 'research_only',
  production_gate_passed: false,
  source: 'stage01_research_bridge',
  question_id: 'Q_treg_to_th1_stim48',
  selection_id: 'SEL_treg_to_th1_stim48_r1',
  contrast_id: 'a1b2c3d4e5f60718',
  program_a: {
    program_id: 'treg_like',
    score_field: 'treg_like_score',
    display_label: 'Treg-like',
    direction: 'low',
  },
  program_b: {
    program_id: 'th1_like',
    score_field: 'th1_like_score',
    display_label: 'Th1-like',
    direction: 'high',
  },
  analysis_condition: 'Stim48hr',
  dataset_id: 'marson2025_gwcd4_perturbseq',
  donor_scope: 'all',
  artifact_status: 'research_only · production_eligible=false',
};
