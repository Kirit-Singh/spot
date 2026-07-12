// Per-page empty-scaffold descriptors (output shape only) for the four downstream
// island pages. One line per region — no prose, no fake data.

import type { ScaffoldRegion } from '../shell/StageScaffold';
import type { PageKey } from './pages';

interface Scaffold {
  purpose: string;
  regions: ScaffoldRegion[];
}

export const MPA_SCAFFOLDS: Record<Exclude<PageKey, 'programs'>, Scaffold> = {
  targets: {
    purpose: 'Targets — independent arm effects, joint Pareto ordering, marker breadth',
    regions: [
      { label: 'Away-from-A / Toward-B effects', hint: 'Per-target rank and signed effect for each objective, independently.' },
      { label: 'Joint · Pareto ordering', hint: 'joint_status and Pareto tier — typed ordering, never an averaged score.' },
      { label: 'Marker-breadth diagnostics', hint: 'Supporting-marker count and single-marker-driven flag per target.' },
    ],
  },
  pathways: {
    purpose: 'Pathways — convergent perturbation signatures and druggable nodes',
    regions: [
      { label: 'Convergent signatures', hint: 'Contributing targets, arm of support, and enrichment evidence per node.' },
      { label: 'Druggable nodes', hint: 'Which convergent nodes are themselves druggable entities.' },
    ],
  },
  drugs: {
    purpose: 'Drugs — direct-target and pathway-node candidates with mechanism direction',
    regions: [
      { label: 'Direct-target candidates', hint: 'Drugs acting on a Stage-2 target: mechanism action and direction.' },
      { label: 'Pathway-node candidates', hint: 'Drugs acting on a convergent pathway node.' },
      { label: 'Supporting arm + direction', hint: 'The exact arm and direction supporting each drug — traced, not inferred.' },
    ],
  },
  pksafety: {
    purpose: 'PK & safety — delivery, exposure, NEBPI state, treatment-context safety',
    regions: [
      { label: 'Delivery requirement', hint: 'Systemic vs local / intrathecal, with supporting evidence.' },
      { label: 'Exposure', hint: 'Systemic / unbound exposure and measured CNS / tumour evidence.' },
      { label: 'NEBPI state', hint: 'Decision tier and path — neutral typed state, no traffic light.' },
      { label: 'Treatment-context safety', hint: 'Safety in the intended treatment setting.' },
    ],
  },
};
