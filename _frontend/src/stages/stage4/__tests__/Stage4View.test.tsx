import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Stage4View } from '../Stage4View';
import { createFixtureRepository } from '../../../repository/repository';
import { parseStage4 } from '../../../adapters/stage4Adapter';
import { stage4FixtureRaw } from '../../../fixtures/stage4.fixture';
import { loadedArtifact, renderWithProvenance } from '../../../test/harness';

const artifact = () => loadedArtifact(createFixtureRepository().getStage4());

describe('Stage 4 — safety & brain exposure', () => {
  it('separates the five evidence panels', () => {
    renderWithProvenance(<Stage4View artifact={artifact()} />);
    expect(screen.getAllByText('Human safety / regulatory').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Systemic / unbound exposure').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Measured CNS / tumour').length).toBeGreaterThan(0);
    expect(screen.getAllByText('CNS-MPO descriptor support').length).toBeGreaterThan(0);
    expect(screen.getAllByText('NEBPI decision path').length).toBeGreaterThan(0);
  });

  it('shows the delivery-requirement and treatment-context safety panels', () => {
    renderWithProvenance(<Stage4View artifact={artifact()} />);
    expect(screen.getAllByText('Delivery requirement').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Treatment-context safety').length).toBeGreaterThan(0);
  });

  it('shows missing data as missing / not evaluated — never as zero', () => {
    renderWithProvenance(<Stage4View artifact={artifact()} />);
    expect(screen.getAllByText('missing').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Missing').length).toBeGreaterThan(0);
    expect(screen.getAllByText('not evaluated').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Not evaluated').length).toBeGreaterThan(0);
  });

  it('distinguishes measured from calculated evidence', () => {
    renderWithProvenance(<Stage4View artifact={artifact()} />);
    expect(screen.getAllByText('Measured').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Calculated').length).toBeGreaterThan(0);
  });

  it('keeps the CNS-MPO panel but no heuristic caveat sentence on the canvas', () => {
    renderWithProvenance(<Stage4View artifact={artifact()} />);
    // The operational panel label stays; the caveat lives in Methods & provenance only.
    expect(screen.getAllByText('CNS-MPO descriptor support').length).toBeGreaterThan(0);
    expect(screen.queryByText(/not clinical brain exposure/)).toBeNull();
  });

  it('shows the exact NEBPI decision path', () => {
    renderWithProvenance(<Stage4View artifact={artifact()} />);
    expect(screen.getAllByText(/Measured unbound CNS exposure available/).length).toBeGreaterThan(0);
  });

  it('offers only adapter-supplied sort keys and never a composite', () => {
    renderWithProvenance(<Stage4View artifact={artifact()} />);
    expect(screen.getByRole('button', { name: 'evidence completeness' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'NEBPI tier' })).toBeInTheDocument();
    // No composite / best / merged sort option is offered on the canvas.
    expect(screen.queryByRole('button', { name: /composite|best|merged/i })).toBeNull();
  });

  it('styles NEBPI tiers neutrally, never as a safe/caution/danger traffic light', () => {
    renderWithProvenance(<Stage4View artifact={artifact()} />);
    const suff = screen.getByText('NEBPI: sufficiently permeable');
    expect(suff.className).not.toMatch(/text-ok|border-ok|text-danger|text-amber/);
  });

  it('uses neutral styling for the impermeable tier (no red)', () => {
    const raw = structuredClone(stage4FixtureRaw);
    raw.scorecards[0].nebpi.tier = 'impermeable';
    renderWithProvenance(<Stage4View artifact={parseStage4(raw, 'fixture')} />);
    const imp = screen.getByText('NEBPI: impermeable');
    expect(imp.className).not.toMatch(/text-danger|border-danger|text-ok|text-amber/);
  });

  it('does not carry the DrugBank brand in the shipped Stage-4 fixture', () => {
    expect(JSON.stringify(stage4FixtureRaw)).not.toMatch(/DrugBank/i);
    renderWithProvenance(<Stage4View artifact={artifact()} />);
    expect(screen.queryByText(/DrugBank/i)).toBeNull();
  });

  it('hides sort controls the adapter does not supply', () => {
    const raw = structuredClone(stage4FixtureRaw);
    raw.sortable_by = [];
    const noSort = parseStage4(raw, 'fixture');
    renderWithProvenance(<Stage4View artifact={noSort} />);
    expect(screen.queryByRole('button', { name: 'evidence completeness' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'NEBPI tier' })).toBeNull();
  });
});
