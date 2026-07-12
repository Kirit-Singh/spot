// The shared five-page pipeline nav (Programs · Targets · Pathways · Drugs · PK & Safety).
// Same visual grammar as the Stage-1 baseline; links carry the current query so the
// selection thread + demo flag persist across pages. Active step scrolls into view.

import { useEffect, useRef } from 'react';
import type { PageKey } from './pages';
import { PAGES, hrefWithSearch } from './pages';

export function MpaNav({ active }: { active: PageKey }) {
  const activeRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    activeRef.current?.scrollIntoView({ inline: 'nearest', block: 'nearest' });
  }, [active]);

  return (
    <nav
      aria-label="Pipeline stages"
      className="stage-nav flex items-center overflow-x-auto whitespace-nowrap border-b border-line bg-surface"
    >
      {PAGES.map((p, i) => {
        const on = p.key === active;
        const inner = (
          <>
            <span className={`font-mono text-[10.5px] ${on ? 'text-accent' : 'opacity-55'}`}>{p.n}</span>
            {p.label}
          </>
        );
        const base = 'stage-nav__step flex items-center gap-1.5 rounded-lg font-medium';
        return (
          <div key={p.key} className="flex items-center">
            {on ? (
              <div ref={activeRef} aria-current="page" className={`${base} text-ink shadow-[inset_0_0_0_1.5px_var(--accent)]`}>
                {inner}
              </div>
            ) : (
              <a href={hrefWithSearch(p.href)} className={`${base} text-muted hover:text-ink`}>
                {inner}
              </a>
            )}
            {i < PAGES.length - 1 && <span className="stage-nav__sep text-line-strong">›</span>}
          </div>
        );
      })}
    </nav>
  );
}
