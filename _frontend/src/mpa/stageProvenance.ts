// Resolve a downstream stage's provenance from the repository (the content-addressed
// aggregate binding — the same adapter path the stage views use). Targets + Pathways read
// the Stage-2 slot, Drugs the Stage-3 slot, PK & Safety the Stage-4 slot. Returns a null
// provenance (never a fixture) when the aggregate has not generated that arm.

import type { SpotRepository } from '../repository/repository';
import type { Provenance } from '../domain/common';
import type { StageSelection } from '../domain/selection';
import type { StageView } from './methodsRoutes';

export interface StageProvenance {
  provenance: Provenance | null;
  selection: StageSelection | null;
  status: 'loaded' | 'not_generated' | 'rejected';
  reason: string | null;
}

export function resolveStageProvenance(repo: SpotRepository, stage: StageView): StageProvenance {
  const slot =
    stage === 'drugs' ? repo.getStage3() : stage === 'pksafety' ? repo.getStage4() : repo.getStage2();
  const selection = repo.selection;
  if (slot.status === 'loaded') {
    return { provenance: slot.artifact.provenance, selection, status: 'loaded', reason: null };
  }
  if (slot.status === 'rejected') {
    return { provenance: null, selection, status: 'rejected', reason: slot.reason };
  }
  return { provenance: null, selection, status: 'not_generated', reason: null };
}
