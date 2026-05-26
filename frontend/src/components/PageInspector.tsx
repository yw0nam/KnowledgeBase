// PageInspector — right push-rail primitive for the Decisions tab.
// Spec §7.3:
//   - Two zones only: frontmatter editor (top) + edit history (bottom).
//   - NO body preview.
//   - Header is one mono line (stem) + "Open source ↗" link.
//   - cmd+s / cmd+enter → save. esc → close (confirm if dirty).
//   - Footer cheat strip: cmd+s save · esc close · r reject · a approve
//     · k send to kanban. Dims when an input is focused.
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

function fileUrl(absPath: string): string {
  // The decision row carries the wiki-relative path. The spec asks
  // for an "Open source" link that hands the file to the OS; a
  // `file://` href is the contract. The link only works when the
  // browser can resolve absolute paths — for now we hand it the
  // best string we have. The user can also copy the path from the
  // anchor target.
  if (absPath.startsWith('/')) return `file://${absPath}`;
  return `file:///${absPath}`;
}

export function PageInspector({ decision, onClose, onSaved }: Props) {
  const [width, setWidth] = useState<number>(readPersistedWidth);
  const [dirty, setDirty] = useState(false);
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [timelineTotal, setTimelineTotal] = useState(0);
  const [timelineReloadKey, setTimelineReloadKey] = useState(0);
  const [overlay, setOverlay] = useState(
    () => typeof window !== 'undefined' && window.innerWidth < OVERLAY_BREAKPOINT,
  );

  const saveRef = useRef<(() => Promise<void>) | null>(null);
  const rootRef = useRef<HTMLElement | null>(null);

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

  // Load timeline. Refresh when stem changes or after a save.
  useEffect(() => {
    let cancelled = false;
    fetchTimeline(decision.stem, { limit: 50 })
      .then((res) => {
        if (cancelled) return;
        setTimeline(res.items);
        setTimelineTotal(res.total);
      })
      .catch(() => {
        if (cancelled) return;
        setTimeline([]);
        setTimelineTotal(0);
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
      ref={rootRef}
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
        <a
          className={styles.openSource}
          href={fileUrl(decision.path)}
          target="_blank"
          rel="noreferrer"
        >
          Open source ↗
        </a>
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
        <EditTimeline events={timeline} total={timelineTotal} />
      </div>

      <footer className={styles.footer}>
        <span className={styles.cheat}>
          <kbd className={styles.kbd}>⌘S</kbd> save ·{' '}
          <kbd className={styles.kbd}>esc</kbd> close ·{' '}
          <kbd className={styles.kbd}>r</kbd> reject ·{' '}
          <kbd className={styles.kbd}>a</kbd> approve ·{' '}
          <kbd className={styles.kbd}>k</kbd> send to kanban
        </span>
      </footer>
    </aside>
  );
}
