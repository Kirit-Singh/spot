// Shared provenance-drawer plumbing. Any view can open the single drawer with a
// title + provenance block + the method/limitation notes that belong there (not on
// the main canvas), so provenance is one keystroke away everywhere.

import { createContext, useContext } from 'react';
import type { Provenance } from '../domain/common';
import type { StageMethodsManifest } from '../domain/methodsManifest';

/** A relocated method note / limitation: kept in the drawer, never on the canvas. */
export interface ProvNote {
  title: string;
  body: string;
}

export type DrawerSection = 'methods' | 'provenance';

export interface ProvenanceOpener {
  open: (
    title: string,
    provenance: Provenance | null,
    notes?: ProvNote[],
    methods?: StageMethodsManifest | null,
    section?: DrawerSection,
  ) => void;
}

const ProvenanceContext = createContext<ProvenanceOpener | null>(null);

export const ProvenanceProvider = ProvenanceContext.Provider;

export function useProvenance(): ProvenanceOpener {
  const ctx = useContext(ProvenanceContext);
  if (!ctx) throw new Error('useProvenance must be used within a ProvenanceProvider');
  return ctx;
}
