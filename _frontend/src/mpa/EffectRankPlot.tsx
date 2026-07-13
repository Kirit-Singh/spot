// One selected program = one facet. Within a facet the two desired-direction arms stay separate:
// the decrease arm is reconstructed at x = −arm_value, the increase arm at x = +arm_value, and y is
// the descriptive rank transform −log10(rank / N ranked) — native rank order, not an inferential
// statistic. Nothing here combines, weights, or balances the two arms, and no scale is shared with
// the other facet (each program is its own objective, on its own axis).

import type { CompactEffectRankFacet, CompactTargetRow } from '../domain/compactStage2Projection';
import { axisRange, axisSymmetric, layoutLabels, ticksFrom } from './plotScale';

export interface PlotPoint {
  id: string;
  symbol: string;
  side: 'decrease' | 'increase';
  shift: number;
  rank: number;
  nRanked: number;
  evidence: number;
}

const W = 640;
const H = 406;
const M = { left: 52, right: 18, top: 18, bottom: 56 };
const plotW = W - M.left - M.right;
const plotH = H - M.top - M.bottom;

const INCREASE = '#2D7C8E';
const DECREASE = '#D69834';
// A target carried by BOTH selected arms keeps its direction hue but deepens, and takes a thin ink
// ring. This is a set-membership fact (the same gene is ranked in each arm), NOT a merged score:
// its rank, its arm value and its facet stay exactly what its own arm emitted.
const INCREASE_BOTH = '#17505E';
const DECREASE_BOTH = '#A16A16';

function point(row: CompactTargetRow, side: PlotPoint['side'], nRanked: number): PlotPoint | null {
  if (row.arm_value === null || nRanked < 1) return null;
  return {
    id: row.target_id,
    symbol: row.target_symbol,
    side,
    shift: side === 'increase' ? row.arm_value : -row.arm_value,
    rank: row.rank,
    nRanked,
    evidence: -Math.log10(row.rank / nRanked),
  };
}

export function effectRankPoints(facet: CompactEffectRankFacet): PlotPoint[] {
  return [
    ...facet.decrease.rows.map((row) => point(row, 'decrease', facet.decrease.n_ranked)),
    ...facet.increase.rows.map((row) => point(row, 'increase', facet.increase.n_ranked)),
  ].filter((p): p is PlotPoint => p !== null);
}

function fmt(n: number): string {
  return Number.isFinite(n) ? n.toFixed(3).replace(/0+$/, '').replace(/\.$/, '') : '—';
}

/** An HPA link is generated ONLY from a typed Ensembl gene ID — never inferred from any other id. */
function hpaUrl(id: string): string | null {
  return /^ENSG\d{11}$/.test(id) ? `https://www.proteinatlas.org/${encodeURIComponent(id)}` : null;
}

/** Emphasis is bound to top-five rank, independent of whether a display label was drawn. */
const isTopFive = (p: PlotPoint): boolean => p.rank <= 5;

/** Stage-1's `.ctchip` grammar: the From / To poles keep the identity they were selected with. */
function PoleChip({ role }: { role: 'A' | 'B' }) {
  const from = role === 'A';
  return (
    <span
      className="inline-flex h-5 items-center justify-center rounded-[5px] px-1.5 font-mono text-[9.5px] font-bold uppercase tracking-[0.03em] text-white"
      style={{ background: from ? 'rgb(45,124,142)' : 'rgb(214,152,52)' }}
    >
      {from ? 'From' : 'To'}
    </span>
  );
}

function Legend({ bothCount }: { bothCount: number }) {
  return (
    <span className="flex items-center gap-3 font-mono text-[10.5px] text-muted">
      <span className="flex items-center gap-1">
        <svg width="7" height="7" aria-hidden="true"><circle cx="3.5" cy="3.5" r="3.5" fill={DECREASE} /></svg>
        decreasing
      </span>
      <span className="flex items-center gap-1">
        <svg width="7" height="7" aria-hidden="true"><circle cx="3.5" cy="3.5" r="3.5" fill={INCREASE} /></svg>
        increasing
      </span>
      {bothCount > 0 && (
        <span className="flex items-center gap-1">
          <svg width="9" height="9" aria-hidden="true">
            <circle cx="4.5" cy="4.5" r="3.4" fill={INCREASE_BOTH} stroke="#1E1B16" strokeWidth="0.9" opacity="0.85" />
          </svg>
          in both arms · {bothCount}
        </span>
      )}
    </span>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 truncate">
      <span className="text-muted">{label}</span> <span className="text-ink-2">{value}</span>
    </div>
  );
}

/**
 * Compact detail for the hovered / pinned gene.
 *
 * Its height is RESERVED whether or not a gene is active. That is load-bearing, not cosmetic: if the
 * card collapsed when idle, hovering a table row would grow the facet, push the table down, slide the
 * row out from under the cursor, and un-hover it — a flicker loop. Fixed height, no reflow, no loop.
 */
function DetailCard({ point: p, pinned, inBoth }: { point: PlotPoint | null; pinned: boolean; inBoth: boolean }) {
  const href = p ? hpaUrl(p.id) : null;
  return (
    <div
      className={`flex min-h-[56px] flex-col border-t border-line px-3 py-2 font-mono text-[10.5px] ${
        p ? '' : 'items-center justify-center'
      }`}
      aria-live="polite"
    >
      {!p ? (
        <span className="text-center text-[11px] text-muted">
          Select or hover a gene in the map or table for detail · click to pin it across both facets
        </span>
      ) : (
        <>
          <div className="mb-1 flex flex-wrap items-center gap-x-2 gap-y-1">
            <strong className="text-[11px] text-ink">{p.symbol}</strong>
            <span className="text-muted">{p.id}</span>
            {inBoth && (
              <span className="rounded border border-line bg-sunken px-1 text-[9px] text-ink-2">in both arms</span>
            )}
            {pinned && <span className="rounded border border-accent px-1 text-[9px] text-accent">pinned</span>}
            {href && (
              <a
                className="ml-auto text-accent underline underline-offset-2"
                href={href}
                target="_blank"
                rel="noopener noreferrer"
              >
                HPA ↗
              </a>
            )}
          </div>
          <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 sm:grid-cols-4">
            <Field label="signed shift" value={fmt(p.shift)} />
            <Field label="direction" value={p.side} />
            <Field label="rank" value={`${p.rank}/${p.nRanked}`} />
            <Field label="rank evidence" value={fmt(p.evidence)} />
          </div>
        </>
      )}
    </div>
  );
}

export interface EffectRankPlotProps {
  facet: CompactEffectRankFacet;
  /** Tier-2 display label for the facet's program; falls back to the raw id upstream. */
  programLabel?: string;
  /** This pole's own condition, in the page header's vocabulary (rest / 8 hr / 48 hr). */
  condition?: string;
  /** This pole's selected direction, in the page header's vocabulary (hi / lo). */
  poleDirection?: string;
  /** Gene currently hovered or pinned anywhere on the canvas (may belong to the other facet). */
  activeId?: string | null;
  pinnedId?: string | null;
  /** Targets ranked in BOTH selected arms — a co-membership set, never a merged score. */
  bothArmIds?: ReadonlySet<string>;
  onHover?: (id: string | null) => void;
  onPin?: (id: string | null) => void;
}

const EMPTY: ReadonlySet<string> = new Set();

export function EffectRankPlot({
  facet,
  programLabel,
  condition,
  poleDirection,
  activeId = null,
  pinnedId = null,
  bothArmIds = EMPTY,
  onHover,
  onPin,
}: EffectRankPlotProps) {
  const points = effectRankPoints(facet);

  // Rounded bounds that clear the extreme points, so neither the top- nor the bottom-ranked target
  // lands on the frame. x stays symmetric about the no-shift line; y is floored just below the lowest
  // emitted point (a top-N prefix cannot reach 0) instead of padding the frame with unreachable space.
  // Each facet scales to its own arms — one program, one objective, one axis.
  const evidence = points.map((p) => p.evidence);
  const xAxis = axisSymmetric(Math.max(1e-9, ...points.map((p) => Math.abs(p.shift))), 2);
  const yAxis = axisRange(Math.min(...evidence), Math.max(1e-9, ...evidence), 4);
  const ySpan = yAxis.bound - yAxis.floor;
  const x = (v: number) => M.left + ((v + xAxis.bound) / (2 * xAxis.bound)) * plotW;
  const y = (v: number) => M.top + (1 - (v - yAxis.floor) / ySpan) * plotH;

  const active = points.find((p) => p.id === activeId) ?? null;

  // Labels: the top five per direction, PLUS the hovered gene AND the pinned one. A pin has to
  // survive hovering something else — otherwise the target you deliberately kept goes back to being
  // an anonymous dot the moment the cursor moves. Only ever a verified frozen symbol, never an id.
  // Point EMPHASIS remains bound to top-five rank, independent of labelling.
  const named = (p: PlotPoint) => p.id === activeId || p.id === pinnedId;
  const labels = layoutLabels(
    points
      .filter((p) => (isTopFive(p) || named(p)) && p.symbol.trim() !== '')
      .map((p) => ({ id: p.id, text: p.symbol, px: x(p.shift), py: y(p.evidence), side: p.side })),
    { left: M.left + 2, right: W - M.right - 2, top: M.top, bottom: M.top + plotH },
  );

  return (
    <section
      aria-label={`${facet.program_id} effect-rank facet`}
      className="flex min-w-0 flex-col rounded-lg border border-line bg-surface"
    >
      <header className="flex flex-wrap items-center gap-x-2 gap-y-1 border-b border-line px-3 py-2">
        <PoleChip role={facet.role} />
        {/* the pole as the page header states it — label + its own condition; the raw program_id
            stays in the accessible name, not on the card */}
        <span className="text-[13.5px] font-semibold text-ink">
          {programLabel ?? facet.program_id}
          {poleDirection && <span className="text-ink-2"> {poleDirection}</span>}
          {condition && <span className="font-normal text-ink-2"> ({condition})</span>}
        </span>
        <span className="ml-auto">
          <Legend bothCount={bothArmIds.size} />
        </span>
      </header>

      <div className="px-1 pt-1">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="h-auto w-full min-w-[280px]"
          role="img"
          aria-label={`${facet.program_id}: signed program shift against descriptive rank evidence`}
        >
          {ticksFrom(yAxis).map((tick) => (
            <g key={`y${tick}`}>
              <line x1={M.left} y1={y(tick)} x2={W - M.right} y2={y(tick)} stroke="#EFECE6" />
              <text x={M.left - 7} y={y(tick) + 4} textAnchor="end" className="fill-muted text-[11px]">
                {fmt(tick)}
              </text>
            </g>
          ))}

          <line x1={M.left} y1={M.top + plotH} x2={W - M.right} y2={M.top + plotH} stroke="#D6D0C6" />
          <line x1={M.left} y1={M.top} x2={M.left} y2={M.top + plotH} stroke="#D6D0C6" />
          <line x1={x(0)} y1={M.top} x2={x(0)} y2={M.top + plotH} stroke="#D6D0C6" strokeDasharray="3 3" />

          {ticksFrom(xAxis).map((tick) => (
            <text
              key={`x${tick}`}
              x={x(tick)}
              y={H - 38}
              textAnchor="middle"
              className="fill-muted text-[11px]"
            >
              {fmt(tick)}
            </text>
          ))}

          <text x={M.left + plotW / 2} y={H - 21} textAnchor="middle" className="fill-ink-2 text-[12px]">
            Signed program shift
          </text>
          {/* which way each half of the axis runs — the reconstructed sign, spelled out */}
          <text x={M.left} y={H - 5} textAnchor="start" className="fill-muted text-[11px]">
            ← decreasing
          </text>
          <text x={W - M.right} y={H - 5} textAnchor="end" className="fill-muted text-[11px]">
            increasing →
          </text>
          <text
            transform={`translate(13 ${M.top + plotH / 2}) rotate(-90)`}
            textAnchor="middle"
            className="fill-ink-2 text-[12px]"
          >
            Rank evidence −log10(rank/N)
          </text>

          {/* Paint worst-ranked first so the top-ranked targets land ON TOP of the dense lobe: they
              stay visible, and they win the pointer when neighbouring points overlap. */}
          {[...points].sort((a, b) => b.rank - a.rank).map((p) => {
            const top = isTopFive(p);
            const on = named(p);
            const isPinned = p.id === pinnedId;
            const both = bothArmIds.has(p.id);
            const increase = p.side === 'increase';
            const fill = both
              ? increase
                ? INCREASE_BOTH
                : DECREASE_BOTH
              : increase
                ? INCREASE
                : DECREASE;
            const label = `${p.symbol}, ${p.side}, signed shift ${fmt(p.shift)}, rank ${p.rank} of ${p.nRanked}${
              both ? ', ranked in both selected arms' : ''
            }`;
            return (
              <g
                key={`${p.side}:${p.id}`}
                tabIndex={0}
                role="img"
                aria-label={label}
                className="cursor-pointer focus:outline-none"
                onMouseEnter={() => onHover?.(p.id)}
                onMouseLeave={() => onHover?.(null)}
                onFocus={() => onHover?.(p.id)}
                onBlur={() => onHover?.(null)}
                onClick={() => onPin?.(pinnedId === p.id ? null : p.id)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    onPin?.(pinnedId === p.id ? null : p.id);
                  }
                }}
              >
                {on && (
                  <circle
                    cx={x(p.shift)}
                    cy={y(p.evidence)}
                    r={6.5}
                    fill="none"
                    stroke="#3E7D8C"
                    strokeWidth={isPinned ? 1.8 : 1.2}
                  />
                )}
                <circle
                  cx={x(p.shift)}
                  cy={y(p.evidence)}
                  r={on ? 4.2 : top ? 3.4 : both ? 2.9 : 2.2}
                  fill={fill}
                  stroke={both ? '#1E1B16' : 'none'}
                  strokeWidth={both ? 0.9 : 0}
                  opacity={on || top || both ? 1 : 0.62}
                />
                <title>
                  {`${p.symbol} · ${p.id} · signed shift ${fmt(p.shift)} · ${p.side} · rank ${p.rank}/${p.nRanked} · rank evidence ${fmt(p.evidence)}${both ? ' · ranked in both selected arms' : ''}`}
                </title>
              </g>
            );
          })}

          {labels.map((l) => (
            <text
              key={`label:${l.id}`}
              x={l.x}
              y={l.y}
              textAnchor={l.anchor}
              className={`text-[11px] font-medium ${
                l.id === activeId || l.id === pinnedId ? 'fill-accent' : 'fill-ink'
              }`}
              pointerEvents="none"
            >
              {l.text}
            </text>
          ))}
        </svg>
      </div>

      <DetailCard
        point={active}
        pinned={active !== null && active.id === pinnedId}
        inBoth={active !== null && bothArmIds.has(active.id)}
      />
    </section>
  );
}
