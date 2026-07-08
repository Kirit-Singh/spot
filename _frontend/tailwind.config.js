/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: '#FAF9F7', surface: '#FFFFFF', sunken: '#F4F2EE',
        line: '#E7E3DC', 'line-strong': '#D6D0C6',
        ink: '#1E1B16', 'ink-2': '#5C564C', muted: '#8A8172',
        rep: '#0E7C86', con: '#4C56C0', gen: '#9A3E9C', pred: '#9A6B12',
        warn: '#C2410C', hit: '#111827', gold: '#FFB020',
      },
      fontFamily: {
        sans: ['"Inter Tight"', 'system-ui', 'sans-serif'],
        serif: ['"Newsreader"', 'Georgia', 'serif'],
        mono: ['"IBM Plex Mono"', 'ui-monospace', 'monospace'],
      },
    },
  },
  plugins: [],
}
