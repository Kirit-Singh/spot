// Stage-1 → Stage-2 selection contract (UI-facing shape of spot.stage01_selection.v1).
//
// The ordered A→B program contrast a human chose in Stage 1. The local demo
// bridge can produce a valid selection-shaped object, but it is explicitly
// marked as NOT having passed the live production Stage-1 gate.

import type { Namespace } from './common';

/** Direction convention on a program axis. */
export type ProgramDirection = 'high' | 'low';

/** One pole of the ordered contrast. */
export interface ProgramPole {
  program_id: string;
  score_field: string;
  display_label: string;
  direction: ProgramDirection;
}

/**
 * Optional deterministic provenance the v3 Stage-1 bridge may add. Every field is
 * nullable — fixture and older selections omit them. These are validated and
 * preserved when present, and surfaced ONLY in Methods & provenance (never the bar).
 */
export interface Stage1Bindings {
  stage1_method_version: string | null;
  program_registry_raw_sha256: string | null;
  program_registry_sha256: string | null;
  validation_raw_sha256: string | null;
  v3_overlay_raw_sha256: string | null;
  v3_summary_raw_sha256: string | null;
  source_h5ad_sha256: string | null;
}

export interface StageSelection {
  schema_version: string;
  namespace: Namespace;
  /** True only when the live production Stage-1 gate produced this selection. */
  production_gate_passed: boolean;
  /** Where the selection came from, e.g. "local_demo_bridge" or "stage01_gate". */
  source: string;
  /** Stable question / selection identifiers preserved from Stage 1. */
  question_id: string;
  selection_id: string;
  /** Content-addressed contrast id (reproduces the Stage-1 contract). */
  contrast_id: string;
  program_a: ProgramPole;
  program_b: ProgramPole;
  /** Single executable analysis condition (one timepoint). */
  analysis_condition: string;
  /** Fixed dataset scope carried for provenance. */
  dataset_id: string;
  donor_scope: string;
  /** Human-facing artifact status, e.g. "fixture · production_eligible=false". */
  artifact_status: string;
  /** Optional v3 Stage-1 bridge bindings; null when the bridge omitted all of them. */
  stage1_bindings: Stage1Bindings | null;
}
