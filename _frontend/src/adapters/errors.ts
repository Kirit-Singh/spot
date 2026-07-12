// Validation error type for the artifact adapters. A rejected artifact throws
// this with a machine-stable `code` so tests and the UI can react precisely.

export type AdapterErrorCode =
  | 'unknown_schema_version'
  | 'namespace_mismatch'
  | 'illegal_production_claim'
  | 'invalid_artifact_id'
  | 'missing_hash'
  | 'cross_namespace_pointer'
  | 'stale_combined_field'
  | 'illegal_rank_on_ineligible_arm'
  | 'malformed';

export class AdapterError extends Error {
  readonly code: AdapterErrorCode;
  constructor(code: AdapterErrorCode, message: string) {
    super(message);
    this.name = 'AdapterError';
    this.code = code;
  }
}

export function fail(code: AdapterErrorCode, message: string): never {
  throw new AdapterError(code, message);
}
