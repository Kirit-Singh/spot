// Persistent demo banner shown only under ?demo=1: an unmistakable synthetic marker
// so demo output can never be confused with analysis. Exit drops the demo flag.

export function DemoBar() {
  const exitHref = typeof window !== 'undefined' ? window.location.pathname : '/';
  return (
    <section
      aria-label="Demo mode"
      className="flex flex-none flex-wrap items-center gap-x-3 gap-y-1.5 border-b border-line bg-sunken/60 px-5 py-2"
    >
      <span className="inline-flex items-center rounded-md border border-amber/50 bg-amber/10 px-1.5 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wide text-amber">
        demo · synthetic
      </span>
      <span className="font-mono text-[10.5px] text-muted">artifact_class=fixture</span>
      <a href={exitHref} className="ml-auto font-mono text-[10.5px] text-accent hover:underline">
        exit
      </a>
    </section>
  );
}
