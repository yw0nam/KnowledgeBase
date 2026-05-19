// Top nav: two segments (Queue / Dashboard). On /dashboard the right
// edge shows a tiny mono freshness line driven by /api/dashboard's
// meta.log_last_entry. Empty on /.

import { NavLink, useLocation } from 'react-router-dom';
import type { DashboardMeta } from '../dashboardTypes';
import { formatRelative } from '../dashboardFormat';
import styles from './Nav.module.css';

interface Props {
  meta: DashboardMeta | null;
}

export function Nav({ meta }: Props) {
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
          Queue
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
