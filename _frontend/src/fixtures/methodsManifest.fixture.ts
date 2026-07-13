// Synthetic Methods & Provenance manifest for the explicit ?demo=1 gate ONLY. Never used in
// production (production binds to the real content-addressed stage manifest; missing values
// render as "unavailable"). Values are visibly synthetic.

import type { StageMethodsManifest } from '../domain/methodsManifest';

export function demoMethodsManifest(stage_label: string): StageMethodsManifest {
  return {
    stage_label,
    methods: {
      data_input: 'Marson GWCD4i (synthetic fixture) · masked target arms',
      estimand: 'Two independent arm projections (away_from_A, toward_b); no combined score',
      masks_qc: 'Target-neighborhood mask; QC = on-target significance + guide/donor concordance',
      upstream_model: 'Stage-1 continuous program scorer view (fixture)',
      limitations: [
        'One in-vitro CD4 dataset; suggestive, not confirmatory',
        'Ranking eligibility consumes upstream ontarget_significant only; Stage 2 emits no p/q',
      ],
      method_id: 'target_masked_measured_effect_screen.fixture',
      method_code_sha256: 'f'.repeat(64),
      environment: 'fixture://synthetic-env',
      last_run_utc: '2026-07-13T00:00:00Z',
      reproduce_command: 'python -m analysis.direct.run_screen --lane fixture --demo',
    },
    provenance: {
      release_revision: 'fixture-release@0',
      raw_sha256: 'a'.repeat(64),
      canonical_sha256: 'b'.repeat(64),
      generator_status: 'generated (fixture)',
      verifier_status: 'admitted (fixture verifier)',
      cs_notebook_url: 'fixture://cs-notebook',
      artifact_paths: [`fixture:${stage_label.toLowerCase()}/screen.parquet`],
      source_chain: [
        {
          label: 'Reactome',
          record_id: 'R-FIX-0000',
          url: null,
          license: 'CC BY 4.0 (fixture)',
          retrieval_utc: '2026-07-13T00:00:00Z',
          raw_sha256: 'c'.repeat(64),
          canonical_sha256: 'd'.repeat(64),
        },
      ],
    },
  };
}
