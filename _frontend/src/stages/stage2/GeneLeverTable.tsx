// The central target table. BOTH objectives are always visible; the active view
// (away / toward / joint) drives the sort and a subtle column emphasis. The joint
// column shows the TYPED status + Pareto tier — never an averaged score. Marker
// breadth surfaces single-marker-driven (fragile) support.

import type { GeneLever, JointStatus, LeverArm, Objective } from '../../domain/stage2';
import { StatePill } from '../../shell/chips';

export type ViewMode = 'away_from_A' | 'toward_B' | 'joint';

const JOINT_STYLE: Record<JointStatus, { label: string; tone: Parameters<typeof StatePill>[0]['tone'] }> = {
  both_arms: { label: 'both arms', tone: 'accent' },
  a_only: { label: 'A only', tone: 'neutral' },
  b_only: { label: 'B only', tone: 'neutral' },
  opposed: { label: 'opposed', tone: 'amber' },
  not_evaluated: { label: 'not evaluated', tone: 'muted' },
};

/** One arm's cell: rank + signed effect + a diverging bar, or a not-evaluated note. */
function ArmCell({ arm, dim }: { arm: LeverArm; dim: boolean }) {
  if (!arm.evaluated) {
    return (
      <div className={`flex flex-col gap-0.5 ${dim ? 'opacity-60' : ''}`} title={arm.reason ?? 'not evaluated'}>
        <span className="font-mono text-[10px] text-muted">not evaluated</span>
        {arm.reason && (
          <span className="line-clamp-1 text-[10px] leading-tight text-muted">{arm.reason}</span>
        )}
      </div>
    );
  }
  const e = arm.effect ?? 0;
  const mag = Math.min(1, Math.abs(e) / 0.6);
  const negative = e < 0;
  return (
    <div className={`flex items-center gap-2 ${dim ? 'opacity-60' : ''}`}>
      {arm.rank != null && (
        <span className="inline-flex h-[18px] min-w-[22px] items-center justify-center rounded bg-sunken font-mono text-[10px] font-semibold text-ink-2">
          #{arm.rank}
        </span>
      )}
      <div className="relative h-1.5 w-16 flex-none rounded-full bg-sunken">
        <span
          className={`absolute top-0 h-full rounded-full ${negative ? 'bg-pole-a' : 'bg-pole-b'}`}
          style={{ width: `${mag * 50}%`, [negative ? 'right' : 'left']: '50%' }}
        />
        <span className="absolute left-1/2 top-1/2 h-2 w-px -translate-x-1/2 -translate-y-1/2 bg-line-strong" />
      </div>
      <span className="font-mono text-[11px] text-ink">
        {e >= 0 ? '+' : ''}
        {e.toFixed(2)}
      </span>
    </div>
  );
}

function ArmHeader({ objective, active, onSort }: { objective: Objective; active: boolean; onSort: () => void }) {
  const label = objective === 'away_from_A' ? 'away from A' : 'toward B';
  return (
    <button
      type="button"
      onClick={onSort}
      aria-pressed={active}
      className={`flex items-center gap-1 font-mono text-[10px] uppercase tracking-wide ${
        active ? 'text-accent' : 'text-muted hover:text-ink-2'
      }`}
      title={`Sort by ${label} rank`}
    >
      {label} {active ? '↓' : '↕'}
    </button>
  );
}

/** Compact marker-breadth cell: supporting-marker count + a fragile-support flag. */
function MarkerCell({ lever }: { lever: GeneLever }) {
  const b = lever.marker_breadth;
  return (
    <div className="flex items-center gap-1.5">
      <span className="font-mono text-[10.5px] text-ink-2">{b.supporting_markers} markers</span>
      {b.single_marker_driven && <StatePill label="single-marker" tone="amber" title={b.detail ?? 'single-marker driven'} />}
    </div>
  );
}

export function GeneLeverTable({
  levers,
  view,
  onView,
  selectedGeneId,
  onSelect,
}: {
  levers: GeneLever[];
  view: ViewMode;
  onView: (v: ViewMode) => void;
  selectedGeneId: string | null;
  onSelect: (gene: GeneLever) => void;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-left">
        <thead>
          <tr className="border-b border-line">
            <th scope="col" className="py-2 pr-3 font-mono text-[10px] uppercase tracking-wide text-muted">
              target
            </th>
            <th scope="col" className="py-2 pr-3">
              <ArmHeader objective="away_from_A" active={view === 'away_from_A'} onSort={() => onView('away_from_A')} />
            </th>
            <th scope="col" className="py-2 pr-3">
              <ArmHeader objective="toward_B" active={view === 'toward_B'} onSort={() => onView('toward_B')} />
            </th>
            <th scope="col" className="py-2 pr-3">
              <button
                type="button"
                onClick={() => onView('joint')}
                aria-pressed={view === 'joint'}
                className={`flex items-center gap-1 font-mono text-[10px] uppercase tracking-wide ${
                  view === 'joint' ? 'text-accent' : 'text-muted hover:text-ink-2'
                }`}
                title="Order by Pareto tier"
              >
                joint · pareto {view === 'joint' ? '↓' : '↕'}
              </button>
            </th>
            <th scope="col" className="py-2 pr-3 font-mono text-[10px] uppercase tracking-wide text-muted">
              markers
            </th>
            <th scope="col" className="py-2 font-mono text-[10px] uppercase tracking-wide text-muted">
              support
            </th>
          </tr>
        </thead>
        <tbody>
          {levers.map((g) => {
            const joint = JOINT_STYLE[g.joint_status];
            const selected = g.gene_id === selectedGeneId;
            return (
              <tr
                key={g.gene_id}
                tabIndex={0}
                role="button"
                aria-pressed={selected}
                onClick={() => onSelect(g)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    onSelect(g);
                  }
                }}
                className={`cursor-pointer border-b border-line/70 align-middle ${
                  selected ? 'bg-sunken' : 'hover:bg-sunken/50'
                }`}
              >
                <td className="py-2.5 pr-3">
                  <div className="font-semibold text-ink">{g.gene_id}</div>
                  <div className="font-mono text-[10px] text-muted">{g.ensembl_id ?? 'no Ensembl id'}</div>
                </td>
                <td className="py-2.5 pr-3">
                  <ArmCell arm={g.arms.away_from_A} dim={view === 'toward_B'} />
                </td>
                <td className="py-2.5 pr-3">
                  <ArmCell arm={g.arms.toward_B} dim={view === 'away_from_A'} />
                </td>
                <td className="py-2.5 pr-3">
                  <div className="flex items-center gap-2">
                    <StatePill label={joint.label} tone={joint.tone} />
                    <span className="font-mono text-[10px] text-muted">
                      {g.pareto_tier != null ? `tier ${g.pareto_tier}` : '—'}
                    </span>
                  </div>
                </td>
                <td className="py-2.5 pr-3">
                  <MarkerCell lever={g} />
                </td>
                <td className="py-2.5">
                  <span className="font-mono text-[10.5px] text-ink-2">{g.evidence.support_status}</span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {levers.length === 0 && (
        <p className="py-6 text-center text-[12px] text-muted">No targets match this filter.</p>
      )}
    </div>
  );
}
