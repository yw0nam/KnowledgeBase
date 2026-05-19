// Feedback tab — local draft a reviewer types about the focused
// page. Persisted to localStorage per stem so the note survives
// reloads and page-switches. Honest about state: this is a draft
// until Phase B sends it along with approve / reject.

import { useEffect, useState } from 'react';
import styles from './FeedbackTab.module.css';

interface Props {
  stem: string;
}

const KEY_PREFIX = 'kb-review-feedback:';
const storageKey = (stem: string) => `${KEY_PREFIX}${stem}`;

function readDraft(stem: string): string {
  if (typeof window === 'undefined') return '';
  return window.localStorage.getItem(storageKey(stem)) ?? '';
}

function writeDraft(stem: string, value: string): void {
  if (typeof window === 'undefined') return;
  if (value === '') {
    window.localStorage.removeItem(storageKey(stem));
  } else {
    window.localStorage.setItem(storageKey(stem), value);
  }
}

export function FeedbackTab({ stem }: Props) {
  const [draft, setDraft] = useState<string>(() => readDraft(stem));

  // Re-read when the focused page changes — drafts are per-stem.
  useEffect(() => {
    setDraft(readDraft(stem));
  }, [stem]);

  const update = (next: string) => {
    setDraft(next);
    writeDraft(stem, next);
  };

  return (
    <div className={styles.wrap}>
      <textarea
        className={styles.textarea}
        value={draft}
        onChange={(e) => update(e.target.value)}
        placeholder="Notes about this page — what's right, what's missing, what to fix. Saved locally; sent with approve / reject when Phase B lands."
        rows={8}
        spellCheck
        aria-label="Feedback notes for this page"
      />
      <div className={styles.meta}>
        <span className={styles.charCount}>
          {draft.length} {draft.length === 1 ? 'char' : 'chars'}
        </span>
        <span className={styles.save}>
          {draft.length > 0 ? 'Auto-saved locally' : 'Draft empty'}
        </span>
      </div>
    </div>
  );
}
