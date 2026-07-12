// Honest empty scaffold for a stage with no bound artifact. Shows the stage's output
// SHAPE — the regions it will produce, each labelled with a one-line description and a
// typed `awaiting artifact` state. Dashed frames + typed pills make it unmistakably a
// structure preview, never scientific output. No fake numbers, no prose.

import { StatePill } from './chips';

export interface ScaffoldRegion {
  label: string;
  hint: string;
}

export function StageScaffold({ purpose, regions }: { purpose: string; regions: ScaffoldRegion[] }) {
  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
      <div className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-1.5">
        <StatePill label="no artifact" tone="muted" />
        <span className="font-mono text-[10.5px] text-ink-2">{purpose}</span>
      </div>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {regions.map((r) => (
          <section key={r.label} className="rounded-lg border border-dashed border-line-strong p-3">
            <h4 className="font-mono text-[9.5px] uppercase tracking-wide text-muted">{r.label}</h4>
            <p className="mt-1 text-[11px] leading-snug text-ink-2">{r.hint}</p>
            <div className="mt-2">
              <StatePill label="awaiting artifact" tone="muted" />
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
