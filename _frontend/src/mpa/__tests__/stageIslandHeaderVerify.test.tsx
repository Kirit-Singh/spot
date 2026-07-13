// v3 fail-OPEN fix (gates U05/U07): the production header contrast derives ONLY from the fully
// VERIFIED async v3 selection (readStage1SelectionV3 → hash recompute + routing re-derivation).
// A valid-SHAPED but forged v3 (good canonical_content, tampered full_contract_content_sha256)
// must NOT render a forged contrast: header shows the neutral prompt, no clear control, <main>
// shows the neutral pending state (no stale/fixture rows). A genuinely verified v3 → real contrast.

import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { StageIsland } from '../StageIsland';
import { SELECTION_V3_KEY } from '../../repository/source';
import { canonicalJson, sha256Hex } from '../../stage1/canonical';
import { deriveExecutionStatus } from '../../stage1/selectionV3';

/** Build a spot.stage01_selection.v3 contract with REAL recomputed hashes (treg_like → th1_like @ Stim48hr). */
async function buildV3(opts: { tamperFullContract?: string } = {}): Promise<Record<string, unknown>> {
  const aId = 'treg_like', aDir = 'low', bId = 'th1_like', bDir = 'high';
  const cc: Record<string, unknown> = {
    A: { program_id: aId, score_field: `${aId}_score`, direction: aDir },
    B: { program_id: bId, score_field: `${bId}_score`, direction: bDir },
    analysis_mode: 'within_condition',
    combined_objective: null,
    conditions: ['Stim48hr'],
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
    execution_status: deriveExecutionStatus('within_condition', 'available', 'available', 'available'),
    analysis_mode: 'within_condition',
    estimator_id: 'within_condition_v1',
    estimator_status: 'available',
    selection_id: selFull.slice(0, 16),
    selection_full_sha256: selFull,
    canonical_content: cc,
    poles: {
      A: { program_id: aId, direction: aDir, effect_projection_status: 'available', n_measured: 5, n_panel_in_effect_universe: 5, n_control_in_effect_universe: 5, reason_codes: [] },
      B: { program_id: bId, direction: bDir, effect_projection_status: 'available', n_measured: 4, n_panel_in_effect_universe: 4, n_control_in_effect_universe: 4, reason_codes: [] },
    },
    trust_bindings: { validation_raw_sha256: 'c'.repeat(64) },
    provenance_bindings: { primary_registry_v3_raw_sha256: 'd'.repeat(64) },
    historical_validation_provenance: { kind: 'frozen', selectability_v3_raw_sha256: 'e'.repeat(64), active_gate: false },
  };
  contract.full_contract_content_sha256 = await sha256Hex(canonicalJson(contract));
  if (opts.tamperFullContract) contract.full_contract_content_sha256 = opts.tamperFullContract;
  return contract;
}

const FORGED_CONTRAST = /treg_like lo .* th1_like hi/;

function renderIsland() {
  render(
    <StageIsland page="targets" subtitle="Targets" purpose="p" regions={[]} enqueueTarget="x" renderDemo={() => null} />,
  );
}

describe('StageIsland header — verified v3 only (no fail-open)', () => {
  beforeEach(() => {
    window.history.pushState({}, '', '/targets.html'); // production, no demo
    window.localStorage.clear();
    window.sessionStorage.clear();
  });
  afterEach(() => {
    cleanup();
    window.localStorage.clear();
    window.sessionStorage.clear();
    window.history.pushState({}, '', '/02_page.html');
  });

  it('ATTACK: a forged valid-shaped v3 (bad full_contract_content_sha256) renders NO contrast', async () => {
    const forged = await buildV3({ tamperFullContract: '0'.repeat(64) });
    window.localStorage.setItem(SELECTION_V3_KEY, JSON.stringify(forged));
    renderIsland();

    const main = screen.getByRole('main');
    await waitFor(() => expect(within(main).getByText(/pending independent admission/i)).toBeInTheDocument());

    const header = screen.getByRole('banner');
    // neutral prompt, NOT the forged contrast; no clear control
    expect(within(header).getByText(/Select populations in/)).toBeInTheDocument();
    expect(within(header).queryByText(FORGED_CONTRAST)).toBeNull();
    expect(within(header).queryByRole('button', { name: /Clear selection and return to Programs/ })).toBeNull();
    // <main> has no stale/fixture rows
    expect(main).not.toHaveTextContent(FORGED_CONTRAST);
    expect(main).not.toHaveTextContent(/GENE_A/);
  });

  it('VERIFIED: a genuinely-verified v3 renders the real contrast + a clear control', async () => {
    window.localStorage.setItem(SELECTION_V3_KEY, JSON.stringify(await buildV3()));
    renderIsland();

    const header = screen.getByRole('banner');
    await waitFor(() =>
      expect(within(header).getByText('treg_like lo (at 48 hr) → th1_like hi (at 48 hr)')).toBeInTheDocument(),
    );
    expect(
      within(header).getByRole('button', { name: 'Clear selection and return to Programs' }),
    ).toBeInTheDocument();
    expect(within(header).queryByText(/Select populations in/)).toBeNull();
  });
});
