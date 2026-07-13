// Top brand bar, matching Stage-1: 'spot' in Newsreader with a teal middot, a
// stage subtitle sharing one baseline, and the Methods + Provenance actions that open
// the one shared slide-out drawer (focused on the requested section).

import type { ReactNode } from 'react';

export type DrawerSection = 'methods' | 'provenance';

export function TopBar({
  subtitle,
  subtitleNode,
  onClearSelection,
  onOpenMethods,
}: {
  subtitle: string;
  subtitleNode?: ReactNode;
  onClearSelection?: () => void;
  onOpenMethods: (section?: DrawerSection) => void;
}) {
  // Match the frozen Programs title exactly: Newsreader 16px / weight 500 / ink.
  const titleCls = 'truncate font-editorial text-[16px] font-medium leading-none text-ink';
  return (
    <header className="flex h-[50px] flex-none items-center gap-3 border-b border-line bg-surface px-5">
      <div className="flex min-w-0 items-baseline gap-3">
        <span className="font-editorial text-[20px] font-medium leading-none">
          spot<b className="text-accent">·</b>
        </span>
        <span className="ml-0.5 flex min-w-0 items-baseline gap-2 border-l border-line pl-3 leading-none">
          <span className={titleCls} title={subtitle}>
            {subtitleNode ?? subtitle}
          </span>
          {onClearSelection && (
            <button
              type="button"
              onClick={onClearSelection}
              title="Clear selection and return to Programs"
              aria-label="Clear selection and return to Programs"
              className="flex-none text-[12px] leading-none text-muted hover:text-danger"
            >
              ✕
            </button>
          )}
        </span>
      </div>
      <div className="ml-auto flex items-center gap-1.5">
        <button
          type="button"
          onClick={() => onOpenMethods('methods')}
          className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-surface px-2.5 py-1.5 text-[11px] font-semibold text-ink-2 hover:border-accent hover:text-accent"
        >
          <span className="flex h-[15px] w-[15px] items-center justify-center rounded-full border border-current text-[9px] font-bold italic">
            i
          </span>
          Methods
        </button>
        <button
          type="button"
          onClick={() => onOpenMethods('provenance')}
          className="inline-flex items-center rounded-lg border border-line bg-surface px-2.5 py-1.5 text-[11px] font-semibold text-ink-2 hover:border-accent hover:text-accent"
        >
          Provenance
        </button>
      </div>
    </header>
  );
}
