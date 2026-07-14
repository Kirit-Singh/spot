/** Display-only projection of an independently verified Stage-1 v3 selection.
 *
 * This deliberately keeps the two endpoints separate. It is used only in the downstream
 * Methods & provenance drawer; scientific routing continues to consume SelectionV3 itself.
 */
export interface SelectionDisplayEndpoint {
  program_id: string;
  display_label: string;
  direction: 'high' | 'low';
  condition: string;
}

export interface SelectionDisplayContext {
  selection_id: string;
  question_id: string;
  analysis_mode: 'within_condition' | 'temporal_cross_condition';
  execution_status: 'ready' | 'refused' | 'awaiting_estimator';
  estimator_id: string;
  estimator_status: 'available' | 'not_implemented';
  A: SelectionDisplayEndpoint;
  B: SelectionDisplayEndpoint;
}
