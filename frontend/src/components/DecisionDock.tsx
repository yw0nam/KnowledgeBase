// Right utility column — decision dock. Renders different UI per
// action mode: idle / approving / reject-confirm / rejecting.

import type { ActionMode } from '../QueuePage';
import type { ReviewPage } from '../types';
import { KanbanDispatchPanel } from './KanbanDispatchPanel';
import styles from './DecisionDock.module.css';

interface Props {
  canDecide: boolean;
  mode: ActionMode;
  error: string | null;
  onApprove: () => void;
  onRejectStart: () => void;
  onRejectConfirm: () => void;
  onRejectCancel: () => void;
  rejectDraftPreview?: string;
  page?: ReviewPage | null;
  onDispatched?: () => void;
}

export function DecisionDock({
  canDecide,
  mode,
  error,
  onApprove,
  onRejectStart,
  onRejectConfirm,
  onRejectCancel,
  rejectDraftPreview,
  page,
  onDispatched,
}: Props) {
  const submitting = mode === 'approving' || mode === 'rejecting';
  const inReject = mode === 'reject-confirm' || mode === 'rejecting';

  return (
    <aside className={styles.dock} aria-label="Decision dock">
      <div className={styles.section}>
        <button
          type="button"
          className={`${styles.btn} ${styles.btnPrimary}`}
          disabled={!canDecide || submitting || inReject}
          onClick={onApprove}
        >
          <span>{mode === 'approving' ? 'Approving…' : 'Approve'}</span>
          <kbd className={styles.kbd}>a</kbd>
        </button>

        {inReject ? (
          <>
            <button
              type="button"
              className={`${styles.btn} ${styles.btnDanger}`}
              disabled={submitting}
              onClick={onRejectConfirm}
              autoFocus
            >
              <span>{mode === 'rejecting' ? 'Rejecting…' : 'Confirm reject'}</span>
              <kbd className={styles.kbd}>↵</kbd>
            </button>
            <button
              type="button"
              className={`${styles.btnCancel}`}
              disabled={submitting}
              onClick={onRejectCancel}
            >
              <span>Cancel</span>
              <kbd className={styles.kbd}>Esc</kbd>
            </button>
          </>
        ) : (
          <button
            type="button"
            className={`${styles.btn} ${styles.btnGhost}`}
            disabled={!canDecide || submitting}
            onClick={onRejectStart}
          >
            <span>Reject</span>
            <kbd className={styles.kbd}>r</kbd>
          </button>
        )}

        {error ? (
          <p className={styles.error} role="alert">
            <span className={styles.errorLabel}>Action failed</span>
            <code className={styles.errorDetail}>{error}</code>
          </p>
        ) : null}

        {inReject && rejectDraftPreview !== undefined ? (
          <div className={styles.draftPreviewBlock}>
            <span className={styles.draftPreviewLabel}>Feedback to attach</span>
            {rejectDraftPreview === '' ? (
              <p className={styles.draftPreviewEmpty}>
                No feedback. Reject will record the page with no User Feedback line.
              </p>
            ) : (
              <pre className={styles.draftPreviewBody}>{rejectDraftPreview}</pre>
            )}
          </div>
        ) : null}

        {inReject && !error ? (
          <p className={styles.note}>
            Reject moves the page out of <code>data/wiki/</code> via <code>git mv</code>
            . The Feedback draft becomes the rejected file&apos;s{' '}
            <code>User Feedback</code> line.
          </p>
        ) : null}
      </div>

      {page ? <KanbanDispatchPanel page={page} onDispatched={onDispatched} /> : null}

      <div className={styles.section}>
        <h3 className={styles.heading}>Shortcuts</h3>
        <dl className={styles.shortcuts}>
          <dt>
            <kbd className={styles.kbd}>a</kbd>
          </dt>
          <dd>approve</dd>
          <dt>
            <kbd className={styles.kbd}>r</kbd>
          </dt>
          <dd>reject (then ↵ to confirm)</dd>
          <dt>
            <kbd className={styles.kbd}>Esc</kbd>
          </dt>
          <dd>cancel reject</dd>
          <dt>
            <kbd className={styles.kbd}>s</kbd>
          </dt>
          <dd>send to kanban</dd>
          <dt>
            <kbd className={styles.kbd}>j</kbd>
            <kbd className={styles.kbd}>k</kbd>
          </dt>
          <dd>navigate queue</dd>
          <dt>
            <kbd className={styles.kbd}>⌘</kbd>
            <kbd className={styles.kbd}>K</kbd>
          </dt>
          <dd>command palette</dd>
        </dl>
      </div>
    </aside>
  );
}
