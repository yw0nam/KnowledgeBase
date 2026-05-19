import { useCallback, useState } from 'react';
import { BrowserRouter, Route, Routes } from 'react-router-dom';
import { DashboardPage } from './DashboardPage';
import { Nav } from './components/Nav';
import { QueuePage } from './QueuePage';
import type { DashboardMeta } from './dashboardTypes';
import styles from './AppShell.module.css';

export function App() {
  const [dashboardMeta, setDashboardMeta] = useState<DashboardMeta | null>(null);

  const handleMetaChange = useCallback((meta: DashboardMeta | null) => {
    setDashboardMeta(meta);
  }, []);

  return (
    <BrowserRouter>
      <div className={styles.shell}>
        <Nav meta={dashboardMeta} />
        <Routes>
          <Route path="/" element={<QueuePage />} />
          <Route
            path="/dashboard"
            element={<DashboardPage onMetaChange={handleMetaChange} />}
          />
        </Routes>
      </div>
    </BrowserRouter>
  );
}
