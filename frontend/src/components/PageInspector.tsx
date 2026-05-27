// PageInspector — right push-rail primitive for the Decisions tab.
// Spec §7.3:
//   - Two zones only: frontmatter editor (top) + edit history (bottom).
//   - NO body preview.
//   - Header is one mono line (stem) + a "Copy path" button.
//     The spec asked for a `file://` link, but every modern browser
//     blocks that navigation from an http:// origin, so we copy the
//     path to the clipboard instead — same intent, working result.
//   - cmd+s / cmd+enter → save. esc → close (confirm if dirty).
//   - Footer cheat strip: cmd+s save · esc close. r/a/k are queue
//     verbs (Pending tab); promising them here would lie.
//   - Drag-handle 4px, col-resize, hairline visual. localStorage
//     persists width. <1100px viewport: inspector becomes overlay.
//
// Karpathy: only what the spec requires. No animations, no portals,
// no compound API.

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type MouseEvent as ReactMouseEvent,
} from 'react';
import { fetchTimeline } from '../api';
import type { Decision, FrontmatterPatchResponse, TimelineEvent } from '../types';
import { FrontmatterEditor } from './FrontmatterEditor';
import { EditTimeline } from './EditTimeline';
import styles from './PageInspector.module.css';

interface Props {
  decision: Decision;
  onClose: () => void;
  onSaved?: (res: FrontmatterPatchResponse) => void;
}

const MIN_WIDTH = 360;
const MAX_WIDTH = 720;
const DEFAULT_WIDTH = 420;
const OVERLAY_BREAKPOINT = 1100;
const WIDTH_KEY = 'kb.pageInspector.width';

function readPersistedWidth(): number {
  try {
    const raw = localStorage.getItem(WIDTH_KEY);
    if (!raw) return DEFAULT_WIDTH;
    const n = Number.parseInt(raw, 10);
    if (Number.isNaN(n)) return DEFAULT_WIDTH;
    return Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, n));
  } catch {
    return DEFAULT_WIDTH;
  }
}

async function copyToClipboard(text: string): Promise<boolean> {
  try {
    // navigator.clipboard requires a secure context (https/localhost);
    // both KB use cases qualify. If clipboard API is unavailable we
    // fail silently — the user sees the path stays visible on hover.
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

export function PageInspector({ decision, onClose, onSaved }: Props) {
  const [width, setWidth] = useState<number>(readPersistedWidth);
  const [dirty, setDirty] = useState(false);
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [timelineTotal, setTimelineTotal] = useState(0);
  const [timelineError, setTimelineError] = useState<string | null>(null);
  const [timelineReloadKey, setTimelineReloadKey] = useState(0);
  const [copyMessage, setCopyMessage] = useState<string | null>(null);
  const [overlay, setOverlay] = useState(
    () => typeof window !== 'undefined' && window.innerWidth < OVERLAY_BREAKPOINT,
  );

  const saveRef = useRef<(() => Promise<void>) | null>(null);

  // Track viewport for the <1100px overlay breakpoint.
  useEffect(() => {
    const onResize = () => {
      setOverlay(window.innerWidth < OVERLAY_BREAKPOINT);
    };
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  // Persist width.
  useEffect(() => {
    try {
      localStorage.setItem(WIDTH_KEY, String(width));
    } catch {
      // localStorage may be disabled (private mode); ignore.
    }
  }, [width]);

  // Load timeline. Refresh when stem changes or after a save. The
  // catch path sets `timelineError` (NOT an empty-state) so the
  // inspector doesn't lie about "no edits" when the fetch failed.
  useEffect(() => {
    let cancelled = false;
    setTimelineError(null);
    fetchTimeline(decision.stem, { limit: 50 })
      .then((res) => {
        if (cancelled) return;
        setTimeline(res.items);
        setTimelineTotal(res.total);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setTimeline([]);
        setTimelineTotal(0);
        setTimelineError(err instanceof Error ? err.message : 'fetch failed');
      });
    return () => {
      cancelled = true;
    };
  }, [decision.stem, timelineReloadKey]);

  const close = useCallback(() => {
    if (dirty) {
      const ok = window.confirm(
        'Unsaved changes will be lost. Close the inspector anyway?',
      );
      if (!ok) return;
    }
    onClose();
  }, [dirty, onClose]);

  const handleSaved = useCallback(
    (res: FrontmatterPatchResponse) => {
      setDirty(false);
      setTimelineReloadKey((k) => k + 1);
      onSaved?.(res);
    },
    [onSaved],
  );

  const handleCopyPath = useCallback(async () => {
    const ok = await copyToClipboard(decision.path);
    setCopyMessage(ok ? 'Copied.' : 'Copy failed.');
    setTimeout(() => setCopyMessage(null), 1500);
  }, [decision.path]);

  // Keyboard: cmd+s / cmd+enter save; esc close. No `r`/`a`/`k`
  // bindings here — those live on the page-level handler (spec §7.4
  // "no input focused" scope). The cheat strip in the footer dims
  // when focus is inside an input so the user can see which row of
  // shortcuts is active.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && (e.key === 's' || e.key === 'Enter')) {
        e.preventDefault();
        const fn = saveRef.current;
        if (fn) void fn();
        return;
      }
      if (e.key === 'Escape') {
        e.preventDefault();
        close();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [close]);

  // Width drag handle.
  const onDragStart = (e: ReactMouseEvent<HTMLDivElement>) => {
    e.preventDefault();
    const startX = e.clientX;
    const startWidth = width;
    const onMove = (ev: MouseEvent) => {
      const delta = startX - ev.clientX;
      const next = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, startWidth + delta));
      setWidth(next);
    };
    const onUp = () => {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
    };
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  };

  const style = useMemo(
    () => ({ width: overlay ? '100%' : `${width}px` }),
    [overlay, width],
  );

  return (
    <aside
      className={`${styles.rail} ${overlay ? styles.overlay : ''}`}
      style={style}
      aria-label="Page inspector"
    >
      {!overlay ? (
        <div
          className={styles.handle}
          onMouseDown={onDragStart}
          role="separator"
          aria-orientation="vertical"
          aria-label="Resize inspector"
        />
      ) : null}
      <header className={styles.header}>
        <code className={styles.stem}>{decision.stem}</code>
        <span className={styles.headerRight}>
          {copyMessage ? (
            <span className={styles.copyMsg} role="status">
              {copyMessage}
            </span>
          ) : null}
          <button
            type="button"
            className={styles.copyPath}
            onClick={() => void handleCopyPath()}
            title={decision.path}
          >
            Copy path
          </button>
        </span>
      </header>

      <div className={styles.editor}>
        <FrontmatterEditor
          decision={decision}
          onSaved={handleSaved}
          onDirtyChange={setDirty}
          saveRef={saveRef}
        />
      </div>

      <div className={styles.history}>
        <EditTimeline events={timeline} total={timelineTotal} error={timelineError} />
      </div>

      <footer className={styles.footer}>
        <span className={styles.cheat}>
          {/* r/a/k are queue-tab verbs (approve/reject move the file
              in/out of data/wiki/; send-to-kanban is the Pending tab's
              affordance). They are intentionally absent here so the
              cheat strip is honest about what the Decisions inspector
              actually does — frontmatter PATCH only. */}
          <kbd>⌘S</kbd> save · <kbd>esc</kbd> close
        </span>
      </footer>
    </aside>
  );
}
