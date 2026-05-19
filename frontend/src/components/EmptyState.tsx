// Empty queue — the dominant case in early operation. Honest copy,
// no illustration, no "All caught up!" cheer. Per DESIGN.md and
// PRODUCT.md anti-references.

import type { QueueMeta } from '../types';
import styles from './EmptyState.module.css';

interface Props {
  meta: QueueMeta | null;
}

export function EmptyState({ meta }: Props) {
  const wikiMissing = meta && !meta.wiki_exists;
  return (
    <div className={styles.wrap}>
      <p className={styles.line}>No pages awaiting review.</p>
      {wikiMissing ? (
        <p className={styles.sub}>
          No <code>{meta.wiki_dir}</code> directory found. Set <code>KB_DATA_DIR</code>{' '}
          to point at the local data tree, or wait for the first wiki page to be
          written.
        </p>
      ) : (
        <p className={styles.sub}>
          The promote queue is empty. Either no new raw sources have been ingested, or
          the daily-update agent hasn&apos;t run yet.
        </p>
      )}
    </div>
  );
}
