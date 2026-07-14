// Shared test helper: render a stage view inside a ProvenanceProvider whose
// opener is captured, so tests can assert that provenance was requested.

import { render } from '@testing-library/react';
import { vi } from 'vitest';
import type { ReactElement } from 'react';
import type { Provenance } from '../domain/common';
import type { ArtifactSlot } from '../repository/repository';
import { ProvenanceProvider } from '../shell/provenanceContext';

export function renderWithProvenance(ui: ReactElement) {
  const open = vi.fn<(title: string, provenance: Provenance | null) => void>();
  const result = render(<ProvenanceProvider value={{ open }}>{ui}</ProvenanceProvider>);
  return { ...result, open };
}

/** Unwrap a loaded artifact slot in tests, failing loudly on any other status. */
export function loadedArtifact<T>(slot: ArtifactSlot<T>): T {
  if (slot.status !== 'loaded') throw new Error(`expected a loaded slot, got ${slot.status}`);
  return slot.artifact;
}
