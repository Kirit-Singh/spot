import { EVIDENCE } from '../design/tokens'

const STATES = [
  { key: 'confirmed', color: '#5C564C', dashed: false },
  { key: 'untested', color: '#8A8172', dashed: true },
  { key: 'contradicted', color: '#C2410C', dashed: false },
] as const

function Line({ color, dashed = false, width = 3 }: { color: string; dashed?: boolean; width?: number }) {
  return (
    <svg width="42" height="12" aria-hidden="true">
      <line
        x1="2" y1="6" x2="40" y2="6"
        stroke={color} strokeWidth={width}
        strokeDasharray={dashed ? '5 4' : undefined}
        opacity={dashed ? 0.55 : 1} strokeLinecap="round"
      />
    </svg>
  )
}

export function Legend() {
  return (
    <div>
      <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">Evidence</p>
      <div className="rounded-xl border border-line bg-surface p-3">
        {Object.entries(EVIDENCE).map(([key, v]) => (
          <div key={key} className="flex items-center gap-2.5 py-1 text-sm">
            <Line color={v.color} dashed={key === 'predictive'} width={key === 'predictive' ? 2 : 3} />
            {key}
          </div>
        ))}
        <div className="my-2 h-px bg-line" />
        {STATES.map((s) => (
          <div key={s.key} className="flex items-center gap-2.5 py-1 text-sm">
            <Line color={s.color} dashed={s.dashed} />
            {s.key}
          </div>
        ))}
      </div>
    </div>
  )
}
