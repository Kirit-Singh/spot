// Shared domain primitives for the spot cross-stage artifact contracts.
//
// These are the *validated* runtime shapes the UI consumes. Raw JSON is turned
// into these by the stage adapters, which enforce the fixture firewall. See
// `adapters/`. The three namespaces are strictly separated in code and are
// never a permissive union that can be relabelled by editing a field.

/** The three domain-separated namespaces. Bound in code, never inferred loosely. */
export type Namespace = 'production' | 'research_only' | 'fixture';

export const NAMESPACES: readonly Namespace[] = ['production', 'research_only', 'fixture'];

/** Which stage an artifact belongs to (used in artifact-id prefix validation). */
export type StageKey = 'stage01' | 'stage02' | 'stage03' | 'stage04';

/**
 * Provenance carried by every artifact and surfaced in the Methods & provenance
 * drawer. Claude Science output itself is never evidence — `cs_session` is a
 * pointer for auditability, not a source.
 */
export interface Provenance {
  artifact_id: string;
  schema_version: string;
  namespace: Namespace;
  production_eligible: boolean;
  hashes: ArtifactHashes;
  method: MethodRef;
  sources: PublicSource[];
  /** Claude Science session / frame reference when supplied (auditability, not evidence). */
  cs_session: CsSessionRef | null;
  /** Referential-integrity pointer to the exact upstream-stage artifact, when applicable. */
  upstream_ref: UpstreamRef | null;
}

export interface ArtifactHashes {
  /** Hash of the raw bytes as received. */
  raw_sha256: string;
  /** Hash over canonicalized scientific content (stable ordering, excludes timestamps/labels/paths). */
  canonical_sha256: string;
}

export interface MethodRef {
  method_id: string;
  config_id: string;
  code_ref: string;
  env_ref: string;
}

export interface PublicSource {
  /** Human label, e.g. "ChEMBL", "DepMap", "Reactome". */
  label: string;
  /** Stable record identifier within the source. */
  record_id: string;
  /** Public URL when one exists; null otherwise (never fabricated). */
  url: string | null;
  /** Verbatim record note / accession detail. */
  detail: string;
}

export interface CsSessionRef {
  session_ref: string;
  frame_ref: string;
}

export interface UpstreamRef {
  artifact_id: string;
  canonical_sha256: string;
}

/**
 * How a reported value was obtained. `missing` is never silently coerced to
 * zero or estimated; `not_evaluated` means the pipeline did not run that check.
 */
export type MeasurementState =
  | 'measured'
  | 'calculated'
  | 'label_derived'
  | 'not_evaluated'
  | 'missing';

export const MEASUREMENT_STATES: readonly MeasurementState[] = [
  'measured',
  'calculated',
  'label_derived',
  'not_evaluated',
  'missing',
];

/**
 * A single reported field with its measurement provenance. A `null` value with
 * state `missing`/`not_evaluated` is displayed as such — never as 0.
 */
export interface Field<T> {
  value: T | null;
  state: MeasurementState;
  unit: string | null;
  source: PublicSource | null;
}

/** Human-facing label for a measurement state. */
export function measurementLabel(state: MeasurementState): string {
  switch (state) {
    case 'measured':
      return 'Measured';
    case 'calculated':
      return 'Calculated';
    case 'label_derived':
      return 'Label-derived';
    case 'not_evaluated':
      return 'Not evaluated';
    case 'missing':
      return 'Missing';
  }
}

/** Short status label for a namespace chip. */
export function namespaceLabel(ns: Namespace): string {
  switch (ns) {
    case 'production':
      return 'production';
    case 'research_only':
      return 'research-only';
    case 'fixture':
      return 'fixture';
  }
}
