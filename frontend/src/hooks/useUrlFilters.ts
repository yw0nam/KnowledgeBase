// Decisions browser filter state, mirrored to the URL so reload
// restores tab + filters + inspector selection. See spec §7.2.
//
// Active tab values map 1-1 to `review_status` filter values on the
// backend. They cover the union of (`approved`, `rejected`,
// `dispatched`, `unprocessed`); no "all" tab.

import { useCallback, useMemo } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

export type DecisionsTab = 'approved' | 'rejected' | 'dispatched' | 'unprocessed';

const VALID_TABS: ReadonlySet<DecisionsTab> = new Set<DecisionsTab>([
  'approved',
  'rejected',
  'dispatched',
  'unprocessed',
]);

export interface UrlFilters {
  tab: DecisionsTab;
  type: string[];
  category: string[];
  source: string[];
  editedSince: string | null;
  stem: string | null;
  setTab: (next: DecisionsTab) => void;
  setType: (next: string[]) => void;
  setCategory: (next: string[]) => void;
  setSource: (next: string[]) => void;
  setEditedSince: (next: string | null) => void;
  setStem: (next: string | null) => void;
  clearAll: () => void;
  activeFilterCount: number;
}

function readMulti(params: URLSearchParams, key: string): string[] {
  return params.getAll(key).filter((v) => v.length > 0);
}

function parseTab(raw: string | null): DecisionsTab {
  if (raw && VALID_TABS.has(raw as DecisionsTab)) {
    return raw as DecisionsTab;
  }
  return 'approved';
}

export function useUrlFilters(): UrlFilters {
  const location = useLocation();
  const navigate = useNavigate();

  const params = useMemo(() => new URLSearchParams(location.search), [location.search]);

  const tab = parseTab(params.get('tab'));
  const type = readMulti(params, 'type');
  const category = readMulti(params, 'category');
  const source = readMulti(params, 'source');
  const editedSince = params.get('edited_since');
  const stem = params.get('stem');

  const replace = useCallback(
    (mutate: (p: URLSearchParams) => void) => {
      const next = new URLSearchParams(location.search);
      mutate(next);
      const search = next.toString();
      navigate(
        { pathname: location.pathname, search: search ? `?${search}` : '' },
        { replace: true },
      );
    },
    [location.pathname, location.search, navigate],
  );

  const setTab = useCallback(
    (next: DecisionsTab) => {
      replace((p) => {
        if (next === 'approved') p.delete('tab');
        else p.set('tab', next);
      });
    },
    [replace],
  );

  // setType / setCategory / setSource are memoized over `replace`
  // so consumers that read filters.setType from useEffect deps don't
  // re-fire on every parent render. The whole `filters` object still
  // re-renders fresh, but the inner callbacks are stable.
  const setType = useCallback(
    (next: string[]) => {
      replace((p) => {
        p.delete('type');
        for (const v of next) if (v) p.append('type', v);
      });
    },
    [replace],
  );
  const setCategory = useCallback(
    (next: string[]) => {
      replace((p) => {
        p.delete('category');
        for (const v of next) if (v) p.append('category', v);
      });
    },
    [replace],
  );
  const setSource = useCallback(
    (next: string[]) => {
      replace((p) => {
        p.delete('source');
        for (const v of next) if (v) p.append('source', v);
      });
    },
    [replace],
  );

  const setEditedSince = useCallback(
    (next: string | null) => {
      replace((p) => {
        if (next) p.set('edited_since', next);
        else p.delete('edited_since');
      });
    },
    [replace],
  );

  const setStem = useCallback(
    (next: string | null) => {
      replace((p) => {
        if (next) p.set('stem', next);
        else p.delete('stem');
      });
    },
    [replace],
  );

  const clearAll = useCallback(() => {
    replace((p) => {
      p.delete('type');
      p.delete('category');
      p.delete('source');
      p.delete('edited_since');
    });
  }, [replace]);

  const activeFilterCount =
    type.length + category.length + source.length + (editedSince ? 1 : 0);

  return {
    tab,
    type,
    category,
    source,
    editedSince,
    stem,
    setTab,
    setType,
    setCategory,
    setSource,
    setEditedSince,
    setStem,
    clearAll,
    activeFilterCount,
  };
}
