// Coverage for useUrlFilters — the Decisions browser's filter state
// is mirrored to the URL so reload restores tab/filters/selection.
//
// Spec §9.2: 2 tests
//   1. filter change → URL update
//   2. URL → filter state restoration round-trip

import { describe, expect, it } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { createElement, type ReactNode } from 'react';
import { useUrlFilters } from '../useUrlFilters';

function wrapper(initialEntries: string[]) {
  return ({ children }: { children: ReactNode }) =>
    createElement(MemoryRouter, { initialEntries }, children);
}

describe('useUrlFilters', () => {
  it('writes filter changes into the URL search string', () => {
    const { result, rerender } = renderHook(
      () => {
        const filters = useUrlFilters();
        const location = useLocation();
        return { filters, search: location.search };
      },
      { wrapper: wrapper(['/decisions']) },
    );

    expect(result.current.filters.tab).toBe('approved');
    expect(result.current.filters.type).toEqual([]);

    act(() => {
      result.current.filters.setTab('rejected');
    });
    rerender();
    expect(result.current.search).toContain('tab=rejected');

    act(() => {
      result.current.filters.setType(['entity', 'concept']);
    });
    rerender();
    // multi-valued -> repeated query keys.
    expect(result.current.search).toContain('type=entity');
    expect(result.current.search).toContain('type=concept');

    act(() => {
      result.current.filters.setStem('hermes-zombie-session');
    });
    rerender();
    expect(result.current.search).toContain('stem=hermes-zombie-session');
  });

  it('round-trips: a URL with all filters restores into hook state', () => {
    const url =
      '/decisions?tab=dispatched&type=improvement&type=checklist&category=process&source=github&edited_since=2026-05-01&stem=promote-cron-flow';
    const { result } = renderHook(() => useUrlFilters(), {
      wrapper: wrapper([url]),
    });

    expect(result.current.tab).toBe('dispatched');
    expect(result.current.type).toEqual(['improvement', 'checklist']);
    expect(result.current.category).toEqual(['process']);
    expect(result.current.source).toEqual(['github']);
    expect(result.current.editedSince).toBe('2026-05-01');
    expect(result.current.stem).toBe('promote-cron-flow');
  });
});
