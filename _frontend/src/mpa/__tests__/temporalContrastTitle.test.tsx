// The contrast title must state EACH POLE'S OWN condition. A temporal selection runs an ordered
// From → To across two timepoints, so collapsing both poles to conditions[0] silently relabels the
// To endpoint with the From condition — an 8hr → 48hr selection reading "8 hr → 8 hr".
//
// These tests pin the fix at both levels and on BOTH temporal directions (8→48 AND 48→8, so a test
// cannot pass by hard-coding one order), on every downstream tab that carries the header:
//   · contrastFromV3 + contrastTitle — the pure projection and its formatting
//   · StageIsland — the rendered header on Targets, Pathways, Drugs and PK & Safety
//
// The A/B roles stay ORDERED: A is always the From endpoint, B the To endpoint (selectionV3 rejects
// a temporal contract whose two conditions are equal). Programs are generic — the same program at two
// timepoints is a legitimate temporal selection, so nothing here is Treg/Th1-specific.

import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { StageIsland, contrastFromV3 } from '../StageIsland';
import { contrastTitle } from '../contrastTitle';
import type { PageKey } from '../pages';
import { SELECTION_V3_KEY } from '../../repository/source';
import { canonicalJson, sha256Hex } from '../../stage1/canonical';
import { deriveExecutionStatus } from '../../stage1/selectionV3';
import { deriveQuestionId } from '../../stage1/questionId';
import { parseSelectionV3 } from '../../adapters/selectionV3Adapter';
import type { SelectionV3 } from '../../adapters/selectionV3Adapter';

/** Two generic programs; the temporal cases move ONE program across two timepoints. */
const PROGRAMS = [
  { program_id: 'prog_alpha', display_label: 'Alpha' },
  { program_id: 'prog_beta', display_label: 'Beta' },
];
const LABELS = new Map(PROGRAMS.map((p) => [p.program_id, p.display_label]));

interface PoleSpec {
  program_id: string;
  direction: 'high' | 'low';
}

/**
 * A spot.stage01_selection.v3 contract with REAL recomputed hashes, so the fail-closed verifier
 * (parseSelectionV3) accepts it. `conditions` is the ORDERED condition axis: [from, to] for a
 * temporal selection, [condition] for a within-condition one.
 */
async function buildV3(A: PoleSpec, B: PoleSpec, conditions: string[]): Promise<Record<string, unknown>> {
  const mode = conditions.length === 2 ? 'temporal_cross_condition' : 'within_condition';
  const estimatorId = mode === 'temporal_cross_condition' ? 'temporal_cross_condition_v1' : 'within_condition_v1';
  const cc: Record<string, unknown> = {
    A: { program_id: A.program_id, score_field: `${A.program_id}_score`, direction: A.direction },
    B: { program_id: B.program_id, score_field: `${B.program_id}_score`, direction: B.direction },
    analysis_mode: mode,
    combined_objective: null,
    conditions,
    dataset_id: 'marson2025_gwcd4_perturbseq',
    donor_scope: 'all',
    effect_universe_id: 'eu',
    poles_separate: true,
    registry_scorer_view_sha256: 'a'.repeat(64),
    source_h5ad_sha256: 'b'.repeat(64),
    source_hf_revision: 'rev1',
    stage1_method_version: 'stage1-continuous-v3.0.1',
  };
  const selFull = await sha256Hex(canonicalJson(cc));
  const contract: Record<string, unknown> = {
    schema_version: 'spot.stage01_selection.v3',
    selection_origin: 'user_selected',
    execution_status: deriveExecutionStatus(mode, 'available', 'available', 'available'),
    analysis_mode: mode,
    estimator_id: estimatorId,
    estimator_status: 'available',
    selection_id: selFull.slice(0, 16),
    selection_full_sha256: selFull,
    canonical_content: cc,
    poles: {
      A: { program_id: A.program_id, direction: A.direction, effect_projection_status: 'available', n_measured: 5, n_panel_in_effect_universe: 5, n_control_in_effect_universe: 5, reason_codes: [] },
      B: { program_id: B.program_id, direction: B.direction, effect_projection_status: 'available', n_measured: 4, n_panel_in_effect_universe: 4, n_control_in_effect_universe: 4, reason_codes: [] },
    },
    trust_bindings: { validation_raw_sha256: 'c'.repeat(64) },
    provenance_bindings: { primary_registry_v3_raw_sha256: 'd'.repeat(64) },
    historical_validation_provenance: { kind: 'frozen', selectability_v3_raw_sha256: 'e'.repeat(64), active_gate: false },
    question_id: await deriveQuestionId(A, B, conditions, mode),
  };
  contract.full_contract_content_sha256 = await sha256Hex(canonicalJson(contract));
  return contract;
}

/** The same contract, through the real fail-closed verifier — never a hand-built SelectionV3. */
async function verified(A: PoleSpec, B: PoleSpec, conditions: string[]): Promise<SelectionV3> {
  return parseSelectionV3(await buildV3(A, B, conditions));
}

const ALPHA_HI: PoleSpec = { program_id: 'prog_alpha', direction: 'high' };
const BETA_LO: PoleSpec = { program_id: 'prog_beta', direction: 'low' };

/** Title for a verified v3, exactly as the header renders it (projection + formatting). */
async function titleFor(A: PoleSpec, B: PoleSpec, conditions: string[]): Promise<string | null> {
  return contrastTitle(contrastFromV3(await verified(A, B, conditions), LABELS));
}

describe('contrast title — each pole states its OWN condition', () => {
  it('within-condition: both poles are bracketed with the single selected condition', async () => {
    expect(await titleFor(ALPHA_HI, BETA_LO, ['Stim48hr'])).toBe('Alpha hi (at 48 hr) → Beta lo (at 48 hr)');
    expect(await titleFor(ALPHA_HI, BETA_LO, ['Rest'])).toBe('Alpha hi (at rest) → Beta lo (at rest)');
  });

  it('temporal 8hr → 48hr: A says 8 hr and B says 48 hr', async () => {
    expect(await titleFor(ALPHA_HI, ALPHA_HI, ['Stim8hr', 'Stim48hr'])).toBe(
      'Alpha hi (at 8 hr) → Alpha hi (at 48 hr)',
    );
  });

  it('temporal 48hr → 8hr: the OPPOSITE direction, A says 48 hr and B says 8 hr', async () => {
    expect(await titleFor(ALPHA_HI, ALPHA_HI, ['Stim48hr', 'Stim8hr'])).toBe(
      'Alpha hi (at 48 hr) → Alpha hi (at 8 hr)',
    );
  });

  it('temporal Rest → 48hr across two DIFFERENT programs keeps A=from, B=to (ordered roles)', async () => {
    expect(await titleFor(ALPHA_HI, BETA_LO, ['Rest', 'Stim48hr'])).toBe(
      'Alpha hi (at rest) → Beta lo (at 48 hr)',
    );
  });

  it('REGRESSION: a temporal title never repeats one endpoint condition on both poles', async () => {
    for (const [from, to] of [
      ['Stim8hr', 'Stim48hr'],
      ['Stim48hr', 'Stim8hr'],
      ['Rest', 'Stim8hr'],
      ['Stim48hr', 'Rest'],
    ]) {
      const sel = contrastFromV3(await verified(ALPHA_HI, ALPHA_HI, [from, to]), LABELS);
      expect(sel.condition_a).toBe(from);
      expect(sel.condition_b).toBe(to);
      expect(sel.condition_a).not.toBe(sel.condition_b); // the two endpoints stay distinct
      // and no shared condition is left behind to collapse them back onto one label
      expect(sel.analysis_condition).toBeUndefined();
    }
  });

  it('a within-condition selection still carries the shared condition (both poles, one timepoint)', async () => {
    const sel = contrastFromV3(await verified(ALPHA_HI, BETA_LO, ['Rest']), LABELS);
    expect(sel.analysis_condition).toBe('Rest');
    expect(sel.condition_a).toBe('Rest');
    expect(sel.condition_b).toBe('Rest');
  });
});

// ── the rendered header, on every downstream tab that carries it ─────────────────────────────
const TABS: [PageKey, string][] = [
  ['targets', 'Targets'],
  ['pathways', 'Pathways'],
  ['drugs', 'Drugs'],
  ['pksafety', 'PK & Safety'],
];

describe('StageIsland header — the temporal endpoints survive on every downstream tab', () => {
  beforeEach(() => {
    window.history.pushState({}, '', '/02_page.html'); // production, no demo
    window.localStorage.clear();
    window.sessionStorage.clear();
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: string | URL | Request) => {
        if (String(input) === 'data/stage01_program_registry.json') {
          return { ok: true, text: async () => JSON.stringify({ programs: PROGRAMS }) };
        }
        return { ok: false, text: async () => '' };
      }),
    );
  });
  afterEach(() => {
    cleanup();
    window.localStorage.clear();
    window.sessionStorage.clear();
    vi.unstubAllGlobals();
  });

  async function headerFor(page: PageKey, label: string, conditions: string[]): Promise<HTMLElement> {
    window.localStorage.setItem(
      SELECTION_V3_KEY,
      JSON.stringify(await buildV3(ALPHA_HI, ALPHA_HI, conditions)),
    );
    render(
      <StageIsland page={page} subtitle={label} purpose="p" regions={[]} enqueueTarget="x" renderDemo={() => null} />,
    );
    return screen.getByRole('banner');
  }

  for (const [page, label] of TABS) {
    it(`${label}: an 8hr → 48hr selection reads "8 hr" on A and "48 hr" on B`, async () => {
      const header = await headerFor(page, label, ['Stim8hr', 'Stim48hr']);
      await waitFor(() =>
        expect(
          within(header).getByText('Alpha hi (at 8 hr) → Alpha hi (at 48 hr)'),
        ).toBeInTheDocument(),
      );
      // the collapsed-to-one-endpoint bug, stated as the thing that must NOT render
      expect(within(header).queryByText('Alpha hi (at 8 hr) → Alpha hi (at 8 hr)')).toBeNull();
      expect(within(header).queryByText('Alpha hi (at 48 hr) → Alpha hi (at 48 hr)')).toBeNull();
    });

    it(`${label}: the reverse 48hr → 8hr selection reads "48 hr" on A and "8 hr" on B`, async () => {
      const header = await headerFor(page, label, ['Stim48hr', 'Stim8hr']);
      await waitFor(() =>
        expect(
          within(header).getByText('Alpha hi (at 48 hr) → Alpha hi (at 8 hr)'),
        ).toBeInTheDocument(),
      );
      expect(within(header).queryByText('Alpha hi (at 8 hr) → Alpha hi (at 48 hr)')).toBeNull();
    });

    it(`${label}: a within-condition selection brackets both poles with the one condition`, async () => {
      const header = await headerFor(page, label, ['Stim48hr']);
      await waitFor(() =>
        expect(
          within(header).getByText('Alpha hi (at 48 hr) → Alpha hi (at 48 hr)'),
        ).toBeInTheDocument(),
      );
    });
  }
});
