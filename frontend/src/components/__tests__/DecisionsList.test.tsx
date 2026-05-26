// Coverage for the post-review spec contracts added in Commit 2:
//   1. loading=true renders the "Loading…" line above the table
//   2. empty state copy includes "No <tab> pages match these filters.
//      (N approved pages total.)" when approvedTotal is known

import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { DecisionsList } from '../DecisionsList';

describe('DecisionsList', () => {
  it('renders the Loading… line above the table while loading', () => {
    render(
      <DecisionsList
        items={[]}
        total={0}
        page={1}
        perPage={50}
        loading
        tabLabel="approved"
        approvedTotal={312}
        selectedStem={null}
        onSelect={vi.fn()}
        onPage={vi.fn()}
        onReset={vi.fn()}
      />,
    );
    // Loading status line is exposed via aria role="status".
    expect(screen.getByRole('status')).toHaveTextContent(/loading/i);
  });

  it("shows '(N approved pages total)' in the empty-state copy", () => {
    render(
      <DecisionsList
        items={[]}
        total={0}
        page={1}
        perPage={50}
        loading={false}
        tabLabel="approved"
        approvedTotal={312}
        selectedStem={null}
        onSelect={vi.fn()}
        onPage={vi.fn()}
        onReset={vi.fn()}
      />,
    );
    // The empty-state copy is split across span text — assert via
    // the flattened textContent of the empty <p>.
    const empty = screen.getByText(/no approved pages match these filters/i);
    expect(empty.textContent).toMatch(/\(312 approved pages total\.\)/);
  });
});
