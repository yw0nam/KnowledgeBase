import { useCallback, useEffect, useState } from 'react';
import { ApiError } from './api';
import { fetchDashboard } from './dashboardApi';
import {
  capitalize,
  formatHours,
  formatIsoDate,
  formatWeekAxis,
} from './dashboardFormat';
import type {
  ActivityWeek,
  AutoRejectSoonEntry,
  DashboardResponse,
  DashboardWindow,
  RecentRejection,
  RejectionBySourceKind,
} from './dashboardTypes';
import { CommandPalette } from './components/CommandPalette';
import styles from './DashboardPage.module.css';

const WINDOW_OPTIONS: DashboardWindow[] = [4, 8, 12, 24];

type LoadState =
  | { status: 'loading' }
  | { status: 'ready'; data: DashboardResponse }
  | { status: 'error'; error: string };

function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return 'Unknown error';
}

interface Props {
  onMetaChange: (meta: DashboardResponse['meta'] | null) => void;
}

export function DashboardPage({ onMetaChange }: Props) {
  const [weeks, setWeeks] = useState<DashboardWindow>(8);
  const [state, setState] = useState<LoadState>({ status: 'loading' });
  const [reloadKey, setReloadKey] = useState(0);
  const [paletteOpen, setPaletteOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setState({ status: 'loading' });
    fetchDashboard(weeks)
      .then((data) => {
        if (cancelled) return;
        setState({ status: 'ready', data });
        onMetaChange(data.meta);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setState({ status: 'error', error: errorMessage(err) });
        onMetaChange(null);
      });
    return () => {
      cancelled = true;
    };
  }, [weeks, reloadKey, onMetaChange]);

  const handleReload = useCallback(() => setReloadKey((k) => k + 1), []);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setPaletteOpen((open) => !open);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  const handlePaletteReload = useCallback(() => {
    setPaletteOpen(false);
    handleReload();
  }, [handleReload]);

  const handlePaletteClose = useCallback(() => setPaletteOpen(false), []);
  const noop = useCallback(() => undefined, []);
  const noopSelect = useCallback((_stem: string) => undefined, []);

  return (
    <div className={styles.page}>
      <div className={styles.inner}>
        <TopStrip
          weeks={weeks}
          onChange={setWeeks}
          ttlDays={
            state.status === 'ready' ? state.data.meta.auto_reject_ttl_days : null
          }
          knownTtl={state.status === 'ready'}
        />

        {state.status === 'loading' ? (
          <div className={styles.systemLine}>Loading dashboard…</div>
        ) : state.status === 'error' ? (
          <div className={styles.systemLine}>
            <span>Could not reach the kb-web API.</span>
            <code className={styles.errorCode}>{state.error}</code>
            <button type="button" className={styles.retry} onClick={handleReload}>
              Retry
            </button>
          </div>
        ) : (
          <>
            <div className={styles.middleBand}>
              <ActivityCard activity={state.data.activity} weeks={weeks} />
              <div className={styles.rightColumn}>
                <AutoRejectSoonCard items={state.data.auto_reject_soon} />
                <RateCard
                  heading="REJECTION RATE BY TYPE"
                  rows={state.data.rejection_by_type.map((r) => ({
                    label: r.type,
                    rate: r.rate,
                    total: r.total,
                  }))}
                  capitalizeLabels
                />
                <RateCard
                  heading="REJECTION RATE BY SOURCE"
                  rows={orderSourceKinds(state.data.rejection_by_source_kind).map(
                    (r) => ({
                      label: r.kind,
                      rate: r.rate,
                      total: r.total,
                    }),
                  )}
                  capitalizeLabels
                />
              </div>
            </div>
            <RecentRejectionsCard items={state.data.recent_rejections} />
          </>
        )}
      </div>

      <CommandPalette
        open={paletteOpen}
        pages={[]}
        selectedStem={null}
        mode="idle"
        canDecide={false}
        showQueueCommands={false}
        reloadLabel="Reload dashboard"
        onClose={handlePaletteClose}
        onApprove={noop}
        onRejectStart={noop}
        onReload={handlePaletteReload}
        onSelect={noopSelect}
      />
    </div>
  );
}

// Backend already enforces `unknown` last; this is a defensive sort
// so future contract drift doesn't surface as a UI bug.
function orderSourceKinds(rows: RejectionBySourceKind[]): RejectionBySourceKind[] {
  const known = rows.filter((r) => r.kind !== 'unknown');
  const unknown = rows.filter((r) => r.kind === 'unknown');
  return [...known, ...unknown];
}

interface TopStripProps {
  weeks: DashboardWindow;
  onChange: (w: DashboardWindow) => void;
  ttlDays: number | null;
  knownTtl: boolean;
}

function TopStrip({ weeks, onChange, ttlDays, knownTtl }: TopStripProps) {
  return (
    <div className={styles.topStrip}>
      <div className={styles.windowSelector}>
        <span className={styles.windowLabel}>Window</span>
        {WINDOW_OPTIONS.map((opt) => {
          const active = opt === weeks;
          return (
            <button
              key={opt}
              type="button"
              className={`${styles.windowOption} ${active ? styles.windowOptionActive : ''}`}
              aria-pressed={active}
              onClick={() => onChange(opt)}
            >
              {opt}w
            </button>
          );
        })}
      </div>
      {knownTtl && ttlDays !== null ? (
        <span className={styles.ttlMeta}>auto-reject ttl: {ttlDays}d</span>
      ) : null}
    </div>
  );
}

interface ActivityCardProps {
  activity: ActivityWeek[];
  weeks: DashboardWindow;
}

function ActivityCard({ activity, weeks }: ActivityCardProps) {
  const maxTotal = activity.reduce(
    (m, w) => Math.max(m, w.approved + w.rejected_user + w.rejected_auto_ttl),
    0,
  );
  const isEmpty = maxTotal === 0;
  const labelStride = weeks === 24 ? 4 : 2;

  return (
    <section className={styles.card} aria-labelledby="activity-heading">
      <h2 id="activity-heading" className={styles.cardHeading}>
        Review Activity
      </h2>
      <div className={styles.chartArea}>
        <div className={styles.chart} role="presentation">
          {!isEmpty
            ? activity.map((w) => (
                <ActivityBar key={w.week_start} week={w} maxTotal={maxTotal} />
              ))
            : null}
        </div>
        <div className={styles.axisRow}>
          {activity.map((w, i) => (
            <div key={w.week_start} className={styles.axisLabelWrap}>
              <span
                className={`${styles.axisLabel} ${i % labelStride === 0 ? '' : styles.axisLabelHidden}`}
              >
                {formatWeekAxis(w.week_start)}
              </span>
            </div>
          ))}
        </div>
        {isEmpty ? (
          <p className={styles.empty}>No review activity in the last {weeks} weeks.</p>
        ) : null}
      </div>
    </section>
  );
}

interface ActivityBarProps {
  week: ActivityWeek;
  maxTotal: number;
}

function ActivityBar({ week, maxTotal }: ActivityBarProps) {
  const total = week.approved + week.rejected_user + week.rejected_auto_ttl;
  const scale = (n: number) => (maxTotal === 0 ? 0 : ((n / maxTotal) * 100).toFixed(2));

  return (
    <div className={styles.barWrap} tabIndex={0}>
      <div
        className={styles.bar}
        aria-label={`Week of ${formatIsoDate(week.week_start)}`}
      >
        {week.approved > 0 ? (
          <div
            className={styles.segApproved}
            style={{ height: `${scale(week.approved)}%` }}
          />
        ) : null}
        {week.rejected_user > 0 ? (
          <div
            className={styles.segRejectedUser}
            style={{ height: `${scale(week.rejected_user)}%` }}
          />
        ) : null}
        {week.rejected_auto_ttl > 0 ? (
          <div
            className={styles.segRejectedAuto}
            style={{ height: `${scale(week.rejected_auto_ttl)}%` }}
          />
        ) : null}
      </div>
      <div className={styles.tooltip} role="tooltip">
        <div className={styles.tooltipWeek}>{formatIsoDate(week.week_start)}</div>
        <div className={styles.tooltipLine}>
          <span>approved</span>
          <span>{week.approved}</span>
        </div>
        <div className={styles.tooltipLine}>
          <span>rejected (user)</span>
          <span>{week.rejected_user}</span>
        </div>
        <div className={styles.tooltipLine}>
          <span>rejected (auto)</span>
          <span>{week.rejected_auto_ttl}</span>
        </div>
        <div className={styles.tooltipLine}>
          <span>total</span>
          <span>{total}</span>
        </div>
      </div>
    </div>
  );
}

interface RateCardProps {
  heading: string;
  rows: Array<{ label: string; rate: number; total: number }>;
  capitalizeLabels: boolean;
}

function RateCard({ heading, rows, capitalizeLabels }: RateCardProps) {
  return (
    <section className={styles.card}>
      <h2 className={styles.cardHeading}>{heading}</h2>
      <div className={styles.rateList}>
        {rows.map((row) => {
          const isEmpty = row.total === 0;
          const display = capitalizeLabels ? capitalize(row.label) : row.label;
          const pct = Math.round(row.rate * 100);
          return (
            <div key={row.label} className={styles.rateRow}>
              <span className={styles.rateLabel}>{display}</span>
              {isEmpty ? (
                <span />
              ) : (
                <div className={styles.rateTrack}>
                  <div
                    className={styles.rateBar}
                    style={{ width: `${Math.max(0, Math.min(100, pct))}%` }}
                  />
                </div>
              )}
              <span
                className={`${styles.rateValue} ${isEmpty ? styles.rateValueEmpty : ''}`}
              >
                {isEmpty ? `—  (n=0)` : `${pct}%  (n=${row.total})`}
              </span>
            </div>
          );
        })}
      </div>
    </section>
  );
}

interface AutoRejectSoonCardProps {
  items: AutoRejectSoonEntry[];
}

function AutoRejectSoonCard({ items }: AutoRejectSoonCardProps) {
  return (
    <section className={styles.card}>
      <h2 className={styles.cardHeading}>Auto-reject Soon</h2>
      {items.length === 0 ? (
        <p className={styles.empty}>No pages within 72 hours of auto-rejection.</p>
      ) : (
        <div className={styles.expiringList}>
          {items.map((it) => {
            const display = it.title || it.stem;
            const urgent = it.hours_remaining <= 24;
            return (
              <div key={it.stem} className={styles.expiringRow}>
                <span className={styles.expiringTitle}>{display}</span>
                <span className={styles.expiringMeta}>
                  <span>{it.type}</span>
                  <span className={urgent ? styles.expiringCountdownSignal : undefined}>
                    · {formatHours(it.hours_remaining)}
                  </span>
                </span>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}

interface RecentRejectionsCardProps {
  items: RecentRejection[];
}

function RecentRejectionsCard({ items }: RecentRejectionsCardProps) {
  const count = items.length;
  return (
    <section className={styles.card}>
      <h2 className={styles.cardHeading}>Recent Rejections (last {count})</h2>
      {items.length === 0 ? (
        <p className={styles.empty}>No rejections in the last 5 cycles.</p>
      ) : (
        <div className={styles.recentList}>
          {items.map((it) => (
            <article key={it.stem} className={styles.recentRow}>
              <h3 className={styles.recentTitle}>{it.title || it.stem}</h3>
              <div className={styles.recentMeta}>
                {it.type} · {it.source_kinds.join(', ') || '—'} · {it.rejected_by} ·{' '}
                {formatIsoDate(it.rejected_at)}
              </div>
              {it.feedback_excerpt ? (
                <p className={styles.recentQuote}>{it.feedback_excerpt}</p>
              ) : (
                <p className={styles.recentNoFeedback}>no feedback recorded.</p>
              )}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
