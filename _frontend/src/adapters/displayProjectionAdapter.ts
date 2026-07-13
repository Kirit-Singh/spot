// W3 compact selection-INDEPENDENT DISPLAY projection — the payload the browser consumes instead of the
// full native matrices. It is a VIEW of the authoritative downloadable native artifacts: W3 applies the
// method-versioned per-arm cap/projection policy ONCE (deterministic serialization, no recompute) and
// emits only the capped rows plus a policy + a native-row-equality receipt. The browser renders those
// rows VERBATIM — it applies NO further sort, cap, filter, or pair ranking — after verifying the policy
// and re-deriving the receipt. FAIL-CLOSED on any policy/receipt/count mismatch.

import { canonicalJson, sha256Hex } from '../stage1/canonical';
import { fail } from './errors';
import { arr, isObject, num, str } from './guards';

const HEX64 = /^[0-9a-f]{64}$/;
/** The projection method is versioned; the cap/policy is bound to this version. Pin the exact id with W3. */
export const DISPLAY_PROJECTION_METHOD_PREFIX = 'spot.stage02.display_projection.';

export interface DisplayProjectionCounts {
  n_total: number; // native targets in the arm
  n_evaluable: number; // native evaluable subset
  n_emitted: number; // rows the projection emitted (after the per-arm cap)
}
export interface DisplayProjectionPolicy {
  projection_method_version: string; // method-versioned cap/projection policy
  per_arm_cap: number; // max rows emitted per arm
  projection_policy: string; // e.g. top_n_by_native_rank_no_recompute
  counts: DisplayProjectionCounts;
  source_raw_sha256: string; // authoritative native artifact this is a view of
  source_canonical_sha256: string;
  native_row_equality_receipt: string; // sha256 over the emitted rows' canonical form == the native rows
  artifact_download_refs: string[]; // authoritative downloadable native artifacts (view links)
}

function hex64(v: unknown, path: string): string {
  const s = str(v, path);
  if (!HEX64.test(s)) fail('missing_hash', `${path} must be a 64-hex sha256`);
  return s;
}
function nonNegInt(v: unknown, path: string): number {
  const n = num(v, path);
  if (!Number.isInteger(n) || n < 0) fail('malformed', `${path} must be a non-negative integer`);
  return n;
}
function parseCounts(v: unknown, path: string): DisplayProjectionCounts {
  if (!isObject(v)) fail('malformed', `${path} required`);
  const n_total = nonNegInt(v.n_total, `${path}.n_total`);
  const n_evaluable = nonNegInt(v.n_evaluable, `${path}.n_evaluable`);
  const n_emitted = nonNegInt(v.n_emitted, `${path}.n_emitted`);
  if (!(n_emitted <= n_evaluable && n_evaluable <= n_total)) {
    fail('malformed', `${path} must satisfy n_emitted <= n_evaluable <= n_total (${n_emitted}/${n_evaluable}/${n_total})`);
  }
  return { n_total, n_evaluable, n_emitted };
}

/**
 * Verify a compact display-projection policy against the exact rows the browser will render, FAIL-CLOSED.
 * Enforces: method-versioned policy id; per_arm_cap; monotonic counts (emitted <= evaluable <= total);
 * emitted <= cap; emitted count == rendered rows; and the native-row-equality RECEIPT (the rows the
 * browser will show must hash to the declared receipt, proving they are byte-equal to the native rows —
 * so the browser is a faithful VIEW, never a re-derivation). Throws AdapterError on any mismatch.
 */
export async function verifyDisplayProjection(raw: unknown, emittedRows: unknown[]): Promise<DisplayProjectionPolicy> {
  if (!isObject(raw)) fail('malformed', 'display projection policy must be an object');

  const projection_method_version = str(raw.projection_method_version, 'projection_method_version');
  if (!projection_method_version.startsWith(DISPLAY_PROJECTION_METHOD_PREFIX)) {
    fail('unknown_schema_version', `projection_method_version must start with ${DISPLAY_PROJECTION_METHOD_PREFIX}`);
  }
  const per_arm_cap = nonNegInt(raw.per_arm_cap, 'per_arm_cap');
  const projection_policy = str(raw.projection_policy, 'projection_policy');
  if (projection_policy.trim() === '') fail('malformed', 'projection_policy is required');
  const counts = parseCounts(raw.counts, 'counts');
  if (counts.n_emitted > per_arm_cap) fail('malformed', `n_emitted ${counts.n_emitted} exceeds per_arm_cap ${per_arm_cap}`);

  const source_raw_sha256 = hex64(raw.source_raw_sha256, 'source_raw_sha256');
  const source_canonical_sha256 = hex64(raw.source_canonical_sha256, 'source_canonical_sha256');
  const native_row_equality_receipt = hex64(raw.native_row_equality_receipt, 'native_row_equality_receipt');
  const artifact_download_refs = arr(raw.artifact_download_refs, 'artifact_download_refs').map((x, i) => str(x, `artifact_download_refs[${i}]`));
  if (artifact_download_refs.length === 0) fail('malformed', 'artifact_download_refs must name the authoritative downloadable native artifact(s)');

  // the browser must render EXACTLY the emitted rows — not more (uncapped) nor fewer.
  if (counts.n_emitted !== emittedRows.length) {
    fail('malformed', `n_emitted ${counts.n_emitted} != rendered rows ${emittedRows.length} (no browser cap/expand)`);
  }
  // native-row equality receipt — the rows the browser will show hash to the receipt (byte-equal to native).
  const got = await sha256Hex(canonicalJson(emittedRows));
  if (got !== native_row_equality_receipt) {
    fail('content_hash_mismatch', `native-row equality receipt mismatch (${got} != ${native_row_equality_receipt})`);
  }

  return {
    projection_method_version, per_arm_cap, projection_policy, counts,
    source_raw_sha256, source_canonical_sha256, native_row_equality_receipt, artifact_download_refs,
  };
}
