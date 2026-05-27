// Kanban dispatch panel — sits inside the DecisionDock below the
// approve/reject buttons. Loads boards on mount, lists any previous
// dispatches stored on the page's frontmatter, and POSTs a new
// dispatch when the operator confirms.
//
// Render order (see spec §8.2):
//   1. Previous dispatches list (only when kanban_dispatches.length > 0)
//   2. Re-dispatch warning (same condition)
//   3. Board dropdown
//   4. Direction textarea
//   5. Submit button
//   6. Inline error or success banner

import { useCallback, useEffect, useMemo, useState } from 'react';
import { ApiError, listKanbanBoards, sendPageToKanban } from '../api';
import type {
  Board,
  KanbanDispatchRecord,
  ReviewPage,
  SendToKanbanResponse,
} from '../types';
import styles from './KanbanDispatchPanel.module.css';

interface Props {
  page: ReviewPage;
  onDispatched?: () => void;
}

type Phase = 'idle' | 'submitting';

interface DispatchError {
  detail: string;
  orphan_task_id?: string;
}

// Format an ISO timestamp as "YYYY-MM-DD HH:mm KST". We don't import
// a date library — the spec explicitly forbids it.
function formatKst(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  // toLocaleString with a fixed timeZone gives us deterministic
  // KST output regardless of the user's machine timezone.
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Seoul',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).formatToParts(d);
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? '';
  const date = `${get('year')}-${get('month')}-${get('day')}`;
  const time = `${get('hour')}:${get('minute')}`;
  return `${date} ${time} KST`;
}

function readDispatches(page: ReviewPage): KanbanDispatchRecord[] {
  const raw = page.frontmatter['kanban_dispatches'];
  if (!Array.isArray(raw)) return [];
  return raw.filter(
    (r): r is KanbanDispatchRecord =>
      r !== null &&
      typeof r === 'object' &&
      typeof (r as { board?: unknown }).board === 'string' &&
      typeof (r as { task_id?: unknown }).task_id === 'string' &&
      typeof (r as { dispatched_at?: unknown }).dispatched_at === 'string',
  );
}

export function KanbanDispatchPanel({ page, onDispatched }: Props) {
  const [boards, setBoards] = useState<Board[] | null>(null);
  const [boardsError, setBoardsError] = useState<string | null>(null);
  const [selectedBoard, setSelectedBoard] = useState<string>('');
  const [direction, setDirection] = useState<string>('');
  const [phase, setPhase] = useState<Phase>('idle');
  const [submitError, setSubmitError] = useState<DispatchError | null>(null);
  const [banner, setBanner] = useState<SendToKanbanResponse | null>(null);

  const dispatches = useMemo(() => readDispatches(page), [page]);
  const hasDispatched = dispatches.length > 0;

  // Load the kanban board list once on mount.
  useEffect(() => {
    let cancelled = false;
    listKanbanBoards()
      .then((res) => {
        if (cancelled) return;
        setBoards(res.boards);
        // Default to the first board's slug per spec §8.2.
        if (res.boards.length > 0 && res.boards[0]) {
          setSelectedBoard(res.boards[0].slug);
        }
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const msg = err instanceof ApiError ? err.message : String(err);
        setBoardsError(msg);
        setBoards([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Reset transient state when the focused page changes.
  useEffect(() => {
    setDirection('');
    setSubmitError(null);
    setBanner(null);
    setPhase('idle');
  }, [page.stem]);

  // Auto-dismiss the success banner after 3 seconds.
  useEffect(() => {
    if (!banner) return;
    const t = window.setTimeout(() => setBanner(null), 3000);
    return () => window.clearTimeout(t);
  }, [banner]);

  const handleSubmit = useCallback(async () => {
    if (!selectedBoard || phase === 'submitting') return;
    setPhase('submitting');
    setSubmitError(null);
    try {
      // Spec §7.2: request field is `direction_note` (nullable).
      // Always send the key so the BE sees an explicit null when the
      // textarea is empty; matches the Pydantic v2 default.
      const trimmed = direction.trim();
      const payload = {
        board_slug: selectedBoard,
        direction_note: trimmed || null,
      };
      const res = await sendPageToKanban(page.stem, payload);
      setBanner(res);
      setDirection('');
      setPhase('idle');
      if (onDispatched) onDispatched();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setSubmitError({ detail: err.message, orphan_task_id: err.orphan_task_id });
      } else if (err instanceof Error) {
        setSubmitError({ detail: err.message });
      } else {
        setSubmitError({ detail: 'Unknown error' });
      }
      setPhase('idle');
    }
  }, [direction, onDispatched, page.stem, phase, selectedBoard]);

  const buttonLabel = hasDispatched ? 'Send again to Kanban' : 'Send to Kanban';
  const submitting = phase === 'submitting';
  const boardsEmpty = boards !== null && boards.length === 0;
  const buttonDisabled = submitting || boards === null || boardsEmpty || !selectedBoard;

  // Keyboard shortcut `s` — fire only when no input is focused, no
  // modifier keys are held, and the button would be enabled. Matches
  // the QueuePage handler's in-editor guard so typing `s` in the
  // direction textarea or Feedback panel doesn't trigger dispatch.
  useEffect(() => {
    if (buttonDisabled) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key !== 's') return;
      if (e.metaKey || e.ctrlKey || e.altKey || e.shiftKey) return;
      const t = e.target as HTMLElement | null;
      if (
        t &&
        (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)
      ) {
        return;
      }
      e.preventDefault();
      void handleSubmit();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [buttonDisabled, handleSubmit]);

  return (
    <section className={styles.panel} aria-label="Kanban dispatch">
      <h3 className={styles.heading}>Kanban</h3>

      {hasDispatched ? (
        <>
          <span className={styles.previousLabel}>Previous dispatches</span>
          <ul className={styles.previousList} aria-label="Previous kanban dispatches">
            {dispatches.map((d, i) => (
              <li key={`${d.task_id}-${i}`} className={styles.previousItem}>
                <span className={styles.previousMeta}>
                  <span>{d.board}</span>
                  <span>{formatKst(d.dispatched_at)}</span>
                </span>
                <code className={styles.previousTask}>{d.task_id}</code>
              </li>
            ))}
          </ul>
          <p className={styles.warning}>
            Sending again creates a new task; the previous one is unchanged.
          </p>
        </>
      ) : null}

      {boards === null ? (
        <p className={styles.loading}>Loading kanban boards…</p>
      ) : boardsEmpty ? (
        <p className={styles.empty}>
          No kanban boards available. Install Hermes kanban or run{' '}
          <code>hermes kanban board create</code> to add one.
          {boardsError ? (
            <>
              <br />
              <span className={styles.previousTask}>{boardsError}</span>
            </>
          ) : null}
        </p>
      ) : (
        <>
          <label className={styles.field}>
            <span className={styles.label}>Board</span>
            <select
              className={styles.select}
              value={selectedBoard}
              onChange={(e) => setSelectedBoard(e.target.value)}
              disabled={submitting}
              aria-label="Kanban board"
            >
              {boards.map((b) => (
                <option key={b.slug} value={b.slug}>
                  {b.name} ({b.slug})
                </option>
              ))}
            </select>
          </label>

          <label className={styles.field}>
            <span className={styles.label}>Direction</span>
            <textarea
              className={styles.textarea}
              value={direction}
              onChange={(e) => setDirection(e.target.value)}
              disabled={submitting}
              placeholder="What this task should do. Optional."
              rows={3}
              aria-label="Task direction"
            />
          </label>
        </>
      )}

      <button
        type="button"
        className={styles.btn}
        disabled={buttonDisabled}
        onClick={handleSubmit}
      >
        <span>{submitting ? 'Sending…' : buttonLabel}</span>
      </button>

      {submitError ? (
        <p className={styles.error} role="alert">
          <span className={styles.errorLabel}>Dispatch failed</span>
          <code className={styles.errorDetail}>{submitError.detail}</code>
          {submitError.orphan_task_id ? (
            <code className={styles.errorOrphan}>
              Orphan task: {submitError.orphan_task_id}. Run{' '}
              <code>hermes kanban archive {submitError.orphan_task_id}</code> to clean
              up.
            </code>
          ) : null}
        </p>
      ) : null}

      {banner ? (
        <p className={styles.banner} role="status">
          <span className={styles.bannerLabel}>Dispatched</span>
          <span className={styles.bannerDetail}>
            {banner.external_task_id} → {banner.external_board_id} ·{' '}
            {formatKst(banner.dispatched_at)}
          </span>
        </p>
      ) : null}
    </section>
  );
}
