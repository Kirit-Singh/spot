import { createRoot } from 'react-dom/client';
import '../index.css';
import { PageShell } from '../mpa/PageShell';
import { NotebookView } from '../mpa/methodsViews';
import { stageFromSearch } from '../mpa/methodsRoutes';
import { resolveStageProvenance } from '../mpa/stageProvenance';
import { buildRepository } from '../repository/repository';
import { browserSource } from '../repository/source';
import { isDemoGate, PAGES } from '../mpa/pages';

// Bound to the content-addressed aggregate via the repository (fixtures only behind ?demo=1,
// never the default deploy). No stage selected → default to Targets.
const stage = stageFromSearch() ?? 'targets';
const repo = buildRepository(browserSource(), { demo: isDemoGate() });
const sp = resolveStageProvenance(repo, stage);
const label = PAGES.find((p) => p.key === stage)?.label ?? stage;

createRoot(document.getElementById('root')!).render(
  <PageShell page={stage} subtitle={`${label} · Methods`} selection={sp.selection} methodsProvenance={sp.provenance}>
    <NotebookView stage={stage} provenance={sp.provenance} selection={sp.selection} />
  </PageShell>,
);
