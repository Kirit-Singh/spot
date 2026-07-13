import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import App from './App';
import { SELECTION_KEY } from './repository/source';
import { researchSelectionExampleRaw } from './fixtures/researchSelection.example';

/** Set the full URL (search + hash) before render — the demo gate reads location.search. */
function goto(url: string) {
  window.history.pushState({}, '', url);
}

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

  describe('valid research-only selection', () => {
    beforeEach(() => {
      window.localStorage.setItem(SELECTION_KEY, JSON.stringify(researchSelectionExampleRaw));
    });

    it('shows the real A/B/condition context', () => {
      render(<App />);
      const bar = screen.getByLabelText('Stage-1 selection context');
      expect(within(bar).getByText('Treg-like')).toBeInTheDocument();
      expect(within(bar).getByText('Th1-like')).toBeInTheDocument();
      expect(within(bar).getByText(/Stim48hr/)).toBeInTheDocument();
      expect(within(bar).getByText('research-only')).toBeInTheDocument();
    });

    it('shows analysis-not-generated and never falls back to fixture results', () => {
      render(<App />);
      expect(screen.getByText('analysis not generated')).toBeInTheDocument();
      expect(screen.queryByText('GENE_A')).toBeNull();
      expect(screen.queryByText('PATHWAY_01')).toBeNull();
    });
  });

  it('rejects an unreadable stored selection (no data, no research results)', () => {
    window.localStorage.setItem(SELECTION_KEY, '{ not valid json');
    render(<App />);
    expect(screen.getByText('selection rejected')).toBeInTheDocument();
    expect(screen.queryByText('GENE_A')).toBeNull();
  });

  it('marks Stage 5 as not yet built (disabled)', () => {
    render(<App />);
    expect(screen.getByText('Trial').closest('[aria-disabled="true"]')).not.toBeNull();
  });
});

describe('compact selection context + drawer relocation', () => {
  beforeEach(() => {
    goto('/02_page.html');
    window.localStorage.clear();
    window.localStorage.setItem(SELECTION_KEY, JSON.stringify(researchSelectionExampleRaw));
  });

  it('keeps question/selection/source off the compact context bar', () => {
    render(<App />);
    const bar = screen.getByLabelText('Stage-1 selection context');
    expect(within(bar).getByText('Treg-like')).toBeInTheDocument();
    expect(within(bar).getByText(/Stim48hr/)).toBeInTheDocument();
    expect(within(bar).getByText(/a1b2c3d4e5f60718/)).toBeInTheDocument();
    expect(within(bar).getByText('research-only')).toBeInTheDocument();
    expect(within(bar).queryByText(/Q_treg_to_th1_stim48/)).toBeNull();
    expect(within(bar).queryByText(/SEL_treg_to_th1_stim48_r1/)).toBeNull();
    expect(within(bar).queryByText(/stage01_research_bridge/)).toBeNull();
  });

  it('surfaces the moved selection detail inside the provenance drawer', () => {
    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: /Methods/ }));
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText('Stage-1 selection')).toBeInTheDocument();
    expect(within(dialog).getByText(/Q_treg_to_th1_stim48/)).toBeInTheDocument();
    expect(within(dialog).getByText(/SEL_treg_to_th1_stim48_r1/)).toBeInTheDocument();
    expect(within(dialog).getByText(/stage01_research_bridge/)).toBeInTheDocument();
  });

  it('preserves optional v3 Stage-1 bindings in provenance only, never on the bar', () => {
    const v3 = {
      ...researchSelectionExampleRaw,
      stage1_method_version: 'stage1-continuous-v3.0.1',
      program_registry_sha256: 'a'.repeat(64),
      source_h5ad_sha256: 'b'.repeat(64),
    };
    window.localStorage.setItem(SELECTION_KEY, JSON.stringify(v3));
    render(<App />);
    const bar = screen.getByLabelText('Stage-1 selection context');
    expect(within(bar).queryByText(/stage1-continuous-v3\.0\.1/)).toBeNull();
    expect(within(bar).queryByText(/a{64}/)).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: /Methods/ }));
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText('stage1-continuous-v3.0.1')).toBeInTheDocument();
    expect(within(dialog).getByText('a'.repeat(64))).toBeInTheDocument();
    expect(within(dialog).getByText('b'.repeat(64))).toBeInTheDocument();
  });

  it('shows the analysis-not-generated state with no explanatory paragraph', () => {
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
