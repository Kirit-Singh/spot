// Synthetic Stage-3 drug-candidate set (fixture namespace, production_eligible=false).
//
// Keeps both desired arms visible; preserves mixed / conflicting / not-evaluated
// states. Synthetic identifiers only (COMPOUND_A …). No real drug/target claims.

import { fixtureProvenance } from './synthetic';

function candidateProvenance(slug: string, seed: string) {
  return fixtureProvenance({
    stage: 'stage03',
    slug,
    seed,
    methodId: 'target_to_drug_plus_lincs.fixture',
    sources: [
      { label: 'ChEMBL', record_id: 'CHEMBL-FIX-0000', url: null, detail: 'Synthetic potency record (fixture)' },
      { label: 'Open Targets', record_id: 'OT-FIX-0000', url: null, detail: 'Synthetic target→drug record (fixture)' },
    ],
    upstream: { stage: 'stage02', slug: 'demo_lever_set', seed: 'a2b2c2d2' },
  });
}

export const stage3FixtureRaw = {
  provenance: fixtureProvenance({
    stage: 'stage03',
    slug: 'demo_drug_set',
    seed: 'a3b3c3d3',
    methodId: 'target_to_drug_plus_lincs.fixture',
    sources: [
      { label: 'DGIdb', record_id: 'DGIDB-FIX-0000', url: null, detail: 'Synthetic gene→drug interactions (fixture)' },
    ],
    upstream: { stage: 'stage02', slug: 'demo_lever_set', seed: 'a2b2c2d2' },
  }),
  desired_arms: ['away_from_A', 'toward_B'],
  candidates: [
    {
      candidate_id: 'COMPOUND_A',
      active_moiety: 'Compound A (active moiety)',
      forms: [
        { form_id: 'COMPOUND_A_HCL', relation: 'salt_of', route: 'oral' },
        { form_id: 'COMPOUND_A_BASE', relation: 'parent_of', route: null },
      ],
      mechanism_action: 'INHIBITOR',
      origin: 'direct_target',
      pathway_node: null,
      mechanism_direction: 'down',
      target_entity: { entity_id: 'GENE_A', entity_type: 'gene', label: 'GENE_A product (synthetic)' },
      source_lever_gene_id: 'GENE_A',
      desired_arm: 'away_from_A',
      direction_compatibility: 'compatible',
      directness: 'direct',
      potency_records: [
        {
          relation: '=',
          value: 42,
          unit: 'nM',
          assay: 'Synthetic biochemical IC50 (fixture)',
          source: { label: 'ChEMBL', record_id: 'CHEMBL-FIX-0001', url: null },
        },
        {
          relation: '>',
          value: 1000,
          unit: 'nM',
          assay: 'Synthetic cellular assay (fixture)',
          source: { label: 'ChEMBL', record_id: 'CHEMBL-FIX-0002', url: null },
        },
      ],
      gbm_context: 'not_evaluated',
      source_conflicts: [],
      provenance: candidateProvenance('demo_candidate_a', 'c3a10001'),
    },
    {
      candidate_id: 'COMPOUND_B',
      active_moiety: 'Compound B (active moiety)',
      forms: [{ form_id: 'COMPOUND_B_BASE', relation: 'parent_of', route: 'intravenous' }],
      mechanism_action: 'MODULATOR',
      origin: 'direct_target',
      pathway_node: null,
      mechanism_direction: 'not_evaluated',
      target_entity: { entity_id: 'ENTITY_B', entity_type: 'protein', label: 'Entity B (synthetic)' },
      source_lever_gene_id: 'GENE_B',
      desired_arm: 'away_from_A',
      direction_compatibility: 'not_evaluated',
      directness: 'indirect',
      potency_records: [
        {
          relation: '=',
          value: null,
          unit: null,
          assay: 'Synthetic assay with no reported value (fixture)',
          source: { label: 'ChEMBL', record_id: 'CHEMBL-FIX-0003', url: null },
        },
      ],
      gbm_context: 'conflicting',
      source_conflicts: [
        {
          field: 'mechanism_action',
          values: [
            { source: 'DGIdb', value: 'MODULATOR' },
            { source: 'Open Targets', value: 'AGONIST' },
          ],
        },
      ],
      provenance: candidateProvenance('demo_candidate_b', 'c3b20002'),
    },
    {
      candidate_id: 'COMPOUND_C',
      active_moiety: 'Compound C (active moiety)',
      forms: [{ form_id: 'COMPOUND_C_BASE', relation: 'parent_of', route: 'oral' }],
      mechanism_action: 'INHIBITOR',
      origin: 'pathway_node',
      pathway_node: 'PATHWAY_02',
      mechanism_direction: 'up',
      target_entity: { entity_id: 'ENTITY_C', entity_type: 'complex', label: 'Entity C complex (synthetic)' },
      source_lever_gene_id: 'GENE_D',
      desired_arm: 'toward_B',
      direction_compatibility: 'incompatible',
      directness: 'not_evaluated',
      potency_records: [],
      gbm_context: 'mixed',
      source_conflicts: [],
      provenance: candidateProvenance('demo_candidate_c', 'c3c30003'),
    },
  ],
};
