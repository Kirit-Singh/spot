import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { StageNav } from '../StageNav';

describe('StageNav — active step visibility', () => {
  afterEach(() => vi.restoreAllMocks());

  it('marks the current step with aria-current=page', () => {
    render(<StageNav current="stage-4" onNavigate={() => {}} />);
    const active = screen.getByRole('button', { name: /PK . PD . brain/ });
    expect(active).toHaveAttribute('aria-current', 'page');
  });

  it('scrolls the active step into the nav viewport on load', () => {
    const spy = vi.spyOn(Element.prototype, 'scrollIntoView');
    render(<StageNav current="stage-4" onNavigate={() => {}} />);
    expect(spy).toHaveBeenCalled();
    // Horizontal-only: never a vertical page jump.
    const arg = spy.mock.calls.at(-1)?.[0] as ScrollIntoViewOptions | undefined;
    expect(arg).toMatchObject({ inline: 'nearest', block: 'nearest' });
  });

  it('re-scrolls the active step on route change', () => {
    const spy = vi.spyOn(Element.prototype, 'scrollIntoView');
    const { rerender } = render(<StageNav current="stage-2" onNavigate={() => {}} />);
    const first = spy.mock.calls.length;
    rerender(<StageNav current="stage-4" onNavigate={() => {}} />);
    expect(spy.mock.calls.length).toBeGreaterThan(first);
  });
});
