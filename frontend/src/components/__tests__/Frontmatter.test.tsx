// Coverage for Frontmatter — the Pending tab's <dl> strip.
// Regression: array-of-objects frontmatter values (kanban_dispatches)
// used to render as `[object Object]` because formatValue() called
// String() on each element.

import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Frontmatter } from '../Frontmatter';

describe('Frontmatter', () => {
  it('renders array-of-objects values as a readable summary, not [object Object]', () => {
    render(
      <Frontmatter
        fm={{
          type: 'improvement',
          kanban_dispatches: [
            {
              task: 't_8625a449',
              board: 'default',
              dispatched_at: '2026-05-26 11:52',
            },
            { task: 't_19fab712', board: 'ops' },
          ],
        }}
      />,
    );

    const value = screen.getByText(/t_8625a449/);
    expect(value.textContent).not.toContain('[object Object]');
    expect(value.textContent).toMatch(/task=t_8625a449/);
    expect(value.textContent).toMatch(/board=default/);
    expect(value.textContent).toMatch(/dispatched_at=2026-05-26 11:52/);
    expect(value.textContent).toMatch(/task=t_19fab712/);
  });

  it('renders a single plain object as key=value pairs', () => {
    render(
      <Frontmatter
        fm={{
          type: 'concept',
          provenance: { agent: 'memory-daily', model: 'claude-opus-4-7' },
        }}
      />,
    );

    const value = screen.getByText(/agent=memory-daily/);
    expect(value.textContent).not.toContain('[object Object]');
    expect(value.textContent).toMatch(/model=claude-opus-4-7/);
  });

  it('still renders primitive arrays comma-joined', () => {
    render(
      <Frontmatter
        fm={{
          type: 'entity',
          tags: ['hermes', 'zombie'],
        }}
      />,
    );

    expect(screen.getByText('hermes, zombie')).toBeInTheDocument();
  });
});
