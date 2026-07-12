// Generic downstream island page. Default (real-artifacts-only) shows the typed
// awaiting-artifact scaffold + science-evidence surface — never fake data. Behind the
// explicit ?demo=1 gate it renders the populated view under a persistent DEMO chip.

import { PageShell } from './PageShell';
import { AwaitingArtifact } from './AwaitingArtifact';
import { DemoBar } from './DemoBar';
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
}: {
  page: PageKey;
  subtitle: string;
  purpose: string;
  regions: ScaffoldRegion[];
  enqueueTarget: string;
  renderDemo: () => React.ReactNode;
}) {
  const demo = isDemoGate();
  return (
    <PageShell page={page} subtitle={subtitle}>
      {demo ? (
        <>
          <DemoBar />
          {renderDemo()}
        </>
      ) : (
        <AwaitingArtifact purpose={purpose} regions={regions} evidence={null} enqueueTarget={enqueueTarget} />
      )}
    </PageShell>
  );
}
