// The Targets canvas: a selection summary, one effect–rank facet per selected program, and the two
// producer arm tables. Facets and tables are coordinated by ONE hovered/pinned target id, so the same
// gene lights up everywhere it appears — including in BOTH facets when a program pair ranks it twice.
//
// The two programs remain two independent objectives with their own arms, their own ranks, and their
// own axes. Nothing here merges them into a single score, and no row is displayed without the frozen
// symbol its producer emitted.

import { useEffect, useMemo, useRef, useState } from 'react';
import type {
  CompactStage2SelectionView,
  CompactTargetArm,
  CompactTargetRow,
} from '../domain/compactStage2Projection';
import { conditionLabel } from './contrastTitle';
import { EffectRankPlot } from './EffectRankPlot';

const TH = 'px-2 py-1 text-left font-mono text-[9.5px] uppercase tracking-wide text-muted';
const TD = 'px-2 py-1 font-mono text-[10.5px] text-ink-2';

function shown(n: number): string {
  return new Intl.NumberFormat('en-US').format(n);
}

/** Display precision only — the producer's exact value is preserved in the cell's title. */
function armValue(n: number | null): string {
  if (n === null) return '';
  const abs = Math.abs(n);
  if (abs !== 0 && (abs < 1e-3 || abs >= 1e5)) return n.toExponential(2);
  return String(Number(n.toPrecision(4)));
}

function hpaUrl(id: string): string | null {
  return /^ENSG\d{11}$/.test(id) ? `https://www.proteinatlas.org/${encodeURIComponent(id)}` : null;
}

/** The arm's desired direction, by EXACT arm_key identity against the facets — never parsed from the id. */
function armDirection(view: CompactStage2SelectionView, arm: CompactTargetArm): 'increase' | 'decrease' | null {
  for (const facet of view.effectRankFacets) {
    if (facet.increase.arm_key === arm.arm_key) return 'increase';
    if (facet.decrease.arm_key === arm.arm_key) return 'decrease';
  }
  return null;
}

/** The program this arm belongs to, again by exact arm_key identity. */
function armProgramId(view: CompactStage2SelectionView, arm: CompactTargetArm): string | null {
  for (const facet of view.effectRankFacets) {
    if (facet.increase.arm_key === arm.arm_key || facet.decrease.arm_key === arm.arm_key) {
      return facet.program_id;
    }
  }
  return null;
}

function contextLabel(arm: CompactTargetArm): string {
  return 'condition' in arm.context
    ? arm.context.condition
    : `${arm.context.from_condition} → ${arm.context.to_condition}`;
}

const ARROW: Record<'increase' | 'decrease', string> = { increase: '↑', decrease: '↓' };
const MOTION: Record<'increase' | 'decrease', string> = { increase: 'increasing', decrease: 'decreasing' };

/**
 * The condition this POLE was selected at, in the page header's vocabulary. A within-condition
 * selection puts both poles at the same timepoint; a temporal one runs From → To, so the From facet
 * brackets the start condition and the To facet the end one.
 */
function facetCondition(facet: CompactStage2SelectionView['effectRankFacets'][number]): string {
  const ctx = facet.increase.context;
  if ('condition' in ctx) return conditionLabel(ctx.condition);
  return conditionLabel(facet.role === 'A' ? ctx.from_condition : ctx.to_condition);
}

/** How many producer rows a table shows. The arm itself is untouched: this is a display filter. */
export type RowMode = 'top10' | 'both' | 'all';

const TOP_N = 10;

/**
 * The rows a table shows: the mode's filter, PLUS the pinned gene wherever it ranks.
 *
 * A pinned gene must be visible in every arm that ranks it — pin WDR26 from the map and it is rank 5
 * in one arm but rank 30 in the other, so a plain top-ten filter would silently drop the very row the
 * user asked to see. It is re-inserted at its true rank; the filter is display-only and the producer's
 * rows and ranks are never touched.
 */
function rowsFor(
  arm: CompactTargetArm,
  mode: RowMode,
  bothArmIds: ReadonlySet<string>,
  pinnedId: string | null,
): CompactTargetRow[] {
  const base =
    mode === 'both'
      ? arm.rows.filter((row) => bothArmIds.has(row.target_id))
      : mode === 'top10'
        ? arm.rows.filter((row) => row.rank <= TOP_N)
        : arm.rows;

  if (!pinnedId || base.some((row) => row.target_id === pinnedId)) return base;
  const pinned = arm.rows.find((row) => row.target_id === pinnedId);
  return pinned ? [...base, pinned].sort((a, b) => a.rank - b.rank) : base;
}

/** Stage-1's `.seg` grammar (Show cells · condition): one bordered group, a rule between each button,
 *  12.5px/500 Inter Tight, accent fill on the active one. */
function RowModeControl({
  mode,
  bothCount,
  cap,
  onMode,
}: {
  mode: RowMode;
  bothCount: number;
  cap: number;
  onMode: (mode: RowMode) => void;
}) {
  const options: { key: RowMode; label: string }[] = [
    { key: 'top10', label: `Top ${TOP_N}` },
    ...(bothCount > 0 ? [{ key: 'both' as const, label: `In both · ${shown(bothCount)}` }] : []),
    { key: 'all', label: `All ${shown(cap)}` },
  ];
  return (
    <div
      role="group"
      aria-label="Rows shown"
      className="flex items-center overflow-hidden rounded-[9px] border border-line"
    >
      {options.map((option, i) => (
        <button
          key={option.key}
          type="button"
          aria-pressed={mode === option.key}
          onClick={() => onMode(option.key)}
          className={`px-2.5 py-1 text-[12.5px] font-medium ${i > 0 ? 'border-l border-line' : ''} ${
            mode === option.key ? 'bg-accent text-white' : 'text-ink-2 hover:text-accent'
          }`}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

/** "Rest (6,815 ranked)" / "Rest → Stim8hr (6,815 ranked)" — the arm's context and the size of the
 *  ranking its rows are drawn from, in one line instead of a row of pills. */
function armContext(arm: CompactTargetArm): string {
  return `${contextLabel(arm)} (${shown(arm.n_ranked)} ranked)`;
}

interface ArmTableProps {
  view: CompactStage2SelectionView;
  arm: CompactTargetArm;
  labels: Map<string, string>;
  activeId: string | null;
  pinnedId: string | null;
  bothArmIds: ReadonlySet<string>;
  mode: RowMode;
  onMode: (mode: RowMode) => void;
  onHover: (id: string | null) => void;
  onPin: (id: string | null) => void;
}

function GeneArmTable({
  view,
  arm,
  labels,
  activeId,
  pinnedId,
  bothArmIds,
  mode,
  onMode,
  onHover,
  onPin,
}: ArmTableProps) {
  const rows = rowsFor(arm, mode, bothArmIds, pinnedId);
  const showValue = rows.some((row) => row.arm_value !== null);
  const dir = armDirection(view, arm);
  const programId = armProgramId(view, arm);
  const program = programId ? (labels.get(programId) ?? programId) : null;
  const pinnedRow = useRef<HTMLTableRowElement | null>(null);

  // Follow a gene pinned from the plot into view; 'nearest' keeps the page from jumping.
  useEffect(() => {
    if (pinnedId && pinnedRow.current) pinnedRow.current.scrollIntoView({ block: 'nearest' });
  }, [pinnedId]);

  return (
    <section aria-label="Gene arm" className="min-w-0 rounded-lg border border-line bg-surface">
      <header className="flex flex-wrap items-center gap-x-2 gap-y-1 border-b border-line px-3 py-2">
        {program && <span className="text-[13.5px] font-semibold text-ink">{program}</span>}
        {dir && (
          <span className="font-mono text-[11px] text-ink-2">
            {ARROW[dir]} {MOTION[dir]}
          </span>
        )}
        <span className="font-mono text-[11px] text-muted">{armContext(arm)}</span>
        <span className="ml-auto">
          <RowModeControl mode={mode} bothCount={bothArmIds.size} cap={arm.n_emitted} onMode={onMode} />
        </span>
      </header>
      {/* Stable columns: a fixed layout (not content-sized) plus a reserved scrollbar gutter, so
          switching row modes — 10 rows to 100, scrollbar or none — never reflows the columns. */}
      <div className="max-h-[420px] overflow-auto [scrollbar-gutter:stable]">
        <table className="w-full table-fixed border-collapse">
          <colgroup>
            <col className="w-[10%]" />
            <col className={showValue ? 'w-[28%]' : 'w-[34%]'} />
            <col className={showValue ? 'w-[30%]' : 'w-[40%]'} />
            {showValue && <col className="w-[20%]" />}
            <col className={showValue ? 'w-[12%]' : 'w-[16%]'} />
          </colgroup>
          <thead className="sticky top-0 z-10 bg-surface">
            <tr>
              <th className={TH}>rank</th>
              <th className={TH}>symbol</th>
              <th className={TH}>ensembl</th>
              {showValue && <th className={TH}>arm value</th>}
              <th className={TH}>hpa</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row: CompactTargetRow) => {
              const on = row.target_id === activeId;
              const isPinned = row.target_id === pinnedId;
              const both = bothArmIds.has(row.target_id);
              const href = hpaUrl(row.target_id);
              return (
                <tr
                  key={`${row.target_id}:${row.rank}`}
                  ref={isPinned ? pinnedRow : undefined}
                  onMouseEnter={() => onHover(row.target_id)}
                  onMouseLeave={() => onHover(null)}
                  onClick={() => onPin(isPinned ? null : row.target_id)}
                  aria-selected={isPinned}
                  data-active={on ? 'true' : 'false'}
                  className={`cursor-pointer border-t border-line ${
                    on ? 'bg-sunken' : 'hover:bg-sunken/60'
                  } ${isPinned ? 'shadow-[inset_2px_0_0_0_#3E7D8C]' : ''}`}
                >
                  <td className={TD}>{row.rank}</td>
                  <td className={`${TD} ${on ? 'font-semibold text-ink' : ''}`}>
                    <span className="flex items-center gap-1.5">
                      {row.target_symbol}
                      {both && (
                        <span
                          title="ranked in both selected arms"
                          className="rounded-full border border-ink/70 bg-ink/10 px-1 text-[8.5px] leading-[13px] text-ink-2"
                        >
                          both
                        </span>
                      )}
                    </span>
                  </td>
                  <td className={TD}>{row.target_id}</td>
                  {showValue && (
                    <td className={TD} title={row.arm_value === null ? undefined : String(row.arm_value)}>
                      {armValue(row.arm_value)}
                    </td>
                  )}
                  <td className={TD}>
                    {href && (
                      <a
                        href={href}
                        target="_blank"
                        rel="noopener noreferrer"
                        aria-label={`${row.target_symbol} on the Human Protein Atlas`}
                        onClick={(e) => e.stopPropagation()}
                        className="text-accent underline underline-offset-2"
                      >
                        HPA ↗
                      </a>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

/** The selected arm belonging to a facet's program, by EXACT arm_key identity. */
function selectedArmFor(
  view: CompactStage2SelectionView,
  facet: CompactStage2SelectionView['effectRankFacets'][number],
): CompactTargetArm {
  const keys = [facet.increase.arm_key, facet.decrease.arm_key];
  return keys.includes(view.geneArmA.arm_key) ? view.geneArmA : view.geneArmB;
}

/**
 * Targets ranked in BOTH selected arms — e.g. a gene whose knockdown moves one program down while
 * the other moves up. Pure co-membership of two independently produced rankings: it reorders nothing,
 * scores nothing, and merges nothing. Each arm keeps its own rank and its own value.
 */
function bothArmTargets(view: CompactStage2SelectionView): ReadonlySet<string> {
  const inB = new Set(view.geneArmB.rows.map((row) => row.target_id));
  return new Set(view.geneArmA.rows.map((row) => row.target_id).filter((id) => inB.has(id)));
}

/** The A → B transition, marked the whole way down the gap between the two facets. Bare glyphs, no
 *  chrome; the run of them reads as a direction of travel rather than a single badge. */
const ARROW_RUN = 7;

function TransitionArrows({ from, to, down = false }: { from: string; to: string; down?: boolean }) {
  return (
    <span
      aria-label={`from ${from} to ${to}`}
      className={`pointer-events-none flex select-none text-[20px] leading-none text-muted ${
        down ? 'flex-row justify-center gap-6' : 'h-full flex-col items-center justify-between'
      }`}
    >
      {Array.from({ length: down ? 1 : ARROW_RUN }, (_, i) => (
        <span key={i} aria-hidden="true">
          {down ? '↓' : '→'}
        </span>
      ))}
    </span>
  );
}

export function TargetsCanvas({
  view,
  labels = new Map<string, string>(),
  poleDirections,
}: {
  view: CompactStage2SelectionView;
  labels?: Map<string, string>;
  /** The direction each pole was selected at (hi / lo), as the page header states it. */
  poleDirections?: Partial<Record<'A' | 'B', string>>;
}) {
  const [hovered, setHovered] = useState<string | null>(null);
  const [pinned, setPinned] = useState<string | null>(null);
  const [mode, setMode] = useState<RowMode>('top10');
  const activeId = hovered ?? pinned;
  const bothArmIds = useMemo(() => bothArmTargets(view), [view]);

  const [a, b] = view.effectRankFacets;
  const name = (id: string) => labels.get(id) ?? id;

  return (
    <div
      data-real-canvas
      data-route="targets"
      className="flex min-h-0 flex-1 flex-col gap-3 overflow-auto p-4"
    >
      {/* One column per program: its facet, and directly beneath it the arm that facet's objective
          selected. The two columns never share an axis or a score — only a hovered/pinned gene.
          The column gap is wide enough to seat the arrow run between the two facets. */}
      <div className="grid min-w-0 grid-cols-1 items-start gap-3 xl:grid-cols-2 xl:gap-x-8">
        {view.effectRankFacets.map((facet, index) => (
          <div key={facet.role} className="flex min-w-0 flex-col gap-3">
            <div className="relative min-w-0">
              <EffectRankPlot
                facet={facet}
                programLabel={name(facet.program_id)}
                condition={facetCondition(facet)}
                poleDirection={poleDirections?.[facet.role]}
                activeId={activeId}
                pinnedId={pinned}
                bothArmIds={bothArmIds}
                onHover={setHovered}
                onPin={setPinned}
              />
              {/* seated exactly in the 32px column gap (-right-8 + w-8), never overlapping either card */}
              {index === 0 && (
                <span className="absolute -right-8 bottom-20 top-16 hidden w-8 xl:block">
                  <TransitionArrows from={name(a.program_id)} to={name(b.program_id)} />
                </span>
              )}
            </div>
            <GeneArmTable
              view={view}
              arm={selectedArmFor(view, facet)}
              labels={labels}
              activeId={activeId}
              pinnedId={pinned}
              bothArmIds={bothArmIds}
              mode={mode}
              onMode={setMode}
              onHover={setHovered}
              onPin={setPinned}
            />
            {index === 0 && (
              <span className="flex justify-center xl:hidden">
                <TransitionArrows from={name(a.program_id)} to={name(b.program_id)} down />
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
