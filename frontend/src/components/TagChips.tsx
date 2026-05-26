// Tag chip strip + inline input. Spec §7.3:
//   - Enter or Comma confirms a chip.
//   - "×" on hover removes a chip.
//   - Backspace on empty input removes the trailing chip.
//   - Duplicates silently deduped.
//   - Save sends the full new tag list (PATCH semantics: presence of
//     `tags` = full replacement).

import { useRef, useState, type ChangeEvent, type KeyboardEvent } from 'react';
import styles from './TagChips.module.css';

interface Props {
  value: string[];
  onChange: (next: string[]) => void;
  label: string;
  disabled?: boolean;
  placeholder?: string;
}

function normalize(raw: string): string {
  return raw.trim();
}

export function TagChips({ value, onChange, label, disabled, placeholder }: Props) {
  const [draft, setDraft] = useState('');
  const inputRef = useRef<HTMLInputElement | null>(null);

  const commit = (raw: string) => {
    const tag = normalize(raw);
    if (!tag) {
      setDraft('');
      return;
    }
    if (value.includes(tag)) {
      setDraft('');
      return;
    }
    onChange([...value, tag]);
    setDraft('');
  };

  const remove = (tag: string) => {
    onChange(value.filter((t) => t !== tag));
  };

  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault();
      commit(draft);
    } else if (e.key === 'Backspace' && draft.length === 0 && value.length > 0) {
      e.preventDefault();
      const last = value[value.length - 1];
      if (last !== undefined) remove(last);
    }
  };

  const onChangeInput = (e: ChangeEvent<HTMLInputElement>) => {
    setDraft(e.target.value);
  };

  return (
    <div className={styles.wrap} aria-label={label}>
      <ul className={styles.list}>
        {value.map((tag) => (
          <li key={tag} className={styles.chip}>
            <span className={styles.chipLabel}>{tag}</span>
            <button
              type="button"
              className={styles.chipRemove}
              aria-label={`Remove tag ${tag}`}
              disabled={disabled}
              onClick={() => remove(tag)}
            >
              ×
            </button>
          </li>
        ))}
        <li className={styles.inputItem}>
          <input
            ref={inputRef}
            type="text"
            className={styles.input}
            value={draft}
            placeholder={value.length === 0 ? (placeholder ?? '+ add tag') : ''}
            aria-label="Add tag"
            disabled={disabled}
            onChange={onChangeInput}
            onKeyDown={onKey}
            onBlur={() => commit(draft)}
          />
        </li>
      </ul>
    </div>
  );
}
