// Tier-2 display labels ("Treg-like", "CD4 CTL-like", …) are resolved from the Stage-1 display registry
// (data/stage01_program_registry.json) — the header never shows a raw program_id when the registry names
// it. Display-only: no scientific hash is entered; a null/absent label is skipped; an unreachable registry
// fails closed to an empty map.

import { describe, expect, it } from 'vitest';
import { loadProgramLabels, programLabel } from '../programLabels';
import { contrastFromV3, selectionDisplayFromV3 } from '../StageIsland';
import type { SelectionV3 } from '../../adapters/selectionV3Adapter';

const REGISTRY = JSON.stringify({
  programs: [
    { program_id: 'treg_like', display_label: 'Treg-like' },
    { program_id: 'th17_like', display_label: 'Th17-like' },
    { program_id: 'cd4_ctl_like', display_label: 'CD4 CTL-like' },
    { program_id: 'no_label', display_label: null },
  ],
});
const fetchRegistry = (path: string) =>
  path === 'data/stage01_program_registry.json' ? Promise.resolve(REGISTRY) : Promise.reject(new Error('404'));

describe('Tier-2 program label resolution', () => {
  it('builds program_id → display_label from the display registry (null labels skipped)', async () => {
    const labels = await loadProgramLabels(fetchRegistry);
    expect(labels.get('treg_like')).toBe('Treg-like');
    expect(labels.get('cd4_ctl_like')).toBe('CD4 CTL-like');
    expect(labels.has('no_label')).toBe(false);
  });

  it('fails closed to an empty map when the registry is unreachable', async () => {
    const labels = await loadProgramLabels(() => Promise.reject(new Error('offline')));
    expect(labels.size).toBe(0);
  });

  it('programLabel resolves the label, falling back to the id only when unnamed', async () => {
    const labels = await loadProgramLabels(fetchRegistry);
    expect(programLabel(labels, 'treg_like')).toBe('Treg-like');
    expect(programLabel(labels, 'unknown_prog')).toBe('unknown_prog');
  });

  it('contrastFromV3 shows Tier-2 labels, never raw program_ids', async () => {
    const labels = await loadProgramLabels(fetchRegistry);
    const sel = {
      A: { program_id: 'treg_like', direction: 'high' },
      B: { program_id: 'th17_like', direction: 'low' },
      conditions: ['Rest'],
    } as unknown as SelectionV3;
    const contrast = contrastFromV3(sel, labels);
    expect(contrast.program_a?.display_label).toBe('Treg-like');
    expect(contrast.program_b?.display_label).toBe('Th17-like');
    expect(contrast.program_a?.display_label).not.toBe('treg_like'); // no raw id
  });

  it('contrastFromV3 preserves ordered temporal endpoint conditions', async () => {
    const labels = await loadProgramLabels(fetchRegistry);
    const sel = {
      A: { program_id: 'diff_activated', direction: 'high' },
      B: { program_id: 'diff_activated', direction: 'high' },
      conditions: ['Stim8hr', 'Stim48hr'],
    } as unknown as SelectionV3;
    const contrast = contrastFromV3(sel, labels);
    expect(contrast.condition_a).toBe('Stim8hr');
    expect(contrast.condition_b).toBe('Stim48hr');
    expect(contrast.analysis_condition).toBeUndefined();
  });

  it('selectionDisplayFromV3 preserves distinct endpoints for the provenance drawer', async () => {
    const labels = await loadProgramLabels(fetchRegistry);
    const sel = {
      selection_id: 'selection-1',
      question_id: 'question-1',
      analysis_mode: 'temporal_cross_condition',
      execution_status: 'ready',
      estimator_id: 'temporal_cross_condition_v1',
      estimator_status: 'available',
      A: { program_id: 'diff_activated', direction: 'high' },
      B: { program_id: 'diff_activated', direction: 'high' },
      conditions: ['Stim8hr', 'Stim48hr'],
    } as unknown as SelectionV3;
    const display = selectionDisplayFromV3(sel, labels);
    expect(display.A.condition).toBe('Stim8hr');
    expect(display.B.condition).toBe('Stim48hr');
    expect(display.analysis_mode).toBe('temporal_cross_condition');
  });
});
