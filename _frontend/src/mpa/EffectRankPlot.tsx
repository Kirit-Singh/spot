import { useState } from 'react';
import type { CompactEffectRankFacet, CompactTargetRow } from '../domain/compactStage2Projection';
import { StatePill } from '../shell/chips';
import type { P2sSecondarySupport } from '../p2s/p2sSecondarySupport';
import type { P2sSupportView } from '../p2s/types';

interface PlotPoint {
  id: string;
  armKey: string;
  symbol: string;
  side: 'decrease' | 'increase';
  shift: number;
  rank: number;
  nRanked: number;
  evidence: number;
}

const W = 640;
const H = 250;
const M = { left: 53, right: 18, top: 18, bottom: 43 };
const plotW = W - M.left - M.right;
const plotH = H - M.top - M.bottom;

function point(row: CompactTargetRow, side: PlotPoint['side'], armKey: string,
  nRanked: number): PlotPoint | null {
  if (row.arm_value === null || nRanked < 1) return null;
  return {
    id: row.target_id,
    armKey,
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
    ...facet.decrease.rows.map((row) => point(row, 'decrease', facet.decrease.arm_key,
      facet.decrease.n_ranked)),
    ...facet.increase.rows.map((row) => point(row, 'increase', facet.increase.arm_key,
      facet.increase.n_ranked)),
  ].filter((p): p is PlotPoint => p !== null);
}

function fmt(n: number): string {
  return Number.isFinite(n) ? n.toFixed(3).replace(/0+$/, '').replace(/\.$/, '') : '—';
}

function hpaUrl(id: string): string | null {
  return /^ENSG\d{11}$/.test(id) ? `https://www.proteinatlas.org/${encodeURIComponent(id)}` : null;
}

function SecondaryDetail({ support }: { support: P2sSupportView | null }) {
  if (!support) return null;
  const lodo = support.robustness.lodoSignConcordance;
  return <>
    <span className="text-muted">P2S reconstruction support · secondary/non-gating</span>
    <span>{support.available && support.coefficient !== null ? `coef ${fmt(support.coefficient)}` : 'unavailable'}</span>
    <span>reconstruction sign {support.sign}</span>
    <span>{support.nRuns} runs</span>
    {lodo !== null && <span>LODO sign {fmt(lodo)} ({support.robustness.nLodo})</span>}
  </>;
}

function Tooltip({ point, p2s }: { point: PlotPoint | null; p2s?: P2sSecondarySupport }) {
  if (!point) return <div className="h-12 border-t border-line px-3 py-2" aria-live="polite" />;
  const href = hpaUrl(point.id);
  return (
    <div className="flex min-h-12 flex-wrap items-center gap-x-3 gap-y-1 border-t border-line px-3 py-2 font-mono text-[10px] text-ink-2" aria-live="polite">
      <strong className="text-ink">{point.symbol}</strong>
      <span>{point.id}</span>
      <span>signed shift {fmt(point.shift)}</span>
      <span>{point.side}</span>
      <span>rank {point.rank}/{point.nRanked}</span>
      <span>rank evidence {fmt(point.evidence)}</span>
      <SecondaryDetail support={p2s?.supportForTarget(point.id, point.armKey) ?? null} />
      {href && <a className="text-accent underline underline-offset-2" href={href} target="_blank" rel="noopener noreferrer">HPA ↗</a>}
    </div>
  );
}

export function EffectRankPlot({ facet, p2s }: { facet: CompactEffectRankFacet;
  p2s?: P2sSecondarySupport }) {
  const points = effectRankPoints(facet);
  const [active, setActive] = useState<PlotPoint | null>(null);
  const xMax = Math.max(1e-9, ...points.map((p) => Math.abs(p.shift)));
  const yMax = Math.max(1e-9, ...points.map((p) => p.evidence));
  const x = (v: number) => M.left + ((v + xMax) / (2 * xMax)) * plotW;
  const y = (v: number) => M.top + (1 - v / yMax) * plotH;
  const top = (p: PlotPoint) => p.rank <= 5;

  return (
    <section aria-label={`${facet.program_id} effect-rank facet`} className="min-w-0 rounded-lg border border-line bg-surface">
      <header className="flex flex-wrap items-center gap-2 border-b border-line px-3 py-2">
        <StatePill label={`program ${facet.role}`} tone="muted" />
        <span className="font-mono text-[10.5px] text-ink-2">{facet.program_id}</span>
      </header>
      <div className="overflow-x-auto px-1 pt-1">
        <svg viewBox={`0 0 ${W} ${H}`} className="h-auto min-w-[520px] w-full" role="img"
          aria-label={`${facet.program_id}: signed program shift against descriptive rank evidence`}>
          <line x1={M.left} y1={M.top + plotH} x2={W - M.right} y2={M.top + plotH} stroke="#D6D0C6" />
          <line x1={x(0)} y1={M.top} x2={x(0)} y2={M.top + plotH} stroke="#D6D0C6" strokeDasharray="3 3" />
          <line x1={M.left} y1={M.top} x2={M.left} y2={M.top + plotH} stroke="#D6D0C6" />
          {[0, yMax / 2, yMax].map((tick) => (
            <g key={tick}>
              <line x1={M.left - 4} y1={y(tick)} x2={W - M.right} y2={y(tick)} stroke="#E7E3DC" />
              <text x={M.left - 7} y={y(tick) + 3} textAnchor="end" className="fill-muted font-mono text-[9px]">{fmt(tick)}</text>
            </g>
          ))}
          {[-xMax, 0, xMax].map((tick) => (
            <text key={tick} x={x(tick)} y={H - 25} textAnchor="middle" className="fill-muted font-mono text-[9px]">{fmt(tick)}</text>
          ))}
          <text x={M.left + plotW / 2} y={H - 7} textAnchor="middle" className="fill-ink-2 font-mono text-[9.5px]">Signed program shift</text>
          <text transform={`translate(12 ${M.top + plotH / 2}) rotate(-90)`} textAnchor="middle" className="fill-ink-2 font-mono text-[9.5px]">Rank evidence −log10(rank/N)</text>
          {points.map((p) => {
            const href = hpaUrl(p.id);
            const label = `${p.symbol}, ${p.side}, signed shift ${fmt(p.shift)}, rank ${p.rank} of ${p.nRanked}`;
            const glyph = (
              <g>
                <circle cx={x(p.shift)} cy={y(p.evidence)} r={top(p) ? 3.4 : 2.2}
                  fill={p.side === 'increase' ? '#2D7C8E' : '#D69834'} opacity={top(p) ? 1 : 0.62} />
                <title>{`${p.symbol} · ${p.id} · signed shift ${fmt(p.shift)} · ${p.side} · rank ${p.rank}/${p.nRanked} · rank evidence ${fmt(p.evidence)}`}</title>
                {top(p) && <text x={x(p.shift) + (p.side === 'increase' ? 5 : -5)} y={y(p.evidence) - 4}
                  textAnchor={p.side === 'increase' ? 'start' : 'end'} className="fill-ink font-mono text-[8.5px]">{p.symbol}</text>}
              </g>
            );
            const events = { onMouseEnter: () => setActive(p), onMouseLeave: () => setActive(null),
              onFocus: () => setActive(p), onBlur: () => setActive(null) };
            return href
              ? <a key={`${p.side}:${p.id}`} href={href} target="_blank" rel="noopener noreferrer" aria-label={label} {...events}>{glyph}</a>
              : <g key={`${p.side}:${p.id}`} tabIndex={0} role="img" aria-label={label} {...events}>{glyph}</g>;
          })}
        </svg>
      </div>
      <Tooltip point={active} p2s={p2s} />
    </section>
  );
}
