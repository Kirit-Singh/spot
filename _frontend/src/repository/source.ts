// The artifact source seam. Everything the shell reads (the Stage-1 selection and
// any matching research Stage-2/3/4 artifacts) comes through this interface, so the
// repository never talks to localStorage or fetch() directly. A `/data/`-pointer
// loader can populate a map source with the same keys without touching components.

/** Versioned localStorage / data keys the shell reads. */
// AUTHORITATIVE live Stage-1 → downstream handoff. The Stage-1 page writes this key; the
// production selection read binds ONLY to it and verifies via the fail-closed v3 adapter.
export const SELECTION_V3_KEY = 'spot.stage01_selection.v3';
// Legacy v1 selection key — retained ONLY for the demo/fixture path and legacy imports; the
// production selection read no longer honours it (a v1 object in the v3 key is rejected).
export const SELECTION_KEY = 'spot.stage01_selection.v1';
export const STAGE2_KEY = 'spot.stage02_gene_lever_set.v1';
export const STAGE3_KEY = 'spot.stage03_drug_candidate_set.v1';
export const STAGE4_KEY = 'spot.stage04_scorecard_set.v1';

export const RESEARCH_KEYS = [SELECTION_KEY, STAGE2_KEY, STAGE3_KEY, STAGE4_KEY] as const;

export interface ArtifactSource {
  read(key: string): string | null;
}

/** Source backed by a plain map (tests, and the `/data/`-pointer prefetch path). */
export function mapSource(map: Record<string, string | null | undefined>): ArtifactSource {
  return { read: (key) => map[key] ?? null };
}

/** Source backed by a Storage (window.localStorage in the browser). */
export function storageSource(storage: Pick<Storage, 'getItem'>): ArtifactSource {
  return {
    read: (key) => {
      try {
        return storage.getItem(key);
      } catch {
        return null;
      }
    },
  };
}

function safeGet(storage: Pick<Storage, 'getItem'> | undefined, key: string): string | null {
  try {
    return storage?.getItem(key) ?? null;
  } catch {
    return null;
  }
}

/**
 * Reconciled Stage-1 v3 read (gate U18). Reads SELECTION_V3_KEY from BOTH sessionStorage and
 * localStorage and applies ONE documented rule, so the header and the repository can never
 * bind DIFFERENT selections (no split-brain):
 *   - both present & BYTE-IDENTICAL → that value
 *   - both present & DIFFERENT      → null  (FAIL CLOSED — bind nothing)
 *   - exactly one present           → that value
 *   - neither present               → null
 * The legacy v1 key is NEVER consulted.
 */
export function readReconciledV3Raw(): string | null {
  if (typeof window === 'undefined') return null;
  const session = safeGet(window.sessionStorage, SELECTION_V3_KEY);
  const local = safeGet(window.localStorage, SELECTION_V3_KEY);
  if (session !== null && local !== null) return session === local ? session : null;
  return session ?? local;
}

/**
 * Browser default. SELECTION_V3_KEY is read through the reconciled both-stores rule
 * ({@link readReconciledV3Raw}) so buildRepository binds the SAME bytes the header does;
 * every other key reads localStorage. An empty source off-browser.
 */
export function browserSource(): ArtifactSource {
  if (typeof window !== 'undefined' && window.localStorage) {
    return {
      read: (key) =>
        key === SELECTION_V3_KEY ? readReconciledV3Raw() : safeGet(window.localStorage, key),
    };
  }
  return mapSource({});
}
