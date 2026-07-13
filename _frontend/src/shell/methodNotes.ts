// Method & interpretation notes that used to live as editorial sentences on the
// main canvas. They belong once, here, surfaced only inside Methods & provenance.
// Keep each body a single concise line — a field, not an essay.

import type { ProvNote } from './provenanceContext';

/**
 * Present on every stage: the single factual production-gate/promotion record.
 * (Merges the former Stage-3-specific "Promotion" note so the point is stated once.)
 */
export const PRODUCTION_GATE_NOTE: ProvNote = {
  title: 'Production gate',
  body: 'Frozen Stage-1 has 0/33 production-selectable pairs, so promotion is disabled: research_only / fixture candidates can be inspected but never promoted, and such a context never yields a production pointer. Research analysis stays available.',
};

export const STAGE2_NOTES: ProvNote[] = [
  {
    title: 'Two independent objectives',
    body: 'away_from_A and toward_B carry independent nullable per-arm ranks; never merged into a combined or balanced score.',
  },
  {
    title: 'Not-evaluated arms',
    body: 'A not-evaluated arm shows its reason and a null rank — not a zero and not a low score.',
  },
  {
    title: 'Pathway support',
    body: 'Pathway rows are descriptive Reactome overrepresentation among lever genes — support, not causal confirmation.',
  },
  PRODUCTION_GATE_NOTE,
];

export const STAGE3_NOTES: ProvNote[] = [
  {
    title: 'Evidence is not collapsed',
    body: 'Mixed, conflicting and not-evaluated states stay as-is — no best-evidence collapse and no composite rank.',
  },
  // Promotion is covered once by the shared Production gate note above.
  PRODUCTION_GATE_NOTE,
];

export const STAGE4_NOTES: ProvNote[] = [
  {
    title: 'Missingness semantics',
    body: 'Measured / calculated / label-derived / not-evaluated / missing are distinguished; a missing value stays null, never zero or estimated.',
  },
  {
    title: 'CNS-MPO is a heuristic',
    body: 'CNS-MPO is a physicochemical property heuristic, not a measurement of clinical brain exposure.',
  },
  {
    title: 'No composite ranking',
    body: 'No fabricated composite; sorting is offered only for evidence completeness or NEBPI tier when the adapter supplies it.',
  },
  PRODUCTION_GATE_NOTE,
];
