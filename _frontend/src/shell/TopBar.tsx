// Top brand bar, matching Stage-1: 'spot' in Newsreader with a teal middot, a
// stage subtitle sharing one baseline, and a Methods & provenance button.

export function TopBar({
  subtitle,
  onOpenMethods,
}: {
  subtitle: string;
  onOpenMethods: () => void;
}) {
  return (
    <header className="flex h-[50px] flex-none items-center gap-3 border-b border-line bg-surface px-5">
      <div className="flex min-w-0 items-baseline gap-3">
        <span className="font-editorial text-[20px] font-medium">
          spot<b className="text-accent">·</b>
        </span>
        <span className="flex items-baseline gap-2 border-l border-line pl-3">
          <span className="font-editorial text-[16px] font-medium text-ink">{subtitle}</span>
        </span>
      </div>
      <div className="ml-auto flex items-center gap-2.5">
        <button
          type="button"
          onClick={onOpenMethods}
          className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-surface px-2.5 py-1.5 text-[11px] font-semibold text-ink-2 hover:border-accent hover:text-accent"
        >
          <span className="flex h-[15px] w-[15px] items-center justify-center rounded-full border border-current text-[9px] font-bold italic">
            i
          </span>
          <span className="hidden sm:inline">Methods &amp; provenance</span>
        </button>
      </div>
    </header>
  );
}
