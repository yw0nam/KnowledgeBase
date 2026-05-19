// StaleBanner — one-line factual notice rendered above TopStrip when the
// dashboard meta says log.md hasn't seen a recent entry. Per DESIGN.md and
// the PRODUCT.md "lint-grade honesty" register: no exclamation marks, no
// encouragement, no background tint, no side-stripe. Just glyph + label +
// fact.

import { formatIsoDate, hoursAgo } from '../dashboardFormat';
import styles from './StaleBanner.module.css';

interface Props {
  isStale: boolean;
  logLastEntry: string | null;
}

export function StaleBanner({ isStale, logLastEntry }: Props) {
  // is_stale === false and no entry: render nothing.
  // is_stale === false and there is an entry: render nothing (fresh).
  if (!isStale) return null;

  let body: string;
  if (logLastEntry === null) {
    body = 'log.md has no entries yet. Dashboard data may be missing recent runs.';
  } else {
    const n = hoursAgo(logLastEntry);
    const unit = n === 1 ? 'hour' : 'hours';
    body = `log.md last entry ${n} ${unit} ago — ${formatIsoDate(logLastEntry)}. Dashboard data may be missing recent runs.`;
  }

  return (
    <div className={styles.banner} role="status" aria-live="polite">
      <span className={styles.glyph} aria-hidden="true">
        ◷
      </span>
      <span className={styles.label}>Stale</span>
      <span className={styles.text}>{body}</span>
    </div>
  );
}
