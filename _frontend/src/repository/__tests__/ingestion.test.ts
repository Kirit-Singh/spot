// Selection ingestion + namespace separation contract.
//
// The Stage-1 research bridge writes a `spot.stage01_selection.v1` object to
// localStorage and navigates to /02_page.html#/stage-2. This suite pins how the
// shell ingests that: research vs fixture vs rejected, and the strict binding of a
// research Stage-2 artifact to its selection. Fixture results must NEVER be shown
// beneath a real research selection.

import { describe, expect, it } from 'vitest';
import { buildRepository } from '../repository';
import { mapSource, SELECTION_KEY, STAGE2_KEY } from '../source';
import { researchSelectionExampleRaw } from '../../fixtures/researchSelection.example';
import { stage2FixtureRaw } from '../../fixtures/stage2.fixture';
import { makeResearchStage2 } from '../../test/researchStage2Example';

const j = (o: unknown) => JSON.stringify(o);

describe('mode selection from localStorage', () => {
  it('no selection, no demo → empty scaffold (no data rendered)', () => {
    const repo = buildRepository(mapSource({}));
    expect(repo.mode).toBe('empty');
    expect(repo.selection).toBeNull();
    // Empty mode never surfaces artifacts — the stage renders its shape only.
    expect(repo.getStage2().status).toBe('not_generated');
  });

  it('no selection + explicit demo gate → demo mode with synthetic artifacts', () => {
    const repo = buildRepository(mapSource({}), { demo: true });
    expect(repo.mode).toBe('demo');
    expect(repo.namespace).toBe('fixture');
    expect(repo.getStage2().status).toBe('loaded');
  });

  it('valid research selection → research mode with real A/B/condition context', () => {
    const repo = buildRepository(mapSource({ [SELECTION_KEY]: j(researchSelectionExampleRaw) }));
    expect(repo.mode).toBe('research');
    expect(repo.namespace).toBe('research_only');
    expect(repo.selection?.program_a.display_label).toBe('Treg-like');
    expect(repo.selection?.program_b.display_label).toBe('Th1-like');
    expect(repo.selection?.analysis_condition).toBe('Stim48hr');
    expect(repo.selection?.production_gate_passed).toBe(false);
  });

  it('research selection with no artifact → not_generated, never fixture results', () => {
    const repo = buildRepository(mapSource({ [SELECTION_KEY]: j(researchSelectionExampleRaw) }));
    const slot = repo.getStage2();
    expect(slot.status).toBe('not_generated');
    expect(slot.status).not.toBe('loaded');
  });

  it('invalid/unknown selection → rejected_selection (not fixture, not research)', () => {
    const repo = buildRepository(mapSource({ [SELECTION_KEY]: j({ schema_version: 'nope.v9' }) }));
    expect(repo.mode).toBe('rejected_selection');
    expect(repo.selection).toBeNull();
    expect(repo.selectionRejection).toBeTruthy();
  });

  it('malformed JSON selection → rejected_selection', () => {
    const repo = buildRepository(mapSource({ [SELECTION_KEY]: '{ not json ]' }));
    expect(repo.mode).toBe('rejected_selection');
  });
});

describe('production can never be promoted through the research bridge', () => {
  it('a selection claiming production namespace is rejected (never a production repo)', () => {
    const evil = structuredClone(researchSelectionExampleRaw);
    evil.namespace = 'production';
    const repo = buildRepository(mapSource({ [SELECTION_KEY]: j(evil) }));
    expect(repo.mode).toBe('rejected_selection');
    expect(repo.namespace).not.toBe('production');
  });

  it('a selection claiming production_gate_passed=true is rejected', () => {
    const evil = structuredClone(researchSelectionExampleRaw);
    evil.production_gate_passed = true;
    const repo = buildRepository(mapSource({ [SELECTION_KEY]: j(evil) }));
    expect(repo.mode).toBe('rejected_selection');
  });

  it('a fixture-namespace selection in the research bridge channel is rejected', () => {
    const evil = structuredClone(researchSelectionExampleRaw);
    evil.namespace = 'fixture';
    const repo = buildRepository(mapSource({ [SELECTION_KEY]: j(evil) }));
    expect(repo.mode).toBe('rejected_selection');
  });
});

describe('research Stage-2 artifact binding (adapter seam)', () => {
  it('loads a matching research Stage-2 artifact', () => {
    const art = makeResearchStage2(researchSelectionExampleRaw);
    const repo = buildRepository(
      mapSource({ [SELECTION_KEY]: j(researchSelectionExampleRaw), [STAGE2_KEY]: j(art) }),
    );
    const slot = repo.getStage2();
    expect(slot.status).toBe('loaded');
    if (slot.status === 'loaded') {
      expect(slot.artifact.provenance.namespace).toBe('research_only');
      expect(slot.artifact.levers[0].gene_id).toBe('RESEARCH_GENE_1');
    }
  });

  it('rejects a research artifact whose selection_id mismatches', () => {
    const mismatched = makeResearchStage2({ ...researchSelectionExampleRaw, selection_id: 'SEL_OTHER' });
    const repo = buildRepository(
      mapSource({ [SELECTION_KEY]: j(researchSelectionExampleRaw), [STAGE2_KEY]: j(mismatched) }),
    );
    expect(repo.getStage2().status).toBe('rejected');
  });

  it('rejects a fixture-namespace Stage-2 artifact under a research selection', () => {
    const repo = buildRepository(
      mapSource({ [SELECTION_KEY]: j(researchSelectionExampleRaw), [STAGE2_KEY]: j(stage2FixtureRaw) }),
    );
    // Never silently accept fixture results in a research context.
    expect(repo.getStage2().status).toBe('rejected');
  });
});
