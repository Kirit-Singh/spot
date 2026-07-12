// Pipeline navigation, matching the Stage-1 language: five ordered steps, the
// active one ringed in the teal accent. Stage 1 links out to the built page;
// Stage 5 is not yet built (visibly disabled). The strip scrolls horizontally and
// the active step is scrolled into the nav viewport on load and on every route
// change, so it is never clipped off-screen at narrow widths.

import { useEffect, useRef } from 'react';
import type { StageRoute } from './routing';

interface Step {
  n: string;
  label: string;
  route: StageRoute | null;
  href?: string;
  disabled?: boolean;
}

const STEPS: Step[] = [
  { n: '01', label: 'CD4 programs', route: null, href: '/01_page.html' },
  { n: '02', label: 'Skewing genes', route: 'stage-2' },
  { n: '03', label: 'Drug link', route: 'stage-3' },
  { n: '04', label: 'PK / PD · brain', route: 'stage-4' },
  { n: '05', label: 'Trial', route: null, disabled: true },
];

export function StageNav({
  current,
  onNavigate,
}: {
  current: StageRoute;
  onNavigate: (r: StageRoute) => void;
}) {
  const activeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    // Keep the active step inside the horizontal nav viewport (never a vertical jump).
    activeRef.current?.scrollIntoView({ inline: 'nearest', block: 'nearest' });
  }, [current]);

  return (
    <nav
      aria-label="Pipeline stages"
      className="stage-nav flex items-center overflow-x-auto whitespace-nowrap border-b border-line bg-surface"
    >
      {STEPS.map((s, i) => {
        const on = s.route === current;
        const inner = (
          <>
            <span className={`font-mono text-[10.5px] ${on ? 'text-accent' : 'opacity-55'}`}>
              {s.n}
            </span>
            {s.label}
          </>
        );
        const base = 'stage-nav__step flex items-center gap-1.5 rounded-lg font-medium';
        return (
          <div key={s.n} className="flex items-center">
            {s.href ? (
              <a
                href={s.href}
                className={`${base} text-muted hover:text-accent`}
                title="Open the built Stage-1 page"
              >
                {inner}
              </a>
            ) : s.route ? (
              <button
                type="button"
                ref={on ? activeRef : undefined}
                aria-current={on ? 'page' : undefined}
                onClick={() => onNavigate(s.route as StageRoute)}
                className={`${base} ${
                  on
                    ? 'text-ink shadow-[inset_0_0_0_1.5px_var(--accent)]'
                    : 'text-muted hover:text-ink'
                }`}
              >
                {inner}
              </button>
            ) : (
              <span
                aria-disabled="true"
                className={`${base} cursor-not-allowed text-muted opacity-50`}
                title="Not yet built"
              >
                {inner}
              </span>
            )}
            {i < STEPS.length - 1 && <span className="stage-nav__sep text-line-strong">›</span>}
          </div>
        );
      })}
    </nav>
  );
}
