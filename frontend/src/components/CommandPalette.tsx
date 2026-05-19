// Cmd/Ctrl-K command palette. Keyboard-first; mouse hover never moves
// highlight (Raycast/Linear behavior). Static commands first, then a
// "Pages" group derived from the live queue.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { pageTitle } from '../api';
import type { ReviewPage } from '../types';
import type { ActionMode } from '../QueuePage';
import styles from './CommandPalette.module.css';

interface Props {
  open: boolean;
  pages: ReviewPage[];
  selectedStem: string | null;
  mode: ActionMode;
  canDecide: boolean;
  // When false, queue-specific commands (Approve/Reject) and the
  // Pages group are hidden — palette only shows the page-agnostic
  // Reload command. Used on /dashboard where those actions have no
  // focused target.
  showQueueCommands: boolean;
  reloadLabel: string;
  onClose: () => void;
  onApprove: () => void;
  onRejectStart: () => void;
  onReload: () => void;
  onSelect: (stem: string) => void;
}

type CommandKind = 'static' | 'page';

interface Command {
  id: string;
  kind: CommandKind;
  label: string;
  subtitle: string;
  disabled: boolean;
  run: () => void;
}

export function CommandPalette({
  open,
  pages,
  selectedStem,
  mode,
  canDecide,
  showQueueCommands,
  reloadLabel,
  onClose,
  onApprove,
  onRejectStart,
  onReload,
  onSelect,
}: Props) {
  const [filter, setFilter] = useState('');
  const [highlight, setHighlight] = useState(0);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);

  const idleDecidable = mode === 'idle' && canDecide && !!selectedStem;
  const pagesEnabled = mode === 'idle';

  const allCommands = useMemo<Command[]>(() => {
    const list: Command[] = [];
    if (showQueueCommands) {
      list.push({
        id: 'cmd:approve',
        kind: 'static',
        label: 'Approve current page',
        subtitle: '',
        disabled: !idleDecidable,
        run: onApprove,
      });
      list.push({
        id: 'cmd:reject',
        kind: 'static',
        label: 'Reject current page',
        subtitle: '',
        disabled: !idleDecidable,
        run: onRejectStart,
      });
    }
    list.push({
      id: 'cmd:reload',
      kind: 'static',
      label: reloadLabel,
      subtitle: '',
      disabled: false,
      run: onReload,
    });
    if (showQueueCommands) {
      for (const p of pages) {
        list.push({
          id: `page:${p.stem}`,
          kind: 'page',
          label: pageTitle(p),
          subtitle: p.stem,
          disabled: !pagesEnabled,
          run: () => onSelect(p.stem),
        });
      }
    }
    return list;
  }, [
    pages,
    idleDecidable,
    pagesEnabled,
    showQueueCommands,
    reloadLabel,
    onApprove,
    onRejectStart,
    onReload,
    onSelect,
  ]);

  const visible = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return allCommands;
    return allCommands.filter((c) =>
      `${c.label} ${c.subtitle}`.toLowerCase().includes(q),
    );
  }, [allCommands, filter]);

  useEffect(() => {
    if (!open) return;
    previousFocusRef.current =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setFilter('');
    setHighlight(0);
    const t = window.setTimeout(() => {
      inputRef.current?.focus();
    }, 0);
    return () => window.clearTimeout(t);
  }, [open]);

  useEffect(() => {
    if (!open) {
      const prev = previousFocusRef.current;
      if (prev && typeof prev.focus === 'function') {
        prev.focus();
      }
      previousFocusRef.current = null;
    }
  }, [open]);

  useEffect(() => {
    setHighlight((h) => {
      if (visible.length === 0) return 0;
      return Math.min(h, visible.length - 1);
    });
  }, [visible.length]);

  useEffect(() => {
    if (!open) return;
    const list = document.getElementById('command-list');
    const row = list?.querySelector(`[data-index="${highlight}"]`);
    if (row) {
      (row as HTMLElement).scrollIntoView({ block: 'nearest' });
    }
  }, [highlight, open]);

  const close = useCallback(() => {
    onClose();
  }, [onClose]);

  const runHighlighted = useCallback(() => {
    const cmd = visible[highlight];
    if (!cmd || cmd.disabled) return;
    cmd.run();
  }, [visible, highlight]);

  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        close();
        return;
      }
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        if (visible.length === 0) return;
        setHighlight((h) => Math.min(h + 1, visible.length - 1));
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        if (visible.length === 0) return;
        setHighlight((h) => Math.max(h - 1, 0));
        return;
      }
      if (e.key === 'Home') {
        e.preventDefault();
        setHighlight(0);
        return;
      }
      if (e.key === 'End') {
        e.preventDefault();
        if (visible.length === 0) return;
        setHighlight(visible.length - 1);
        return;
      }
      if (e.key === 'Enter') {
        e.preventDefault();
        runHighlighted();
        return;
      }
      if (e.key === 'Tab') {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [open, close, runHighlighted, visible.length]);

  if (!open) return null;

  const activeId = visible[highlight]?.id;
  const firstPageIndex = visible.findIndex((c) => c.kind === 'page');

  return (
    <div
      className={styles.scrim}
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) close();
      }}
    >
      <div
        className={styles.panel}
        role="dialog"
        aria-label="Command palette"
        aria-modal="true"
      >
        <div className={styles.inputRow}>
          <input
            ref={inputRef}
            type="text"
            className={styles.input}
            placeholder="Type a command or page title…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            aria-controls="command-list"
            aria-activedescendant={activeId}
            autoComplete="off"
            spellCheck={false}
          />
        </div>
        <ul id="command-list" role="listbox" className={styles.list}>
          {visible.length === 0 ? (
            <li className={styles.empty} role="presentation">
              No matching commands.
            </li>
          ) : (
            visible.flatMap((c, i) => {
              const isHeader = c.kind === 'page' && i === firstPageIndex;
              const nodes = [];
              if (isHeader) {
                nodes.push(
                  <li
                    key="__header:pages"
                    className={styles.groupHeader}
                    role="presentation"
                  >
                    Pages
                  </li>,
                );
              }
              nodes.push(
                <li
                  key={c.id}
                  id={c.id}
                  role="option"
                  aria-selected={i === highlight}
                  aria-disabled={c.disabled || undefined}
                  data-index={i}
                  className={`${styles.row} ${
                    i === highlight ? styles.rowSelected : ''
                  } ${c.disabled ? styles.rowDisabled : ''}`}
                  onClick={() => {
                    if (!c.disabled) c.run();
                  }}
                >
                  <span className={styles.label}>{c.label}</span>
                  {c.subtitle ? (
                    <span className={styles.subtitle}>{c.subtitle}</span>
                  ) : null}
                </li>,
              );
              return nodes;
            })
          )}
        </ul>
      </div>
    </div>
  );
}
