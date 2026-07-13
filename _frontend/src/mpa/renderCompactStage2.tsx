// Minimal Stage-2 canvas for W3's admitted compact prefix. Every cell is present in the
// projection; unavailable optional columns are omitted wholesale rather than filled or inferred.
/* oxlint-disable react/only-export-components -- this module intentionally exports render functions */

import type {
  CompactPathwayArm,
  CompactPathwayRow,
  CompactStage2SelectionView,
} from '../domain/compactStage2Projection';
import { StatePill } from '../shell/chips';
import { TargetsCanvas } from './TargetsCanvas';

const TH = 'px-2 py-1 text-left font-mono text-[9.5px] uppercase tracking-wide text-muted';
const TD = 'px-2 py-1 font-mono text-[10.5px] text-ink-2';
const CANVAS = 'flex min-h-0 flex-1 flex-col gap-3 overflow-auto p-4';

function shown(n: number): string {
  return new Intl.NumberFormat('en-US').format(n);
}

function value(n: number | null): string {
  return n === null ? '' : String(n);
}

function ReleaseStrip({ view }: { view: CompactStage2SelectionView }) {
  return (
    <div aria-label="Stage-2 release" className="flex flex-wrap items-center gap-2">
      <StatePill label={view.mode === 'within_condition' ? 'direct' : 'temporal'} tone="muted" />
      <StatePill label={view.pathway_source} tone="muted" />
    </div>
  );
}

type PathwayColumn = {
  label: string;
  available: (row: CompactPathwayRow) => boolean;
  render: (row: CompactPathwayRow) => string;
};

const PATHWAY_COLUMNS: PathwayColumn[] = [
  { label: 'enrichment', available: (r) => r.enrichment_value !== null, render: (r) => value(r.enrichment_value) },
  { label: 'source coverage', available: (r) => r.target_source_coverage !== null, render: (r) => value(r.target_source_coverage) },
  { label: 'disposition', available: (r) => r.global_coverage_disposition !== null, render: (r) => r.global_coverage_disposition ?? '' },
  { label: 'leading edge', available: (r) => r.n_leading_edge !== null, render: (r) => value(r.n_leading_edge) },
  { label: 'peak rank', available: (r) => r.peak_rank !== null, render: (r) => value(r.peak_rank) },
];

function PathwayMeta({ arm }: { arm: CompactPathwayArm }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <StatePill label={`${shown(arm.n_emitted)} shown`} tone="muted" />
      <StatePill label={`${shown(arm.n_sets_total)} sets`} tone="muted" />
      <StatePill label={`${shown(arm.n_with_coverage)} covered`} tone="muted" />
      {arm.is_a_prefix && <StatePill label={`first ${shown(arm.cap)}`} tone="muted" />}
      <StatePill label="native order" tone="muted" />
    </div>
  );
}

function PathwayArmTable({ arm, context }: { arm: CompactPathwayArm; context: string }) {
  const columns = PATHWAY_COLUMNS.filter((column) => arm.rows.some(column.available));
  return (
    <section aria-label="Pathway arm" className="rounded-lg border border-line bg-surface">
      <header className="flex flex-wrap items-center gap-2 border-b border-line px-3 py-2">
        <StatePill label="pathway arm" tone="muted" />
        <StatePill label={context} tone="muted" />
        <span className="break-all font-mono text-[10.5px] text-ink-2">{arm.arm_key}</span>
        <span className="ml-auto"><PathwayMeta arm={arm} /></span>
      </header>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse">
          <thead>
            <tr>
              <th className={TH}>set</th>
              {columns.map((column) => <th key={column.label} className={TH}>{column.label}</th>)}
            </tr>
          </thead>
          <tbody>
            {arm.rows.map((row, index) => (
              <tr key={`${row.set_id}:${index}`} className="border-t border-line">
                <td className={TD}>{row.set_id}</td>
                {columns.map((column) => <td key={column.label} className={TD}>{column.render(row)}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function renderCompactTargets(
  view: CompactStage2SelectionView,
  display?: { labels?: Map<string, string>; poleDirections?: Partial<Record<'A' | 'B', string>> },
): React.ReactNode {
  return <TargetsCanvas view={view} labels={display?.labels} poleDirections={display?.poleDirections} />;
}

export function renderCompactPathways(view: CompactStage2SelectionView): React.ReactNode {
  if (!view.pathwayArmA || !view.pathwayArmB) return null;
  return (
    <div data-real-canvas data-route="pathways" className={CANVAS}>
      <ReleaseStrip view={view} />
      <PathwayArmTable arm={view.pathwayArmA} context={view.pathway_context} />
      <PathwayArmTable arm={view.pathwayArmB} context={view.pathway_context} />
    </div>
  );
}
