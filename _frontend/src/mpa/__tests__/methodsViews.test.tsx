import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { NotebookView, TraceView } from '../methodsViews';
import { resolveStageProvenance } from '../stageProvenance';
import { createDemoRepository, buildRepository } from '../../repository/repository';
import { mapSource } from '../../repository/source';

function hrefOf(name: RegExp) {
  const href = screen.getByRole('link', { name }).getAttribute('href') ?? '';
  return { base: href.split('?')[0], stage: new URLSearchParams(href.split('?')[1]).get('stage') };
}

describe('resolveStageProvenance — content-addressed aggregate binding', () => {
  it('maps each stage to its slot (targets/pathways→S2, drugs→S3, pksafety→S4)', () => {
    const repo = createDemoRepository();
    expect(resolveStageProvenance(repo, 'targets').status).toBe('loaded');
    expect(resolveStageProvenance(repo, 'pathways').status).toBe('loaded');
    expect(resolveStageProvenance(repo, 'drugs').provenance?.artifact_id).toMatch(/stage03/);
    expect(resolveStageProvenance(repo, 'pksafety').provenance?.artifact_id).toMatch(/stage04/);
  });

  it('returns a null provenance (never a fixture) when the aggregate has not generated the arm', () => {
    const sp = resolveStageProvenance(buildRepository(mapSource({})), 'targets');
    expect(sp.status).toBe('not_generated');
    expect(sp.provenance).toBeNull();
  });
});

describe('NotebookView / TraceView — clean Methods & Provenance, cross-linked', () => {
  const sp = resolveStageProvenance(createDemoRepository(), 'targets');

  it('NotebookView shows the method and links to the trace', () => {
    render(<NotebookView stage="targets" provenance={sp.provenance} selection={sp.selection} />);
    expect(screen.getByRole('heading', { name: 'Methods' })).toBeInTheDocument();
    expect(screen.getByText(sp.provenance!.method.method_id)).toBeInTheDocument();
    const link = hrefOf(/Provenance trace/);
    expect(link.base).toBe('01_trace.html');
    expect(link.stage).toBe('targets');
  });

  it('TraceView shows the content-addressed identity + canonical hash and links to the notebook', () => {
    render(<TraceView stage="targets" provenance={sp.provenance} selection={sp.selection} />);
    expect(screen.getByRole('heading', { name: 'Provenance trace' })).toBeInTheDocument();
    expect(screen.getByText(sp.provenance!.hashes.canonical_sha256)).toBeInTheDocument();
    const link = hrefOf(/^Methods/);
    expect(link.base).toBe('01_notebook.html');
    expect(link.stage).toBe('targets');
  });

  it('awaiting state renders no fixture data when the arm is not generated', () => {
    render(<NotebookView stage="drugs" provenance={null} selection={null} />);
    expect(screen.getByText(/once this arm is generated/)).toBeInTheDocument();
    expect(screen.queryByText(/fixture/)).toBeNull();
  });
});
