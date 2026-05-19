// Fetcher for /api/dashboard. Reuses the same ApiError contract as
// api.ts so error rendering is consistent across pages.

import { ApiError } from './api';
import type { DashboardResponse, DashboardWindow } from './dashboardTypes';

export function fetchDashboard(weeks: DashboardWindow): Promise<DashboardResponse> {
  const path = `/api/dashboard?window=${weeks}`;
  return fetch(path, { headers: { Accept: 'application/json' } }).then(async (res) => {
    if (!res.ok) {
      throw new ApiError(res.status, `${res.status} ${res.statusText} on ${path}`);
    }
    return (await res.json()) as DashboardResponse;
  });
}
