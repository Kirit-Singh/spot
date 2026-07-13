// Stage-2 — targets (UI shape of spot.stage02_gene_lever_set.v1).
//
// COMPATIBILITY-ONLY (ROUND4_ADDENDUM.md, sha c4773562): this is the legacy pair-bound
// lever set. The forward release is per-program reusable arms (see repository/armKey.ts +
// domain/stage2RealRun.ts) joined on demand into a pair. Its pair-shaped fields (joint_status,
// pareto_tier) are pair-derived, join-time display concepts here — they are excluded from the
// production all-arm manifest and are never stored in a reusable arm bundle.
//
// Two INDEPENDENT, authoritative objectives — never averaged into one score:
//   away_from_A  — reduction of the A program
//   toward_B     — increase of the B program
// Each arm carries its own nullable rank/effect. On top of the arms, Stage 2 emits
// explicitly-TYPED joint ordering (multi-objective / Pareto) — never a numeric
// combined/balanced score and never a hidden weighting:
//   joint_status  — both_arms / a_only / b_only / opposed / not_evaluated
//   pareto_tier   — dominance tier (1 = non-dominated); null when not evaluated
//   joint_ordering_method_id (artifact-level) — the exact frozen ordering method

import type { Provenance } from './common';
import type { StageSelection } from './selection';

export type Objective = 'away_from_A' | 'toward_B';

/** One arm's measured result for a target. Ranks are null unless evaluated. */
export interface LeverArm {
  objective: Objective;
  evaluated: boolean;
  /** Reason the arm was not evaluated; null when evaluated. */
  reason: string | null;
  /** Target-masked measured projection (signed logFC-space); null when not evaluated. */
  effect: number | null;
  /** Rank within this arm only; MUST be null when `evaluated` is false. */
  rank: number | null;
  /** Retained squared-weight coverage of the axis after target masking; null when not evaluated. */
  coverage: number | null;
}

/**
 * Typed joint status across the two arms (replaces the old cross_class). Describes
 * the relationship, never a merged score:
 *   both_arms — evaluated and same-direction on both objectives
 *   a_only / b_only — supported on exactly one arm
 *   opposed — evaluated on both, but the arms disagree in direction
 *   not_evaluated — neither arm produced a result
 */
export type JointStatus = 'both_arms' | 'a_only' | 'b_only' | 'opposed' | 'not_evaluated';

export const JOINT_STATUSES: readonly JointStatus[] = [
  'both_arms',
  'a_only',
  'b_only',
  'opposed',
  'not_evaluated',
];

/** Direct-vs-Perturb2State stability lane status (secondary; cannot rescue direct evidence). */
export type Perturb2StateStatus =
  | 'direct_only'
  | 'perturb2state_supported'
  | 'perturb2state_discordant'
  | 'not_evaluated';

export interface GuideSupport {
  guide_id: string;
  effect: number | null;
  sign_agrees: boolean | null;
}

export interface DonorSupport {
  effective_n: number;
  denominator: string;
  pair_discordance: boolean | null;
}

export interface DepMapAnnotation {
  status: string;
  detail: string | null;
}

/**
 * Marker-breadth diagnostic: is a target supported by many markers, or driven by a
 * single marker? A typed state, not a numeric verdict.
 */
export interface MarkerBreadth {
  /** Count of markers contributing support for this target. */
  supporting_markers: number;
  /** True when the effect is dominated by one marker (fragile support). */
  single_marker_driven: boolean;
  /** Optional short note (e.g. the dominating marker id). */
  detail: string | null;
}

/** Everything shown in the per-target evidence inspector. */
export interface GeneEvidence {
  guides: GuideSupport[];
  donor_support: DonorSupport;
  on_target_detected: boolean | null;
  perturb2state: Perturb2StateStatus;
  depmap: DepMapAnnotation;
  support_status: string;
  source_links: { label: string; url: string | null; detail: string }[];
}

export interface GeneLever {
  gene_id: string;
  ensembl_id: string | null;
  arms: Record<Objective, LeverArm>;
  /** Typed joint relationship across arms. */
  joint_status: JointStatus;
  /** Pareto dominance tier (1 = non-dominated); null when not evaluated. */
  pareto_tier: number | null;
  /** Marker-breadth / single-marker diagnostic. */
  marker_breadth: MarkerBreadth;
  evidence: GeneEvidence;
}

/** Which arm(s) support a convergent pathway signature. */
export type ArmSupport = 'a' | 'b' | 'both';

export const ARM_SUPPORTS: readonly ArmSupport[] = ['a', 'b', 'both'];

/**
 * A convergent perturbation signature: multiple targets converging on one pathway
 * node. Descriptive enrichment support only — never a causal claim.
 */
export interface PathwayNode {
  pathway_id: string;
  name: string;
  /** Target gene-ids converging on this node. */
  contributing_targets: string[];
  /** Which arm(s) the convergence is supported on. */
  arm_support: ArmSupport;
  /** Reactome-style enrichment value as supplied; null when not evaluated. */
  enrichment: number | null;
  /** True when the node itself is a druggable entity. */
  druggable: boolean;
  method: string;
  source_hash: string;
}

export interface Stage2Artifact {
  provenance: Provenance;
  /** The Stage-1 selection this target set was computed against. */
  selection: StageSelection;
  /** Named eligible family size emitted at run time. */
  tested_family_size: number;
  /** True when a calibrated null was produced; otherwise significance is not_calibrated. */
  significance_calibrated: boolean;
  /** Exact frozen method used to compute the joint/Pareto ordering (provenance). */
  joint_ordering_method_id: string;
  levers: GeneLever[];
  pathways: PathwayNode[];
}
