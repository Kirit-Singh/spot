import { EvidenceGraph } from './components/EvidenceGraph'
import { Legend } from './components/Legend'

export default function App() {
  return (
    <div className="flex h-screen flex-col bg-bg font-sans text-ink">
      <header className="flex h-[52px] flex-none items-center gap-3 border-b border-line px-4">
        <span className="font-serif text-lg">spot</span>
        <span className="text-sm text-ink-2">
          hit · <b className="font-semibold text-ink">RASA2</b> · CD4+ T · Stim
        </span>
        <span className="ml-auto rounded-full border border-line bg-surface px-3 py-1 font-mono text-xs text-ink-2">
          live · 6/8 resolved
        </span>
      </header>
      <div className="flex min-h-0 flex-1">
        <aside className="w-60 flex-none border-r border-line p-4">
          <Legend />
        </aside>
        <main className="relative min-w-0 flex-1">
          <EvidenceGraph />
        </main>
      </div>
    </div>
  )
}
