// Per-stem reviewer-feedback draft, persisted to localStorage so it
// survives page-switches and reloads. Cleared when an approve or
// reject succeeds — the draft becomes the action's feedback text.

const KEY_PREFIX = 'kb-review-feedback:';

function key(stem: string): string {
  return `${KEY_PREFIX}${stem}`;
}

export function readDraft(stem: string): string {
  if (typeof window === 'undefined') return '';
  return window.localStorage.getItem(key(stem)) ?? '';
}

export function writeDraft(stem: string, value: string): void {
  if (typeof window === 'undefined') return;
  if (value === '') {
    window.localStorage.removeItem(key(stem));
  } else {
    window.localStorage.setItem(key(stem), value);
  }
}

export function clearDraft(stem: string): void {
  if (typeof window === 'undefined') return;
  window.localStorage.removeItem(key(stem));
}
