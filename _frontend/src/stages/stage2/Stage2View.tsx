// Stage 2 — targets. Two independent objectives stay authoritative; a segmented
// control switches between the Away-from-A, Toward-B, and Joint·Pareto views (the
// Joint view orders by Pareto tier, never an averaged score). A joint-status filter
// narrows rows; a convergent-pathway rail and a per-target evidence inspector sit
// alongside. (Selection context is rendered by the shell.)

import { useMemo, useState } from 'react';
import type { GeneLever, JointStatus, Stage2Artifact } from '../../domain/stage2';
import { JOINT_STATUSES } from '../../domain/stage2';
import { StatePill } from '../../shell/chips';
import { useProvenance } from '../../shell/provenanceContext';
import { STAGE2_NOTES } from '../../shell/methodNotes';
import { GeneLeverTable } from './GeneLeverTable';
import type { ViewMode } from './GeneLeverTable';
import { GeneEvidenceInspector } from './GeneEvidenceInspector';
import { PathwayPanel } from './PathwayPanel';

const VIEWS: { key: ViewMode; label: string }[] = [
  { key: 'away_from_A', label: 'Away from A' },
  { key: 'toward_B', label: 'Toward B' },
  { key: 'joint', label: 'Joint · Pareto' },
];

type Filter = 'all' | JointStatus;
const FILTERS: Filter[] = ['all', ...JOINT_STATUSES];
const FILTER_LABEL: Record<Filter, string> = {
  all: 'all',
  both_arms: 'both arms',
  a_only: 'A only',
  b_only: 'B only',
  opposed: 'opposed',
  not_evaluated: 'not evaluated',
};

/** Order by the active view: Pareto tier for joint, else the chosen arm's rank; nulls sink. */
function byView(a: GeneLever, b: GeneLever, view: ViewMode): number {
  if (view === 'joint') {
    const ta = a.pareto_tier;
    const tb = b.pareto_tier;
    if (ta == null && tb == null) return 0;
    if (ta == null) return 1;
    if (tb == null) return -1;
    return ta - tb;
  }
  const ra = a.arms[view].rank;
  const rb = b.arms[view].rank;
  if (ra == null && rb == null) return 0;
  if (ra == null) return 1;
  if (rb == null) return -1;
  return ra - rb;
}

export function Stage2View({ artifact }: { artifact: Stage2Artifact }) {
  const { open } = useProvenance();
  const [view, setView] = useState<ViewMode>('joint');
  const [filter, setFilter] = useState<Filter>('all');
  const [selected, setSelected] = useState<GeneLever | null>(null);

  const rows = useMemo(() => {
    const filtered = artifact.levers.filter((g) => filter === 'all' || g.joint_status === filter);
    return [...filtered].sort((a, b) => byView(a, b, view));
  }, [artifact.levers, filter, view]);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-line bg-surface px-5 py-2.5">
        <div
          data-testid="stage2-view-group"
          role="group"
          aria-label="Objective view"
          className="flex min-w-0 flex-wrap items-center overflow-hidden rounded-lg border border-line"
        >
          {VIEWS.map((v) => (
            <button
              key={v.key}
              type="button"
              aria-pressed={view === v.key}
              onClick={() => setView(v.key)}
              className={`px-2.5 py-1 font-mono text-[10.5px] ${
                view === v.key ? 'bg-accent text-white' : 'text-ink-2 hover:text-accent'
              }`}
            >
              {v.label}
            </button>
          ))}
        </div>

        <div
          data-testid="stage2-filter-group"
          role="group"
          aria-label="Filter by joint status"
          className="flex min-w-0 flex-wrap items-center gap-1.5"
        >
          {FILTERS.map((f) => (
            <button
              key={f}
              type="button"
              aria-pressed={filter === f}
              onClick={() => setFilter(f)}
              className={`rounded-md border px-2 py-1 font-mono text-[10.5px] ${
                filter === f ? 'border-accent bg-accent text-white' : 'border-line text-ink-2 hover:border-accent'
              }`}
            >
              {FILTER_LABEL[f]}
            </button>
          ))}
        </div>

        <div className="ml-auto flex flex-wrap items-center gap-3">
          <span className="font-mono text-[10.5px] text-muted">
            tested family: {artifact.tested_family_size}
          </span>
          <StatePill
            label={artifact.significance_calibrated ? 'significance calibrated' : 'significance not_calibrated'}
            tone={artifact.significance_calibrated ? 'ok' : 'muted'}
          />
          <button
            type="button"
            onClick={() => open('Stage 2 — target set', artifact.provenance, STAGE2_NOTES)}
            className="inline-flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-1 text-[11px] font-semibold text-ink-2 hover:border-accent hover:text-accent"
          >
            <span className="flex h-[14px] w-[14px] items-center justify-center rounded-full border border-current text-[8px] font-bold italic">
              i
            </span>
            Provenance
          </button>
        </div>
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-1 grid-rows-[minmax(240px,1fr)_auto] overflow-hidden rail:grid-cols-[minmax(0,1fr)_340px] rail:grid-rows-1">
        <div className="min-h-0 overflow-y-auto px-5 py-4">
          <GeneLeverTable
            levers={rows}
            view={view}
            onView={setView}
            selectedGeneId={selected?.gene_id ?? null}
            onSelect={setSelected}
          />
        </div>

        <aside className="min-h-0 max-h-[48vh] overflow-y-auto border-t border-line bg-surface px-4 py-3 rail:max-h-none rail:border-l rail:border-t-0">
          <PathwayPanel pathways={artifact.pathways} />
        </aside>
      </div>

      {selected && <GeneEvidenceInspector gene={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}
