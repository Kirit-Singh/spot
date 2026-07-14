// Frozen Science evidence-record shape + a display-only mapping from artifact provenance.
// Kept out of the component file so ScienceEvidence.tsx exports only a component.

import type { Provenance } from '../domain/common';

export interface ScienceEvidenceRecord {
  science_evidence_id: string;
  sha256: string;
  record_type: string;
}

/** Derive the frozen evidence-record view from an artifact's provenance (display only). */
export function evidenceFromProvenance(prov: Provenance): ScienceEvidenceRecord {
  return {
    science_evidence_id: prov.artifact_id,
    sha256: prov.hashes.canonical_sha256,
    record_type: `${prov.namespace} · ${prov.schema_version}`,
  };
}
