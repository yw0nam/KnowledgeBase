// Right utility column — decision dock. Phase A: visible but inert.
// Approve/reject buttons are disabled with a clear note; the
// shortcut cheatsheet shows what will be live. Honest about state.

import styles from './DecisionDock.module.css';

export function DecisionDock() {
  return (
    <aside className={styles.dock} aria-label="Decision dock">
      <div className={styles.section}>
        <button
          type="button"
          className={`${styles.btn} ${styles.btnPrimary}`}
          disabled
          aria-disabled
          title="Approve — wired in Phase B"
        >
          <span>Approve</span>
          <kbd className={styles.kbd}>a</kbd>
        </button>
        <button
          type="button"
          className={`${styles.btn} ${styles.btnGhost}`}
          disabled
          aria-disabled
          title="Reject — wired in Phase B"
        >
          <span>Reject</span>
          <kbd className={styles.kbd}>r</kbd>
        </button>
        <p className={styles.note}>Approve / reject endpoints land in Phase B.</p>
      </div>

      <div className={styles.section}>
        <h3 className={styles.heading}>Shortcuts</h3>
        <dl className={styles.shortcuts}>
          <dt>
            <kbd className={styles.kbd}>j</kbd> <kbd className={styles.kbd}>k</kbd>
          </dt>
          <dd>navigate queue</dd>
          <dt>
            <kbd className={styles.kbd}>a</kbd>
          </dt>
          <dd>approve</dd>
          <dt>
            <kbd className={styles.kbd}>r</kbd>
          </dt>
          <dd>reject</dd>
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
