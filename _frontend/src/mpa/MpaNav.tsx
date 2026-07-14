// The shared five-page pipeline nav (Programs · Targets · Pathways · Drugs · PK & Safety).
// Same visual grammar as the Stage-1 baseline; links carry the current query so the
// selection thread + demo flag persist across pages. Active step scrolls into view.

import { useEffect, useRef } from 'react';
import type { PageKey } from './pages';
import { PAGES, hrefWithSearch } from './pages';

export function MpaNav({ active }: { active: PageKey }) {
  const activeRef = useRef<HTMLAnchorElement>(null);
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
        const base = 'stage-nav__step flex items-center gap-[7px] rounded-[9px]';
        // Targets and Pathways are two views of the SAME stage (both 02): a subtler mid-dot
        // groups them, while the '›' arrow marks progression to the next stage number.
        const hasNext = i < PAGES.length - 1;
        const sameStage = hasNext && PAGES[i + 1].n === p.n;
        // Every step is a link with a STABLE href on every page; the current page is marked with
        // aria-current="page" only (never by dropping the href). This keeps the nav MODEL identical
        // across all five routes (the harness compares n|label|href per step) while the active tab
        // still resolves via aria-current — matching programs.html's nav exactly.
        return (
          <div key={p.key} className="flex items-center gap-[3px]">
            <a
              ref={on ? activeRef : undefined}
              href={hrefWithSearch(p.href)}
              aria-current={on ? 'page' : undefined}
              className={`${base} ${
                on ? 'font-semibold text-ink shadow-[inset_0_0_0_1.5px_var(--accent)]' : 'font-medium text-muted hover:text-ink'
              }`}
            >
              {inner}
            </a>
            {hasNext && <span className="stage-nav__sep text-line-strong">{sameStage ? '·' : '›'}</span>}
          </div>
        );
      })}
    </nav>
  );
}
