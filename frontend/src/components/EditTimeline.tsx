// Audit-driven edit + dispatch timeline. Spec §7.3:
//   - Arrow-anchored row: `{timestamp · tabular} {field}: {old} → {new}`
//   - No user column.
//   - Default 3 most-recent visible; "Show all N" expands inline,
//     capped at 50% of inspector height with internal scroll so the
//     editor's Save button never gets pushed off-screen.

import { useState } from 'react';
import type { TimelineEvent } from '../types';
import styles from './EditTimeline.module.css';

interface Props {
  events: TimelineEvent[];
  total: number;
  defaultVisible?: number;
}

function formatTimestamp(at: string): string {
  // The backend emits KST-suffixed ISO strings ("…+09:00"). Slice the
  // YYYY-MM-DD HH:mm portion for display; no library, no locale drift.
  if (at.length >= 16) {
    return `${at.slice(0, 10)} ${at.slice(11, 16)}`;
  }
  return at;
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return '—';
  if (Array.isArray(value)) {
    return value.length === 0 ? '[]' : `[${value.join(', ')}]`;
  }
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

function eventLabel(ev: TimelineEvent): string {
  if (ev.kind === 'edit') return ev.field;
  if (ev.kind === 'dispatched') return 'dispatched';
  // status:<status> -> "status"
  return 'status';
}

function eventRightSide(ev: TimelineEvent): { old: string; next: string } {
  if (ev.kind === 'edit') {
    return { old: formatValue(ev.old_value), next: formatValue(ev.new_value) };
  }
  if (ev.kind === 'dispatched') {
    return { old: '—', next: ev.external_task_id };
  }
  // status:<status>
  const status = ev.kind.slice('status:'.length);
  return { old: 'dispatched', next: status };
}

export function EditTimeline({ events, total, defaultVisible = 3 }: Props) {
  const [expanded, setExpanded] = useState(false);
  const hasMore = events.length > defaultVisible;
  const visible = expanded ? events : events.slice(0, defaultVisible);

  if (events.length === 0) {
    return (
      <p className={styles.empty}>
        No edits yet. Future frontmatter changes will appear here.
      </p>
    );
  }

  return (
    <div className={styles.wrap}>
      <header className={styles.header}>
        <span className={styles.headLabel}>Edit history</span>
        <span className={styles.headCount}>· {total} events</span>
      </header>
      <ol className={`${styles.list} ${expanded ? styles.listExpanded : ''}`}>
        {visible.map((ev, i) => {
          const { old, next } = eventRightSide(ev);
          return (
            <li key={i} className={styles.row}>
              <time className={styles.ts}>{formatTimestamp(ev.at)}</time>
              <span className={styles.field}>{eventLabel(ev)}:</span>
              <span className={styles.transition}>
                <span className={styles.oldVal}>{old}</span>
                <span className={styles.arrow} aria-hidden>
                  {' → '}
                </span>
                <span className={styles.newVal}>{next}</span>
              </span>
            </li>
          );
        })}
      </ol>
      {hasMore ? (
        <button
          type="button"
          className={styles.expand}
          onClick={() => setExpanded((x) => !x)}
        >
          {expanded ? 'Collapse' : `Show all ${events.length}`}
        </button>
      ) : null}
    </div>
  );
}
