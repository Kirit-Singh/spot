// Shared island shell: the Stage-1 top bar + five-page nav + a single Methods &
// provenance drawer, wrapping one stage's body. Every React page renders through this,
// so the visual system is identical and DRY across the MPA.

import { useMemo, useState } from 'react';
import type { Provenance } from '../domain/common';
import type { StageSelection } from '../domain/selection';
import { TopBar } from '../shell/TopBar';
import { ProvenanceDrawer } from '../shell/ProvenanceDrawer';
import { ProvenanceProvider } from '../shell/provenanceContext';
import type { ProvNote } from '../shell/provenanceContext';
import { MpaNav } from './MpaNav';
import type { PageKey } from './pages';

interface DrawerState {
  open: boolean;
  title: string;
  provenance: Provenance | null;
  selection: StageSelection | null;
  notes: ProvNote[];
}

export function PageShell({
  page,
  subtitle,
  subtitleNode,
  onClearSelection,
  selection = null,
  methodsProvenance = null,
  methodsNotes = [],
  children,
}: {
  page: PageKey;
  subtitle: string;
  subtitleNode?: React.ReactNode;
  onClearSelection?: () => void;
  selection?: StageSelection | null;
  methodsProvenance?: Provenance | null;
  methodsNotes?: ProvNote[];
  children: React.ReactNode;
}) {
  const [drawer, setDrawer] = useState<DrawerState>({
    open: false,
    title: '',
    provenance: null,
    selection: null,
    notes: [],
  });
  const opener = useMemo(
    () => ({
      open: (title: string, provenance: Provenance | null, notes: ProvNote[] = []) =>
        setDrawer({ open: true, title, provenance, selection, notes }),
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
          onOpenMethods={() => opener.open(`${subtitle} — methods`, methodsProvenance, methodsNotes)}
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
        onClose={() => setDrawer((d) => ({ ...d, open: false }))}
      />
    </ProvenanceProvider>
  );
}
