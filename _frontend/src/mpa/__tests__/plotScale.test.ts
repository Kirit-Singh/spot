import { describe, expect, it } from 'vitest';
import { axisRange, axisSymmetric, layoutLabels, niceStep, ticksFrom } from '../plotScale';

/** Rank evidence for the worst / best emitted rank of an arm: −log10(rank / n_ranked). */
const evidence = (rank: number, nRanked: number) => -Math.log10(rank / nRanked);

describe('axis bounds', () => {
  it('snaps the tick step to the nice ladder', () => {
    expect(niceStep(0.442)).toBe(0.5);
    expect(niceStep(0.958)).toBe(1);
    expect(niceStep(7.2)).toBe(8);
  });

  it('clears both extremes, so neither the top- nor bottom-ranked point sits on the frame', () => {
    for (const [min, max] of [[1.833, 3.833], [0.7, 2.7], [0, 1], [0.5, 0.5]] as const) {
      const axis = axisRange(min, max);
      expect(axis.bound).toBeGreaterThan(max);
      expect(axis.floor).toBeLessThan(min === 0 ? 0.0001 : min);
    }
  });

  it('floors just under the real data on a round step, not on a hardcoded value', () => {
    // the live arm: 6,815 ranked, top-100 prefix → evidence spans 1.833…3.833
    const axis = axisRange(evidence(100, 6815), evidence(1, 6815), 4);
    expect(axis).toEqual({ floor: 1.5, bound: 4, step: 0.5 });
    expect(ticksFrom(axis)).toEqual([1.5, 2, 2.5, 3, 3.5, 4]);
  });

  it('moves the floor with the arm — a smaller ranked set floors lower, never at a fixed 1.5', () => {
    // 500 ranked, same top-100 prefix → evidence bottoms out at log10(5) ≈ 0.7, not 1.83
    const axis = axisRange(evidence(100, 500), evidence(1, 500), 4);
    expect(axis.floor).toBeLessThan(0.7);
    expect(axis.floor).toBeGreaterThanOrEqual(0);
  });

  it('floors at zero when an arm ranks fewer targets than the cap', () => {
    // 80 ranked, 80 emitted → the worst emitted rank IS N, so evidence reaches exactly 0
    const axis = axisRange(evidence(80, 80), evidence(1, 80), 4);
    expect(axis.floor).toBe(0); // −log10(rank/N) cannot go below 0, and the axis never does either
  });

  it('keeps the no-shift line on a symmetric signed axis', () => {
    const x = axisSymmetric(0.884, 2);
    expect(ticksFrom(x)).toEqual([-1, -0.5, 0, 0.5, 1]);
    expect(x.bound).toBeGreaterThan(0.884);
  });

  it('degrades safely on an empty or non-finite range', () => {
    expect(axisRange(0, 0).bound).toBeGreaterThan(0);
    expect(axisRange(Number.NaN, Number.NaN).bound).toBeGreaterThan(0);
  });
});

describe('label placement', () => {
  const bounds = { left: 46, right: 624, top: 16, bottom: 202 };

  it('separates labels that would otherwise overprint each other', () => {
    // five top-ranked points stacked within 3px, as the real top-five cluster is
    const items = Array.from({ length: 5 }, (_, i) => ({
      id: `g${i}`, text: `GENE${i}`, px: 100, py: 20 + i * 0.7, side: 'decrease' as const,
    }));
    const placed = layoutLabels(items, bounds);
    const ys = placed.map((p) => p.y).sort((a, b) => a - b);
    for (let i = 1; i < ys.length; i += 1) expect(ys[i] - ys[i - 1]).toBeGreaterThanOrEqual(10);
  });

  it('keeps every label inside the frame, flipping its anchor rather than clipping', () => {
    const placed = layoutLabels(
      [
        { id: 'l', text: 'LONGSYMBOL', px: 50, py: 100, side: 'decrease' }, // hard against the left edge
        { id: 'r', text: 'LONGSYMBOL', px: 620, py: 100, side: 'increase' }, // hard against the right
      ],
      bounds,
    );
    expect(placed.find((p) => p.id === 'l')?.anchor).toBe('start'); // flipped inward
    expect(placed.find((p) => p.id === 'r')?.anchor).toBe('end');
    for (const p of placed) {
      expect(p.y).toBeGreaterThanOrEqual(bounds.top);
      expect(p.y).toBeLessThanOrEqual(bounds.bottom);
    }
  });
});
