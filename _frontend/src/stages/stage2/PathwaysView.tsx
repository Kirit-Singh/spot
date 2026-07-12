// Pathways island — the convergent perturbation signatures as a full page (the same
// PathwayPanel used in the Targets rail, given the whole canvas here).

import type { Stage2Artifact } from '../../domain/stage2';
import { useProvenance } from '../../shell/provenanceContext';
import { STAGE2_NOTES } from '../../shell/methodNotes';
import { PathwayPanel } from './PathwayPanel';

export function PathwaysView({ artifact }: { artifact: Stage2Artifact }) {
  const { open } = useProvenance();
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-line bg-surface px-5 py-2.5">
        <span className="font-mono text-[10.5px] uppercase tracking-wide text-muted">
          convergent perturbation signatures
        </span>
        <button
          type="button"
          onClick={() => open('Pathways — convergent signatures', artifact.provenance, STAGE2_NOTES)}
          className="ml-auto inline-flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-1 text-[11px] font-semibold text-ink-2 hover:border-accent hover:text-accent"
        >
          <span className="flex h-[14px] w-[14px] items-center justify-center rounded-full border border-current text-[8px] font-bold italic">
            i
          </span>
          Provenance
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
        <PathwayPanel pathways={artifact.pathways} />
      </div>
    </div>
  );
}
