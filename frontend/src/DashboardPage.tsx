import { useCallback, useEffect, useRef, useState, type Ref } from 'react';
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
  MatrixCell,
  RecentRejection,
  RejectionBySourceKind,
  RejectionByTypeAndSource,
} from './dashboardTypes';
import { CommandPalette } from './components/CommandPalette';
import { StaleBanner } from './components/StaleBanner';
import styles from './DashboardPage.module.css';

const WINDOW_OPTIONS: DashboardWindow[] = [4, 8, 12, 24];

// Six review-status wiki types; "summary" is excluded — summaries do not
// flow through the approve/reject lifecycle and therefore never appear in
// recent rejections. Order matches docs/reference/wiki-categories.md so the
// chip row reads top-down the same way the wiki is structured.
const CANONICAL_REVIEW_TYPES = [
  'entity',
  'concept',
  'decision',
  'improvement',
  'checklist',
  'question',
] as const;

const ALL_TYPES_FILTER = '__all__';

function prefersReducedMotion(): boolean {
  return (
    typeof window !== 'undefined' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  );
}

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
  const [recentFilter, setRecentFilter] = useState<string>(ALL_TYPES_FILTER);
  const rejectionsRef = useRef<HTMLElement | null>(null);

  // Drilldown from the type×source matrix: change chip selection on the
  // rejections card and scroll the card into view. Honors the operator's
  // reduced-motion preference — the smooth scroll falls back to instant.
  const handleMatrixTypeSelect = useCallback((type: string) => {
    setRecentFilter(type);
    const el = rejectionsRef.current;
    if (el) {
      el.scrollIntoView({
        behavior: prefersReducedMotion() ? 'auto' : 'smooth',
        block: 'start',
      });
    }
  }, []);

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
        {state.status === 'ready' && state.data.meta.is_stale ? (
          <StaleBanner
            isStale={state.data.meta.is_stale}
            logLastEntry={state.data.meta.log_last_entry}
          />
        ) : null}

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
                  showVolume
                />
              </div>
            </div>
            <TypeSourceMatrix
              matrix={state.data.rejection_by_type_and_source}
              selectedType={recentFilter}
              onTypeSelect={handleMatrixTypeSelect}
            />
            <RecentRejectionsCard
              items={state.data.recent_rejections}
              filter={recentFilter}
              onFilterChange={setRecentFilter}
              sectionRef={rejectionsRef}
            />
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
      <ActivityTable activity={activity} />
    </section>
  );
}

interface ActivityTableProps {
  activity: ActivityWeek[];
}

// Compact below-chart table so operators don't have to hover each bar to
// read the numbers. Internal scroll only — never lifts the card height.
function ActivityTable({ activity }: ActivityTableProps) {
  if (activity.length === 0) return null;
  return (
    <div className={styles.activityTableWrap}>
      <table className={styles.activityTable}>
        <thead>
          <tr>
            <th>week</th>
            <th>approved</th>
            <th>rejected (user)</th>
            <th>rejected (auto)</th>
            <th>total</th>
          </tr>
        </thead>
        <tbody>
          {activity.map((w) => {
            const total = w.approved + w.rejected_user + w.rejected_auto_ttl;
            return (
              <tr key={w.week_start}>
                <td className={styles.activityWeekCell}>
                  {formatIsoDate(w.week_start)}
                </td>
                <td className={styles.activityNumApproved}>{w.approved}</td>
                <td className={styles.activityNumRejectedUser}>{w.rejected_user}</td>
                <td className={styles.activityNumRejectedAuto}>
                  {w.rejected_auto_ttl}
                </td>
                <td className={styles.activityNumTotal}>{total}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
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
  showVolume?: boolean;
}

function RateCard({ heading, rows, capitalizeLabels, showVolume }: RateCardProps) {
  const maxTotal = showVolume ? rows.reduce((m, r) => Math.max(m, r.total), 0) : 0;
  return (
    <section className={styles.card}>
      <h2 className={styles.cardHeading}>{heading}</h2>
      <div className={styles.rateList}>
        {rows.map((row) => {
          const isEmpty = row.total === 0;
          const display = capitalizeLabels ? capitalize(row.label) : row.label;
          const pct = Math.round(row.rate * 100);
          const volPct = showVolume && maxTotal > 0 ? (row.total / maxTotal) * 100 : 0;
          return (
            <div key={row.label} className={styles.rateRow}>
              <span className={styles.rateLabel}>{display}</span>
              {isEmpty && !showVolume ? (
                <span />
              ) : showVolume ? (
                <div className={`${styles.rateTrack} ${styles.rateTrackDual}`}>
                  <div className={styles.rateBarSlot}>
                    {!isEmpty ? (
                      <div
                        className={styles.rateBar}
                        style={{ width: `${Math.max(0, Math.min(100, pct))}%` }}
                      />
                    ) : null}
                  </div>
                  <div className={styles.rateBarSlot}>
                    <div
                      className={styles.volumeBar}
                      style={{ width: `${Math.max(0, Math.min(100, volPct))}%` }}
                      aria-label={`volume ${row.total}`}
                    />
                  </div>
                </div>
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

interface TypeSourceMatrixProps {
  matrix: RejectionByTypeAndSource | undefined;
  selectedType?: string;
  onTypeSelect?: (type: string) => void;
}

// Cross-cut of rejection rate × volume across (type, source_kind). Sparse
// cells come from the backend; we filter rows/columns where every cell is
// empty so the operator scans a dense surface. Empty cells render `—` so
// the table doesn't look noisy with zeros. PRODUCT.md success scenario:
// "concepts × conversations 60% reject rate" jumps out at a glance.
//
// When `onTypeSelect` is provided, non-empty cells become buttons that
// drill down into the Recent Rejections card. `selectedType` highlights
// the row matching the current Recent Rejections chip so the matrix and
// the rejections list stay visually coupled.
function TypeSourceMatrix({
  matrix,
  selectedType,
  onTypeSelect,
}: TypeSourceMatrixProps) {
  // Backend may not have shipped yet — render section heading + loading
  // shape so layout is stable on first render before the field exists.
  if (!matrix) {
    return (
      <section className={styles.card}>
        <h2 className={styles.cardHeading}>REJECTION RATE BY TYPE × SOURCE</h2>
        <p className={styles.empty}>Loading…</p>
      </section>
    );
  }

  const cellLookup = new Map<string, MatrixCell>();
  for (const cell of matrix.cells) {
    if (cell.total > 0) cellLookup.set(`${cell.type}::${cell.source_kind}`, cell);
  }

  const visibleTypes = matrix.types.filter((t) =>
    matrix.source_kinds.some((s) => cellLookup.has(`${t}::${s}`)),
  );
  const visibleSources = matrix.source_kinds.filter((s) =>
    matrix.types.some((t) => cellLookup.has(`${t}::${s}`)),
  );

  if (visibleTypes.length === 0 || visibleSources.length === 0) {
    return (
      <section className={styles.card}>
        <h2 className={styles.cardHeading}>REJECTION RATE BY TYPE × SOURCE</h2>
        <p className={styles.empty}>
          Not enough data for a type × source breakdown yet.
        </p>
      </section>
    );
  }

  return (
    <section className={styles.card}>
      <h2 className={styles.cardHeading}>REJECTION RATE BY TYPE × SOURCE</h2>
      <div className={styles.matrixScroll}>
        <table className={styles.matrixTable}>
          <thead>
            <tr>
              <th className={styles.matrixCorner} aria-hidden="true" />
              {visibleSources.map((s) => (
                <th key={s} className={styles.matrixColHeader} scope="col">
                  {capitalize(s)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visibleTypes.map((t) => {
              const rowSelected = !!selectedType && selectedType === t;
              const rowHeaderCls = rowSelected
                ? `${styles.matrixRowHeader} ${styles.matrixRowHeaderActive}`
                : styles.matrixRowHeader;
              return (
                <tr key={t}>
                  <th className={rowHeaderCls} scope="row">
                    {capitalize(t)}
                  </th>
                  {visibleSources.map((s) => {
                    const cell = cellLookup.get(`${t}::${s}`);
                    if (!cell) {
                      return (
                        <td
                          key={s}
                          className={`${styles.matrixCell} ${styles.matrixEmpty}`}
                        >
                          —
                        </td>
                      );
                    }
                    const pct = Math.round(cell.rate * 100);
                    const cellContent = (
                      <>
                        <div className={styles.matrixRate}>{pct}%</div>
                        <div className={styles.matrixCount}>n={cell.total}</div>
                      </>
                    );
                    const cellCls = rowSelected
                      ? `${styles.matrixCell} ${styles.matrixCellActive}`
                      : styles.matrixCell;
                    return (
                      <td key={s} className={cellCls}>
                        {onTypeSelect ? (
                          <button
                            type="button"
                            className={styles.matrixCellButton}
                            onClick={() => onTypeSelect(t)}
                            aria-label={`Filter rejections to ${capitalize(t)} (${pct}% over ${cell.total} pages with source ${capitalize(s)})`}
                          >
                            {cellContent}
                          </button>
                        ) : (
                          cellContent
                        )}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
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
  filter: string;
  onFilterChange: (filter: string) => void;
  sectionRef?: Ref<HTMLElement>;
}

function RecentRejectionsCard({
  items,
  filter,
  onFilterChange,
  sectionRef,
}: RecentRejectionsCardProps) {
  const count = items.length;

  const countsByType = items.reduce<Record<string, number>>((acc, it) => {
    const key = it.type || '(untyped)';
    acc[key] = (acc[key] ?? 0) + 1;
    return acc;
  }, {});
  // Type chips render in canonical order so the row stays stable across reloads.
  const typesPresent = CANONICAL_REVIEW_TYPES.filter((t) => (countsByType[t] ?? 0) > 0);
  const showChips = typesPresent.length >= 2;

  const filteredItems =
    filter === ALL_TYPES_FILTER ? items : items.filter((it) => it.type === filter);

  return (
    <section className={styles.card} ref={sectionRef}>
      <h2 className={styles.cardHeading}>Recent Rejections (last {count})</h2>
      {items.length === 0 ? (
        <p className={styles.empty}>No rejections in the last 5 cycles.</p>
      ) : (
        <>
          {showChips ? (
            <div
              className={styles.recentChips}
              role="tablist"
              aria-label="Filter recent rejections by type"
            >
              <RecentChip
                label="All"
                value={ALL_TYPES_FILTER}
                count={count}
                active={filter === ALL_TYPES_FILTER}
                onSelect={onFilterChange}
              />
              {typesPresent.map((t) => (
                <RecentChip
                  key={t}
                  label={capitalize(t)}
                  value={t}
                  count={countsByType[t] ?? 0}
                  active={filter === t}
                  onSelect={onFilterChange}
                />
              ))}
            </div>
          ) : null}
          {filteredItems.length === 0 ? (
            <p className={styles.empty}>No rejections of this type in view.</p>
          ) : (
            <div className={styles.recentList}>
              {filteredItems.map((it) => (
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
        </>
      )}
    </section>
  );
}

interface RecentChipProps {
  label: string;
  value: string;
  count: number;
  active: boolean;
  onSelect: (value: string) => void;
}

function RecentChip({ label, value, count, active, onSelect }: RecentChipProps) {
  const cls = active
    ? `${styles.recentChip} ${styles.recentChipActive}`
    : styles.recentChip;
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      className={cls}
      onClick={() => onSelect(value)}
    >
      <span>{label}</span>
      <span className={styles.recentChipCount}>{count}</span>
    </button>
  );
}
