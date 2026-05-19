import { useEffect, useState } from 'react';
import { ApiError, fetchQueue } from './api';
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

export function App() {
  const [state, setState] = useState<LoadState>({ status: 'loading' });
  const [selectedStem, setSelectedStem] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setState({ status: 'loading' });
    fetchQueue()
      .then((data) => {
        if (cancelled) return;
        setState({ status: 'ready', data });
        // Default-select first page when the queue is non-empty.
        if (data.pages.length > 0 && data.pages[0]) {
          setSelectedStem(data.pages[0].stem);
        } else {
          setSelectedStem(null);
        }
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const msg =
          err instanceof ApiError
            ? err.message
            : err instanceof Error
              ? err.message
              : 'Unknown error';
        setState({ status: 'error', error: msg });
      });
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  const pages = state.status === 'ready' ? state.data.pages : [];
  const meta = state.status === 'ready' ? state.data.meta : null;
  const selected: ReviewPage | undefined = pages.find((p) => p.stem === selectedStem);

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
      <DecisionDock />
    </div>
  );
}
