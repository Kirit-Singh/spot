// Stage Methods & Provenance manifest — the content rendered in the ONE shared header
// slide-out drawer, per active tab. Every field comes from the real stage manifest; a null
// (or empty list) renders as "unavailable" and is NEVER invented. No editorial prose — the
// limitations are compact factual rows intrinsic to the method.

import type { Provenance } from './common';

export interface MethodsBlock {
  data_input: string | null; // exact data / input
  source_tissue: string | null; // source-tissue fact (source-backed; not inferred)
  estimand: string | null; // estimand / formula / algorithm
  masks_qc: string | null; // masks / QC
  upstream_model: string | null; // upstream model, if any
  limitations: string[]; // method-intrinsic limitations (factual)
  method_id: string | null;
  method_code_sha256: string | null; // method / code hash
  environment: string | null; // solver-locked env ref/hash
  last_run_utc: string | null; // last successful run, UTC ISO-8601
  reproduce_command: string | null; // copyable reproduce command
}

export interface SourceChainLink {
  label: string;
  record_id: string;
  url: string | null;
  license: string | null; // license / terms
  retrieval_utc: string | null;
  raw_sha256: string | null;
  canonical_sha256: string | null;
}

export interface ProvenanceBlock {
  release_revision: string | null; // release / revision
  raw_sha256: string | null;
  canonical_sha256: string | null;
  generator_status: string | null; // generator status
  verifier_status: string | null; // independent verifier status
  cs_notebook_url: string | null; // Claude Science notebook / session export link
  artifact_paths: string[];
  source_chain: SourceChainLink[]; // content-addressed source chain
}

export interface StageMethodsManifest {
  stage_label: string;
  methods: MethodsBlock;
  provenance: ProvenanceBlock;
}

/**
 * The source-tissue fact for a stage — source-backed, never inferred, so it is stated even
 * before an arm is generated. Stage 1/2 (Marson): one experimental source, primary human CD4
 * T cells across donor/stimulation conditions, no multi-tissue expression analysis. Stage-4
 * safety: organ-system groups come only from label evidence, never inferred tissue expression.
 */
export function stageSourceTissue(stage_label: string): string | null {
  const s = stage_label.toLowerCase();
  if (s.includes('target') || s.includes('pathway')) {
    return 'Primary human CD4 T cells (Marson GWCD4i) — one experimental source, across donor/stimulation conditions; no multi-tissue expression analysis.';
  }
  if (s.includes('pk') || s.includes('safety')) {
    return 'Organ-system safety groups are shown only from source-backed label evidence, never inferred from tissue expression.';
  }
  return null;
}

/** Honest all-unavailable manifest — the production state before an arm is generated. */
export function unavailableManifest(stage_label: string): StageMethodsManifest {
  return {
    stage_label,
    methods: {
      data_input: null,
      source_tissue: stageSourceTissue(stage_label),
      estimand: null,
      masks_qc: null,
      upstream_model: null,
      limitations: [],
      method_id: null,
      method_code_sha256: null,
      environment: null,
      last_run_utc: null,
      reproduce_command: null,
    },
    provenance: {
      release_revision: null,
      raw_sha256: null,
      canonical_sha256: null,
      generator_status: null,
      verifier_status: null,
      cs_notebook_url: null,
      artifact_paths: [],
      source_chain: [],
    },
  };
}

/**
 * Manifest derived from a loaded artifact's provenance. Only the fields the provenance
 * actually carries are populated; everything the stage manifest has not supplied stays null
 * ("unavailable"). Never fabricates estimand/QC/run-time/reproduce values.
 */
export function manifestFromProvenance(stage_label: string, p: Provenance): StageMethodsManifest {
  const base = unavailableManifest(stage_label);
  return {
    stage_label,
    methods: {
      ...base.methods,
      method_id: p.method.method_id,
      environment: p.method.env_ref,
    },
    provenance: {
      ...base.provenance,
      raw_sha256: p.hashes.raw_sha256,
      canonical_sha256: p.hashes.canonical_sha256,
      cs_notebook_url: p.cs_session ? p.cs_session.frame_ref : null,
      artifact_paths: [p.artifact_id],
      source_chain: p.sources.map((s) => ({
        label: s.label,
        record_id: s.record_id,
        url: s.url,
        license: null,
        retrieval_utc: null,
        raw_sha256: null,
        canonical_sha256: null,
      })),
    },
  };
}
