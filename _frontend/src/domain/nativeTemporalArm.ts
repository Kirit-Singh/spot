// NATIVE W5 reusable-temporal-arm contract — aligned to the exact shipped producer shape
// (spot.stage02_temporal_arm_bundle.v1; W5 @ cc82599 / native audit
// TEMPORAL_STAGE2_STAGE3_CONTRACT_CROSSCHECK.md). This SUPERSEDES the earlier memo-based
// TemporalArm* shapes in ./reusableArm.ts for temporal.
//
// Native facts encoded here (not the prior memo):
//   · files: arm_bundle.json / temporal_provenance.json / temporal_verification.json / rankings/*.json
//   · identity lives ONCE in `base_records`, keyed by base_key = "<program_id>|<target_id>" —
//     rows join by base_key (never by symbol); base_key repeats across bundles, so it is scoped
//     by the bundle, not globally unique.
//   · arm records carry `arm_value` (population DiD; not "did"/"value"), `temporal_status`, a
//     native `desired_target_modulation`, and a RETAINED `rank: null` for unrankable rows.
//   · each arm references its ranking file by {path, raw_sha256, canonical_sha256}.
//   · verification_ref is the independent verifier id; external W11 admission is PENDING.

import type { Provenance } from './common';
import type { DesiredChange } from './reusableArm';

/** Native W5 desired-target modulation vocabulary (Stage-3 translates this, verbatim never assumed). */
export type TemporalModulation =
  | 'not_evaluable'
  | 'supports_target_inhibition'
  | 'opposed_would_require_target_activation'
  | 'no_directional_response';

export const TEMPORAL_MODULATIONS: readonly TemporalModulation[] = [
  'not_evaluable',
  'supports_target_inhibition',
  'opposed_would_require_target_activation',
  'no_directional_response',
];

/** Independent-verifier identity W5 references; external admission (W11) is pending. */
export const TEMPORAL_INDEPENDENT_VERIFIER_ID = 'spot.stage02.temporal.arm.independent_verifier.v1';

/** One native arm record — joins to a base record by base_key; rank is retained (null when unrankable). */
export interface NativeTemporalArmRecord {
  target_id: string;
  base_key: string;
  /** Population program-projection DiD (native `arm_value`); null when not evaluable. */
  arm_value: number | null;
  evaluable: boolean;
  temporal_status: string;
  desired_target_modulation: TemporalModulation;
  /** RETAINED even when null (unrankable rows are kept, not omitted). */
  rank: number | null;
}

/** Immutable target identity retained once per bundle, keyed by base_key = "<program_id>|<target_id>". */
export interface NativeTemporalBaseRecord {
  base_key: string;
  program_id: string;
  target_id: string;
  target_symbol: string | null;
  target_ensembl: string | null;
  target_id_namespace: string | null;
  perturbation_modality: string | null;
  from_condition: string;
  to_condition: string;
  temporal_status: string | null;
  evaluable: boolean | null;
  base_delta: number | null;
}

/** A per-arm ranking file reference (byte-pinned). */
export interface NativeTemporalRankingRef {
  path: string;
  raw_sha256: string;
  canonical_sha256: string;
}

/** A native reusable temporal arm, keyed by temporalArmKey(program_id, desired_change, from, to). */
export interface NativeTemporalArm {
  arm_key: string;
  program_id: string;
  desired_change: DesiredChange;
  from_condition: string;
  to_condition: string;
  n_targets: number;
  n_evaluable: number;
  n_ranked: number;
  records: NativeTemporalArmRecord[];
  ranking: NativeTemporalRankingRef;
}

/** A native all-arm temporal bundle for one ordered (from → to) pair. */
export interface NativeTemporalArmBundle {
  schema_version: 'spot.stage02_temporal_arm_bundle.v1';
  lane: 'temporal';
  analysis_mode: 'temporal_cross_condition';
  from_condition: string;
  to_condition: string;
  bundle_id: string;
  /** identity by base_key = "<program_id>|<target_id>" (rows join here, never by symbol). */
  base_records: Record<string, NativeTemporalBaseRecord>;
  arms: Record<string, NativeTemporalArm>;
  /** independent verifier id W5 references; external W11 admission is pending (see adapter). */
  verification_ref: string;
  provenance: Provenance;
}
