// Focused accessibility checks: landmark roles, an active nav step marked
// aria-current, segmented controls exposing pressed state, and reachable dialog
// affordances. Renders in demo mode so the interactive controls are present.

import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import App from '../App';

function goto(url: string) {
  window.history.pushState({}, '', url);
}

afterEach(() => {
  cleanup();
  goto('/02_page.html');
});

describe('accessibility', () => {
  it('exposes navigation + main landmarks and marks the active step aria-current', () => {
    goto('/02_page.html?demo=1#/stage-3');
    render(<App />);
    expect(screen.getByRole('navigation', { name: /pipeline stages/i })).toBeInTheDocument();
    expect(screen.getByRole('main')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Drug link/ })).toHaveAttribute('aria-current', 'page');
  });

  it('segmented objective view exposes a pressed state', () => {
    goto('/02_page.html?demo=1#/stage-2');
    render(<App />);
    const group = screen.getByRole('group', { name: /objective view/i });
    const buttons = within(group).getAllByRole('button');
    expect(buttons.length).toBe(3);
    expect(buttons.some((b) => b.getAttribute('aria-pressed') === 'true')).toBe(true);
  });

  it('opens a labelled modal dialog from the Methods & provenance control', () => {
    goto('/02_page.html?demo=1#/stage-2');
    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: /Methods & provenance/ }));
    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(dialog).toHaveAccessibleName();
  });

  it('empty scaffold uses region landmarks, not fake data', () => {
    goto('/02_page.html#/stage-2');
    render(<App />);
    expect(screen.getByLabelText('No selection')).toBeInTheDocument();
    expect(within(screen.getByRole('main')).getByText('no artifact')).toBeInTheDocument();
  });
});
