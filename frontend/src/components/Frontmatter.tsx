// Frontmatter strip across the top of the focused page. Tabular
// keys in uppercase Label type, values in Body or Body-Mono
// depending on the field. Lint-grade honesty: render only fields
// that exist, never invent placeholders.

import type { Frontmatter as FM } from '../types';
import styles from './Frontmatter.module.css';

interface Props {
  fm: FM;
}

// Fields that read as mono (paths, codes, identifiers, timestamps).
const MONO_KEYS = new Set([
  'sources',
  'captured_at',
  'created',
  'updated',
  'review_status',
  'type',
  'contributor',
]);

// Order matters: most useful first. Anything not in this list
// renders below in alphabetical order.
const PRIMARY_ORDER = [
  'type',
  'review_status',
  'created',
  'captured_at',
  'contributor',
  'sources',
  'tags',
];

// Frontmatter keys rendered by a dedicated surface elsewhere; skipped
// here to avoid duplicate (and lossy) rendering of complex shapes.
// Phase 2: kanban_dispatches is DB-backed (see /api/dispatches); any
// legacy page still carrying the key renders as raw text below until
// kb-migrate-kanban-dispatches has been run. That's honest, not a
// regression — the user sees pre-backfill state for what it is.
const SKIP_KEYS: ReadonlySet<string> = new Set();

function formatValue(value: unknown): string {
  if (Array.isArray(value)) {
    return value.join(', ');
  }
  if (value === null || value === undefined) return '—';
  return String(value);
}

export function Frontmatter({ fm }: Props) {
  const keys = Object.keys(fm);
  const ordered = [
    ...PRIMARY_ORDER.filter((k) => k in fm && !SKIP_KEYS.has(k)),
    ...keys
      .filter((k) => !PRIMARY_ORDER.includes(k) && k !== 'title' && !SKIP_KEYS.has(k))
      .sort(),
  ];
  if (ordered.length === 0) {
    return null;
  }
  return (
    <dl className={styles.grid}>
      {ordered.map((key) => {
        const isMono = MONO_KEYS.has(key);
        return (
          <div key={key} className={styles.row}>
            <dt className={styles.key}>{key.replace(/_/g, ' ')}</dt>
            <dd className={`${styles.value} ${isMono ? styles.valueMono : ''}`}>
              {formatValue(fm[key])}
            </dd>
          </div>
        );
      })}
    </dl>
  );
}
