// RUNTIME derivation of the active Stage-1 v3 selection's identity. results/current.json is
// SELECTION-INDEPENDENT (one reusable admitted release serves ARBITRARY within/temporal dropdown
// choices without regeneration); the browser INDEPENDENTLY re-derives the active selection's
// analysis_mode + selection_id + exact two gene arm keys here, then selects those slots from the global
// release (Stage-2) and — per the published W6/W3 Stage-3/4 contracts — will filter Stage-3 by arm
// membership and Stage-4 by the selected Stage-3 candidate membership.
//
// The gene arm keys are derived from the selection's A/B programs + directions + condition(s) via the
// SAME joinPlan the view uses, so they are the exact selected arms and source-independent. The biology-only
// `question_id` (Stage-1 contract 539431d recipe) is re-derived + required upstream in parseSelectionV3
// (a null or reforged value is refused there); it is carried through here alongside selection_id/mode/arm
// keys, DISTINCT from the method/input-bound selection_id.

import type { SelectionV3 } from '../adapters/selectionV3Adapter';
import { selectionToJoinInput } from '../repository/joinResolver';
import { joinPlan } from '../repository/joinSemantics';

export interface SelectionIdentity {
  selection_id: string; // method/input-bound (distinct from question_id)
  question_id: string; // biology-only ordered-question identity (539431d), verified upstream
  analysis_mode: 'within_condition' | 'temporal_cross_condition';
  /** The two exact selected gene arm keys (Direct for within, Temporal for cross-time), sorted. */
  arm_keys: string[];
}

/**
 * Independently derive the active selection's binding identity. Throws (via joinPlan) on a malformed
 * selection, and REFUSES only IDENTICAL FULL ENDPOINTS (both poles resolve to the exact same arm) — a
 * same-program same-direction CROSS-TIME selection stays valid (its two poles carry distinct
 * desired_change arms: away_from_A vs toward_b). selection_id and question_id are both carried (the
 * biology-only question_id is re-derived + verified upstream in parseSelectionV3; a null/mismatch is
 * refused there).
 */
export function selectionIdentity(sel: SelectionV3): SelectionIdentity {
  const plan = joinPlan(selectionToJoinInput(sel, 'reactome')); // gene arm keys are source-independent
  if (plan.gene_arm_keys[0] === plan.gene_arm_keys[1]) {
    throw new Error('identical full endpoints — both poles resolve to the same arm; refuse');
  }
  return {
    selection_id: sel.selection_id,
    question_id: sel.question_id,
    analysis_mode: sel.analysis_mode,
    arm_keys: [...plan.gene_arm_keys].sort(),
  };
}
