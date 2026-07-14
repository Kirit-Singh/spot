// The ordered Stage-1 selection context, preserved at the top of a stage view.
// Compact by design: the two poles, the one analysis condition, a short contrast
// id, and a single namespace/status chip. Everything else — question/selection ids,
// source, dataset/donor, eligibility, gate detail and v3 hashes — lives one keystroke
// away in Methods & provenance, never on the canvas.

import type { ProgramPole, StageSelection } from '../domain/selection';
import { NamespaceChip } from './chips';

function Pole({ tag, pole }: { tag: 'A' | 'B'; pole: ProgramPole }) {
  const color = tag === 'A' ? 'bg-pole-a' : 'bg-pole-b';
  return (
    <span className="inline-flex min-w-0 items-center gap-1.5">
      <span
        className={`inline-flex h-[18px] min-w-[18px] items-center justify-center rounded px-1 font-mono text-[9.5px] font-bold uppercase text-white ${color}`}
      >
        {tag}
      </span>
      <span className="truncate text-[12.5px] font-semibold text-ink" title={pole.display_label}>
        {pole.display_label}
      </span>
      <span className="flex-none font-mono text-[10px] uppercase text-muted">{pole.direction}</span>
    </span>
  );
}

export function SelectionContextBar({
  selection,
  demo = false,
}: {
  selection: StageSelection;
  demo?: boolean;
}) {
  return (
    <section
      aria-label="Stage-1 selection context"
      className="flex flex-col gap-1.5 border-b border-line bg-sunken/60 px-5 py-2"
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <Pole tag="A" pole={selection.program_a} />
        <span className="flex-none font-mono text-[11px] text-muted">→</span>
        <Pole tag="B" pole={selection.program_b} />
        {demo && (
          <span className="ml-auto flex items-center gap-2">
            <span className="inline-flex items-center rounded-md border border-amber/50 bg-amber/10 px-1.5 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wide text-amber">
              demo · synthetic
            </span>
            <a
              href={typeof window !== 'undefined' ? `?${window.location.hash}` : '?'}
              className="font-mono text-[10px] text-accent hover:underline"
            >
              exit
            </a>
          </span>
        )}
      </div>

      <div className="flex min-w-0 items-center gap-x-3">
        <span className="flex-none font-mono text-[10.5px] text-ink-2">
          <span className="text-muted">condition</span> {selection.analysis_condition}
        </span>
        <span
          className="min-w-0 truncate font-mono text-[10.5px] text-ink-2"
          title={selection.contrast_id}
        >
          <span className="text-muted">contrast</span> {selection.contrast_id}
        </span>
        <span className="ml-auto flex-none">
          <NamespaceChip ns={selection.namespace} />
        </span>
      </div>
    </section>
  );
}
