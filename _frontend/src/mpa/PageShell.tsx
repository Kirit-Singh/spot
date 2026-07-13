// Shared island shell: the Stage-1 top bar + five-page nav + a single Methods &
// provenance drawer, wrapping one stage's body. Every React page renders through this,
// so the visual system is identical and DRY across the MPA.

import { useMemo, useState } from 'react';
import type { Provenance } from '../domain/common';
import type { StageSelection } from '../domain/selection';
import type { StageMethodsManifest } from '../domain/methodsManifest';
import { TopBar } from '../shell/TopBar';
import { ProvenanceDrawer } from '../shell/ProvenanceDrawer';
import { ProvenanceProvider } from '../shell/provenanceContext';
import type { ProvNote, DrawerSection } from '../shell/provenanceContext';
import { MpaNav } from './MpaNav';
import type { PageKey } from './pages';

interface DrawerState {
  open: boolean;
  title: string;
  provenance: Provenance | null;
  selection: StageSelection | null;
  notes: ProvNote[];
  methods: StageMethodsManifest | null;
  focus: DrawerSection;
}

export function PageShell({
  page,
  subtitle,
  subtitleNode,
  onClearSelection,
  selection = null,
  methodsProvenance = null,
  methodsNotes = [],
  methodsManifest = null,
  children,
}: {
  page: PageKey;
  subtitle: string;
  subtitleNode?: React.ReactNode;
  onClearSelection?: () => void;
  selection?: StageSelection | null;
  methodsProvenance?: Provenance | null;
  methodsNotes?: ProvNote[];
  methodsManifest?: StageMethodsManifest | null;
  children: React.ReactNode;
}) {
  const [drawer, setDrawer] = useState<DrawerState>({
    open: false,
    title: '',
    provenance: null,
    selection: null,
    notes: [],
    methods: null,
    focus: 'methods',
  });
  const opener = useMemo(
    () => ({
      open: (
        title: string,
        provenance: Provenance | null,
        notes: ProvNote[] = [],
        methods: StageMethodsManifest | null = null,
        section: DrawerSection = 'methods',
      ) => setDrawer({ open: true, title, provenance, selection, notes, methods, focus: section }),
    }),
    [selection],
  );

  return (
    <ProvenanceProvider value={opener}>
      <div data-shell-root className="flex h-screen flex-col overflow-hidden">
        <TopBar
          subtitle={subtitle}
          subtitleNode={subtitleNode}
          onClearSelection={onClearSelection}
          onOpenMethods={(section) =>
            opener.open(
              `${subtitle} — methods & provenance`,
              methodsProvenance,
              methodsNotes,
              methodsManifest,
              section,
            )
          }
        />
        <MpaNav active={page} />
        <main className="flex min-h-0 flex-1 flex-col">{children}</main>
      </div>
      <ProvenanceDrawer
        open={drawer.open}
        title={drawer.title}
        provenance={drawer.provenance}
        selection={drawer.selection}
        notes={drawer.notes}
        methods={drawer.methods}
        focus={drawer.focus}
        onClose={() => setDrawer((d) => ({ ...d, open: false }))}
      />
    </ProvenanceProvider>
  );
}
