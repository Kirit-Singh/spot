// Synthetic Stage-4 scorecard set (fixture namespace, production_eligible=false).
//
// Every field carries a measurement state (measured / calculated / label-derived /
// not-evaluated / missing). Missing values stay null — never coerced to 0. CNS-MPO
// is shown as a property heuristic, not clinical brain exposure. No composite ranking.

import { fixtureProvenance } from './synthetic';

function f(value: number | string | null, state: string, unit: string | null = null, source: unknown = null) {
  return { value, state, unit, source };
}

// Explicitly synthetic generic drug-label source. No bundled/licensed DrugBank record.
const SRC_LABEL = { label: 'Synthetic label source', record_id: 'SYN-LABEL-FIX-0000', url: null, detail: 'Synthetic generic drug-label record (fixture)' };
const SRC_PK = { label: 'ChEMBL', record_id: 'CHEMBL-FIX-PK-0000', url: null, detail: 'Synthetic PK record (fixture)' };

function scorecardProvenance(slug: string, seed: string) {
  return fixtureProvenance({
    stage: 'stage04',
    slug,
    seed,
    methodId: 'cns_mpo_nebpi_2026.fixture',
    sources: [SRC_LABEL, SRC_PK],
    upstream: { stage: 'stage03', slug: 'demo_drug_set', seed: 'a3b3c3d3' },
  });
}

export const stage4FixtureRaw = {
  provenance: fixtureProvenance({
    stage: 'stage04',
    slug: 'demo_scorecard_set',
    seed: 'a4b4c4d4',
    methodId: 'cns_mpo_nebpi_2026.fixture',
    sources: [SRC_LABEL],
    upstream: { stage: 'stage03', slug: 'demo_drug_set', seed: 'a3b3c3d3' },
  }),
  sortable_by: ['evidence_completeness', 'nebpi_tier'],
  scorecards: [
    {
      scorecard_id: 'SCORECARD_A',
      candidate_id: 'COMPOUND_A',
      active_moiety: 'Compound A (active moiety)',
      form: 'COMPOUND_A_HCL',
      delivery: {
        requirement: f('Systemic (oral) sufficient — synthetic', 'label_derived', null, SRC_LABEL),
        supporting_evidence: f('Measured Kp,uu above threshold (fixture)', 'measured', null, SRC_PK),
      },
      safety: {
        regulatory_status: f('Synthetic approved-label state', 'label_derived', null, SRC_LABEL),
        boxed_warning: f('None on synthetic label', 'label_derived', null, SRC_LABEL),
        key_risks: f('Synthetic risk summary (fixture)', 'label_derived', null, SRC_LABEL),
      },
      exposure: {
        systemic_cmax: f(1.8, 'measured', 'uM', SRC_PK),
        unbound_fraction: f(0.12, 'measured', 'fraction', SRC_PK),
        half_life: f(6.5, 'measured', 'h', SRC_PK),
      },
      cns: {
        kp_uu: f(0.34, 'measured', 'ratio', SRC_PK),
        csf_concentration: f(0.21, 'measured', 'uM', SRC_PK),
        tumour_concentration: f(null, 'not_evaluated'),
      },
      cns_mpo: {
        clogp: f(2.4, 'calculated'),
        clogd: f(1.9, 'calculated'),
        tpsa: f(62, 'calculated', 'A^2'),
        mw: f(342, 'calculated', 'Da'),
        hbd: f(1, 'calculated'),
        pka: f(8.1, 'calculated'),
        descriptor_score: f(4.2, 'calculated'),
      },
      nebpi: {
        version: 'NEBPI 2026 (Grossman et al., Neuro-Oncology)',
        tier: 'sufficiently_permeable',
        rationale: 'Synthetic: measured Kp,uu above threshold with adequate descriptor support (fixture).',
        decision_path: [
          { label: 'Measured unbound CNS exposure available?', outcome: 'yes (synthetic Kp,uu)' },
          { label: 'Kp,uu ≥ threshold?', outcome: 'yes (synthetic)' },
          { label: 'Efflux liability disqualifying?', outcome: 'no (synthetic)' },
          { label: 'Tier', outcome: 'sufficiently_permeable' },
        ],
      },
      treatment_context: {
        setting: f('Adjunct to radiotherapy + temozolomide (synthetic)', 'label_derived', null, SRC_LABEL),
        concerns: f('Additive myelosuppression risk (synthetic)', 'label_derived', null, SRC_LABEL),
      },
      provenance: scorecardProvenance('demo_scorecard_a', 'd4a10001'),
    },
    {
      scorecard_id: 'SCORECARD_B',
      candidate_id: 'COMPOUND_B',
      active_moiety: 'Compound B (active moiety)',
      form: 'COMPOUND_B_BASE',
      delivery: {
        requirement: f('Requires local / intrathecal delivery — synthetic', 'label_derived', null, SRC_LABEL),
        supporting_evidence: f(null, 'not_evaluated'),
      },
      safety: {
        regulatory_status: f(null, 'not_evaluated'),
        boxed_warning: f(null, 'missing'),
        key_risks: f(null, 'missing'),
      },
      exposure: {
        systemic_cmax: f(null, 'missing', 'uM'),
        unbound_fraction: f(null, 'not_evaluated', 'fraction'),
        half_life: f(null, 'missing', 'h'),
      },
      cns: {
        kp_uu: f(null, 'not_evaluated', 'ratio'),
        csf_concentration: f(null, 'missing', 'uM'),
        tumour_concentration: f(null, 'not_evaluated'),
      },
      cns_mpo: {
        clogp: f(3.6, 'calculated'),
        clogd: f(3.1, 'calculated'),
        tpsa: f(95, 'calculated', 'A^2'),
        mw: f(511, 'calculated', 'Da'),
        hbd: f(3, 'calculated'),
        pka: f(6.2, 'calculated'),
        descriptor_score: f(2.1, 'calculated'),
      },
      nebpi: {
        version: 'NEBPI 2026 (Grossman et al., Neuro-Oncology)',
        tier: 'not_evaluated',
        rationale: 'Synthetic: no measured CNS exposure; descriptor-only support is insufficient to assign a tier (fixture).',
        decision_path: [
          { label: 'Measured unbound CNS exposure available?', outcome: 'no (synthetic)' },
          { label: 'Descriptor-only path permitted for tier assignment?', outcome: 'no — heuristic, not exposure' },
          { label: 'Tier', outcome: 'not_evaluated' },
        ],
      },
      treatment_context: {
        setting: f(null, 'not_evaluated'),
        concerns: f(null, 'missing'),
      },
      provenance: scorecardProvenance('demo_scorecard_b', 'd4b20002'),
    },
  ],
};
