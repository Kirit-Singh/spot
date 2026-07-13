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
import { readStage1Selection, contrastTitle, clearStage1Selection, NO_SELECTION_TITLE } from './contrastTitle';
import type { Stage1Selection } from './contrastTitle';
import { selectionFixtureRaw } from '../fixtures/selection.fixture';
import { buildRepository } from '../repository/repository';
import { browserSource } from '../repository/source';
import { manifestFromProvenance, unavailableManifest } from '../domain/methodsManifest';
import { demoMethodsManifest } from '../fixtures/methodsManifest.fixture';

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
  // Header title = the carried Stage-1 selection contrast (the nav already shows the stage
  // name). Real selection via the validated storage bridge; demo falls back to the fixture.
  const selection: Stage1Selection | null =
    readStage1Selection() ?? (demo ? (selectionFixtureRaw as Stage1Selection) : null);
  const contrast = contrastTitle(selection);
  const headerTitle = contrast ?? NO_SELECTION_TITLE;
  // no selection → only the word "Programs" is a link (persistent underline) back to Stage 1
  const headerNode = contrast ? undefined : (
    <>
      Select populations in{' '}
      <a
        href="01_page.html"
        className="underline decoration-ink underline-offset-[3px] hover:text-accent hover:decoration-accent"
      >
        Programs
      </a>{' '}
      →
    </>
  );
  // offer Clear only when a selection is bound; clears the bridge and returns to Programs
  const onClearSelection = contrast
    ? () => {
        clearStage1Selection();
        window.location.assign('01_page.html');
      }
    : undefined;
  // Bind the header Methods/Provenance drawer to the content-addressed aggregate for this
  // stage (targets/pathways→S2, drugs→S3, pksafety→S4). Fixtures only behind ?demo=1; in
  // production a not-yet-generated arm yields an all-"unavailable" manifest (never invented).
  const repo = buildRepository(browserSource(), { demo });
  const slot = page === 'drugs' ? repo.getStage3() : page === 'pksafety' ? repo.getStage4() : repo.getStage2();
  const stageProvenance = slot.status === 'loaded' ? slot.artifact.provenance : null;
  const methodsManifest = demo
    ? demoMethodsManifest(subtitle)
    : stageProvenance
      ? manifestFromProvenance(subtitle, stageProvenance)
      : unavailableManifest(subtitle);
  return (
    <PageShell
      page={page}
      subtitle={headerTitle}
      subtitleNode={headerNode}
      onClearSelection={onClearSelection}
      methodsProvenance={stageProvenance}
      methodsManifest={methodsManifest}
    >
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
