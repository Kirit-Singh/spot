// Convergent perturbation signatures. Each node lists the contributing targets, the
// arm(s) it is supported on, its enrichment evidence, and whether the node itself is a
// druggable entity. Compact evidence fields only; interpretation lives in provenance.

import type { ArmSupport, PathwayNode } from '../../domain/stage2';
import { StatePill } from '../../shell/chips';

const ARM_LABEL: Record<ArmSupport, string> = { a: 'A arm', b: 'B arm', both: 'both arms' };

export function PathwayPanel({ pathways }: { pathways: PathwayNode[] }) {
  return (
    <section aria-label="Convergent pathways">
      <h3 className="font-sans text-[10px] font-semibold uppercase tracking-wide text-ink-2">
        Convergent pathways
      </h3>
      {pathways.length === 0 ? (
        <p className="mt-3 font-mono text-[10.5px] text-muted">no convergent signature</p>
      ) : (
        <ul className="mt-3 space-y-2.5">
          {pathways.map((p) => (
            <li key={p.pathway_id} className="border-t border-line pt-2.5 first:border-t-0 first:pt-0">
              <div className="flex items-baseline justify-between gap-2">
                <span className="text-[12px] font-semibold text-ink">{p.name}</span>
                <span className="font-mono text-[10px] text-muted">{p.pathway_id}</span>
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-1.5">
                <StatePill label={ARM_LABEL[p.arm_support]} tone={p.arm_support === 'both' ? 'accent' : 'neutral'} />
                {p.druggable && <StatePill label="druggable node" tone="accent" />}
                <span className="font-mono text-[10.5px] text-ink-2">
                  <span className="text-muted">enrichment</span>{' '}
                  {p.enrichment != null ? p.enrichment.toFixed(2) : 'not evaluated'}
                </span>
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-1">
                <span className="font-mono text-[9.5px] text-muted">targets</span>
                {p.contributing_targets.map((t) => (
                  <span key={t} className="rounded bg-sunken px-1 py-0.5 font-mono text-[9.5px] text-ink-2">
                    {t}
                  </span>
                ))}
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-x-3 font-mono text-[9.5px] text-muted">
                <span>{p.method}</span>
                <span>hash {p.source_hash}</span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
