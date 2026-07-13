import { cleanup, render } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
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

describe('EffectRankPlot', () => {
  it('uses exact signed arm values and descriptive rank evidence, never a p/q statistic', () => {
    const points = effectRankPoints(facet);
    expect(points.find((p) => p.side === 'increase')?.shift).toBe(0.6);
    expect(points.find((p) => p.side === 'decrease')?.shift).toBe(-0.6);
    expect(points.find((p) => p.rank === 1)?.evidence).toBeCloseTo(1); // -log10(1/10)
  });

  it('labels only ranks 1–5 on each side and keeps all points keyboard focusable', () => {
    const { container } = render(<EffectRankPlot facet={facet} />);
    const plotText = [...container.querySelectorAll('svg text')].map((node) => node.textContent);
    for (const side of ['UP', 'DOWN']) {
      for (let rank = 1; rank <= 5; rank += 1) expect(plotText).toContain(`${side}${rank}`);
      expect(plotText).not.toContain(`${side}6`);
    }
    expect(container.querySelectorAll('svg a[aria-label]')).toHaveLength(12);
    expect(container.textContent).not.toMatch(/p.?value|q.?value|fdr|significance/i);
  });
});
