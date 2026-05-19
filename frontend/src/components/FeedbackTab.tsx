// Feedback tab — local draft a reviewer types about the focused
// page. Persisted to localStorage per stem so the note survives
// reloads and page-switches. Honest about state: this is a draft
// until Phase B sends it along with approve / reject.

import { useEffect, useState } from 'react';
import { readDraft, writeDraft } from '../feedback';
import styles from './FeedbackTab.module.css';

interface Props {
  stem: string;
}

export function FeedbackTab({ stem }: Props) {
  const [draft, setDraft] = useState<string>(() => readDraft(stem));

  // Re-read when the focused page changes — drafts are per-stem.
  // Also rescans when stem stays the same but localStorage was
  // cleared by a successful approve/reject in App.
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
        placeholder="Notes about this page — what's right, what's missing, what to fix. Sent as the User Feedback line on approve, or attached to the rejected file on reject."
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
