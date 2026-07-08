import type { EvidenceType } from '../design/tokens'

export interface GraphEdge {
  id: string
  label: string
  sub: string
  axis: string
  ev: EvidenceType
  state: 'confirmed' | 'untested'
  weight: number
  angle: number // authored degrees; fixed radial position, grouped by axis
}

export const CENTER = {
  id: 'hit',
  label: 'RASA2',
  sub: 'CRISPRi · CD4+ T · -11 to -14 · 3/3 sig',
}

// Seeded from Marson2025 GWCD4i DE_stats (see data/seed_graph_spec.json).
export const EDGES: GraphEdge[] = [
  { id: 'ibd', label: 'Autoimmune / IBD', sub: 'Open Targets', axis: 'disease', ev: 'genetic', state: 'confirmed', weight: 0.75, angle: 20 },
  { id: 'cd8', label: 'CD8 T cell', sub: 'Census CL:0000625', axis: 'cell type', ev: 'consistency', state: 'confirmed', weight: 0.7, angle: 65 },
  { id: 'treg', label: 'Treg', sub: 'Census CL:0000815', axis: 'cell type', ev: 'consistency', state: 'confirmed', weight: 0.55, angle: 108 },
  { id: 'model', label: 'Lane B model', sub: 'held-out', axis: 'predictive', ev: 'predictive', state: 'untested', weight: 0.4, angle: 150 },
  { id: 'cart', label: 'RASA2-KO CAR-T', sub: 'Carnevale 2022', axis: 'modality', ev: 'replication', state: 'confirmed', weight: 0.95, angle: 195 },
  { id: 'donors', label: 'Donors D1/D2', sub: 'Marson pseudobulk', axis: 'population', ev: 'consistency', state: 'confirmed', weight: 0.65, angle: 240 },
  { id: 'ctx', label: 'Rest / Stim', sub: '3 conditions', axis: 'context', ev: 'consistency', state: 'confirmed', weight: 0.8, angle: 290 },
  { id: 'tumor', label: 'Solid tumor / ACT', sub: 'Open Targets', axis: 'disease', ev: 'genetic', state: 'confirmed', weight: 0.5, angle: 340 },
]
