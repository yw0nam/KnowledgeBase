// Decisions table. Spec §7.2:
//   - Columns: stem · type · category · edited
//   - Default sort: last_edited_at DESC (header-click sort is a
//     Phase 2.1 feature; not implemented here).
//   - Mono on stem + type, tabular figures on edited + pagination.
//   - Row click opens PageInspector.
//   - j/k row nav scoped to "no input focused".
//   - Pagination footer renders "1–50 of 312".

import { useEffect } from 'react';
import type { Decision } from '../types';
import styles from './DecisionsList.module.css';

interface Props {
  items: Decision[];
  total: number;
  page: number;
  perPage: number;
  loading: boolean;
  // Active tab — drives the empty-state copy ("No <tab> pages match
  // these filters…"). Free string so this primitive doesn't have to
  // import the DecisionsTab union.
  tabLabel: string;
  // Total approved pages in the corpus, refreshed on save. Used in
  // the parenthetical of the empty-state copy per spec §7.5. May be
  // null while the aux fetch is in flight or has failed.
  approvedTotal: number | null;
  selectedStem: string | null;
  onSelect: (stem: string) => void;
  onPage: (page: number) => void;
  onReset: () => void;
}

function relativeAge(iso: string | null): string {
  if (!iso) return '—';
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return '—';
  const seconds = Math.max(0, (Date.now() - then) / 1000);
  if (seconds < 60) return 'now';
  const minutes = seconds / 60;
  if (minutes < 60) return `${Math.round(minutes)}m`;
  const hours = minutes / 60;
  if (hours < 24) return `${Math.round(hours)}h`;
  const days = hours / 24;
  if (days < 30) return `${Math.round(days)}d`;
  const months = days / 30;
  if (months < 12) return `${Math.round(months)}mo`;
  return `${Math.round(months / 12)}y`;
}

export function DecisionsList({
  items,
  total,
  page,
  perPage,
  loading,
  tabLabel,
  approvedTotal,
  selectedStem,
  onSelect,
  onPage,
  onReset,
}: Props) {
  // j/k row navigation. Skip when focus is in an input. The
  // PageInspector handles its own escape; the page-level handler
  // never sees Escape here.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const t = e.target as HTMLElement | null;
      if (
        t &&
        (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)
      ) {
        return;
      }
      if (items.length === 0) return;
      if (e.key !== 'j' && e.key !== 'k') return;

      e.preventDefault();
      const idx = items.findIndex((d) => d.stem === selectedStem);
      if (idx < 0) {
        const first = items[0];
        if (first) onSelect(first.stem);
        return;
      }
      const next =
        e.key === 'j'
          ? items[Math.min(items.length - 1, idx + 1)]
          : items[Math.max(0, idx - 1)];
      if (next) onSelect(next.stem);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [items, selectedStem, onSelect]);

  const start = total === 0 ? 0 : (page - 1) * perPage + 1;
  const end = Math.min(total, page * perPage);
  const totalPages = Math.max(1, Math.ceil(total / perPage));

  if (!loading && items.length === 0) {
    return (
      <div className={styles.empty}>
        <p className={styles.emptyLine}>
          No {tabLabel} pages match these filters.
          {approvedTotal !== null
            ? ` (${approvedTotal} approved pages total.)`
            : ''}{' '}
          <button type="button" className={styles.resetLink} onClick={onReset}>
            Reset filters
          </button>
        </p>
      </div>
    );
  }

  return (
    <div className={styles.wrap}>
      {loading ? (
        <p className={styles.loadingLine} role="status">
          Loading…
        </p>
      ) : null}
      <table className={styles.table} role="grid" aria-rowcount={total}>
        <thead>
          <tr className={styles.headRow}>
            <th className={styles.thStem}>stem</th>
            <th className={styles.thType}>type</th>
            <th className={styles.thCategory}>category</th>
            <th className={styles.thEdited}>edited</th>
          </tr>
        </thead>
        <tbody>
          {items.map((d) => {
            const selected = d.stem === selectedStem;
            return (
              <tr
                key={d.stem}
                className={selected ? styles.rowSelected : styles.row}
                aria-selected={selected}
                onClick={() => onSelect(d.stem)}
              >
                <td className={styles.cellStem}>{d.stem}</td>
                <td className={styles.cellType}>{d.type ?? '—'}</td>
                <td className={styles.cellCategory}>{d.category ?? '—'}</td>
                <td className={styles.cellEdited}>{relativeAge(d.last_edited_at)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <footer className={styles.footer}>
        <span className={styles.pageInfo}>
          {start}–{end} of {total}
        </span>
        <nav className={styles.pager} aria-label="Pagination">
          <button
            type="button"
            className={styles.pagerBtn}
            disabled={page <= 1}
            onClick={() => onPage(page - 1)}
            aria-label="Previous page"
          >
            ‹
          </button>
          <span className={styles.pageOfPages}>
            {page} / {totalPages}
          </span>
          <button
            type="button"
            className={styles.pagerBtn}
            disabled={page >= totalPages}
            onClick={() => onPage(page + 1)}
            aria-label="Next page"
          >
            ›
          </button>
        </nav>
      </footer>
    </div>
  );
}
