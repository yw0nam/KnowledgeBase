// Shared custom dropdown primitive. NOT a native <select> — the
// review console needs uniform styling/behavior across filters and
// the PageInspector. Spec §7.2 + §7.3.
//
// Modes:
//   - single-select  (default; review_status, type)
//   - multi-select   (filter chips)
//   - free-input + suggestions (category editor)
//
// Keyboard:
//   - Open: click trigger, or Enter/Space when focused.
//   - Close: Escape, click outside, Tab.
//   - ArrowUp/Down move the highlight; Enter commits the highlight.
//
// Karpathy: no Context, no compound-component API. A leaf primitive.

import {
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type KeyboardEvent as ReactKeyboardEvent,
} from 'react';
import styles from './Dropdown.module.css';

export interface DropdownOption {
  value: string;
  label?: string;
}

interface BaseProps {
  options: DropdownOption[];
  placeholder?: string;
  label: string;
  disabled?: boolean;
  triggerClassName?: string;
  // When true, the dropdown accepts a free-text value alongside its
  // suggestion list. Only honored in single-select mode (multi-select
  // free input would be the TagChips component instead).
  allowFreeText?: boolean;
}

interface SingleProps extends BaseProps {
  multi?: false;
  value: string;
  onChange: (next: string) => void;
}

interface MultiProps extends BaseProps {
  multi: true;
  value: string[];
  onChange: (next: string[]) => void;
}

type Props = SingleProps | MultiProps;

function labelFor(opt: DropdownOption): string {
  return opt.label ?? opt.value;
}

export function Dropdown(props: Props) {
  const { options, placeholder, label, disabled, triggerClassName, allowFreeText } =
    props;
  const isMulti = props.multi === true;
  const value = props.value;

  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(0);
  const [draft, setDraft] = useState<string>(
    !isMulti && allowFreeText && typeof value === 'string' ? value : '',
  );

  const rootRef = useRef<HTMLDivElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const listboxId = useId();

  // Reset draft when the controlled value or the free-text mode changes.
  useEffect(() => {
    if (!isMulti && allowFreeText && typeof value === 'string') {
      setDraft(value);
    }
  }, [value, allowFreeText, isMulti]);

  // Close on outside click and Escape.
  useEffect(() => {
    if (!open) return;
    const onDocClick = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setOpen(false);
        triggerRef.current?.focus();
      }
    };
    document.addEventListener('mousedown', onDocClick);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDocClick);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const visible = useMemo(() => {
    if (allowFreeText && !isMulti && draft.length > 0) {
      const q = draft.toLowerCase();
      return options.filter((o) => labelFor(o).toLowerCase().includes(q));
    }
    return options;
  }, [allowFreeText, isMulti, draft, options]);

  const onChange = props.onChange;
  const commit = useCallback(
    (next: string) => {
      if (isMulti) {
        const current = Array.isArray(value) ? value : [];
        const exists = current.includes(next);
        const after = exists ? current.filter((v) => v !== next) : [...current, next];
        (onChange as (next: string[]) => void)(after);
      } else {
        (onChange as (next: string) => void)(next);
        if (allowFreeText) setDraft(next);
        setOpen(false);
      }
    },
    [isMulti, value, allowFreeText, onChange],
  );

  const onTriggerKey = (e: ReactKeyboardEvent<HTMLButtonElement>) => {
    // Closed: open on ArrowDown/Enter/Space. Open: drive the list
    // (highlight / commit) from the trigger directly so the user
    // never has to tab into a separate listbox node.
    if (!open) {
      if (e.key === 'ArrowDown' || e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        setOpen(true);
      }
      return;
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setHighlight((i) => Math.min(visible.length - 1, i + 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setHighlight((i) => Math.max(0, i - 1));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const opt = visible[highlight];
      if (opt) commit(opt.value);
    } else if (e.key === 'Escape') {
      e.preventDefault();
      setOpen(false);
    }
  };

  const onListKey = (e: ReactKeyboardEvent<HTMLUListElement>) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setHighlight((i) => Math.min(visible.length - 1, i + 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setHighlight((i) => Math.max(0, i - 1));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const opt = visible[highlight];
      if (opt) commit(opt.value);
      else if (allowFreeText && !isMulti && draft.length > 0) {
        commit(draft);
      }
    }
  };

  const onInputChange = (e: ChangeEvent<HTMLInputElement>) => {
    setDraft(e.target.value);
    setOpen(true);
    setHighlight(0);
  };

  const onInputKey = (e: ReactKeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setHighlight((i) => Math.min(visible.length - 1, i + 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setHighlight((i) => Math.max(0, i - 1));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const opt = visible[highlight];
      if (opt) commit(opt.value);
      else if (draft.length > 0) commit(draft);
    } else if (e.key === 'Escape') {
      setOpen(false);
    }
  };

  const summary = useMemo(() => {
    if (isMulti) {
      const arr = Array.isArray(value) ? value : [];
      if (arr.length === 0) return placeholder ?? '';
      if (arr.length === 1) {
        const opt = options.find((o) => o.value === arr[0]);
        return opt ? labelFor(opt) : (arr[0] ?? '');
      }
      return `${arr.length} selected`;
    }
    const v = typeof value === 'string' ? value : '';
    if (!v) return placeholder ?? '';
    const opt = options.find((o) => o.value === v);
    return opt ? labelFor(opt) : v;
  }, [isMulti, value, options, placeholder]);

  return (
    <div ref={rootRef} className={styles.root}>
      {allowFreeText && !isMulti ? (
        <input
          type="text"
          className={`${styles.input} ${triggerClassName ?? ''}`}
          value={draft}
          aria-label={label}
          aria-haspopup="listbox"
          aria-expanded={open}
          aria-controls={listboxId}
          placeholder={placeholder}
          disabled={disabled}
          onChange={onInputChange}
          onKeyDown={onInputKey}
          onFocus={() => setOpen(true)}
        />
      ) : (
        <button
          ref={triggerRef}
          type="button"
          className={`${styles.trigger} ${triggerClassName ?? ''}`}
          aria-haspopup="listbox"
          aria-expanded={open}
          aria-controls={listboxId}
          aria-label={label}
          disabled={disabled}
          onClick={() => setOpen((o) => !o)}
          onKeyDown={onTriggerKey}
        >
          <span className={styles.triggerValue}>{summary}</span>
          <span className={styles.caret} aria-hidden>
            ▾
          </span>
        </button>
      )}
      {open && visible.length > 0 ? (
        <ul
          id={listboxId}
          role="listbox"
          tabIndex={-1}
          aria-multiselectable={isMulti || undefined}
          className={styles.list}
          onKeyDown={onListKey}
        >
          {visible.map((opt, i) => {
            const selected = isMulti
              ? Array.isArray(value) && value.includes(opt.value)
              : value === opt.value;
            return (
              <li
                key={opt.value}
                role="option"
                aria-selected={selected}
                tabIndex={-1}
                className={`${styles.option} ${
                  i === highlight ? styles.optionHi : ''
                } ${selected ? styles.optionSelected : ''}`}
                onMouseEnter={() => setHighlight(i)}
                onClick={() => commit(opt.value)}
              >
                <span>{labelFor(opt)}</span>
                {selected ? (
                  <span className={styles.check} aria-hidden>
                    ✓
                  </span>
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );
}
