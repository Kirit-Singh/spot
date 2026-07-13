// RUNTIME derivation of the active Stage-1 v3 selection's identity. results/current.json is
// SELECTION-INDEPENDENT (one reusable admitted release serves ARBITRARY within/temporal dropdown
// choices without regeneration); the browser INDEPENDENTLY re-derives the active selection's
// analysis_mode + selection_id + exact two gene arm keys here, then selects those slots from the global
// release (Stage-2) and — per the published W6/W3 Stage-3/4 contracts — will filter Stage-3 by arm
// membership and Stage-4 by the selected Stage-3 candidate membership.
//
// The gene arm keys are derived from the selection's A/B programs + directions + condition(s) via the
// SAME joinPlan the view uses, so they are the exact selected arms and source-independent. `question_id`
// is intentionally NOT derived yet — W13 owns the required biology-only canonical recipe; it will be
// re-derived + required here (alongside selection_id/mode/arm keys) once that handoff lands.

import type { SelectionV3 } from '../adapters/selectionV3Adapter';
import { selectionToJoinInput } from '../repository/joinResolver';
import { joinPlan } from '../repository/joinSemantics';

export interface SelectionIdentity {
  selection_id: string;
  analysis_mode: 'within_condition' | 'temporal_cross_condition';
  /** The two exact selected gene arm keys (Direct for within, Temporal for cross-time), sorted. */
  arm_keys: string[];
}

/** Independently derive the active selection's binding identity. Throws (via joinPlan) on a malformed selection. */
export function selectionIdentity(sel: SelectionV3): SelectionIdentity {
  const plan = joinPlan(selectionToJoinInput(sel, 'reactome')); // gene arm keys are source-independent
  return {
    selection_id: sel.selection_id,
    analysis_mode: sel.analysis_mode,
    arm_keys: [...plan.gene_arm_keys].sort(),
  };
}
