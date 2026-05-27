// Decisions tab. Spec §7.2 + §7.3:
//   - Top: tab + filter row over the live URL state.
//   - Left: paginated list. Row click opens body + PageInspector.
//   - Center: markdown body of the selected page (read-only) — added
//     to let the user decide without opening an external editor.
//   - Right: PageInspector (push-rail; overlay <1100px).
//   - `?` overlay toggle, leader nav (g p / g d / g a), j/k row nav.

import { useCallback, useEffect, useState } from 'react';
import { ApiError, fetchDecisions, fetchPageWithBody } from './api';
import { useUrlFilters, type DecisionsTab } from './hooks/useUrlFilters';
import { DecisionsFilter } from './components/DecisionsFilter';
import { DecisionsList } from './components/DecisionsList';
import { PageDetail } from './components/PageDetail';
import { PageInspector } from './components/PageInspector';
import { KeyboardHelpOverlay } from './components/KeyboardHelpOverlay';
import type { Decision, FrontmatterPatchResponse, ReviewPage } from './types';
import styles from './DecisionsPage.module.css';

interface Props {
  // Bumped on every PATCH /api/pages/{stem}/frontmatter that touches
  // review_status, so the App-level Pending (n) badge stays live.
  onReviewStatusChange?: () => void;
}

const PER_PAGE = 50;

const TAB_TO_REVIEW_STATUS: Record<DecisionsTab, string> = {
  approved: 'approved',
  rejected: 'rejected',
  // The "Dispatched" tab is a derived view backed by has_dispatch on
  // the server (see the fetch effect).
  dispatched: 'pending_for_approve',
  unprocessed: 'not_processed',
};

type BodyState =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'ready'; page: ReviewPage }
  | { kind: 'missing' }
  | { kind: 'error'; message: string };

export function DecisionsPage({ onReviewStatusChange }: Props = {}) {
  const filters = useUrlFilters();

  const [items, setItems] = useState<Decision[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [helpOpen, setHelpOpen] = useState(false);
  const [approvedTotal, setApprovedTotal] = useState<number | null>(null);
  const [bodyState, setBodyState] = useState<BodyState>({ kind: 'idle' });

  // Build the query from the current filters + tab. The "Dispatched"
  // sub-tab is server-filtered via has_dispatch=true so total +
  // pagination reflect the full corpus, not a post-filter slice.
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
      has_dispatch: isDispatched ? true : undefined,
      page,
      per_page: PER_PAGE,
    })
      .then((res) => {
        if (cancelled) return;
        setItems(res.items);
        setTotal(res.total);
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

  // Auxiliary approved-total fetch, fire-and-forget, used by the
  // empty-state copy per spec §7.5. Re-fetched on `reloadKey` so a
  // PATCH that crosses approve/reject keeps the count honest.
  useEffect(() => {
    let cancelled = false;
    fetchDecisions({ status: ['approved'], page: 1, per_page: 1 })
      .then((res) => {
        if (!cancelled) setApprovedTotal(res.total);
      })
      .catch(() => {
        if (!cancelled) setApprovedTotal(null);
      });
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  const selected = items.find((d) => d.stem === filters.stem) ?? null;

  // Fetch the markdown body for the selected stem. Race-safe via the
  // cancelled flag so a rapid j/k stream always lands on the latest
  // selection. `reloadKey` re-fetches after a frontmatter save so the
  // frontmatter strip in PageDetail stays truthful.
  useEffect(() => {
    if (!filters.stem) {
      setBodyState({ kind: 'idle' });
      return;
    }
    let cancelled = false;
    setBodyState({ kind: 'loading' });
    fetchPageWithBody(filters.stem)
      .then((page) => {
        if (cancelled) return;
        setBodyState({ kind: 'ready', page });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 404) {
          setBodyState({ kind: 'missing' });
          return;
        }
        setBodyState({
          kind: 'error',
          message: err instanceof Error ? err.message : 'Unknown error',
        });
      });
    return () => {
      cancelled = true;
    };
  }, [filters.stem, reloadKey]);

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

  const handleSaved = useCallback(
    (res: FrontmatterPatchResponse) => {
      setReloadKey((k) => k + 1);
      if (res.edits.some((e) => e.field === 'review_status')) {
        onReviewStatusChange?.();
      }
    },
    [onReviewStatusChange],
  );

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
            tabLabel={filters.tab}
            approvedTotal={approvedTotal}
            selectedStem={filters.stem}
            onSelect={(stem) => filters.setStem(stem)}
            onPage={(p) => setPage(p)}
            onReset={handleResetFilters}
          />
        )}
      </main>
      <section className={styles.center} aria-label="Page body">
        <div className={styles.centerInner}>
          <BodyPanel state={bodyState} hasSelection={!!filters.stem} />
        </div>
      </section>
      {selected ? (
        <PageInspector
          decision={selected}
          onClose={handleCloseInspector}
          onSaved={handleSaved}
        />
      ) : null}
      <KeyboardHelpOverlay open={helpOpen} onClose={() => setHelpOpen(false)} />
    </div>
  );
}

interface BodyPanelProps {
  state: BodyState;
  hasSelection: boolean;
}

function BodyPanel({ state, hasSelection }: BodyPanelProps) {
  if (state.kind === 'ready') {
    return <PageDetail page={state.page} />;
  }
  if (state.kind === 'loading') {
    return (
      <p className={styles.systemLine} role="status">
        Loading body…
      </p>
    );
  }
  if (state.kind === 'missing') {
    return (
      <p className={styles.systemLine}>
        Page not found on disk. It may have been moved to <code>rejected/</code> or
        deleted by the TTL sweep.
      </p>
    );
  }
  if (state.kind === 'error') {
    return (
      <p className={styles.systemLine} role="alert">
        Could not load page body.
        <span className={styles.systemLineSub}>{state.message}</span>
      </p>
    );
  }
  // idle — either initial mount with no ?stem= in URL, or all filters
  // cleared. The list auto-selects the first row when one exists, so
  // this lands only when the list is empty too.
  return (
    <p className={styles.systemLine}>
      {hasSelection
        ? 'Loading body…'
        : 'Select a page from the list to read its content.'}
    </p>
  );
}
