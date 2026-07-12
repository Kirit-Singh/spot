// Selection threaded across the MPA via URL params + the canonical id hierarchy
// (question_id → selection_id → stage2_run_id → …), never SPA memory.

export interface SelectionThread {
  selection_id: string | null;
  question_id: string | null;
  stage2_run_id: string | null;
}

export function readSelectionThread(): SelectionThread {
  if (typeof window === 'undefined') {
    return { selection_id: null, question_id: null, stage2_run_id: null };
  }
  const p = new URLSearchParams(window.location.search);
  return {
    selection_id: p.get('selection_id'),
    question_id: p.get('question_id'),
    stage2_run_id: p.get('stage2_run_id'),
  };
}
