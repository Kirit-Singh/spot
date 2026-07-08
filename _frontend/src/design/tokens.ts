// spot design tokens (code source of truth; mirrors the Claude Design system).
export const EVIDENCE = {
  replication: { color: '#0E7C86', label: 'replication' },
  consistency: { color: '#4C56C0', label: 'consistency' },
  genetic: { color: '#9A3E9C', label: 'genetic' },
  predictive: { color: '#9A6B12', label: 'predictive' },
} as const

export type EvidenceType = keyof typeof EVIDENCE

export const COLORS = {
  bg: '#FAF9F7', surface: '#FFFFFF', line: '#E7E3DC',
  ink: '#1E1B16', ink2: '#5C564C', muted: '#8A8172',
  warn: '#C2410C', hit: '#111827', gold: '#FFB020',
} as const
