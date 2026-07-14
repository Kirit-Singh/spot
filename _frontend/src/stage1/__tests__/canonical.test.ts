// sha256Hex must be a correct, deterministic SHA-256 that works in an INSECURE browser context
// (plain-HTTP, non-localhost — how the :8347 distribution is served), where WebCrypto's crypto.subtle
// is unavailable. It is backed by the audited MIT @noble/hashes, NOT crypto.subtle. These tests pin:
//   · official FIPS-180 / NIST SHA-256 vectors,
//   · behaviour with crypto.subtle absent (the deployed-context regression), and
//   · byte-for-byte parity with Python's hashlib.sha256 (the emitter's hashing), including a
//     non-ASCII input and a canonical-JSON string — values PRECOMPUTED with python3 hashlib.

import { describe, expect, it } from 'vitest';
import { sha256Hex, canonicalJson } from '../canonical';

// Official SHA-256 test vectors (identical to python hashlib.sha256(x).hexdigest()).
const VECTORS: [string, string][] = [
  ['', 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'],
  ['abc', 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'],
  [
    'The quick brown fox jumps over the lazy dog',
    'd7a8fbb307d7809469ca9abcb0082e4f8d5651e46d3cdb762d02d0bf37c9e592',
  ],
];

describe('sha256Hex — official SHA-256 vectors', () => {
  for (const [input, expected] of VECTORS) {
    it(`sha256("${input.slice(0, 24)}${input.length > 24 ? '…' : ''}")`, async () => {
      expect(await sha256Hex(input)).toBe(expected);
    });
  }
});

describe('sha256Hex — Python hashlib parity (precomputed with python3)', () => {
  // hashlib.sha256(s.encode('utf-8')).hexdigest() for each s.
  const PY: [string, string][] = [
    ['spot·stage01', '388feec319ca60f1ef08aa518c83a4f686d0a45f82d44d4a94a64a4637389925'], // non-ASCII middot
    ['{"a":[1,2,3],"m":null,"z":"\\u00e9"}', 'fe2149017d734327a457cfec61f81b072903a46cab14609bd85e87944983918c'],
  ];
  for (const [s, expected] of PY) {
    it(`matches python hashlib for ${JSON.stringify(s.slice(0, 24))}`, async () => {
      expect(await sha256Hex(s)).toBe(expected);
    });
  }
  it('canonicalJson output hashes identically to python (ensure_ascii escaping)', async () => {
    // canonicalJson sorts keys + escapes non-ASCII → the exact bytes python hashed above.
    const canon = canonicalJson({ z: 'é', a: [1, 2, 3], m: null });
    expect(canon).toBe('{"a":[1,2,3],"m":null,"z":"\\u00e9"}');
    expect(await sha256Hex(canon)).toBe('fe2149017d734327a457cfec61f81b072903a46cab14609bd85e87944983918c');
  });
});

describe('sha256Hex — works with crypto.subtle ABSENT (insecure-context regression)', () => {
  it('computes the correct digest even when globalThis.crypto is removed', async () => {
    const saved = globalThis.crypto;
    try {
      // Simulate a plain-HTTP, non-localhost browser: no WebCrypto at all.
      // @ts-expect-error — deliberately removing the global for the test
      delete globalThis.crypto;
      expect(typeof (globalThis as { crypto?: unknown }).crypto).toBe('undefined');
      expect(await sha256Hex('abc')).toBe('ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad');
      expect(await sha256Hex(canonicalJson({ b: 2, a: 1 }))).toMatch(/^[0-9a-f]{64}$/);
    } finally {
      globalThis.crypto = saved;
    }
  });

  it('computes the correct digest when crypto exists but crypto.subtle is undefined', async () => {
    const saved = globalThis.crypto;
    try {
      Object.defineProperty(globalThis, 'crypto', { value: {}, configurable: true });
      expect((globalThis.crypto as { subtle?: unknown }).subtle).toBeUndefined();
      expect(await sha256Hex('')).toBe('e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855');
    } finally {
      Object.defineProperty(globalThis, 'crypto', { value: saved, configurable: true });
    }
  });
});
