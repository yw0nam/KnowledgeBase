// Frontmatter editor inside PageInspector. Spec §7.3 + §7.6.
//
// Controls (in render order):
//   1. review_status   Dropdown (single, constrained)
//   2. type            Dropdown (single, constrained)
//   3. category        Dropdown (single, free input + suggestions)
//   4. tags            TagChips (full replacement on PATCH)
//
// Behaviour:
//   - Dirty middot (·) prefix on the Save button label.
//   - Type change requiring a directory rename → inline warning under
//     the type field, Save disabled until the value is reverted.
//   - PATCH body sends only the changed fields. `tags` is always a
//     full replacement when present.
//   - 409 lint failure → inline error list under the action row;
//     form state preserved (no value rewind).
//   - cmd+s / cmd+enter saves; the keyboard handler is global and
//     fires even while focus sits in the editor's controls because
//     the modifier is always required.

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from 'react';
import { ApiError, fetchCategoryEnums, patchFrontmatter } from '../api';
import type { Decision, FrontmatterPatch, FrontmatterPatchResponse } from '../types';
import { Dropdown } from './Dropdown';
import { TagChips } from './TagChips';
import styles from './FrontmatterEditor.module.css';

interface Props {
  decision: Decision;
  onSaved?: (res: FrontmatterPatchResponse) => void;
  onDirtyChange?: (dirty: boolean) => void;
  // Imperative save trigger (exposed so PageInspector can wire
  // cmd+s/cmd+enter without re-implementing the editor's state).
  saveRef?: { current: (() => Promise<void>) | null };
}

type WikiType =
  | 'entity'
  | 'concept'
  | 'decision'
  | 'question'
  | 'improvement'
  | 'checklist'
  | 'summary';

type ReviewStatus = 'pending_for_approve' | 'approved' | 'rejected' | 'not_processed';

const REVIEW_OPTIONS = [
  { value: 'pending_for_approve', label: 'pending_for_approve' },
  { value: 'approved', label: 'approved' },
  { value: 'rejected', label: 'rejected' },
  { value: 'not_processed', label: 'not_processed' },
];

const TYPE_OPTIONS = [
  { value: 'entity', label: 'entity' },
  { value: 'concept', label: 'concept' },
  { value: 'decision', label: 'decision' },
  { value: 'question', label: 'question' },
  { value: 'improvement', label: 'improvement' },
  { value: 'checklist', label: 'checklist' },
  { value: 'summary', label: 'summary' },
];

// type → directory segment. Used to decide if a type change requires
// a manual file rename (spec §7.3 "Type-change cascade").
const TYPE_DIR: Record<WikiType, string> = {
  entity: 'entities',
  concept: 'concepts',
  decision: 'decisions',
  question: 'questions',
  improvement: 'improvements',
  checklist: 'checklists',
  summary: 'summaries',
};

function pathRequiresRename(path: string, nextType: WikiType): boolean {
  // The path passes through wiki/<dir>/...; an entity page lives
  // under wiki/entities/. If the next type's dir segment isn't
  // present in the path, the file would have to move.
  const seg = TYPE_DIR[nextType];
  return !path.includes(`/${seg}/`) && !path.startsWith(`${seg}/`);
}

interface DraftState {
  review_status: string;
  type: string;
  category: string;
  tags: string[];
}

function initialDraft(d: Decision): DraftState {
  return {
    review_status: d.review_status ?? '',
    type: d.type ?? '',
    category: d.category ?? '',
    tags: [...(d.tags ?? [])],
  };
}

function arraysEqual(a: string[], b: string[]): boolean {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) {
    if (a[i] !== b[i]) return false;
  }
  return true;
}

function buildPatch(initial: DraftState, draft: DraftState): FrontmatterPatch {
  const patch: FrontmatterPatch = {};
  if (draft.review_status !== initial.review_status && draft.review_status) {
    patch.review_status = draft.review_status as ReviewStatus;
  }
  if (draft.type !== initial.type && draft.type) {
    patch.type = draft.type as WikiType;
  }
  if (draft.category !== initial.category) {
    patch.category = draft.category || null;
  }
  if (!arraysEqual(initial.tags, draft.tags)) {
    patch.tags = draft.tags;
  }
  return patch;
}

export function FrontmatterEditor({
  decision,
  onSaved,
  onDirtyChange,
  saveRef,
}: Props) {
  const initial = useMemo(() => initialDraft(decision), [decision]);
  const [draft, setDraft] = useState<DraftState>(initial);
  const [saving, setSaving] = useState(false);
  const [lintErrors, setLintErrors] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<string[]>([]);

  // Reset draft when the focused page changes.
  useEffect(() => {
    setDraft(initial);
    setLintErrors([]);
    setError(null);
  }, [initial]);

  // Load category suggestions for the current type. Refresh when type
  // changes — categories are scoped per-type on the backend.
  useEffect(() => {
    if (!draft.type) {
      setSuggestions([]);
      return;
    }
    let cancelled = false;
    fetchCategoryEnums(draft.type)
      .then((res) => {
        if (!cancelled) setSuggestions(res.categories);
      })
      .catch(() => {
        if (!cancelled) setSuggestions([]);
      });
    return () => {
      cancelled = true;
    };
  }, [draft.type]);

  const dirty = useMemo(() => {
    return (
      initial.review_status !== draft.review_status ||
      initial.type !== draft.type ||
      initial.category !== draft.category ||
      !arraysEqual(initial.tags, draft.tags)
    );
  }, [initial, draft]);

  useEffect(() => {
    onDirtyChange?.(dirty);
  }, [dirty, onDirtyChange]);

  const typeRenameRequired = useMemo(() => {
    if (!draft.type || draft.type === initial.type) return false;
    return pathRequiresRename(decision.path, draft.type as WikiType);
  }, [draft.type, initial.type, decision.path]);

  const handleSave = useCallback(async () => {
    if (!dirty || saving || typeRenameRequired) return;
    const patch = buildPatch(initial, draft);
    if (Object.keys(patch).length === 0) return;
    setSaving(true);
    setLintErrors([]);
    setError(null);
    try {
      const res = await patchFrontmatter(decision.stem, patch);
      setSaving(false);
      onSaved?.(res);
    } catch (err) {
      setSaving(false);
      if (err instanceof ApiError) {
        if (err.lint_errors && err.lint_errors.length > 0) {
          setLintErrors(err.lint_errors);
        } else {
          setError(err.message);
        }
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('Unknown error');
      }
    }
  }, [dirty, draft, initial, saving, typeRenameRequired, decision.stem, onSaved]);

  // Expose handleSave through the imperative ref so PageInspector can
  // bind cmd+s / cmd+enter without lifting the editor state.
  const saveRefStable = useRef(handleSave);
  saveRefStable.current = handleSave;
  useEffect(() => {
    if (saveRef) saveRef.current = () => saveRefStable.current();
    return () => {
      if (saveRef) saveRef.current = null;
    };
  }, [saveRef]);

  const onSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    void handleSave();
  };

  const categorySuggestionOptions = useMemo(
    () => suggestions.map((s) => ({ value: s, label: s })),
    [suggestions],
  );

  return (
    <form className={styles.form} onSubmit={onSubmit}>
      <Field label="review_status">
        <Dropdown
          label="review_status"
          options={REVIEW_OPTIONS}
          value={draft.review_status}
          onChange={(next) => setDraft((d) => ({ ...d, review_status: next }))}
          placeholder="pick a status"
        />
      </Field>

      <Field label="type">
        <Dropdown
          label="type"
          options={TYPE_OPTIONS}
          value={draft.type}
          onChange={(next) => setDraft((d) => ({ ...d, type: next }))}
          placeholder="pick a type"
        />
        {typeRenameRequired ? (
          <p className={styles.warning} role="status">
            type change requires manual rename — page lives in{' '}
            <code className={styles.code}>{decision.path}</code>. Move the file with git
            first, then come back to flip the type.
          </p>
        ) : null}
      </Field>

      <Field label="category">
        <Dropdown
          label="category"
          allowFreeText
          options={categorySuggestionOptions}
          value={draft.category}
          onChange={(next) => setDraft((d) => ({ ...d, category: next }))}
          placeholder="category"
        />
      </Field>

      <Field label="tags">
        <TagChips
          label="tags"
          value={draft.tags}
          onChange={(next) => setDraft((d) => ({ ...d, tags: next }))}
        />
      </Field>

      {lintErrors.length > 0 ? (
        <ul className={styles.lintErrors} role="alert">
          {lintErrors.map((err) => (
            <li key={err} className={styles.lintErr}>
              {err}
            </li>
          ))}
        </ul>
      ) : null}
      {error ? (
        <p className={styles.error} role="alert">
          {error}
        </p>
      ) : null}

      <div className={styles.saveRow}>
        <button
          type="submit"
          className={styles.save}
          disabled={!dirty || saving || typeRenameRequired}
        >
          {dirty ? <span className={styles.dirty}>·</span> : null}
          {saving ? 'Saving…' : 'Save'}
          <kbd className={styles.kbd}>⌘S</kbd>
        </button>
      </div>
    </form>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className={styles.field}>
      <span className={styles.label}>{label}</span>
      {children}
    </label>
  );
}
