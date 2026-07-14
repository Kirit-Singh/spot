// Round-4 REUSABLE-ARM domain shapes (ROUND4_ADDENDUM.md, Rule 2, sha c4773562).
//
// A perturbation effect is computed ONCE per (program, context); the two logical arms
// (`increase` / `decrease`) are exact sign transforms of that single base effect — two
// logical arms, NOT two experimental estimates. Reusable artifacts are therefore keyed on
// the perturbation's DESIRED_CHANGE, never on a pole's high|low direction and never on an
// arm's role (away_from_A / toward_b). See `repository/armKey.ts` for the frozen keys.
//
// A BUNDLE is one physical, content-addressed all-arm artifact per (lane, context) that
// carries EVERY program × desired_change arm for that context, each independently
// addressable by its `arm_key`. The release materializes 300 logical arm slots
// (60 direct + 120 temporal + 120 pathway) with 15 such bundles.
//
// These shapes are strictly ARM-SCOPED. A pair (away_from_A of program A + toward_b of
// program B) is a cheap JOIN of two independent arms, derived on demand at display time —
// so these shapes deliberately carry NO pair fields (no `away_from_A`/`toward_b` columns),
// NO combined/balanced/weighted score, and NO stored `joint_status`/`pareto_tier`.

import type { Provenance } from './common';

/** The perturbation's desired change — the ONLY axis a reusable arm keys on. */
export type DesiredChange = 'increase' | 'decrease';

/**
 * Immutable target identity, retained ONCE per bundle in `base_records` (W5/W11 contract):
 * arm rows join to it by `base_key` (or `target_id`) — NEVER by symbol — so identity is not
 * duplicated per arm. Keyed by base_key in {@link DirectArmBundle.base_records}. This is
 * forward-compatible/optional until the final W5/W11 emitted contract lands.
 */
export interface BaseRecord {
  base_key: string;
  target_id: string;
  target_ensembl: string | null;
  target_symbol: string | null;
}

/**
 * Display disposition of a knockdown response relative to the desired change. A positive
 * desired-direction response reads as `supports_inhibition`; a negative one as `opposed` /
 * `activation_needed` — NEVER inferring pharmacologic reversibility. Null effect → `unavailable`.
 */
export type DesiredDirectionDisposition =
  | 'supports_inhibition'
  | 'opposed'
  | 'activation_needed'
  | 'unavailable';

// ───────────────────────────── Direct arm ─────────────────────────────

/**
 * One normalized Direct arm row: a single target's arm-scoped effect + deterministic rank.
 * `effect` is the one signed projection for THIS arm (not a per-pole pair); `null` means the
 * arm was not evaluated for that target and is never coerced to zero.
 */
export interface DirectArmRow {
  target_ensembl: string;
  target_symbol: string | null;
  /** Immutable base identity key — the row joins to bundle.base_records by this (never symbol). */
  base_key?: string;
  /** Signed arm effect (logFC-space); null when not evaluated. */
  effect: number | null;
  /** Deterministic within-arm rank (1-based); null when not ranked. */
  rank: number | null;
  /** Upstream Marson `ontarget_significant` (eligibility input; never a spot p/q). */
  ontarget_significant: boolean | null;
}

/** A reusable Direct arm, addressed by {@link directArmKey}(program_id, desired_change, condition). */
export interface DirectArm {
  arm_key: string;
  program_id: string;
  desired_change: DesiredChange;
  condition: string;
  rows: DirectArmRow[];
}

/** A physical all-arm Direct bundle for one condition; every arm keyed by its `arm_key`. */
export interface DirectArmBundle {
  provenance: Provenance;
  lane: 'direct';
  condition: string;
  /** Content address of the physical bundle. */
  bundle_sha256: string;
  /** Immutable target identities retained once per bundle (W5/W11); rows join by base_key. */
  base_records?: Record<string, BaseRecord>;
  arms: Record<string, DirectArm>;
}

// ───────────────────────────── Temporal arm ─────────────────────────────

/**
 * One normalized Temporal arm row: an arm-scoped difference-in-differences across an ordered
 * (from → to) condition pair, carrying BOTH endpoints. A target present at only one endpoint
 * has the other endpoint null + its present flag false. Single arm effect — no pair columns.
 */
export interface TemporalArmRow {
  target_ensembl: string;
  target_symbol: string | null;
  /** Immutable base identity key — the row joins to bundle.base_records by this (never symbol). */
  base_key?: string;
  /** DiD on this arm's program projection across the ordered pair; null when not evaluated. */
  did: number | null;
  /** Arm effect at each endpoint; null when that endpoint is absent/not evaluated. */
  effect_from: number | null;
  effect_to: number | null;
  /** Whether the target was present at each endpoint of the pair (union rows). */
  present_from: boolean | null;
  present_to: boolean | null;
}

/** A reusable Temporal arm, addressed by {@link temporalArmKey}(program_id, desired_change, from, to). */
export interface TemporalArm {
  arm_key: string;
  program_id: string;
  desired_change: DesiredChange;
  from: string;
  to: string;
  rows: TemporalArmRow[];
}

/** A physical all-arm Temporal bundle for one ordered (from → to) pair. */
export interface TemporalArmBundle {
  provenance: Provenance;
  lane: 'temporal';
  from: string;
  to: string;
  bundle_sha256: string;
  /** Immutable target identities retained once per bundle (W5/W11); rows join by base_key. */
  base_records?: Record<string, BaseRecord>;
  arms: Record<string, TemporalArm>;
}

// ───────────────────────────── Pathway arm ─────────────────────────────

/**
 * One arm-scoped pathway enrichment. `arm_headline_rankable` + `arm_coverage_disposition`
 * are the server-decided per-arm eligibility that separate headline from descriptive-only
 * results; the UI shows only `rankable` as headline. `enrichment_value` is AS SUPPLIED by
 * the gene-set method (never a spot p/q); null when undefined.
 */
export interface PathwayArmEnrichment {
  /** Server-decided headline eligibility — trusted to split headline vs descriptive. */
  arm_headline_rankable: boolean;
  /** Server-decided coverage disposition (e.g. rankable / descriptive_only_* / undefined). */
  arm_coverage_disposition: string;
  /** Enrichment value as supplied by the gene-set method; null when undefined. */
  enrichment_value: number | null;
  /** Pathway members present in this arm's ranking; null when not evaluated. */
  n_hits_in_ranking: number | null;
  /** Fraction of source members present in the target namespace; null when not evaluated. */
  source_coverage: number | null;
}

/** One converging pathway node under a Pathway arm; enrichment is arm-scoped (no per-role split). */
/**
 * Stage-3 v2 feeds two drug-evidence classes (forward-compat, optional until W11 lands):
 *   observed_perturbation_target — a directly observed perturbation target
 *   pathway_hypothesis           — a separate pathway-membership hypothesis
 * Pathway membership ALONE never supplies desired activation/inhibition: a direction_unresolved
 * node may be shown as a contextual pathway target but must NOT read as compatible or improve
 * ordering. Values come only from the emitted contract — never fabricated in production.
 */
export type OriginType = 'observed_perturbation_target' | 'pathway_hypothesis';
export type DirectionStatus = 'resolved' | 'direction_unresolved';

export interface PathwayArmRecord {
  pathway_id: string;
  name: string;
  /** Target gene-ids converging on this node (membership = targets). */
  contributing_targets: string[];
  druggable: boolean | null;
  enrichment: PathwayArmEnrichment;
  /** Which drug-evidence class this node is (Stage-3 v2); optional until the W11 contract lands. */
  origin_type?: OriginType;
  /** Whether a desired activation/inhibition direction is resolved; unresolved = contextual only. */
  direction_status?: DirectionStatus;
}

/**
 * A reusable Pathway arm, addressed by {@link pathwayArmKey}(program_id, desired_change,
 * condition, source). `convergence_ref` points at the ONE shared transcriptional-convergence
 * artifact for its (condition, source) — computed once, referenced by all 20 enrichment arms,
 * never duplicated per arm.
 */
export interface PathwayArm {
  arm_key: string;
  program_id: string;
  desired_change: DesiredChange;
  condition: string;
  source: string;
  /** {@link convergenceKey}(condition, source) — the shared convergence this arm references. */
  convergence_ref: string;
  records: PathwayArmRecord[];
}

/** A physical all-arm Pathway bundle for one (condition, source), with its shared convergence. */
export interface PathwayArmBundle {
  provenance: Provenance;
  lane: 'pathway';
  condition: string;
  source: string;
  /** {@link convergenceKey}(condition, source) — one convergence artifact per bundle. */
  convergence_ref: string;
  bundle_sha256: string;
  arms: Record<string, PathwayArm>;
}
