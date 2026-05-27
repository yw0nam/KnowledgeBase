// Top nav: three segments (Pending / Decisions / Dashboard). Spec
// §7.1. "Pending (n)" shows the live pending count when known. On
// /dashboard the right edge keeps the freshness line.

import { NavLink, useLocation } from 'react-router-dom';
import type { DashboardMeta } from '../dashboardTypes';
import { formatRelative } from '../dashboardFormat';
import styles from './Nav.module.css';

interface Props {
  meta: DashboardMeta | null;
  pendingCount: number | null;
}

export function Nav({ meta, pendingCount }: Props) {
  const location = useLocation();
  const onDashboard = location.pathname === '/dashboard';

  return (
    <header className={styles.nav}>
      <div className={styles.segments}>
        <NavLink
          to="/"
          end
          className={({ isActive }) =>
            isActive ? `${styles.link} ${styles.linkActive}` : styles.link
          }
        >
          Pending
          {pendingCount !== null ? (
            <span className={styles.count}> ({pendingCount})</span>
          ) : null}
        </NavLink>
        <NavLink
          to="/decisions"
          className={({ isActive }) =>
            isActive ? `${styles.link} ${styles.linkActive}` : styles.link
          }
        >
          Decisions
        </NavLink>
        <NavLink
          to="/dashboard"
          className={({ isActive }) =>
            isActive ? `${styles.link} ${styles.linkActive}` : styles.link
          }
        >
          Dashboard
        </NavLink>
      </div>
      {onDashboard && meta && meta.log_last_entry ? (
        <span
          className={`${styles.freshness} ${meta.is_stale ? styles.freshnessStale : ''}`}
        >
          data · {formatRelative(meta.log_last_entry)}
          {meta.is_stale ? ' · stale' : ''}
        </span>
      ) : null}
    </header>
  );
}
