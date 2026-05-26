// Keyboard shortcut overlay (spec §7.4): centered card on a
// low-opacity scrim. No backdrop blur. Opacity-fade transition only.

import { useEffect } from 'react';
import styles from './KeyboardHelpOverlay.module.css';

interface Props {
  open: boolean;
  onClose: () => void;
}

const ROWS: { keys: string; label: string }[] = [
  { keys: '⌘S / ⌘↵', label: 'save inspector' },
  { keys: 'esc', label: 'close inspector' },
  { keys: 'a', label: 'approve focused row' },
  { keys: 'r', label: 'reject focused row' },
  { keys: 'k', label: 'send to kanban' },
  { keys: 'j / k', label: 'next / previous row' },
  { keys: 'g p', label: 'go to Pending' },
  { keys: 'g d', label: 'go to Decisions' },
  { keys: 'g a', label: 'go to Dashboard' },
  { keys: '?', label: 'this overlay' },
];

export function KeyboardHelpOverlay({ open, onClose }: Props) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' || e.key === '?') {
        e.preventDefault();
        onClose();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className={styles.scrim}
      role="dialog"
      aria-modal="true"
      aria-label="Keyboard shortcuts"
      onClick={onClose}
    >
      <div className={styles.card} onClick={(e) => e.stopPropagation()}>
        <header className={styles.header}>Keyboard</header>
        <dl className={styles.list}>
          {ROWS.map((r) => (
            <div key={r.keys} className={styles.row}>
              <dt className={styles.keys}>
                <kbd className={styles.kbd}>{r.keys}</kbd>
              </dt>
              <dd className={styles.label}>{r.label}</dd>
            </div>
          ))}
        </dl>
      </div>
    </div>
  );
}
