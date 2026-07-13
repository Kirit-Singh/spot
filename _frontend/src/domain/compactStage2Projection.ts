// Browser-facing view of W3's admitted, selection-independent Stage-2 display projection.
// The native Direct / temporal / pathway artifacts remain authoritative; this document is
// only their method-versioned capped prefix. A selection resolves exactly two gene arms and
// two endpoint/condition-matched pathway arms from this immutable all-arm map.

export const COMPACT_STAGE2_SCHEMA = 'spot.stage02_display_projection.v2' as const;
export const COMPACT_STAGE2_METHOD = 'spot.stage02.display_projection.v2' as const;
export const COMPACT_STAGE2_VERIFIER =
  'spot.stage02.display_projection.independent_verifier.v1' as const;
export const COMPACT_STAGE2_SYMBOL_CROSSWALK_RAW_SHA256 =
  'd27bc749b5137346f799e00f65ca88e429672babe2f5c8357c97b01c1615764b' as const;
export const COMPACT_STAGE2_SYMBOL_CROSSWALK_CANONICAL_SHA256 =
  '8fd8ba97fd9e19455ff75a29645a18c932773d601ce6aa21e352f718a1313eea' as const;

export type CompactLane = 'direct' | 'temporal' | 'pathway';

export interface CompactTargetRow {
  target_id: string;
  /** Frozen symbol from the projection's bound Stage-1 effect-universe crosswalk; null if unmapped. */
  target_symbol: string | null;
  rank: number;
  arm_value: number | null;
}

export interface CompactPathwayRow {
  set_id: string;
  enrichment_value: number | null;
  target_source_coverage: number | null;
  global_coverage_disposition: string | null;
  n_leading_edge: number | null;
  peak_rank: number | null;
}

interface CompactArmBase {
  arm_key: string;
  source_bundle: string;
  is_a_prefix: boolean;
  n_emitted: number;
  cap: number;
}

export interface CompactTargetArm extends CompactArmBase {
  lane: 'direct' | 'temporal';
  context:
    | { condition: string }
    | { from_condition: string; to_condition: string };
  n_rows_total: number;
  n_evaluable: number;
  n_ranked: number;
  rows: CompactTargetRow[];
}

export interface CompactPathwayArm extends CompactArmBase {
  lane: 'pathway';
  context: { condition: string; gene_set_source: string };
  n_sets_total: number;
  n_with_coverage: number;
  coverage_disposition_counts: Record<string, number>;
  row_order: 'native_producer_emission_order';
  rows_are_ranked: false;
  why_not_ranked: string;
  rows: CompactPathwayRow[];
}

export type CompactStage2Arm = CompactTargetArm | CompactPathwayArm;

export interface CompactSourceFileBinding {
  raw_sha256: string;
}

export interface CompactSourceBundleBinding {
  lane: CompactLane;
  bundle_id: string;
  files: Record<string, CompactSourceFileBinding>;
}

export interface CompactSymbolCrosswalkBinding {
  crosswalk_id: 'spot.stage01.effect_universe_gwcd4i.symbol_to_ensembl.v1';
  inversion_rule_id: 'spot.stage02.symbol_crosswalk.invert_one_to_one_only.v1';
  path: string;
  raw_sha256: string;
  canonical_sha256: string;
  target_namespace: 'ensembl_gene_id';
  symbol_namespace: 'hgnc_symbol';
  coverage_universe: 'de_readout';
  n_symbols: number;
  n_one_to_one: number;
  n_ambiguous_dropped: number;
  ambiguous_ensembl_ids: string[];
}

export interface CompactStage2Projection {
  schema_version: typeof COMPACT_STAGE2_SCHEMA;
  method_version: typeof COMPACT_STAGE2_METHOD;
  selection_independent: true;
  authoritative_artifacts_are_the_native_ones: true;
  projection_sha256: string;
  n_arms: number;
  arms: Record<string, CompactStage2Arm>;
  bindings: {
    native_bundles: Record<string, CompactSourceBundleBinding>;
    symbol_crosswalk: CompactSymbolCrosswalkBinding;
  };
}

/** Explicit release identity carried by each Stage-2 results/current.json route entry. */
export interface CompactStage2ReleaseMetadata {
  schema_version: 'spot.ui_compact_stage2_release.v1';
  /** Content-addressed identity of the admitted selection-independent DISPLAY release; not an estimator run. */
  display_release_id: string;
  release_conditions: ['Rest', 'Stim8hr', 'Stim48hr'];
  pathway_sources: ['reactome', 'go_bp'];
  active_pathway_source: 'reactome' | 'go_bp';
  projection_raw_sha256: string;
  projection_canonical_sha256: string;
  projection_self_sha256: string;
  independent_verifier: {
    verifier_id: typeof COMPACT_STAGE2_VERIFIER;
    receipt_path: string;
    receipt_raw_sha256: string;
    receipt_canonical_sha256: string;
  };
}

/**
 * W3 exact admission subject (verify_display_projection.py). Binds the independent receipt to the EXACT
 * projection bytes it verified — the raw-file hash, the canonical hash, and the projection's own self-hash
 * (both the document's declared value and the verifier's recompute, plus their agreement) — closing the
 * n_arms-alone weakness where a receipt was transferable to any different projection with the same arm
 * count. The verifier recomputes these from the file on disk; the UI checks them against the served bytes.
 */
export interface CompactReceiptAdmissionSubject {
  projection_file: string;
  projection_raw_sha256: string;
  projection_canonical_sha256: string;
  projection_self_sha256_declared: string;
  projection_self_sha256_recomputed: string;
  self_hash_agrees: boolean;
}

export interface CompactDisplayVerificationReceipt {
  verifier_id: typeof COMPACT_STAGE2_VERIFIER;
  generator_is_not_verifier: true;
  rebuilt_from_admitted_native_bytes: true;
  /** Exact projection-subject binding (W3). Required — a receipt admitting by n_arms alone is refused. */
  subject: CompactReceiptAdmissionSubject;
  /** Per-lane external admission evidence the view was rebuilt from (dynamic keys). Must be non-empty. */
  admitted_inputs: Record<string, unknown>;
  n_arms: number;
  n_failed: 0;
  failures: [];
  verdict: 'admit';
}

export interface CompactStage2SelectionView {
  schema_version: 'spot.ui_compact_stage2_selection_view.v1';
  display_release_id: string;
  pathway_source: 'reactome' | 'go_bp';
  mode: 'within_condition' | 'temporal_cross_condition';
  pathway_context: 'condition_matched' | 'endpoint_pathway_context';
  geneArmA: CompactTargetArm;
  geneArmB: CompactTargetArm;
  /** Both signed directions for each selected program, kept in two separate program facets. */
  effectRankFacets: [CompactEffectRankFacet, CompactEffectRankFacet];
  /** Null on the targets route so an admitted Direct/Temporal release can render before Pathway lands. */
  pathwayArmA: CompactPathwayArm | null;
  pathwayArmB: CompactPathwayArm | null;
}

export interface CompactEffectRankFacet {
  role: 'A' | 'B';
  program_id: string;
  increase: CompactTargetArm;
  decrease: CompactTargetArm;
}
