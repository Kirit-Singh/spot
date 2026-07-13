// Per-stage routing to the Methods (notebook) and Provenance (trace) views. A quiet footer
// link pair in the clean design language — no banner, no counts, no editorial badge.

import { notebookHref, traceHref, STAGE_VIEWS } from './methodsRoutes';
import type { PageKey } from './pages';
import type { StageView } from './methodsRoutes';

export function MethodsLinks({ page }: { page: PageKey }) {
  if (!STAGE_VIEWS.includes(page as StageView)) return null;
  const stage = page as StageView;
  return (
    <div className="flex flex-none items-center gap-4 border-t border-line px-5 py-2">
      <span className="font-mono text-[10px] uppercase tracking-wide text-muted">Methods &amp; provenance</span>
      <a href={notebookHref(stage)} className="font-mono text-[11px] text-accent hover:underline">
        Methods ↗
      </a>
      <a href={traceHref(stage)} className="font-mono text-[11px] text-accent hover:underline">
        Provenance trace ↗
      </a>
    </div>
  );
}
