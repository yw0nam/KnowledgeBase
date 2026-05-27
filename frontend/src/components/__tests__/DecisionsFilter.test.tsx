// Coverage for the post-review spec contracts added in Commit 2:
//   1. tab change → subtitle changes
//   2. per-chip × removes a single value + Clear all (N) clears everything

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { DecisionsFilter } from '../DecisionsFilter';
import type { UrlFilters } from '../../hooks/useUrlFilters';

interface MockResponseInit {
  status?: number;
  body?: unknown;
}

function mockResponse({ status = 200, body = {} }: MockResponseInit): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? 'OK' : 'ERR',
    json: async () => body,
  } as unknown as Response;
}

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  globalThis.fetch = fetchMock as unknown as typeof fetch;
  fetchMock.mockResolvedValue(mockResponse({ body: { categories: [] } }));
});

afterEach(() => {
  vi.useRealTimers();
});

function buildFilters(overrides: Partial<UrlFilters> = {}): UrlFilters {
  return {
    tab: 'approved',
    type: [],
    category: [],
    source: [],
    editedSince: null,
    stem: null,
    setTab: vi.fn(),
    setType: vi.fn(),
    setCategory: vi.fn(),
    setSource: vi.fn(),
    setEditedSince: vi.fn(),
    setStem: vi.fn(),
    clearAll: vi.fn(),
    activeFilterCount: 0,
    ...overrides,
  };
}

describe('DecisionsFilter', () => {
  it('renders the active tab subtitle and swaps when the tab changes', () => {
    const { rerender } = render(
      <MemoryRouter>
        <DecisionsFilter filters={buildFilters({ tab: 'approved' })} />
      </MemoryRouter>,
    );
    expect(screen.getByText(/pages you've approved/i)).toBeInTheDocument();

    rerender(
      <MemoryRouter>
        <DecisionsFilter filters={buildFilters({ tab: 'dispatched' })} />
      </MemoryRouter>,
    );
    expect(
      screen.getByText(/sent to kanban that haven't returned a status/i),
    ).toBeInTheDocument();
  });

  it('per-chip × removes a single value and Clear all (N) wipes them', () => {
    const setType = vi.fn();
    const setSource = vi.fn();
    const clearAll = vi.fn();
    const filters = buildFilters({
      type: ['entity', 'concept'],
      source: ['github'],
      activeFilterCount: 3,
      setType,
      setSource,
      clearAll,
    });

    render(
      <MemoryRouter>
        <DecisionsFilter filters={filters} />
      </MemoryRouter>,
    );

    // × on the type:concept chip removes only that value.
    act(() => {
      fireEvent.click(
        screen.getByRole('button', { name: /remove type filter concept/i }),
      );
    });
    expect(setType).toHaveBeenCalledWith(['entity']);

    // Clear all (3) is visible because activeFilterCount >= 2.
    const clearAllBtn = screen.getByRole('button', { name: /clear all \(3\)/i });
    act(() => {
      fireEvent.click(clearAllBtn);
    });
    expect(clearAll).toHaveBeenCalledTimes(1);
  });
});
