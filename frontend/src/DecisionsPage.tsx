// Decisions tab. Spec §7.2 + §7.3:
//   - Top: tab + filter row over the live URL state.
//   - Center: paginated list. Row click opens PageInspector.
//   - Right: PageInspector (push-rail; overlay <1100px).
//   - `?` overlay toggle, leader nav (g p / g d / g a), j/k row nav.

import { useCallback, useEffect, useState } from 'react';
import { fetchDecisions } from './api';
import { useUrlFilters, type DecisionsTab } from './hooks/useUrlFilters';
import { DecisionsFilter } from './components/DecisionsFilter';
import { DecisionsList } from './components/DecisionsList';
import { PageInspector } from './components/PageInspector';
import { KeyboardHelpOverlay } from './components/KeyboardHelpOverlay';
import type { Decision } from './types';
import styles from './DecisionsPage.module.css';

const PER_PAGE = 50;

const TAB_TO_REVIEW_STATUS: Record<DecisionsTab, string> = {
  approved: 'approved',
  rejected: 'rejected',
  // The "Dispatched" tab is a derived view — see the fetch effect.
  dispatched: 'pending_for_approve',
  unprocessed: 'not_processed',
};

export function DecisionsPage() {
  const filters = useUrlFilters();

  const [items, setItems] = useState<Decision[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [helpOpen, setHelpOpen] = useState(false);

  // Build the query from the current filters + tab. The "Dispatched"
  // tab is the only one that filters on dispatch_summary (not a
  // review_status); for that we send no status filter and post-filter
  // client-side.
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    const isDispatched = filters.tab === 'dispatched';
    const status = isDispatched ? undefined : [TAB_TO_REVIEW_STATUS[filters.tab]];
    fetchDecisions({
      status,
      type: filters.type.length > 0 ? filters.type : undefined,
      category: filters.category.length > 0 ? filters.category : undefined,
      source: filters.source.length > 0 ? filters.source : undefined,
      edited_since: filters.editedSince ?? undefined,
      page,
      per_page: PER_PAGE,
    })
      .then((res) => {
        if (cancelled) return;
        const filtered = isDispatched
          ? res.items.filter((d) => d.dispatch_summary !== null)
          : res.items;
        setItems(filtered);
        setTotal(isDispatched ? filtered.length : res.total);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : 'Unknown error');
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [
    filters.tab,
    filters.type,
    filters.category,
    filters.source,
    filters.editedSince,
    page,
    reloadKey,
  ]);

  // Reset to page 1 when filters change.
  useEffect(() => {
    setPage(1);
  }, [
    filters.tab,
    filters.type,
    filters.category,
    filters.source,
    filters.editedSince,
  ]);

  const selected = items.find((d) => d.stem === filters.stem) ?? null;

  // Auto-select the first row when nothing is selected and the
  // current selection no longer matches the loaded list. Keeps the
  // inspector live on tab/filter changes.
  useEffect(() => {
    if (items.length === 0) {
      if (filters.stem) filters.setStem(null);
      return;
    }
    if (filters.stem && items.some((d) => d.stem === filters.stem)) return;
    const first = items[0];
    if (first) filters.setStem(first.stem);
  }, [items, filters]);

  // `?` overlay toggle. Scoped to "no input focused".
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== '?') return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const t = e.target as HTMLElement | null;
      if (
        t &&
        (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)
      ) {
        return;
      }
      e.preventDefault();
      setHelpOpen((o) => !o);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const handleCloseInspector = useCallback(() => {
    filters.setStem(null);
  }, [filters]);

  const handleResetFilters = useCallback(() => {
    filters.clearAll();
  }, [filters]);

  return (
    <div className={styles.shell}>
      <main className={styles.main}>
        <DecisionsFilter filters={filters} />
        {error ? (
          <p className={styles.error} role="alert">
            Could not load decisions: <code>{error}</code>
          </p>
        ) : (
          <DecisionsList
            items={items}
            total={total}
            page={page}
            perPage={PER_PAGE}
            loading={loading}
            selectedStem={filters.stem}
            onSelect={(stem) => filters.setStem(stem)}
            onPage={(p) => setPage(p)}
            onReset={handleResetFilters}
          />
        )}
      </main>
      {selected ? (
        <PageInspector
          decision={selected}
          onClose={handleCloseInspector}
          onSaved={() => setReloadKey((k) => k + 1)}
        />
      ) : null}
      <KeyboardHelpOverlay open={helpOpen} onClose={() => setHelpOpen(false)} />
    </div>
  );
}
