// Pure formatting helpers for the dashboard. No locale, no library —
// Intl/Date is enough.

export function formatRelative(iso: string | null, now: Date = new Date()): string {
  if (!iso) return '';
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return '';
  const seconds = Math.max(0, (now.getTime() - then.getTime()) / 1000);
  if (seconds < 60) return `${Math.round(seconds)}s ago`;
  const minutes = seconds / 60;
  if (minutes < 60) return `${Math.round(minutes)}m ago`;
  const hours = minutes / 60;
  if (hours < 24) return `${Math.round(hours)}h ago`;
  const days = hours / 24;
  if (days < 7) return `${Math.round(days)}d ago`;
  return then.toISOString().slice(0, 10);
}

export function formatHours(totalHours: number): string {
  if (totalHours < 0) totalHours = 0;
  if (totalHours < 1) {
    const minutes = Math.round(totalHours * 60);
    return `${minutes}m`;
  }
  const whole = Math.floor(totalHours);
  const fractional = totalHours - whole;
  if (whole < 24 && fractional > 0) {
    const minutes = Math.round(fractional * 60);
    if (minutes === 0) return `${whole}h`;
    if (minutes === 60) return `${whole + 1}h`;
    return `${whole}h ${minutes}m`;
  }
  return `${whole}h`;
}

// "Mar 25" — short month + day, en-US (stable across locales for
// chart axis labels).
const AXIS_FMT = new Intl.DateTimeFormat('en-US', {
  month: 'short',
  day: 'numeric',
});

export function formatWeekAxis(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return AXIS_FMT.format(d);
}

export function formatIsoDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toISOString().slice(0, 10);
}

export function capitalize(word: string): string {
  if (!word) return word;
  return word.charAt(0).toUpperCase() + word.slice(1);
}

// Whole-hours diff between `now` and an ISO timestamp. Returns 0 if iso is
// null or unparseable. Used by the stale banner; we render it as
// "{N} {hour/hours} ago" with the integer-rounded count.
export function hoursAgo(iso: string | null, now: Date = new Date()): number {
  if (!iso) return 0;
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return 0;
  const ms = now.getTime() - then.getTime();
  return Math.max(0, Math.round(ms / 3_600_000));
}
