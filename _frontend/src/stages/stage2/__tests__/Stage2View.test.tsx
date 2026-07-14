import { fireEvent, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Stage2View } from '../Stage2View';
import { createFixtureRepository } from '../../../repository/repository';
import { loadedArtifact, renderWithProvenance } from '../../../test/harness';

const artifact = () => loadedArtifact(createFixtureRepository().getStage2());

describe('Stage 2 — perturbation levers', () => {
  it('shows both objectives simultaneously, neither as a headline', () => {
    renderWithProvenance(<Stage2View artifact={artifact()} />);
    // Both the view control and the column headers reference each arm.
    expect(screen.getAllByRole('button', { name: /away from A/i }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole('button', { name: /toward B/i }).length).toBeGreaterThan(0);
    // A third, explicitly-typed joint view exists (Pareto), never an averaged score.
    expect(screen.getByRole('button', { name: /Joint . Pareto/ })).toBeInTheDocument();
  });

  it('never shows a combined or balanced score', () => {
    renderWithProvenance(<Stage2View artifact={artifact()} />);
    expect(screen.queryByText(/combined/i)).toBeNull();
    expect(screen.queryByText(/balanced/i)).toBeNull();
    expect(screen.queryByText(/best.of/i)).toBeNull();
  });

  it('preserves the typed joint statuses (both arms, A only, B only, opposed, not evaluated)', () => {
    renderWithProvenance(<Stage2View artifact={artifact()} />);
    // Each label appears both as a filter control and as a row pill — assert presence.
    expect(screen.getAllByText('both arms').length).toBeGreaterThan(0);
    expect(screen.getAllByText('A only').length).toBeGreaterThan(0);
    expect(screen.getAllByText('B only').length).toBeGreaterThan(0);
    expect(screen.getAllByText('opposed').length).toBeGreaterThan(0);
    expect(screen.getAllByText('not evaluated').length).toBeGreaterThan(0);
  });

  it('exposes Pareto tiers and marker-breadth without any averaged score', () => {
    renderWithProvenance(<Stage2View artifact={artifact()} />);
    expect(screen.getAllByText(/tier \d/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/\d+ markers/).length).toBeGreaterThan(0);
    expect(screen.getAllByText('single-marker').length).toBeGreaterThan(0);
    expect(screen.queryByText(/combined|balanced|composite/i)).toBeNull();
  });

  it('opens a per-gene evidence inspector with guides, donors, stability and sources', () => {
    renderWithProvenance(<Stage2View artifact={artifact()} />);
    fireEvent.click(screen.getByRole('button', { name: /GENE_A/ }));
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText('Contributing guides')).toBeInTheDocument();
    expect(within(dialog).getByText('GUIDE_1')).toBeInTheDocument();
    expect(within(dialog).getByText('Donor support')).toBeInTheDocument();
    expect(within(dialog).getByText(/direct.perturb2state/)).toBeInTheDocument();
    expect(within(dialog).getByText(/DepMap/)).toBeInTheDocument();
  });

  it('shows convergent pathways with contributing targets, arm support and druggable nodes', () => {
    renderWithProvenance(<Stage2View artifact={artifact()} />);
    expect(screen.getByText('Convergent pathways')).toBeInTheDocument();
    expect(screen.getByText('PATHWAY_01')).toBeInTheDocument();
    expect(screen.getAllByText('druggable node').length).toBeGreaterThan(0);
    // No descriptive/causal editorializing on the canvas heading.
    expect(screen.queryByText(/pathway support\s*·\s*descriptive/i)).toBeNull();
    expect(screen.queryByText(/not a causal pathway confirmation/i)).toBeNull();
  });

  it('lets the cross-arm filter group wrap instead of clipping (min-w-0)', () => {
    renderWithProvenance(<Stage2View artifact={artifact()} />);
    const group = screen.getByTestId('stage2-filter-group');
    expect(group.className).toMatch(/\bmin-w-0\b/);
    expect(group.className).toMatch(/\bflex-wrap\b/);
  });

  it('requests provenance (with method notes) when the Provenance button is clicked', () => {
    const { open } = renderWithProvenance(<Stage2View artifact={artifact()} />);
    fireEvent.click(screen.getByRole('button', { name: /Provenance/ }));
    expect(open).toHaveBeenCalledWith('Stage 2 — target set', expect.anything(), expect.anything());
  });
});
