import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { ScienceEvidence } from '../ScienceEvidence';
import { evidenceFromProvenance } from '../evidence';
import type { Provenance } from '../../domain/common';

afterEach(cleanup);

describe('Science-firewall surface', () => {
  it('shows "no evidence record bound" + an enqueue seam that only records intent', () => {
    render(<ScienceEvidence record={null} enqueueTarget="stage02_review" />);
    expect(screen.getByText('no evidence record bound')).toBeInTheDocument();
    expect(screen.getByText(/stage02_review/)).toBeInTheDocument();
    const btn = screen.getByRole('button', { name: /Enqueue review job/ });
    fireEvent.click(btn);
    // The seam records intent locally and drives nothing — the button just latches.
    expect(screen.getByRole('button', { name: /review job requested/ })).toBeDisabled();
  });

  it('displays a frozen {science_evidence_id, sha256, record_type} record', () => {
    render(
      <ScienceEvidence
        record={{ science_evidence_id: 'EV-123', sha256: 'a'.repeat(64), record_type: 'research_only · v1' }}
        enqueueTarget="t"
      />,
    );
    expect(screen.getByText(/EV-123/)).toBeInTheDocument();
    expect(screen.getByText(/a{64}/)).toBeInTheDocument();
    expect(screen.getByText('research_only · v1')).toBeInTheDocument();
  });

  it('derives the evidence record from artifact provenance (display only)', () => {
    const prov = {
      artifact_id: 'fixture:stage02:demo@abcdef012345',
      schema_version: 'spot.stage02_gene_lever_set.v1',
      namespace: 'fixture',
      hashes: { raw_sha256: 'b'.repeat(64), canonical_sha256: 'd'.repeat(64) },
    } as unknown as Provenance;
    const rec = evidenceFromProvenance(prov);
    expect(rec.science_evidence_id).toBe('fixture:stage02:demo@abcdef012345');
    expect(rec.sha256).toBe('d'.repeat(64));
    expect(rec.record_type).toContain('fixture');
  });
});
