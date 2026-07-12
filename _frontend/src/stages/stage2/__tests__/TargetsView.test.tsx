import { fireEvent, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { TargetsView } from '../TargetsView';
import { createDemoRepository } from '../../../repository/repository';
import { loadedArtifact, renderWithProvenance } from '../../../test/harness';

const artifact = () => loadedArtifact(createDemoRepository().getStage2());

describe('TargetsView — Targets island (table only)', () => {
  it('shows the three objective views + joint statuses + Pareto tiers, no pathways rail', () => {
    renderWithProvenance(<TargetsView artifact={artifact()} />);
    expect(screen.getByRole('button', { name: /Joint . Pareto/ })).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /away from A/i }).length).toBeGreaterThan(0);
    expect(screen.getAllByText('both arms').length).toBeGreaterThan(0);
    expect(screen.getAllByText('opposed').length).toBeGreaterThan(0);
    expect(screen.getAllByText(/tier \d/).length).toBeGreaterThan(0);
    // Convergent pathways live on the separate Pathways island, not here.
    expect(screen.queryByText('Convergent pathways')).toBeNull();
    expect(screen.queryByText('PATHWAY_01')).toBeNull();
  });

  it('never shows an averaged/combined score', () => {
    renderWithProvenance(<TargetsView artifact={artifact()} />);
    expect(screen.queryByText(/combined|balanced|composite/i)).toBeNull();
  });

  it('opens the per-target evidence inspector', () => {
    renderWithProvenance(<TargetsView artifact={artifact()} />);
    fireEvent.click(screen.getByRole('button', { name: /GENE_A/ }));
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText('Contributing guides')).toBeInTheDocument();
  });
});
