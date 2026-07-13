import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import App from './App';
import { SELECTION_V3_KEY } from './repository/source';

/** Set the full URL (search + hash) before render — the demo gate reads location.search. */
function goto(url: string) {
  window.history.pushState({}, '', url);
}

/** A minimal, structurally-valid spot.stage01_selection.v3 contract (the sync gate is shallow). */
const selectionV3Raw = {
  schema_version: 'spot.stage01_selection.v3',
  selection_id: 'a1b2c3d4e5f60718',
  question_id: 'q'.repeat(16), // biology-only id; shallow projection shape-checks it present
  analysis_mode: 'within_condition',
  execution_status: 'ready',
  estimator_id: 'within_condition_v1',
  estimator_status: 'available',
  selection_full_sha256: 'f'.repeat(64),
  full_contract_content_sha256: '9'.repeat(64),
  canonical_content: {
    A: { program_id: 'treg_like', score_field: 'treg_like_score', direction: 'low' },
    B: { program_id: 'th1_like', score_field: 'th1_like_score', direction: 'high' },
    conditions: ['Stim48hr'],
    registry_scorer_view_sha256: 'a'.repeat(64),
    source_h5ad_sha256: 'b'.repeat(64),
  },
};

describe('spot shell — navigation & modes', () => {
  beforeEach(() => {
    goto('/02_page.html'); // clears any ?demo=1 and hash from a prior test
    window.localStorage.clear();
  });

  it('renders the brand and defaults to an honest empty scaffold (no fake data)', () => {
    render(<App />);
    expect(screen.getByText(/^spot/)).toBeInTheDocument();
    expect(screen.getByLabelText('No selection')).toBeInTheDocument();
    const main = screen.getByRole('main');
    expect(within(main).getByText('no artifact')).toBeInTheDocument();
    expect(within(main).queryByText('GENE_A')).toBeNull();
  });

  it('links Stage 1 out to the built page without redrawing it', () => {
    render(<App />);
    expect(screen.getByRole('link', { name: /CD4 programs/ })).toHaveAttribute('href', '/01_page.html');
  });

  it('navigates between stages 2, 3 and 4 (demo mode populated)', () => {
    goto('/02_page.html?demo=1#/stage-2');
    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: /Drug link/ }));
    expect(screen.getByText(/desired directions/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /PK . PD . brain/ }));
    expect(screen.getAllByText(/NEBPI decision path/).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole('button', { name: /Skewing genes/ }));
    expect(screen.getByLabelText('Stage-1 selection context')).toBeInTheDocument();
  });

  it('opens the shared Methods & provenance drawer with hashes and relocated notes', () => {
    goto('/02_page.html?demo=1');
    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: /Methods/ }));
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText(/Canonical/)).toBeInTheDocument();
    expect(within(dialog).getByText(/fixture:stage02:demo_lever_set/)).toBeInTheDocument();
    expect(within(dialog).getByText('Production gate')).toBeInTheDocument();
    expect(within(dialog).getByText('Two independent objectives')).toBeInTheDocument();
  });

  it('keeps combined/balanced/composite language off the main canvas', () => {
    goto('/02_page.html?demo=1');
    render(<App />);
    const main = screen.getByRole('main');
    expect(within(main).queryByText(/combined/i)).toBeNull();
    expect(within(main).queryByText(/balanced/i)).toBeNull();
    expect(within(main).queryByText(/composite/i)).toBeNull();
  });

  describe('explicit demo gate → synthetic example', () => {
    it('shows synthetic demo data, unmistakably marked demo', () => {
      goto('/02_page.html?demo=1');
      render(<App />);
      expect(screen.getAllByText('GENE_A').length).toBeGreaterThan(0);
      expect(screen.getByText(/demo . synthetic/i)).toBeInTheDocument();
    });

    it('default (no demo gate) never shows synthetic data', () => {
      render(<App />);
      expect(screen.queryByText('GENE_A')).toBeNull();
      expect(screen.queryByText(/demo . synthetic/i)).toBeNull();
    });
  });

  describe('valid v3 selection', () => {
    beforeEach(() => {
      window.localStorage.setItem(SELECTION_V3_KEY, JSON.stringify(selectionV3Raw));
    });

    it('enters research mode — not the empty scaffold, not demo', () => {
      render(<App />);
      expect(screen.queryByLabelText('No selection')).toBeNull();
      expect(screen.getByText('analysis not generated')).toBeInTheDocument();
    });

    it('shows analysis-not-generated and never falls back to fixture results', () => {
      render(<App />);
      expect(screen.getByText('analysis not generated')).toBeInTheDocument();
      expect(screen.queryByText('GENE_A')).toBeNull();
      expect(screen.queryByText('PATHWAY_01')).toBeNull();
    });
  });

  it('rejects a v1 object in the v3 key (fail-closed, no v1 fallback)', () => {
    window.localStorage.setItem(
      SELECTION_V3_KEY,
      JSON.stringify({ schema_version: 'spot.stage01_selection.v1' }),
    );
    render(<App />);
    expect(screen.getByText('selection rejected')).toBeInTheDocument();
    expect(screen.queryByText('GENE_A')).toBeNull();
  });

  it('rejects an unreadable stored selection (no data, no research results)', () => {
    window.localStorage.setItem(SELECTION_V3_KEY, '{ not valid json');
    render(<App />);
    expect(screen.getByText('selection rejected')).toBeInTheDocument();
    expect(screen.queryByText('GENE_A')).toBeNull();
  });

  it('marks Stage 5 as not yet built (disabled)', () => {
    render(<App />);
    expect(screen.getByText('Trial').closest('[aria-disabled="true"]')).not.toBeNull();
  });
});

describe('v3 research mode — honest not-generated, no legacy context bar', () => {
  beforeEach(() => {
    goto('/02_page.html');
    window.localStorage.clear();
    window.localStorage.setItem(SELECTION_V3_KEY, JSON.stringify(selectionV3Raw));
  });

  it('does not render the legacy compact Stage-1 selection context bar (v3 carrier is separate)', () => {
    render(<App />);
    expect(screen.queryByLabelText('Stage-1 selection context')).toBeNull();
  });

  it('shows the analysis-not-generated state, the stage-2 target and no explanatory paragraph', () => {
    render(<App />);
    expect(screen.getByText('analysis not generated')).toBeInTheDocument();
    expect(screen.queryByText(/results appear here/i)).toBeNull();
    expect(screen.queryByText(/selection context above is real/i)).toBeNull();
    expect(screen.getByText(/spot\.stage02_gene_lever_set\.v1/)).toBeInTheDocument();
  });
});

describe('fixture source hygiene', () => {
  beforeEach(() => {
    goto('/02_page.html?demo=1#/stage-4');
    window.localStorage.clear();
  });

  it('never renders the DrugBank brand on the Stage-4 canvas or in provenance', () => {
    render(<App />);
    expect(screen.queryByText(/DrugBank/i)).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /Methods/ }));
    expect(within(screen.getByRole('dialog')).queryByText(/DrugBank/i)).toBeNull();
  });
});
