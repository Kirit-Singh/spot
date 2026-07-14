// Shared runtime guards + firewall checks used by every stage adapter.
//
// The firewall is intentionally structural: an artifact cannot be relabelled
// into another namespace by editing a single field, because (a) the caller binds
// the EXPECTED namespace in code, (b) the artifact-id encodes its namespace and
// must agree, and (c) upstream pointers must stay within the same namespace.

import type {
  ArtifactHashes,
  MeasurementState,
  MethodRef,
  Namespace,
  Provenance,
  PublicSource,
  StageKey,
  UpstreamRef,
} from '../domain/common';
import { MEASUREMENT_STATES, NAMESPACES } from '../domain/common';
import { fail } from './errors';

export function isObject(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

export function str(v: unknown, path: string): string {
  if (typeof v !== 'string') fail('malformed', `${path} must be a string`);
  return v;
}

export function optStr(v: unknown, path: string): string | null {
  if (v === null || v === undefined) return null;
  return str(v, path);
}

/** Optional lowercase-hex digest (8–64 hex) — validated in shape when present. */
export function optHex(v: unknown, path: string): string | null {
  if (v === null || v === undefined) return null;
  const s = str(v, path);
  if (!HEX_SHORT.test(s)) fail('malformed', `${path} must be a lowercase hex digest`);
  return s;
}

export function num(v: unknown, path: string): number {
  if (typeof v !== 'number' || Number.isNaN(v)) fail('malformed', `${path} must be a number`);
  return v;
}

export function optNum(v: unknown, path: string): number | null {
  if (v === null || v === undefined) return null;
  return num(v, path);
}

export function bool(v: unknown, path: string): boolean {
  if (typeof v !== 'boolean') fail('malformed', `${path} must be a boolean`);
  return v;
}

export function optBool(v: unknown, path: string): boolean | null {
  if (v === null || v === undefined) return null;
  return bool(v, path);
}

export function arr(v: unknown, path: string): unknown[] {
  if (!Array.isArray(v)) fail('malformed', `${path} must be an array`);
  return v;
}

export function enumOf<T extends string>(
  v: unknown,
  allowed: readonly T[],
  path: string,
): T {
  const s = str(v, path);
  if (!(allowed as readonly string[]).includes(s)) {
    fail('malformed', `${path} must be one of ${allowed.join(', ')}`);
  }
  return s as T;
}

const HEX64 = /^[0-9a-f]{64}$/;
const HEX_SHORT = /^[0-9a-f]{8,64}$/;
const ARTIFACT_ID = /^(production|research_only|fixture):(stage0[1234]):[a-z0-9_]+@[0-9a-f]{8,64}$/;

/** No stale combined/balanced ranking may leak through the firewall. */
const FORBIDDEN_COMBINED_KEYS = [
  'combined_score',
  'balanced_score',
  'balanced_a_to_b',
  'rank_combined',
  'rank_balanced',
  'best_of',
];

export function assertNoCombinedFields(v: unknown, path: string): void {
  if (Array.isArray(v)) {
    v.forEach((item, i) => assertNoCombinedFields(item, `${path}[${i}]`));
    return;
  }
  if (isObject(v)) {
    for (const key of Object.keys(v)) {
      if (FORBIDDEN_COMBINED_KEYS.includes(key)) {
        fail('stale_combined_field', `${path}.${key} is a forbidden combined/balanced field`);
      }
      assertNoCombinedFields(v[key], `${path}.${key}`);
    }
  }
}

export function namespaceOf(v: unknown, path: string): Namespace {
  return enumOf<Namespace>(v, NAMESPACES, path);
}

export function measurementState(v: unknown, path: string): MeasurementState {
  return enumOf<MeasurementState>(v, MEASUREMENT_STATES, path);
}

function hashes(v: unknown, path: string): ArtifactHashes {
  if (!isObject(v)) fail('missing_hash', `${path} hashes object is required`);
  const raw = v.raw_sha256;
  const canon = v.canonical_sha256;
  if (typeof raw !== 'string' || !HEX64.test(raw)) {
    fail('missing_hash', `${path}.raw_sha256 must be a 64-hex sha256`);
  }
  if (typeof canon !== 'string' || !HEX64.test(canon)) {
    fail('missing_hash', `${path}.canonical_sha256 must be a 64-hex sha256`);
  }
  return { raw_sha256: raw, canonical_sha256: canon };
}

function methodRef(v: unknown, path: string): MethodRef {
  if (!isObject(v)) fail('malformed', `${path} method object is required`);
  return {
    method_id: str(v.method_id, `${path}.method_id`),
    config_id: str(v.config_id, `${path}.config_id`),
    code_ref: str(v.code_ref, `${path}.code_ref`),
    env_ref: str(v.env_ref, `${path}.env_ref`),
  };
}

function publicSource(v: unknown, path: string): PublicSource {
  if (!isObject(v)) fail('malformed', `${path} source object is required`);
  return {
    label: str(v.label, `${path}.label`),
    record_id: str(v.record_id, `${path}.record_id`),
    url: optStr(v.url, `${path}.url`),
    detail: str(v.detail, `${path}.detail`),
  };
}

export function publicSources(v: unknown, path: string): PublicSource[] {
  return arr(v, path).map((s, i) => publicSource(s, `${path}[${i}]`));
}

function upstreamRef(v: unknown, path: string, ns: Namespace): UpstreamRef | null {
  if (v === null || v === undefined) return null;
  if (!isObject(v)) fail('malformed', `${path} must be an object or null`);
  const artifact_id = str(v.artifact_id, `${path}.artifact_id`);
  // A pointer may never cross namespaces (no fixture → production pointer).
  const ptrNs = artifact_id.split(':')[0];
  if (ptrNs !== ns) {
    fail(
      'cross_namespace_pointer',
      `${path}.artifact_id namespace "${ptrNs}" may not differ from artifact namespace "${ns}"`,
    );
  }
  const canonical = v.canonical_sha256;
  if (typeof canonical !== 'string' || !HEX64.test(canonical)) {
    fail('missing_hash', `${path}.canonical_sha256 must be a 64-hex sha256`);
  }
  return { artifact_id, canonical_sha256: canonical };
}

/**
 * Validate a provenance block and enforce the namespace firewall.
 *
 * @param expected  namespace bound in code by the repository (the source of truth)
 * @param stage     which stage the artifact-id must declare
 * @param known     accepted schema versions; anything else is rejected
 */
export function provenance(
  v: unknown,
  path: string,
  expected: Namespace,
  stage: StageKey,
  known: readonly string[],
): Provenance {
  if (!isObject(v)) fail('malformed', `${path} provenance object is required`);

  const schema_version = str(v.schema_version, `${path}.schema_version`);
  if (!known.includes(schema_version)) {
    fail('unknown_schema_version', `${path}.schema_version "${schema_version}" is not accepted`);
  }

  const declared = namespaceOf(v.namespace, `${path}.namespace`);
  if (declared !== expected) {
    fail(
      'namespace_mismatch',
      `${path}.namespace "${declared}" does not match code-bound namespace "${expected}"`,
    );
  }

  const production_eligible = bool(v.production_eligible, `${path}.production_eligible`);
  if (production_eligible && declared !== 'production') {
    fail(
      'illegal_production_claim',
      `${path} is ${declared} but claims production_eligible=true`,
    );
  }

  const artifact_id = str(v.artifact_id, `${path}.artifact_id`);
  if (!ARTIFACT_ID.test(artifact_id)) {
    fail('invalid_artifact_id', `${path}.artifact_id "${artifact_id}" has an invalid prefix/shape`);
  }
  const [idNs, idStage] = artifact_id.split(/[:@]/);
  if (idNs !== declared) {
    fail('namespace_mismatch', `${path}.artifact_id namespace segment must equal namespace`);
  }
  if (idStage !== stage) {
    fail('invalid_artifact_id', `${path}.artifact_id stage segment must be ${stage}`);
  }

  let cs_session: Provenance['cs_session'] = null;
  if (v.cs_session !== null && v.cs_session !== undefined) {
    if (!isObject(v.cs_session)) fail('malformed', `${path}.cs_session must be an object or null`);
    cs_session = {
      session_ref: str(v.cs_session.session_ref, `${path}.cs_session.session_ref`),
      frame_ref: str(v.cs_session.frame_ref, `${path}.cs_session.frame_ref`),
    };
  }

  return {
    artifact_id,
    schema_version,
    namespace: declared,
    production_eligible,
    hashes: hashes(v.hashes, `${path}.hashes`),
    method: methodRef(v.method, `${path}.method`),
    sources: publicSources(v.sources, `${path}.sources`),
    cs_session,
    upstream_ref: upstreamRef(v.upstream_ref, `${path}.upstream_ref`, declared),
  };
}

export { HEX_SHORT, ARTIFACT_ID };
