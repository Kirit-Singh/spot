// Default (real-artifacts-only) body for a downstream page when no verified artifact is
// bound: the selection thread (if any), the honest output-shape scaffold, and the
// science-evidence surface. Never fake data — the real Stage 2/3/4 artifacts do not
// exist yet, so this is the truthful state, not a placeholder for demo output.

import { StatePill } from '../shell/chips';
import { StageScaffold } from '../shell/StageScaffold';
import type { ScaffoldRegion } from '../shell/StageScaffold';
import { ScienceEvidence } from './ScienceEvidence';
import type { ScienceEvidenceRecord } from './ScienceEvidence';
import { readSelectionThread } from './selectionUrl';

export function AwaitingArtifact({
  purpose,
  regions,
  evidence,
  enqueueTarget,
}: {
  purpose: string;
  regions: ScaffoldRegion[];
  evidence: ScienceEvidenceRecord | null;
  enqueueTarget: string;
}) {
  const thread = readSelectionThread();
  const banner = thread.selection_id ? (
    <section
      aria-label="Selection thread"
      className="flex flex-wrap items-center gap-x-3 gap-y-1.5 border-b border-line bg-sunken/60 px-5 py-2"
    >
      <StatePill label="selection" tone="muted" />
      <span className="font-mono text-[10.5px] text-ink-2">
        <span className="text-muted">selection_id</span> {thread.selection_id}
      </span>
    </section>
  ) : (
    <section
      aria-label="No selection"
      className="flex flex-wrap items-center gap-x-3 gap-y-1.5 border-b border-line bg-sunken/60 px-5 py-2"
    >
      <StatePill label="no selection" tone="muted" />
      <span className="font-mono text-[10.5px] text-ink-2">select programs in Stage 1</span>
      <a href="programs.html" className="ml-auto font-mono text-[10.5px] text-accent hover:underline">
        ← Programs
      </a>
    </section>
  );

  return (
    <StageScaffold
      purpose={purpose}
      regions={regions}
      banner={banner}
      footer={<ScienceEvidence record={evidence} enqueueTarget={enqueueTarget} />}
    />
  );
}
