// The spot shell for stages 2–4. Functional stage navigation, a single shared
// Methods & provenance drawer, and a repository that ingests the Stage-1 selection
// from localStorage — deciding empty / demo / research_only / rejected in code.
//
// Default (no selection, no demo) shows an honest workflow scaffold — output shape
// only, never fake data. Synthetic example data renders solely behind ?demo=1. A
// research selection with no artifact shows a compact "analysis not generated" state.

import { useMemo, useState } from 'react';
import type { ReactElement } from 'react';
import type { Provenance } from './domain/common';
import type { StageSelection } from './domain/selection';
import { buildRepository } from './repository/repository';
import type { ArtifactSlot, SpotRepository } from './repository/repository';
import { browserSource, SELECTION_V3_KEY, STAGE2_KEY, STAGE3_KEY, STAGE4_KEY } from './repository/source';
import { TopBar } from './shell/TopBar';
import { StageNav } from './shell/StageNav';
import { ProvenanceDrawer } from './shell/ProvenanceDrawer';
import { ProvenanceProvider } from './shell/provenanceContext';
import type { ProvNote } from './shell/provenanceContext';
import { SelectionContextBar } from './shell/SelectionContextBar';
import { AnalysisNotGenerated, ArtifactRejected, SelectionRejected } from './shell/StageState';
import { StageScaffold } from './shell/StageScaffold';
import { STAGE_SCAFFOLDS } from './shell/scaffolds';
import { StatePill } from './shell/chips';
import { STAGE2_NOTES, STAGE3_NOTES, STAGE4_NOTES } from './shell/methodNotes';
import { useStageRoute } from './shell/routing';
import type { StageRoute } from './shell/routing';
import { Stage2View } from './stages/stage2/Stage2View';
import { Stage3View } from './stages/stage3/Stage3View';
import { Stage4View } from './stages/stage4/Stage4View';

/** Explicit demo gate: synthetic data renders only when ?demo=1 is present. */
function isDemoGate(): boolean {
  if (typeof window === 'undefined') return false;
  return new URLSearchParams(window.location.search).get('demo') === '1';
}

function currentHash(): string {
  return typeof window === 'undefined' ? '' : window.location.hash;
}

const SUBTITLE: Record<StageRoute, string> = {
  'stage-2': 'Skewing genes',
  'stage-3': 'Drug link',
  'stage-4': 'PK / PD · brain',
};
const STAGE_LABEL: Record<StageRoute, string> = {
  'stage-2': 'Stage-2 gene-lever',
  'stage-3': 'Stage-3 drug-candidate',
  'stage-4': 'Stage-4 scorecard',
};
const STAGE_NOTES: Record<StageRoute, ProvNote[]> = {
  'stage-2': STAGE2_NOTES,
  'stage-3': STAGE3_NOTES,
  'stage-4': STAGE4_NOTES,
};
const STAGE_TARGET: Record<StageRoute, string> = {
  'stage-2': STAGE2_KEY,
  'stage-3': STAGE3_KEY,
  'stage-4': STAGE4_KEY,
};

interface DrawerState {
  open: boolean;
  title: string;
  provenance: Provenance | null;
  selection: StageSelection | null;
  notes: ProvNote[];
}

export default function App() {
  const demo = isDemoGate();
  const repo = useMemo(() => buildRepository(browserSource(), { demo }), [demo]);
  const [route, navigate] = useStageRoute();
  const [drawer, setDrawer] = useState<DrawerState>({
    open: false,
    title: '',
    provenance: null,
    selection: null,
    notes: [],
  });

  // The shell-global Stage-1 selection is always attached to the drawer, so its full
  // detail lives there rather than on the compact context bar.
  const opener = useMemo(
    () => ({
      open: (title: string, provenance: Provenance | null, notes: ProvNote[] = []) =>
        setDrawer({ open: true, title, provenance, selection: repo.selection, notes }),
    }),
    [repo],
  );

  return (
    <ProvenanceProvider value={opener}>
      <div data-shell-root className="flex h-screen flex-col overflow-hidden">
        <TopBar
          subtitle={SUBTITLE[route]}
          onOpenMethods={() => {
            const slot = slotFor(repo, route);
            const prov = slot.status === 'loaded' ? slot.artifact.provenance : null;
            opener.open(`${SUBTITLE[route]} — methods`, prov, STAGE_NOTES[route]);
          }}
        />
        <StageNav current={route} onNavigate={navigate} />
        <main className="flex min-h-0 flex-1 flex-col">
          {repo.mode === 'rejected_selection' ? (
            <SelectionRejected reason={repo.selectionRejection ?? 'unknown'} target={SELECTION_V3_KEY} />
          ) : repo.mode === 'empty' ? (
            <>
              <EmptyBar />
              <StageScaffold {...STAGE_SCAFFOLDS[route]} />
            </>
          ) : (
            <>
              {repo.selection && (
                <SelectionContextBar selection={repo.selection} demo={repo.mode === 'demo'} />
              )}
              <StageBody repo={repo} route={route} />
            </>
          )}
        </main>
      </div>

      <ProvenanceDrawer
        open={drawer.open}
        title={drawer.title}
        provenance={drawer.provenance}
        selection={drawer.selection}
        notes={drawer.notes}
        onClose={() => setDrawer((d) => ({ ...d, open: false }))}
      />
    </ProvenanceProvider>
  );
}

/** Compact honest header shown in empty mode — no selection bound, with the demo entry. */
function EmptyBar() {
  return (
    <section
      aria-label="No selection"
      className="flex flex-wrap items-center gap-x-3 gap-y-1.5 border-b border-line bg-sunken/60 px-5 py-2"
    >
      <StatePill label="no selection" tone="muted" />
      <span className="font-mono text-[10.5px] text-ink-2">select programs in Stage 1</span>
      <a
        href={`?demo=1${currentHash()}`}
        className="ml-auto font-mono text-[10.5px] text-accent hover:underline"
      >
        open demo →
      </a>
    </section>
  );
}

function slotFor(repo: SpotRepository, route: StageRoute): ArtifactSlot<{ provenance: Provenance }> {
  if (route === 'stage-2') return repo.getStage2();
  if (route === 'stage-3') return repo.getStage3();
  return repo.getStage4();
}

function StageBody({ repo, route }: { repo: SpotRepository; route: StageRoute }) {
  const label = STAGE_LABEL[route];
  const target = STAGE_TARGET[route];
  const contrastId = repo.selection?.contrast_id ?? null;
  const ctx = { label, target, contrastId };
  if (route === 'stage-2') return renderSlot(repo.getStage2(), ctx, (a) => <Stage2View artifact={a} />);
  if (route === 'stage-3') return renderSlot(repo.getStage3(), ctx, (a) => <Stage3View artifact={a} />);
  return renderSlot(repo.getStage4(), ctx, (a) => <Stage4View artifact={a} />);
}

interface SlotContext {
  label: string;
  target: string;
  contrastId: string | null;
}

function renderSlot<T>(slot: ArtifactSlot<T>, ctx: SlotContext, render: (a: T) => ReactElement): ReactElement {
  if (slot.status === 'loaded') return render(slot.artifact);
  if (slot.status === 'not_generated') {
    return <AnalysisNotGenerated target={ctx.target} contrastId={ctx.contrastId} />;
  }
  return <ArtifactRejected reason={slot.reason} target={ctx.target} />;
}
