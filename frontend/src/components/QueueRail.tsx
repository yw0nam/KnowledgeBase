// Left rail — "up next" queue. Click a row to select. No hover
// reveals, no decorative cards. Per DESIGN.md: hairlines, no
// shadows; the selected row is marked by a 1px ring on the inside
// left edge using Signal, plus a faint Signal-bg fill.

import { ageLabel, pageCreated, pageSources, pageTitle, pageType } from '../api';
import type { ReviewPage } from '../types';
import styles from './QueueRail.module.css';

interface Props {
  pages: ReviewPage[];
  selectedStem: string | null;
  onSelect: (stem: string) => void;
}

export function QueueRail({ pages, selectedStem, onSelect }: Props) {
  return (
    <aside className={styles.rail} aria-label="Review queue">
      <header className={styles.header}>
        <h1 className={styles.heading}>Review</h1>
        <span className={styles.count}>
          {pages.length} {pages.length === 1 ? 'pending' : 'pending'}
        </span>
      </header>
      <ol className={styles.list} role="listbox" aria-label="Pending pages">
        {pages.map((p) => (
          <QueueRow
            key={p.stem}
            page={p}
            selected={p.stem === selectedStem}
            onSelect={onSelect}
          />
        ))}
      </ol>
    </aside>
  );
}

interface RowProps {
  page: ReviewPage;
  selected: boolean;
  onSelect: (stem: string) => void;
}

function QueueRow({ page, selected, onSelect }: RowProps) {
  const title = pageTitle(page);
  const type = pageType(page);
  const sourceCount = pageSources(page).length;
  const age = ageLabel(pageCreated(page));

  return (
    <li
      className={`${styles.row} ${selected ? styles.rowSelected : ''}`}
      role="option"
      aria-selected={selected}
      tabIndex={0}
      onClick={() => onSelect(page.stem)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onSelect(page.stem);
        }
      }}
    >
      <div className={styles.title} title={title}>
        {title}
      </div>
      <div className={styles.meta}>
        {type ? <span className={styles.typeChip}>{type}</span> : null}
        <span className={styles.dot} aria-hidden>
          ·
        </span>
        <span>
          {sourceCount} {sourceCount === 1 ? 'source' : 'sources'}
        </span>
        <span className={styles.dot} aria-hidden>
          ·
        </span>
        <span>{age}</span>
      </div>
    </li>
  );
}
