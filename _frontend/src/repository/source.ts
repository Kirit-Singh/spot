// The artifact source seam. Everything the shell reads (the Stage-1 selection and
// any matching research Stage-2/3/4 artifacts) comes through this interface, so the
// repository never talks to localStorage or fetch() directly. A `/data/`-pointer
// loader can populate a map source with the same keys without touching components.

/** Versioned localStorage / data keys the shell reads. */
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

/** Browser default: read from localStorage when available, else an empty source. */
export function browserSource(): ArtifactSource {
  if (typeof window !== 'undefined' && window.localStorage) {
    return storageSource(window.localStorage);
  }
  return mapSource({});
}
