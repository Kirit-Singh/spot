import { fireEvent, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Stage3View } from '../Stage3View';
import { createFixtureRepository } from '../../../repository/repository';
import { loadedArtifact, renderWithProvenance } from '../../../test/harness';

const artifact = () => loadedArtifact(createFixtureRepository().getStage3());

describe('Stage 3 — direction-compatible drug linkage', () => {
  it('keeps both desired-arm directions visible', () => {
    renderWithProvenance(<Stage3View artifact={artifact()} />);
    expect(screen.getByText(/desired directions/)).toBeInTheDocument();
    expect(screen.getAllByText(/away from A/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/toward B/).length).toBeGreaterThan(0);
  });

  it('renders the mechanism relationship strip (gene → target → mechanism → moiety → form)', () => {
    renderWithProvenance(<Stage3View artifact={artifact()} />);
    expect(screen.getAllByText('active moiety').length).toBeGreaterThan(0);
    expect(screen.getAllByText('mechanism').length).toBeGreaterThan(0);
  });

  it('gives mechanism nodes a readable min width and scrolls the strip (no crushing)', () => {
    renderWithProvenance(<Stage3View artifact={artifact()} />);
    const strips = screen.getAllByTestId('mechanism-strip');
    expect(strips.length).toBeGreaterThan(0);
    strips.forEach((s) => expect(s.className).toMatch(/overflow-x-auto/));
    // Each labelled node keeps a fixed, non-shrinking width — never G… / IN… fragments.
    const geneNode = within(strips[0]).getAllByText('gene')[0].parentElement as HTMLElement;
    expect(geneNode.className).toMatch(/flex-none/);
    expect(geneNode.className).toMatch(/w-\[96px\]/);
  });

  it('traces candidate origin, supporting arm and mechanism direction', () => {
    renderWithProvenance(<Stage3View artifact={artifact()} />);
    expect(screen.getAllByText(/origin: direct target/).length).toBeGreaterThan(0);
    expect(screen.getByText(/origin: pathway node . PATHWAY_02/)).toBeInTheDocument();
    expect(screen.getAllByText(/supporting arm:/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/mechanism: (?:up|down|not_evaluated)/).length).toBeGreaterThan(0);
  });

  it('cannot promote fixture candidates (disabled action states why)', () => {
    renderWithProvenance(<Stage3View artifact={artifact()} />);
    const promotes = screen.getAllByRole('button', { name: /Promote/ });
    expect(promotes.length).toBeGreaterThan(0);
    promotes.forEach((b) => expect(b).toBeDisabled());
  });

  it('shows source conflicts without collapsing them', () => {
    renderWithProvenance(<Stage3View artifact={artifact()} />);
    // Expand the candidate that carries a conflict.
    const inspects = screen.getAllByRole('button', { name: /Inspect evidence/ });
    inspects.forEach((b) => fireEvent.click(b));
    // Plain heading; the "shown, not collapsed" policy lives once in provenance.
    expect(screen.getByRole('heading', { name: 'Source conflicts' })).toBeInTheDocument();
    expect(screen.queryByText(/shown, not collapsed/i)).toBeNull();
    // The conflicting values themselves remain visible (that is the behaviour).
    expect(screen.getByText(/DGIdb: MODULATOR/)).toBeInTheDocument();
    expect(screen.getByText(/Open Targets: AGONIST/)).toBeInTheDocument();
  });

  it('keeps potency records with their original relation and unit', () => {
    renderWithProvenance(<Stage3View artifact={artifact()} />);
    const inspects = screen.getAllByRole('button', { name: /Inspect evidence/ });
    inspects.forEach((b) => fireEvent.click(b));
    expect(screen.getByText(/= 42 nM/)).toBeInTheDocument();
    expect(screen.getByText(/> 1000 nM/)).toBeInTheDocument();
  });
});
