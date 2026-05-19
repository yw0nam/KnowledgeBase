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
    ...PRIMARY_ORDER.filter((k) => k in fm),
    ...keys.filter((k) => !PRIMARY_ORDER.includes(k) && k !== 'title').sort(),
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
