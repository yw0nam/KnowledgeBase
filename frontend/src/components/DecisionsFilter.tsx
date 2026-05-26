// Decisions filter row. Spec §7.2:
//   - Tab + Filter row sit above the list.
//   - Tabs cover review_status only — Approved · Rejected ·
//     Dispatched · Unprocessed; no "All" tab.
//   - Filters: Type / Category / Source / Edited (multi-valued via
//     custom Dropdown primitive — not native <select>).
//   - Active filter chips: hairline Signal border + weight bump,
//     with `× clear` per chip and a "Clear all (N)" link top-right
//     when ≥2 filters are active.
//
// Karpathy: no abstraction over the filter row — three JSX lines
// beat a premature <FilterGroup>.

import { useEffect, useState } from 'react';
import { fetchCategoryEnums } from '../api';
import type { DecisionsTab, UrlFilters } from '../hooks/useUrlFilters';
import { Dropdown } from './Dropdown';
import styles from './DecisionsFilter.module.css';

interface Props {
  filters: UrlFilters;
}

const TABS: { value: DecisionsTab; label: string }[] = [
  { value: 'approved', label: 'Approved' },
  { value: 'rejected', label: 'Rejected' },
  { value: 'dispatched', label: 'Dispatched' },
  { value: 'unprocessed', label: 'Unprocessed' },
];

const TYPE_OPTIONS = [
  { value: 'entity' },
  { value: 'concept' },
  { value: 'decision' },
  { value: 'question' },
  { value: 'improvement' },
  { value: 'checklist' },
  { value: 'summary' },
];

const EDITED_OPTIONS = [
  { value: '', label: 'any time' },
  { value: '24h', label: 'last 24h' },
  { value: '7d', label: 'last 7 days' },
  { value: '30d', label: 'last 30 days' },
];

function editedSinceIso(window: string): string {
  const now = new Date();
  if (window === '24h') return new Date(now.getTime() - 86400_000).toISOString();
  if (window === '7d') return new Date(now.getTime() - 7 * 86400_000).toISOString();
  if (window === '30d') return new Date(now.getTime() - 30 * 86400_000).toISOString();
  return '';
}

function editedSinceLabel(iso: string | null): string {
  if (!iso) return 'any time';
  const now = Date.now();
  const then = new Date(iso).getTime();
  const days = Math.round((now - then) / 86400_000);
  if (days <= 1) return 'last 24h';
  if (days <= 8) return 'last 7 days';
  return `since ${iso.slice(0, 10)}`;
}

export function DecisionsFilter({ filters }: Props) {
  const [categorySuggestions, setCategorySuggestions] = useState<string[]>([]);

  // Load category suggestions; refetch when tab/type changes.
  useEffect(() => {
    let cancelled = false;
    const t = filters.type[0];
    fetchCategoryEnums(t)
      .then((res) => {
        if (!cancelled) setCategorySuggestions(res.categories);
      })
      .catch(() => {
        if (!cancelled) setCategorySuggestions([]);
      });
    return () => {
      cancelled = true;
    };
  }, [filters.type]);

  const showClearAll = filters.activeFilterCount >= 2;

  return (
    <div className={styles.wrap}>
      <nav className={styles.tabs} aria-label="Decision status">
        {TABS.map((t) => {
          const active = filters.tab === t.value;
          return (
            <button
              key={t.value}
              type="button"
              className={active ? styles.tabActive : styles.tab}
              onClick={() => filters.setTab(t.value)}
            >
              {t.label}
            </button>
          );
        })}
      </nav>

      <div className={styles.filterRow}>
        <Dropdown
          multi
          label="Type"
          options={TYPE_OPTIONS}
          value={filters.type}
          onChange={filters.setType}
          placeholder="Type"
          triggerClassName={filters.type.length > 0 ? styles.activeChip : ''}
        />
        <Dropdown
          multi
          label="Category"
          options={categorySuggestions.map((c) => ({ value: c }))}
          value={filters.category}
          onChange={filters.setCategory}
          placeholder="Category"
          triggerClassName={filters.category.length > 0 ? styles.activeChip : ''}
        />
        <Dropdown
          multi
          label="Source"
          options={[
            { value: 'github' },
            { value: 'conversations' },
            { value: 'calendar' },
            { value: 'web' },
            { value: 'manual' },
          ]}
          value={filters.source}
          onChange={filters.setSource}
          placeholder="Source"
          triggerClassName={filters.source.length > 0 ? styles.activeChip : ''}
        />
        <Dropdown
          label="Edited"
          options={EDITED_OPTIONS}
          value={filters.editedSince ? editedSinceLabel(filters.editedSince) : ''}
          onChange={(next) => {
            const iso = editedSinceIso(next);
            filters.setEditedSince(iso || null);
          }}
          placeholder="Edited"
          triggerClassName={filters.editedSince ? styles.activeChip : ''}
        />

        {showClearAll ? (
          <button type="button" className={styles.clearAll} onClick={filters.clearAll}>
            Clear all ({filters.activeFilterCount})
          </button>
        ) : null}
      </div>
    </div>
  );
}
