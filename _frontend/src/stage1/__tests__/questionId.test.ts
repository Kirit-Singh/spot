// deriveQuestionId pins the Stage-1 contract 539431d biology-only recipe:
//   question_id = sha256(canonical_json({
//     A:{program_id,direction,condition:conditions[0]},
//     B:{program_id,direction,condition:conditions[-1]}, analysis_mode}))[:16]
// KNOWN-VALUE bytes below are computed once from the exact canonical recipe; a drift in key order,
// spacing, ASCII-escaping, or the [:16] truncation changes them and fails this test.

import { describe, expect, it } from 'vitest';
import { deriveQuestionId } from '../questionId';

const A = { program_id: 'treg_like', direction: 'low' };
const B = { program_id: 'th1_like', direction: 'high' };

describe('deriveQuestionId — 539431d biology-only recipe', () => {
  it('KNOWN VALUE: temporal cross-condition (from=Rest, to=Stim48hr)', async () => {
    expect(await deriveQuestionId(A, B, ['Rest', 'Stim48hr'], 'temporal_cross_condition')).toBe('e09645d2ce31129f');
  });

  it('KNOWN VALUE: within_condition (single condition → from==to)', async () => {
    expect(await deriveQuestionId(A, B, ['Stim48hr'], 'within_condition')).toBe('a259b68d78b4f339');
  });

  it('is a 16-hex-char slice and deterministic', async () => {
    const q = await deriveQuestionId(A, B, ['Rest', 'Stim48hr'], 'temporal_cross_condition');
    expect(q).toMatch(/^[0-9a-f]{16}$/);
    expect(q).toBe(await deriveQuestionId(A, B, ['Rest', 'Stim48hr'], 'temporal_cross_condition'));
  });

  it('binds ONLY the ordered endpoints — intermediate conditions never enter the id', async () => {
    // conditions[0] and conditions[-1] are the only condition inputs: a different middle → same id.
    const two = await deriveQuestionId(A, B, ['Rest', 'Stim48hr'], 'temporal_cross_condition');
    const three = await deriveQuestionId(A, B, ['Rest', 'Stim8hr', 'Stim48hr'], 'temporal_cross_condition');
    expect(three).toBe(two);
  });

  it('changes when ANY bound field changes (program / direction / endpoint / mode)', async () => {
    const base = await deriveQuestionId(A, B, ['Rest', 'Stim48hr'], 'temporal_cross_condition');
    expect(await deriveQuestionId({ ...A, program_id: 'th17_like' }, B, ['Rest', 'Stim48hr'], 'temporal_cross_condition')).not.toBe(base);
    expect(await deriveQuestionId({ ...A, direction: 'high' }, B, ['Rest', 'Stim48hr'], 'temporal_cross_condition')).not.toBe(base);
    expect(await deriveQuestionId(A, B, ['Rest', 'Stim8hr'], 'temporal_cross_condition')).not.toBe(base); // changed 'to'
    expect(await deriveQuestionId(A, B, ['Stim8hr', 'Stim48hr'], 'temporal_cross_condition')).not.toBe(base); // changed 'from'
    expect(await deriveQuestionId(A, B, ['Rest', 'Stim48hr'], 'within_condition')).not.toBe(base); // changed mode
  });

  it('is ORDER-SENSITIVE in the poles (A↔B swap → different question)', async () => {
    const ab = await deriveQuestionId(A, B, ['Rest', 'Stim48hr'], 'temporal_cross_condition');
    const ba = await deriveQuestionId(B, A, ['Rest', 'Stim48hr'], 'temporal_cross_condition');
    expect(ba).not.toBe(ab);
  });
});
