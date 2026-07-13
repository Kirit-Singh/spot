// Byte-exact replica of the Stage-1 emitter's canonical JSON + sha256, so the UI can
// INDEPENDENTLY recompute selection_id / full_contract_content_sha256 (never trusting
// the artifact's own hash fields). Mirrors `stage2_bridge/canonical.py`:
//   canonical_json = json.dumps(obj, sort_keys=True, separators=(",",":"),
//                               ensure_ascii=True, allow_nan=False)
// selection contracts contain only strings / enums / ints / bools / null / string-arrays,
// so there is no Python↔JS float-formatting divergence to worry about.

import { sha256 } from '@noble/hashes/sha2.js';
import { bytesToHex } from '@noble/hashes/utils.js';

/** JSON string with ensure_ascii=True: escape every non-ASCII code unit as \uXXXX. */
function ensureAsciiString(s: string): string {
  return JSON.stringify(s).replace(/[-￿]/g, (c) => '\\u' + c.charCodeAt(0).toString(16).padStart(4, '0'));
}

/** Deterministic canonical JSON: sorted keys, no spaces, ASCII-escaped, no NaN/Infinity. */
export function canonicalJson(value: unknown): string {
  if (value === null) return 'null';
  const t = typeof value;
  if (t === 'boolean') return value ? 'true' : 'false';
  if (t === 'number') {
    if (!Number.isFinite(value as number)) throw new Error('canonicalJson: NaN/Infinity not allowed');
    return JSON.stringify(value);
  }
  if (t === 'string') return ensureAsciiString(value as string);
  if (Array.isArray(value)) return '[' + value.map((v) => canonicalJson(v)).join(',') + ']';
  if (t === 'object') {
    const obj = value as Record<string, unknown>;
    const keys = Object.keys(obj).sort();
    return '{' + keys.map((k) => ensureAsciiString(k) + ':' + canonicalJson(obj[k])).join(',') + '}';
  }
  throw new Error('canonicalJson: unserializable value of type ' + t);
}

/**
 * SHA-256 hex of a UTF-8 string. Uses the audited MIT @noble/hashes implementation directly,
 * NOT WebCrypto: crypto.subtle is unavailable in an INSECURE browser context (plain-HTTP,
 * non-localhost origin — exactly how the :8347 distribution is served), which previously made
 * every content-address recompute reject and fall back to "unavailable". noble is deterministic
 * and context-independent, so hash verification is preserved everywhere. The async signature is
 * kept (noble is synchronous) so callers are unchanged.
 */
export async function sha256Hex(text: string): Promise<string> {
  return bytesToHex(sha256(new TextEncoder().encode(text)));
}

/** content_hash: sha256 of the canonical JSON form (Direct hashing.content_hash). */
export function contentHash(value: unknown): Promise<string> {
  return sha256Hex(canonicalJson(value));
}
