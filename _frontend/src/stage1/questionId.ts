// Biology-only ordered-question identity (Stage-1 contract 539431d canonical recipe). It binds ONLY the
// scientific question — the two poles' program/direction/condition (A@from, B@to) + analysis_mode — with
// NO method/input binding, so ONE question_id names a biological question across method/registry/source
// revisions. selection_id stays the DISTINCT method/input-bound identity (over canonical_content). The
// browser re-derives this independently and refuses a null or tampered/reforged question_id.
//
//   question_id = sha256(canonical_json({
//     "A": {"program_id", "direction", "condition": conditions[0]},
//     "B": {"program_id", "direction", "condition": conditions[-1]},
//     "analysis_mode"}))[:16]
//
// canonical_json = sorted keys, no spaces, ensure_ascii — byte-identical to the emitter's canonicalJSON.

import { canonicalJson, sha256Hex } from './canonical';

export interface QuestionPole {
  program_id: string;
  direction: string;
}

/** Re-derive the biology-only question_id from the poles + ordered conditions + mode (539431d recipe). */
export async function deriveQuestionId(A: QuestionPole, B: QuestionPole, conditions: string[], analysis_mode: string): Promise<string> {
  const qc = {
    A: { program_id: A.program_id, direction: A.direction, condition: conditions[0] },
    B: { program_id: B.program_id, direction: B.direction, condition: conditions[conditions.length - 1] },
    analysis_mode,
  };
  return (await sha256Hex(canonicalJson(qc))).slice(0, 16);
}
