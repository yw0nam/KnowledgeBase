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
// Distinct constant for the source-axis filter on Recent Rejections. The
// underlying string value matches ALL_TYPES_FILTER on purpose (both are
// sentinel "any" values), but the second declaration makes axis intent
// obvious at every call site so callers don't accidentally cross axes.
const ALL_SOURCES_FILTER = '__all__';

// Mirrors backend KNOWN_SOURCE_KINDS. Chip render order follows this list
// so the source row stays stable across reloads.
const CANONICAL_SOURCE_KINDS = [
  'github',
  'conversations',
  'calendar',
  'web',
  'manual',
  'unknown',
] as const;

function prefersReducedMotion(): boolean {
  return (
    typeof window !== 'undefined' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  );
}

// Shared scroll behavior for drilldown callers (matrix + rate cards). The
// matrix sets both filters at once; rate cards set one axis. Both want
// the rejections card brought into view, with reduced-motion honored.
function scrollSectionIntoView(el: HTMLElement | null): void {
  if (!el) return;
  el.scrollIntoView({
    behavior: prefersReducedMotion() ? 'auto' : 'smooth',
    block: 'start',
  });
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
  const [recentSourceFilter, setRecentSourceFilter] =
    useState<string>(ALL_SOURCES_FILTER);
  const rejectionsRef = useRef<HTMLElement | null>(null);

  // Drilldown from the type×source matrix: set BOTH axes at once and
  // scroll the rejections card into view. Honors the operator's
  // reduced-motion preference — the smooth scroll falls back to instant.
  const handleMatrixCellSelect = useCallback((type: string, sourceKind: string) => {
    setRecentFilter(type);
    setRecentSourceFilter(sourceKind);
    scrollSectionIntoView(rejectionsRef.current);
  }, []);

  // 1D drilldown wires: BY TYPE / BY SOURCE rate cards each pin one axis
  // and leave the orthogonal axis untouched. Both scroll the rejections
  // card into view via the same helper as the 2D matrix.
  const handleRateTypeSelect = useCallback((type: string) => {
    setRecentFilter(type);
    scrollSectionIntoView(rejectionsRef.current);
  }, []);
  const handleRateSourceSelect = useCallback((sourceKind: string) => {
    setRecentSourceFilter(sourceKind);
    scrollSectionIntoView(rejectionsRef.current);
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
                  onRowSelect={handleRateTypeSelect}
                  selectedRow={
                    recentFilter !== ALL_TYPES_FILTER ? recentFilter : undefined
                  }
                  selectionAxisLabel="rejections"
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
                  onRowSelect={handleRateSourceSelect}
                  selectedRow={
                    recentSourceFilter !== ALL_SOURCES_FILTER
                      ? recentSourceFilter
                      : undefined
                  }
                  selectionAxisLabel="rejections by source"
                />
              </div>
            </div>
            <TypeSourceMatrix
              matrix={state.data.rejection_by_type_and_source}
              selectedType={recentFilter}
              selectedSource={recentSourceFilter}
              onCellSelect={handleMatrixCellSelect}
            />
            <RecentRejectionsCard
              items={state.data.recent_rejections}
              typeFilter={recentFilter}
              onTypeFilterChange={setRecentFilter}
              sourceFilter={recentSourceFilter}
              onSourceFilterChange={setRecentSourceFilter}
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
  // When provided, each row's label becomes a full-row click target that
  // drills the rejections card down to this label on the relevant axis.
  onRowSelect?: (label: string) => void;
  // The label of the currently-pinned row on this axis (raw, lowercase).
  selectedRow?: string;
  // Suffix used in aria-labels: "Filter <selectionAxisLabel> to <Label>".
  // Lets the BY TYPE card say "rejections" and the BY SOURCE card say
  // "rejections by source", with no extra plumbing.
  selectionAxisLabel?: string;
}

function RateCard({
  heading,
  rows,
  capitalizeLabels,
  showVolume,
  onRowSelect,
  selectedRow,
  selectionAxisLabel,
}: RateCardProps) {
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
          const active = !!selectedRow && selectedRow === row.label;
          const rowCls = active
            ? `${styles.rateRow} ${styles.rateRowActive}`
            : styles.rateRow;
          // Label cell is either a static span or a button-shaped span
          // depending on whether the parent wired drilldown. The button
          // intentionally fills the leftmost grid column only — the bars
          // stay non-interactive so meaning stays read-only.
          const labelNode = onRowSelect ? (
            <button
              type="button"
              className={`${styles.rateLabel} ${styles.rateLabelButton}`}
              aria-label={`Filter ${selectionAxisLabel ?? 'rejections'} to ${display} (${isEmpty ? '0%' : `${pct}%`} over ${row.total} pages)`}
              aria-pressed={active}
              onClick={() => onRowSelect(row.label)}
            >
              {display}
            </button>
          ) : (
            <span className={styles.rateLabel}>{display}</span>
          );
          return (
            <div key={row.label} className={rowCls}>
              {labelNode}
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
  selectedSource?: string;
  onCellSelect?: (type: string, sourceKind: string) => void;
}

// Cross-cut of rejection rate × volume across (type, source_kind). Sparse
// cells come from the backend; we filter rows/columns where every cell is
// empty so the operator scans a dense surface. Empty cells render `—` so
// the table doesn't look noisy with zeros. PRODUCT.md success scenario:
// "concepts × conversations 60% reject rate" jumps out at a glance.
//
// When `onCellSelect` is provided, non-empty cells become buttons that
// drill BOTH axes (type + source) on the Recent Rejections card. The row
// header active state still tracks `selectedType` alone, while the cell
// active state requires both `selectedType` and `selectedSource` to match
// (with the `__all__` sentinels treated as wildcards).
function TypeSourceMatrix({
  matrix,
  selectedType,
  selectedSource,
  onCellSelect,
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
              const rowSelected =
                !!selectedType &&
                selectedType !== ALL_TYPES_FILTER &&
                selectedType === t;
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
                    // A cell is "active" only when BOTH selected axes
                    // match this cell. `__all__` is a wildcard so e.g.
                    // a row-only drilldown lights the whole row but no
                    // individual cell within it claims to be the chosen
                    // intersection.
                    const typeMatches =
                      !selectedType ||
                      selectedType === ALL_TYPES_FILTER ||
                      selectedType === t;
                    const sourceMatches =
                      !selectedSource ||
                      selectedSource === ALL_SOURCES_FILTER ||
                      selectedSource === s;
                    const cellActive =
                      typeMatches &&
                      sourceMatches &&
                      // Require at least one axis to be pinned so the
                      // matrix doesn't tint every cell when no filter
                      // is set.
                      ((!!selectedType && selectedType !== ALL_TYPES_FILTER) ||
                        (!!selectedSource && selectedSource !== ALL_SOURCES_FILTER));
                    const cellCls = cellActive
                      ? `${styles.matrixCell} ${styles.matrixCellActive}`
                      : styles.matrixCell;
                    return (
                      <td key={s} className={cellCls}>
                        {onCellSelect ? (
                          <button
                            type="button"
                            className={styles.matrixCellButton}
                            onClick={() => onCellSelect(t, s)}
                            aria-label={`Filter rejections to ${capitalize(t)} with source ${capitalize(s)} (${pct}% over ${cell.total} pages)`}
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
  typeFilter: string;
  onTypeFilterChange: (filter: string) => void;
  sourceFilter: string;
  onSourceFilterChange: (filter: string) => void;
  sectionRef?: Ref<HTMLElement>;
}

// Predicate helpers — `__all__` is the wildcard sentinel on each axis.
// `source_kinds` is a list, so source matching uses `.includes()` (a page
// touching multiple kinds appears under every kind's chip). Mirrors the
// backend's by_source_kind aggregator.
function matchesType(item: RecentRejection, typeFilter: string): boolean {
  return typeFilter === ALL_TYPES_FILTER || item.type === typeFilter;
}
function matchesSource(item: RecentRejection, sourceFilter: string): boolean {
  return (
    sourceFilter === ALL_SOURCES_FILTER || item.source_kinds.includes(sourceFilter)
  );
}

function RecentRejectionsCard({
  items,
  typeFilter,
  onTypeFilterChange,
  sourceFilter,
  onSourceFilterChange,
  sectionRef,
}: RecentRejectionsCardProps) {
  const count = items.length;

  // Cross-filter-aware chip counts: each chip's count shows how many
  // pages would remain visible after clicking it now (orthogonal axis
  // still applied). "All" on each axis = total matching the orthogonal
  // filter only.
  const typeAxisItems = items.filter((it) => matchesSource(it, sourceFilter));
  const countsByType = typeAxisItems.reduce<Record<string, number>>((acc, it) => {
    const key = it.type || '(untyped)';
    acc[key] = (acc[key] ?? 0) + 1;
    return acc;
  }, {});
  const typeAllCount = typeAxisItems.length;

  const sourceAxisItems = items.filter((it) => matchesType(it, typeFilter));
  // "some" semantics: a page contributes to each of its source_kinds.
  const countsBySource = sourceAxisItems.reduce<Record<string, number>>((acc, it) => {
    for (const kind of it.source_kinds) {
      acc[kind] = (acc[kind] ?? 0) + 1;
    }
    return acc;
  }, {});
  const sourceAllCount = sourceAxisItems.length;

  // Chip-row visibility is computed against the unfiltered list so a
  // chip row doesn't collapse when the orthogonal filter narrows things
  // to a single type/source. We still want the operator to see the row
  // and the zero counts.
  const allTypesPresent = CANONICAL_REVIEW_TYPES.filter((t) =>
    items.some((it) => it.type === t),
  );
  const showTypeChips = allTypesPresent.length >= 2;

  const allSourcesPresent = CANONICAL_SOURCE_KINDS.filter((s) =>
    items.some((it) => it.source_kinds.includes(s)),
  );
  const showSourceChips = allSourcesPresent.length >= 2;

  const filteredItems = items.filter(
    (it) => matchesType(it, typeFilter) && matchesSource(it, sourceFilter),
  );

  const filterActive =
    typeFilter !== ALL_TYPES_FILTER || sourceFilter !== ALL_SOURCES_FILTER;

  return (
    <section className={styles.card} ref={sectionRef}>
      <h2 className={styles.cardHeading}>Recent Rejections (last {count})</h2>
      {items.length === 0 ? (
        <p className={styles.empty}>No rejections in the last 5 cycles.</p>
      ) : (
        <>
          {showTypeChips || showSourceChips ? (
            <div className={styles.recentChipGroups}>
              {showTypeChips ? (
                <div className={styles.recentChipGroup}>
                  <span className={styles.recentChipGroupLabel}>by type</span>
                  <div
                    className={styles.recentChips}
                    role="tablist"
                    aria-label="Filter recent rejections by type"
                  >
                    <RecentChip
                      label="All"
                      value={ALL_TYPES_FILTER}
                      count={typeAllCount}
                      active={typeFilter === ALL_TYPES_FILTER}
                      onSelect={onTypeFilterChange}
                    />
                    {allTypesPresent.map((t) => (
                      <RecentChip
                        key={t}
                        label={capitalize(t)}
                        value={t}
                        count={countsByType[t] ?? 0}
                        active={typeFilter === t}
                        onSelect={onTypeFilterChange}
                      />
                    ))}
                  </div>
                </div>
              ) : null}
              {showSourceChips ? (
                <div className={styles.recentChipGroup}>
                  <span className={styles.recentChipGroupLabel}>by source</span>
                  <div
                    className={styles.recentChips}
                    role="tablist"
                    aria-label="Filter recent rejections by source"
                  >
                    <RecentChip
                      label="All"
                      value={ALL_SOURCES_FILTER}
                      count={sourceAllCount}
                      active={sourceFilter === ALL_SOURCES_FILTER}
                      onSelect={onSourceFilterChange}
                    />
                    {allSourcesPresent.map((s) => (
                      <RecentChip
                        key={s}
                        label={capitalize(s)}
                        value={s}
                        count={countsBySource[s] ?? 0}
                        active={sourceFilter === s}
                        onSelect={onSourceFilterChange}
                      />
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          ) : null}
          {filteredItems.length === 0 ? (
            <p className={styles.empty}>
              {filterActive
                ? 'No rejections matching this filter.'
                : 'No rejections in the last 5 cycles.'}
            </p>
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
