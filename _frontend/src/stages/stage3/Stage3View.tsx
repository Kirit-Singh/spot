// Stage 3 — direction-compatible drug linkage. Both desired-arm directions stay
// visible; candidates are shown without collapsing mixed/conflicting states.

import type { Stage3Artifact } from '../../domain/stage3';
import type { Objective } from '../../domain/stage2';
import { StatePill } from '../../shell/chips';
import { useProvenance } from '../../shell/provenanceContext';
import { STAGE3_NOTES } from '../../shell/methodNotes';
import { DrugCandidateCard } from './DrugCandidateCard';

const ARM_LABEL: Record<Objective, string> = { away_from_A: 'away from A', toward_B: 'toward B' };

export function Stage3View({ artifact }: { artifact: Stage3Artifact }) {
  const { open } = useProvenance();
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-line bg-surface px-5 py-2.5">
        <span className="font-mono text-[10.5px] uppercase tracking-wide text-muted">
          desired directions
        </span>
        {artifact.desired_arms.map((a) => (
          <StatePill key={a} label={ARM_LABEL[a]} tone="accent" />
        ))}
        <button
          type="button"
          onClick={() => open('Stage 3 — drug candidate set', artifact.provenance, STAGE3_NOTES)}
          className="ml-auto inline-flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-1 text-[11px] font-semibold text-ink-2 hover:border-accent hover:text-accent"
        >
          <span className="flex h-[14px] w-[14px] items-center justify-center rounded-full border border-current text-[8px] font-bold italic">
            i
          </span>
          Provenance
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
        <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
          {artifact.candidates.map((c) => (
            <DrugCandidateCard key={c.candidate_id} candidate={c} />
          ))}
        </div>
      </div>
    </div>
  );
}
