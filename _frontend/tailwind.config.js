/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      // Stage-1 shell reflow breakpoint: the main+rail split collapses to a single
      // column at/under 720px (min-width 721px keeps the 340px side rail).
      screens: {
        rail: '721px',
      },
      colors: {
        // Stage-1 Spot design language (source of truth: 01_programs/app/01_page.html)
        bg: '#FAF9F7', surface: '#FFFFFF', sunken: '#F4F2EE',
        line: '#E7E3DC', 'line-strong': '#D6D0C6',
        ink: '#1E1B16', 'ink-2': '#5C564C', muted: '#8A8172',
        accent: '#3E7D8C', treg: '#9A3E9C',
        // Ordered contrast axes from the approved :8347 baseline (A/From teal, B/To amber).
        // Distinct from the general UI `accent` (focus/navigation) and `treg` (program semantic).
        'pole-a': '#2D7C8E', 'pole-b': '#D69834',
        // restrained status hues (evidence state / decision tier / attention)
        ok: '#2E7D5B', amber: '#B9770E', danger: '#C0392B',
        // retained legacy tokens
        rep: '#0E7C86', con: '#4C56C0', gen: '#9A3E9C', pred: '#9A6B12',
        warn: '#C2410C', hit: '#111827', gold: '#FFB020',
      },
      fontFamily: {
        sans: ['"Inter Tight"', 'system-ui', 'sans-serif'],
        serif: ['"Newsreader"', 'Georgia', 'serif'],
        mono: ['"IBM Plex Mono"', 'ui-monospace', 'monospace'],
      },
      borderRadius: { xl2: '11px' },
      boxShadow: {
        pop: '0 8px 28px rgba(30,27,22,.16)',
        drawer: '-24px 0 64px rgba(30,27,22,.28)',
      },
    },
  },
  plugins: [],
}
