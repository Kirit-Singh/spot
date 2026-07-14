// Per-stage empty-scaffold descriptors: what each stage will produce, as compact
// structural regions. Used only in `empty` mode. One line per region — no prose.

import type { ScaffoldRegion } from './StageScaffold';
import type { StageRoute } from './routing';

interface Scaffold {
  purpose: string;
  regions: ScaffoldRegion[];
}

export const STAGE_SCAFFOLDS: Record<StageRoute, Scaffold> = {
  'stage-2': {
    purpose: 'Targets — independent arm effects, joint Pareto ordering, marker breadth, convergent pathways',
    regions: [
      { label: 'Away-from-A / Toward-B effects', hint: 'Per-target rank and signed effect for each objective, independently.' },
      { label: 'Joint · Pareto ordering', hint: 'joint_status and Pareto tier — typed ordering, never an averaged score.' },
      { label: 'Marker-breadth diagnostics', hint: 'Supporting-marker count and single-marker-driven flag per target.' },
      { label: 'Convergent pathways · druggable nodes', hint: 'Contributing targets, arm of support, enrichment, druggable-node flag.' },
    ],
  },
  'stage-3': {
    purpose: 'Drugs — direct-target and pathway-node candidates with mechanism direction',
    regions: [
      { label: 'Direct-target candidates', hint: 'Drugs acting on a Stage-2 target: mechanism action and direction.' },
      { label: 'Pathway-node candidates', hint: 'Drugs acting on a convergent pathway node.' },
      { label: 'Supporting arm + direction', hint: 'The exact arm and direction supporting each drug — traced, not inferred.' },
    ],
  },
  'stage-4': {
    purpose: 'PK & safety — delivery, exposure, NEBPI state, treatment-context safety',
    regions: [
      { label: 'Delivery requirement', hint: 'Systemic vs local / intrathecal, with supporting evidence.' },
      { label: 'Exposure', hint: 'Systemic / unbound exposure and measured CNS / tumour evidence.' },
      { label: 'NEBPI state', hint: 'Decision tier and path — neutral typed state, no traffic light.' },
      { label: 'Treatment-context safety', hint: 'Safety in the intended treatment setting.' },
    ],
  },
};
