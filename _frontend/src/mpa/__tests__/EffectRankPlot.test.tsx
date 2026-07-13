import { cleanup, fireEvent, render } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { CompactEffectRankFacet, CompactTargetArm } from '../../domain/compactStage2Projection';
import { EffectRankPlot, effectRankPoints } from '../EffectRankPlot';

afterEach(cleanup);

function arm(side: 'increase' | 'decrease'): CompactTargetArm {
  return {
    lane: 'direct', arm_key: `direct|program_x|${side}|Rest`, context: { condition: 'Rest' },
    source_bundle: 'direct/Rest', n_rows_total: 10, n_evaluable: 10, n_ranked: 10,
    n_emitted: 6, cap: 100, is_a_prefix: true,
    rows: Array.from({ length: 6 }, (_, i) => ({
      target_id: `ENSG${String(10_000_000_001 + i + (side === 'increase' ? 100 : 0))}`,
      target_symbol: `${side === 'increase' ? 'UP' : 'DOWN'}${i + 1}`,
      rank: i + 1, arm_value: 0.6 - i * 0.05,
    })),
  };
}

const facet: CompactEffectRankFacet = {
  role: 'A', program_id: 'program_x', increase: arm('increase'), decrease: arm('decrease'),
};

const points = (container: HTMLElement) => container.querySelectorAll('svg g[role="img"][tabindex="0"]');

describe('EffectRankPlot', () => {
  it('uses exact signed arm values and descriptive rank evidence, never a p/q statistic', () => {
    const p = effectRankPoints(facet);
    expect(p.find((q) => q.side === 'increase')?.shift).toBe(0.6);
    expect(p.find((q) => q.side === 'decrease')?.shift).toBe(-0.6);
    expect(p.find((q) => q.rank === 1)?.evidence).toBeCloseTo(1); // -log10(1/10)
  });

  it('labels only ranks 1–5 on each side and keeps all points keyboard focusable', () => {
    const { container } = render(<EffectRankPlot facet={facet} />);
    const plotText = [...container.querySelectorAll('svg text')].map((node) => node.textContent);
    for (const side of ['UP', 'DOWN']) {
      for (let rank = 1; rank <= 5; rank += 1) expect(plotText).toContain(`${side}${rank}`);
      expect(plotText).not.toContain(`${side}6`);
    }
    expect(points(container)).toHaveLength(12); // every point reachable by keyboard, labelled or not
    expect(container.textContent).not.toMatch(/p.?value|q.?value|fdr|significance/i);
  });

  it('keeps the top-ranked point inside the frame: every axis bound clears its extreme value', () => {
    const { container } = render(<EffectRankPlot facet={facet} />);
    const ticks = [...container.querySelectorAll('svg text')]
      .map((n) => Number(n.textContent))
      .filter((n) => Number.isFinite(n));
    // rank-1 evidence is exactly 1.0 and |shift| peaks at exactly 0.6 — both already "round", so a
    // bound that merely rounds up would place them ON the frame. The axis must clear them outright.
    expect(Math.max(...ticks)).toBeGreaterThan(1);
    expect(Math.max(...ticks.filter((t) => t <= 1))).toBeGreaterThan(0.6);
  });

  it('paints the top-ranked targets last, so they sit on top of the dense lobe and win the pointer', () => {
    const { container } = render(<EffectRankPlot facet={facet} />);
    const ranks = [...points(container)].map((g) => {
      const label = g.getAttribute('aria-label') ?? '';
      return Number(/rank (\d+) of/.exec(label)?.[1]);
    });
    // later in document order = painted on top; rank 1 must be among the last painted
    const decrease = ranks.filter((_, i) => i < ranks.length / 2);
    expect(decrease[decrease.length - 1]).toBeLessThan(decrease[0]);
  });

  it('emphasises the active gene and pins it on click, without navigating away', () => {
    const onPin = vi.fn();
    const onHover = vi.fn();
    const { container, rerender } = render(
      <EffectRankPlot facet={facet} onPin={onPin} onHover={onHover} />,
    );
    // a point is not an anchor: clicking selects the gene rather than leaving the workbench
    expect(container.querySelectorAll('svg a')).toHaveLength(0);

    const rank1 = [...points(container)].find((g) =>
      (g.getAttribute('aria-label') ?? '').startsWith('DOWN1,'),
    ) as Element;
    fireEvent.mouseEnter(rank1);
    expect(onHover).toHaveBeenCalledWith('ENSG10000000001');
    fireEvent.click(rank1);
    expect(onPin).toHaveBeenCalledWith('ENSG10000000001');

    // the active gene's detail — including its official HPA link — renders in the facet's card
    rerender(<EffectRankPlot facet={facet} activeId="ENSG10000000001" pinnedId="ENSG10000000001" />);
    expect(container.textContent).toContain('signed shift -0.6');
    expect(container.textContent).toContain('rank 1/10');
    const hpa = container.querySelector('a[href^="https://www.proteinatlas.org/"]');
    expect(hpa).toHaveAttribute('href', 'https://www.proteinatlas.org/ENSG10000000001');
    expect(hpa).toHaveAttribute('target', '_blank');
    expect(hpa?.getAttribute('rel')).toContain('noopener');
  });
});
