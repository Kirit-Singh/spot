// Stage-2 REAL-RUN artifact shapes (UI-facing, validated), aligned to the authoritative
// serializations the pipeline emits:
//   · Direct screen     — screen.parquet   (FLAT rows: spot.stage02_screen.v1)
//   · Temporal DiD       — temporal.parquet  (FLAT rows: population-level difference-in-differences)
//   · Pathway convergence — pathway.json     (records[].enrichment.{away_from_A,toward_b})
//
// Contract facts these shapes encode (see 02_geneskew/analysis/direct/run_screen.py and the
// W18 temporal handoff):
//   · The two Direct objectives use the real asymmetric column names `away_from_A` and
//     `toward_b`; they are INDEPENDENT arms, never averaged into a combined/balanced score.
//   · The adapters ALLOWLIST the UI-facing fields and PROJECT AWAY everything else —
//     machine/provenance columns (delta_*, *_zscore, balanced_skew, support_*, mask_*),
//     the temporal `batch_partially_confounded` methods-only field and its reliability
//     metric, and any stray combined column. Projected-away fields are never rendered, and
//     their mere presence NEVER rejects an already-verified artifact.
//   · Stage 2 emits no new p/q/FDR; only the upstream `ontarget_significant` boolean is kept.
//   · Temporal is a population-level cross-condition difference-in-differences (never lineage).

import type { Provenance } from './common';
import type { StageSelection } from './selection';

/** The two independent Direct objectives, by their real serialized column names. */
export type DirectObjective = 'away_from_A' | 'toward_b';

export const DIRECT_OBJECTIVES: readonly DirectObjective[] = ['away_from_A', 'toward_b'];

// ───────────────────────── Direct screen (flat screen.parquet row) ─────────────────────────

/**
 * One normalized Direct screen row. `away_from_A` / `toward_b` are the two independent arm
 * effects read straight from the flat columns; `rank` is the screen's deterministic order.
 */
export interface DirectScreenRow {
  target_ensembl: string;
  target_symbol: string | null;
  condition: string;
  /** Upstream Marson `obs.ontarget_significant` (eligibility input; not a spot p/q). */
  ontarget_significant: boolean | null;
  /** Disposition eligibility state (e.g. eligible / ineligible_*). */
  eligibility_state: string | null;
  /** Typed cross-arm direction relationship (aligned_both / *_only / opposed) — never a score. */
  direction_class: string | null;
  /** Deterministic within-screen rank (1-based); null when not ranked. */
  rank: number | null;
  /** away_from_A arm measured projection (signed logFC-space); null when not evaluated. */
  away_from_A: number | null;
  /** toward_b arm measured projection (signed logFC-space); null when not evaluated. */
  toward_b: number | null;
}

export interface DirectScreenArtifact {
  provenance: Provenance;
  selection: StageSelection;
  /** The single within-condition timepoint this screen was run at (Rest / Stim8hr / Stim48hr). */
  condition: string;
  rows: DirectScreenRow[];
}

// ───────────────────────── Temporal DiD (flat temporal.parquet row) ─────────────────────────

/**
 * One normalized temporal record for a (target, ordered pair). A difference-in-differences
 * on program projections, per arm, carrying BOTH endpoints (a target present at only one
 * endpoint has the other endpoint null + present flag false). The methods-only
 * `batch_partially_confounded` field and its reliability metric are projected away.
 */
export interface TemporalDiDRow {
  target_ensembl: string;
  target_symbol: string | null;
  /** DiD on the away_from_A program projection across the ordered pair; null when not evaluated. */
  away_from_A_did: number | null;
  /** DiD on the toward_b program projection across the ordered pair; null when not evaluated. */
  toward_b_did: number | null;
  /** away_from_A arm effect at each endpoint; null when that endpoint is absent/not evaluated. */
  away_from_A_from: number | null;
  away_from_A_to: number | null;
  /** toward_b arm effect at each endpoint; null when that endpoint is absent/not evaluated. */
  toward_b_from: number | null;
  toward_b_to: number | null;
  /** Whether the target was present at each endpoint of the pair (union rows). */
  present_from: boolean | null;
  present_to: boolean | null;
}

export interface TemporalDiDArtifact {
  provenance: Provenance;
  selection: StageSelection;
  from_condition: string;
  to_condition: string;
  /** Population-level cross-condition difference-in-differences only — never lineage tracking. */
  analysis_mode: 'temporal_cross_condition';
  rows: TemporalDiDRow[];
}

// ─────────────────── Pathway convergence (pathway.json records[].enrichment) ───────────────────

/**
 * Per-arm coverage disposition (server-decided). Only `rankable` is headline-rankable;
 * everything else is descriptive-only and must be kept clearly separated from headline
 * results. Read as a string (the server owns the vocabulary); the known values are:
 *   rankable · descriptive_only_low_source_coverage · descriptive_only_thin_arm · undefined
 */
export type ArmCoverageDisposition =
  | 'rankable'
  | 'descriptive_only_low_source_coverage'
  | 'descriptive_only_thin_arm'
  | 'undefined';

/** One arm's enrichment under `records[].enrichment.<objective>`. Arms are independent. */
export interface PathwayArmEnrichment {
  objective: DirectObjective;
  /** Server-decided coverage disposition; UI shows only `rankable` as headline. */
  arm_coverage_disposition: string;
  /** Server-decided headline eligibility — the UI trusts this to separate headline vs descriptive. */
  arm_headline_rankable: boolean;
  /** Enrichment value AS SUPPLIED by the gene-set method; null when undefined. Never a spot p/q. */
  enrichment_value: number | null;
  /** Pathway members present in this arm's ranking; null when not evaluated. */
  n_hits_in_ranking: number | null;
  /** Fraction of source members present in the target namespace; null when not evaluated. */
  source_coverage: number | null;
}

export interface PathwayConvergenceRecord {
  pathway_id: string;
  name: string;
  /** Target gene-ids converging on this node (membership = targets). */
  contributing_targets: string[];
  druggable: boolean | null;
  /** Per-arm enrichment keyed by objective — the real shape is `record.enrichment.<objective>`. */
  enrichment: Record<DirectObjective, PathwayArmEnrichment>;
}

export interface PathwayConvergenceArtifact {
  provenance: Provenance;
  selection: StageSelection;
  condition: string;
  /** Which annotation resource the gene sets came from (e.g. reactome / go_bp). */
  gene_set_source: string;
  records: PathwayConvergenceRecord[];
}
