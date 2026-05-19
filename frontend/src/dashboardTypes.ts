// Mirrors the response shape from /api/dashboard (see backend
// agent's parallel work). Window is one of 4/8/12/24 weeks.

export type DashboardWindow = 4 | 8 | 12 | 24;

export interface DashboardMeta {
  data_dir: string;
  auto_reject_ttl_days: number;
  log_last_entry: string | null;
  is_stale: boolean;
}

export interface DashboardWindowInfo {
  weeks: number;
  from: string;
  to: string;
}

export interface ActivityWeek {
  week_start: string;
  approved: number;
  rejected_user: number;
  rejected_auto_ttl: number;
}

export interface RejectionRateRow {
  type?: string;
  kind?: string;
  rejected: number;
  total: number;
  rate: number;
}

export interface RejectionByType {
  type: string;
  rejected: number;
  total: number;
  rate: number;
}

export interface RejectionBySourceKind {
  kind: string;
  rejected: number;
  total: number;
  rate: number;
}

export interface AutoRejectSoonEntry {
  stem: string;
  rel_path: string;
  type: string;
  title: string;
  created_at: string;
  auto_reject_at: string;
  hours_remaining: number;
}

export interface RecentRejection {
  stem: string;
  title: string;
  type: string;
  source_kinds: string[];
  rejected_at: string;
  rejected_by: 'user' | 'auto_ttl';
  feedback_excerpt: string;
}

export interface MatrixCell {
  type: string;
  source_kind: string;
  approved: number;
  rejected: number;
  total: number;
  rate: number;
}

export interface RejectionByTypeAndSource {
  types: string[];
  source_kinds: string[];
  cells: MatrixCell[];
}

export interface DashboardResponse {
  window: DashboardWindowInfo;
  meta: DashboardMeta;
  activity: ActivityWeek[];
  rejection_by_type: RejectionByType[];
  rejection_by_source_kind: RejectionBySourceKind[];
  rejection_by_type_and_source?: RejectionByTypeAndSource;
  auto_reject_soon: AutoRejectSoonEntry[];
  recent_rejections: RecentRejection[];
}
