import { useCallback, useEffect, useMemo, useState } from 'react';
import { ApiError, approvePage, fetchQueue, rejectPage } from './api';
import { clearDraft, readDraft } from './feedback';
import type { QueueResponse, ReviewPage } from './types';
import { DecisionDock } from './components/DecisionDock';
import { EmptyState } from './components/EmptyState';
import { PageDetail } from './components/PageDetail';
import { QueueRail } from './components/QueueRail';
import styles from './App.module.css';

type LoadState =
  | { status: 'loading' }
  | { status: 'ready'; data: QueueResponse }
  | { status: 'error'; error: string };

export type ActionMode = 'idle' | 'approving' | 'reject-confirm' | 'rejecting';

function nextStemAfter(pages: ReviewPage[], stem: string): string | null {
  const idx = pages.findIndex((p) => p.stem === stem);
  if (idx < 0) return null;
  return pages[idx + 1]?.stem ?? pages[idx - 1]?.stem ?? null;
}

function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return 'Unknown error';
}

export function App() {
  const [state, setState] = useState<LoadState>({ status: 'loading' });
  const [selectedStem, setSelectedStem] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [mode, setMode] = useState<ActionMode>('idle');
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setState({ status: 'loading' });
    fetchQueue()
      .then((data) => {
        if (cancelled) return;
        setState({ status: 'ready', data });
        if (data.pages.length > 0 && data.pages[0]) {
          setSelectedStem(data.pages[0].stem);
        } else {
          setSelectedStem(null);
        }
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setState({ status: 'error', error: errorMessage(err) });
      });
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  const pages = useMemo(
    () => (state.status === 'ready' ? state.data.pages : []),
    [state],
  );
  const meta = state.status === 'ready' ? state.data.meta : null;
  const selected: ReviewPage | undefined = pages.find((p) => p.stem === selectedStem);

  const decide = useCallback(
    async (action: 'approve' | 'reject', stem: string) => {
      const nextStem = nextStemAfter(pages, stem);
      const submittingMode: ActionMode =
        action === 'approve' ? 'approving' : 'rejecting';
      setMode(submittingMode);
      setActionError(null);
      try {
        const feedback = readDraft(stem);
        if (action === 'approve') {
          await approvePage(stem, feedback);
        } else {
          await rejectPage(stem, feedback);
        }
        clearDraft(stem);
        const data = await fetchQueue();
        setState({ status: 'ready', data });
        const fallback = data.pages[0]?.stem ?? null;
        setSelectedStem(
          nextStem && data.pages.some((p) => p.stem === nextStem) ? nextStem : fallback,
        );
        setMode('idle');
      } catch (err) {
        setActionError(errorMessage(err));
        // Reject: return to confirm so the user can retry without
        // re-pressing 'r'. Approve: snap back to idle.
        setMode(action === 'reject' ? 'reject-confirm' : 'idle');
      }
    },
    [pages],
  );

  const handleApprove = useCallback(() => {
    if (mode !== 'idle' || !selectedStem) return;
    void decide('approve', selectedStem);
  }, [mode, selectedStem, decide]);

  const handleRejectStart = useCallback(() => {
    if (mode !== 'idle' || !selectedStem) return;
    setActionError(null);
    setMode('reject-confirm');
  }, [mode, selectedStem]);

  const handleRejectConfirm = useCallback(() => {
    if (mode !== 'reject-confirm' || !selectedStem) return;
    void decide('reject', selectedStem);
  }, [mode, selectedStem, decide]);

  const handleRejectCancel = useCallback(() => {
    if (mode !== 'reject-confirm') return;
    setActionError(null);
    setMode('idle');
  }, [mode]);

  // Keyboard shortcuts: a/r/Enter/Esc. Skip when focus is inside an
  // editable element (the Feedback textarea), so typing 'a' or 'r'
  // there doesn't trigger the action.
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      const inEditor =
        !!t &&
        (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable);
      if (inEditor) return;
      if (e.key === 'a' && mode === 'idle') {
        e.preventDefault();
        handleApprove();
      } else if (e.key === 'r' && mode === 'idle') {
        e.preventDefault();
        handleRejectStart();
      } else if (e.key === 'Enter' && mode === 'reject-confirm') {
        e.preventDefault();
        handleRejectConfirm();
      } else if (e.key === 'Escape' && mode === 'reject-confirm') {
        e.preventDefault();
        handleRejectCancel();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [mode, handleApprove, handleRejectStart, handleRejectConfirm, handleRejectCancel]);

  return (
    <div className={styles.app}>
      <QueueRail pages={pages} selectedStem={selectedStem} onSelect={setSelectedStem} />
      <section className={styles.center} aria-label="Page detail">
        <div className={styles.centerInner}>
          {state.status === 'loading' ? (
            <div className={styles.systemLine}>Loading queue…</div>
          ) : state.status === 'error' ? (
            <div className={styles.systemLine}>
              <span>Could not reach the kb-web API.</span>
              <code className={styles.errorCode}>{state.error}</code>
              <button
                type="button"
                className={styles.retry}
                onClick={() => setReloadKey((k) => k + 1)}
              >
                Retry
              </button>
            </div>
          ) : selected ? (
            <PageDetail page={selected} />
          ) : (
            <EmptyState meta={meta} />
          )}
        </div>
      </section>
      <DecisionDock
        canDecide={!!selected && state.status === 'ready'}
        mode={mode}
        error={actionError}
        onApprove={handleApprove}
        onRejectStart={handleRejectStart}
        onRejectConfirm={handleRejectConfirm}
        onRejectCancel={handleRejectCancel}
        rejectDraftPreview={
          (mode === 'reject-confirm' || mode === 'rejecting') && selectedStem
            ? readDraft(selectedStem)
            : undefined
        }
      />
    </div>
  );
}
