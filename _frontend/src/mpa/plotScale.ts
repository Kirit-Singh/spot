// Axis + label-placement helpers for the effect–rank facets. Pure geometry only: no scientific
// semantics live here. The plot component stays presentational and these stay unit-testable.

/** The "nice" ladder a tick step snaps to, per decade. */
const LADDER = [1, 1.25, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10];

/** Round a float to 12 significant digits, killing 0.30000000000000004-style drift in tick values. */
const clean = (n: number): number => Number(n.toPrecision(12));

/** Smallest nice tick step ≥ v, from the ladder above. */
export function niceStep(v: number): number {
  if (!Number.isFinite(v) || v <= 0) return 1;
  const pow = Math.pow(10, Math.floor(Math.log10(v)));
  const f = v / pow; // 1 ≤ f < 10
  const step = LADDER.find((s) => f <= s + 1e-9) ?? 10;
  return clean(step * pow);
}

export interface Axis {
  floor: number;
  bound: number;
  step: number;
}

/**
 * An axis on round steps that CLEARS both extremes: the bound lies strictly above `max` and the floor
 * strictly below `min`, so neither the top- nor the bottom-ranked target is ever drawn on the frame.
 * An extreme that is already round (1.0, 0.5) is pushed out one further step rather than touched.
 *
 * The floor is derived, never assumed. Rank evidence bottoms out at log10(n_ranked / cap), which moves
 * with each arm's ranked count — and collapses to 0 when an arm ranks fewer targets than the cap — so
 * a fixed floor would misdraw other selections. It is clamped at 0, which −log10(rank/N) cannot go below.
 */
export function axisRange(min: number, max: number, intervals = 4): Axis {
  const hi = Number.isFinite(max) && max > 0 ? max : 1;
  const lo = Number.isFinite(min) && min > 0 ? Math.min(min, hi) : 0;
  const step = niceStep(Math.max(hi - lo, hi * 0.05, 1e-9) / intervals);

  let bound = clean(Math.ceil(hi / step) * step);
  if (bound <= hi) bound = clean(bound + step);

  let floor = clean(Math.floor(lo / step) * step);
  if (floor >= lo) floor = clean(floor - step);
  if (floor < 0) floor = 0;

  return { floor, bound, step };
}

/** A symmetric −bound…0…+bound axis. Zero is the no-shift line and always stays on the plot. */
export function axisSymmetric(max: number, intervals = 2): Axis {
  const { bound, step } = axisRange(0, max, intervals);
  return { floor: -bound, bound, step };
}

/** Ticks floor, floor+step … bound. Every tick is a whole multiple of the step, so all read round. */
export function ticksFrom({ floor, bound, step }: Axis): number[] {
  const out: number[] = [];
  for (let v = floor; v <= bound + 1e-9; v = clean(v + step)) out.push(clean(v));
  return out;
}

export interface PlacedLabel {
  id: string;
  text: string;
  x: number;
  y: number;
  anchor: 'start' | 'end';
}

interface LabelInput {
  id: string;
  text: string;
  /** anchor point of the datum, in SVG user units */
  px: number;
  py: number;
  /** which way the label prefers to extend from its point */
  side: 'increase' | 'decrease';
}

export interface LabelBounds {
  left: number;
  right: number;
  top: number;
  bottom: number;
}

const CHAR_W = 5.1; // ~8.5px mono advance width
const GAP = 10.5; // minimum vertical distance between two labels on the same side
const OFFSET = 5; // horizontal distance from the point to its text

/**
 * Place the top-ranked labels so they neither overlap each other nor leave the plot frame.
 *
 * Top-ranked points cluster tightly at the top of each lobe, so labels are laddered downward with a
 * minimum vertical gap, then clamped inside `bounds`. A label that would overrun its edge flips to
 * the opposite anchor rather than being clipped. Purely cosmetic: point positions never move, and
 * which points get labelled is decided by the caller (top-five rank), not here.
 */
export function layoutLabels(items: LabelInput[], bounds: LabelBounds): PlacedLabel[] {
  const out: PlacedLabel[] = [];

  for (const side of ['decrease', 'increase'] as const) {
    const lane = items.filter((i) => i.side === side).sort((a, b) => a.py - b.py);
    let lastY = -Infinity;

    for (const item of lane) {
      const y = Math.min(Math.max(item.py, bounds.top + GAP, lastY + GAP), bounds.bottom);
      lastY = y;

      const width = item.text.length * CHAR_W;
      // Prefer extending outward (decrease → left, increase → right); flip in rather than clip.
      let anchor: 'start' | 'end' = side === 'increase' ? 'start' : 'end';
      let x = side === 'increase' ? item.px + OFFSET : item.px - OFFSET;
      if (anchor === 'end' && x - width < bounds.left) {
        anchor = 'start';
        x = item.px + OFFSET;
      } else if (anchor === 'start' && x + width > bounds.right) {
        anchor = 'end';
        x = item.px - OFFSET;
      }

      out.push({ id: item.id, text: item.text, x, y, anchor });
    }
  }

  return out;
}
