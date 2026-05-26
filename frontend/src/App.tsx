import { useCallback, useEffect, useState } from 'react';
import { BrowserRouter, Route, Routes, useNavigate } from 'react-router-dom';
import { DashboardPage } from './DashboardPage';
import { DecisionsPage } from './DecisionsPage';
import { Nav } from './components/Nav';
import { QueuePage } from './QueuePage';
import { fetchQueue } from './api';
import { useLeaderShortcut } from './hooks/useLeaderShortcut';
import type { DashboardMeta } from './dashboardTypes';
import styles from './AppShell.module.css';

function AppInner() {
  const navigate = useNavigate();
  useLeaderShortcut({
    p: () => navigate('/'),
    d: () => navigate('/decisions'),
    a: () => navigate('/dashboard'),
  });
  return null;
}

export function App() {
  const [dashboardMeta, setDashboardMeta] = useState<DashboardMeta | null>(null);
  const [pendingCount, setPendingCount] = useState<number | null>(null);
  const [pendingReloadKey, setPendingReloadKey] = useState(0);

  const handleMetaChange = useCallback((meta: DashboardMeta | null) => {
    setDashboardMeta(meta);
  }, []);

  const handlePendingReload = useCallback(() => {
    setPendingReloadKey((k) => k + 1);
  }, []);

  // Keep the "Pending (n)" badge in the nav live. The QueuePage emits
  // a reload event after each decide; we also refresh on mount.
  useEffect(() => {
    let cancelled = false;
    fetchQueue()
      .then((res) => {
        if (!cancelled) setPendingCount(res.meta.count);
      })
      .catch(() => {
        if (!cancelled) setPendingCount(null);
      });
    return () => {
      cancelled = true;
    };
  }, [pendingReloadKey]);

  return (
    <BrowserRouter>
      <div className={styles.shell}>
        <AppInner />
        <Nav meta={dashboardMeta} pendingCount={pendingCount} />
        <Routes>
          <Route path="/" element={<QueuePage onCountChange={handlePendingReload} />} />
          <Route path="/decisions" element={<DecisionsPage />} />
          <Route
            path="/dashboard"
            element={<DashboardPage onMetaChange={handleMetaChange} />}
          />
        </Routes>
      </div>
    </BrowserRouter>
  );
}
