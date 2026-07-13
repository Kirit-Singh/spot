// FIX #2/#6 gates U08/U09/U13/U14 — the admitted-artifact canvas + clean <main>.
//
// (a) An ADMITTED native temporal fixture (a valid NativeTemporalArmBundle + W5/W11 admission
//     inputs, resolved through the REAL adapters) renders compact real rows via renderReal —
//     no "awaiting artifact", no demo/fixture data, no review chrome. This is the ONLY place a
//     signed fixture may appear.
// (b) Production (no admitted artifact, no ?demo) renders the COMPACT NEUTRAL pending state —
//     no demo data, no ScienceEvidence in <main>.
// (c) <main> carries no methods / provenance / science-evidence / rerun copy.

import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { StageIsland } from '../StageIsland';
import { resolveProductionRealArtifact } from '../resolveRouteArtifact';
import type { RealArtifactResolution } from '../renderReal';
import {
  parseNativeTemporalArmBundle,
  resolveTemporalAdmission,
} from '../../adapters/nativeTemporalArmAdapter';
import { resolveJoinedView } from '../../repository/joinResolver';
import type { SelectionV3 } from '../../adapters/selectionV3Adapter';
import type { PageKey } from '../pages';
import { fixtureProvenance } from '../../fixtures/synthetic';

const ARM = 'temporal|th17_like|decrease|Rest|Stim48hr';
const RELEASE = ['Rest', 'Stim8hr', 'Stim48hr'];

/** A valid W5 native temporal arm bundle (parsed through the real fail-closed adapter). */
function nativeBundleRaw() {
  return {
    schema_version: 'spot.stage02_temporal_arm_bundle.v1',
    lane: 'temporal',
    analysis_mode: 'temporal_cross_condition',
    from_condition: 'Rest',
    to_condition: 'Stim48hr',
    bundle_id: 'abc123def456abcd',
    provenance: {
      ...fixtureProvenance({ stage: 'stage02', slug: 'temporal_arm', seed: 't1t1t1t1', methodId: 'temporal.native.fixture', sources: [] }),
      schema_version: 'spot.stage02_temporal_provenance.v1',
    },
    base_records: {
      'th17_like|ENSG1': { base_key: 'th17_like|ENSG1', program_id: 'th17_like', target_id: 'ENSG1', target_symbol: 'GENE1', target_ensembl: 'ENSG1', target_id_namespace: 'ensembl_gene_id', perturbation_modality: 'CRISPRi_knockdown', from_condition: 'Rest', to_condition: 'Stim48hr', temporal_status: 'evaluable', evaluable: true, base_delta: -0.2 },
      'th17_like|ENSG2': { base_key: 'th17_like|ENSG2', program_id: 'th17_like', target_id: 'ENSG2', target_symbol: null, target_ensembl: 'ENSG2', target_id_namespace: 'ensembl_gene_id', perturbation_modality: 'CRISPRi_knockdown', from_condition: 'Rest', to_condition: 'Stim48hr', temporal_status: 'not_evaluable', evaluable: false, base_delta: null },
    },
    arms: {
      [ARM]: {
        arm_key: ARM, program_id: 'th17_like', desired_change: 'decrease', from_condition: 'Rest', to_condition: 'Stim48hr',
        n_targets: 2, n_evaluable: 1, n_ranked: 1,
        records: [
          { target_id: 'ENSG1', base_key: 'th17_like|ENSG1', arm_value: -0.12, evaluable: true, temporal_status: 'evaluable', desired_target_modulation: 'supports_target_inhibition', rank: 1 },
          { target_id: 'ENSG2', base_key: 'th17_like|ENSG2', arm_value: null, evaluable: false, temporal_status: 'not_evaluable', desired_target_modulation: 'not_evaluable', rank: null },
        ],
        ranking: { path: 'rankings/th17_like__decrease.json', raw_sha256: 'a'.repeat(64), canonical_sha256: 'b'.repeat(64) },
      },
    },
    verification_ref: 'spot.stage02.temporal.arm.independent_verifier.v1',
  };
}

/** A temporal cross-condition v3 selection whose away_from_A(high)=decrease arm the bundle carries. */
function temporalSelection(): SelectionV3 {
  return {
    selection_id: 'a'.repeat(16), analysis_mode: 'temporal_cross_condition', execution_status: 'ready',
    estimator_id: 'temporal_cross_condition_v1', estimator_status: 'available',
    A: { program_id: 'th17_like', direction: 'high' }, // away_from_A(high) = decrease → matches ARM
    B: { program_id: 'th1_like', direction: 'high' }, //  toward_b(high) = increase (no arm → neutral)
    conditions: ['Rest', 'Stim48hr'],
    registry_scorer_view_sha256: 'b'.repeat(64), source_h5ad_sha256: 'c'.repeat(64),
    selection_full_sha256: 'd'.repeat(64), full_contract_content_sha256: 'e'.repeat(64), raw: {},
  };
}

/** Build the ADMITTED resolution the same way production will: real adapters, real admission. */
function admittedResolution(): RealArtifactResolution {
  const bundle = parseNativeTemporalArmBundle(nativeBundleRaw(), 'fixture');
  const bundles = { temporal: bundle, pathwayByContext: {} };
  const view = resolveJoinedView(temporalSelection(), bundles, 'reactome', RELEASE);
  const admission = resolveTemporalAdmission({
    w5_release: { release_sha256: 'r'.repeat(64) },
    w11_verification: { verdict: 'ADMIT', admits_release: 'r'.repeat(64) },
  });
  expect(admission).toBe('admitted'); // guard: the fixture really is admitted
  return { route: 'targets', view, bundles, admission };
}

function renderIsland(
  loadRealArtifact?:
    | RealArtifactResolution
    | null
    | ((page: PageKey) => Promise<RealArtifactResolution | null> | RealArtifactResolution | null),
) {
  const loader = typeof loadRealArtifact === 'function' ? loadRealArtifact : () => loadRealArtifact ?? null;
  return render(
    <StageIsland
      page="targets"
      subtitle="Targets"
      purpose="p"
      regions={[]}
      enqueueTarget="stage02_review"
      renderDemo={() => null}
      loadRealArtifact={loader}
    />,
  );
}

function reset() {
  window.localStorage.clear();
  window.sessionStorage.clear();
  window.history.pushState({}, '', '/02_page.html');
}

describe('StageIsland renderReal — admitted native temporal artifact (U08/U09)', () => {
  beforeEach(() => {
    window.history.pushState({}, '', '/targets.html'); // production, no demo
    window.localStorage.clear();
    window.sessionStorage.clear();
  });
  afterEach(() => {
    cleanup();
    reset();
  });

  it('renders compact REAL rows from the admitted bundle — no awaiting/demo/fixture text', async () => {
    const resolution = admittedResolution();
    renderIsland(() => resolution);
    const main = screen.getByRole('main');

    // Real, base_key-joined identity (GENE1 / ENSG1) + a real rank appear from the artifact.
    await waitFor(() => expect(within(main).getByText('GENE1')).toBeInTheDocument());
    expect(within(main).getAllByText(/ENSG1/).length).toBeGreaterThan(0);

    // NOT the awaiting-artifact scaffold; NOT synthetic demo/fixture data.
    expect(main).not.toHaveTextContent(/awaiting artifact/i);
    expect(main).not.toHaveTextContent(/GENE_A/);
    expect(main).not.toHaveTextContent(/\bdemo\b/i);
    expect(main).not.toHaveTextContent(/fixture/i);

    // NO review chrome on the canvas.
    expect(within(main).queryByText(/Enqueue review job/i)).toBeNull();
    expect(within(main).queryByText(/science evidence/i)).toBeNull();
  });
});

describe('StageIsland — production pending state (U08) + clean <main> (U13/U14)', () => {
  beforeEach(() => {
    window.history.pushState({}, '', '/targets.html');
    window.localStorage.clear();
    window.sessionStorage.clear();
  });
  afterEach(() => {
    cleanup();
    reset();
  });

  it('(b) no admitted artifact, no demo → compact neutral pending state, no demo data', async () => {
    renderIsland(resolveProductionRealArtifact);
    const main = screen.getByRole('main');
    await waitFor(() =>
      expect(within(main).getByText(/pending independent admission/i)).toBeInTheDocument(),
    );
    // no fake results, no old scaffold
    expect(main).not.toHaveTextContent(/GENE_A/);
    expect(main).not.toHaveTextContent(/awaiting artifact/i);
    // no science-evidence / review chrome
    expect(within(main).queryByText(/Enqueue review job/i)).toBeNull();
    expect(within(main).queryByText(/science evidence/i)).toBeNull();
  });

  it('(c) <main> carries no methods / provenance / science-evidence / rerun copy', async () => {
    renderIsland(resolveProductionRealArtifact);
    const main = screen.getByRole('main');
    await waitFor(() =>
      expect(within(main).getByText(/pending independent admission/i)).toBeInTheDocument(),
    );
    expect(main).not.toHaveTextContent(/science evidence/i);
    expect(main).not.toHaveTextContent(/enqueue|review job/i);
    expect(main).not.toHaveTextContent(/re-?run/i);
    expect(main).not.toHaveTextContent(/provenance/i);
    expect(main).not.toHaveTextContent(/\bmethods\b/i);
  });
});
