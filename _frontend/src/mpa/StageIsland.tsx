// Generic downstream island page. Default (real-artifacts-only) shows the typed
// awaiting-artifact scaffold + science-evidence surface — never fake data. Behind the
// explicit ?demo=1 gate it renders the populated view under a persistent DEMO chip, with
// the science-evidence surface (synthetic record) as a footer. The Science-firewall
// surface is present on EVERY stage page and never runs Science / holds credentials.

import { PageShell } from './PageShell';
import { AwaitingArtifact } from './AwaitingArtifact';
import { DemoBar } from './DemoBar';
import { ScienceEvidence } from './ScienceEvidence';
import type { ScienceEvidenceRecord } from './ScienceEvidence';
import { isDemoGate } from './pages';
import type { PageKey } from './pages';
import type { ScaffoldRegion } from '../shell/StageScaffold';

export function StageIsland({
  page,
  subtitle,
  purpose,
  regions,
  enqueueTarget,
  renderDemo,
  demoEvidence = null,
}: {
  page: PageKey;
  subtitle: string;
  purpose: string;
  regions: ScaffoldRegion[];
  enqueueTarget: string;
  renderDemo: () => React.ReactNode;
  demoEvidence?: ScienceEvidenceRecord | null;
}) {
  const demo = isDemoGate();
  return (
    <PageShell page={page} subtitle={subtitle}>
      {demo ? (
        <>
          <DemoBar />
          {renderDemo()}
          <div className="flex-none border-t border-line px-5 py-3">
            <ScienceEvidence record={demoEvidence} enqueueTarget={enqueueTarget} />
          </div>
        </>
      ) : (
        <AwaitingArtifact purpose={purpose} regions={regions} evidence={null} enqueueTarget={enqueueTarget} />
      )}
    </PageShell>
  );
}
