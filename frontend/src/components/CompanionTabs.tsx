// Tab container that lives below the rendered page body. Designed
// to hold Raw / Lint as future siblings — for now it only shows
// Feedback, and the tab strip is kept visible (rather than hiding
// it for a single tab) so the surface is honest about what it is.

import type { ReactNode } from 'react';
import styles from './CompanionTabs.module.css';

export interface CompanionTab {
  id: string;
  label: string;
  hint?: string; // optional kbd hint, e.g. '⌘1'
  content: ReactNode;
}

interface Props {
  tabs: CompanionTab[];
  active: string;
  onActiveChange: (id: string) => void;
}

export function CompanionTabs({ tabs, active, onActiveChange }: Props) {
  const activeTab = tabs.find((t) => t.id === active) ?? tabs[0];
  if (!activeTab) return null;
  return (
    <section className={styles.tabs} aria-label="Page companion">
      <div className={styles.strip} role="tablist">
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            id={`tab-${t.id}`}
            aria-selected={t.id === active}
            aria-controls={`panel-${t.id}`}
            className={`${styles.tab} ${t.id === active ? styles.tabActive : ''}`}
            onClick={() => onActiveChange(t.id)}
          >
            <span>{t.label}</span>
            {t.hint ? <kbd className={styles.kbd}>{t.hint}</kbd> : null}
          </button>
        ))}
      </div>
      <div
        className={styles.panel}
        role="tabpanel"
        id={`panel-${activeTab.id}`}
        aria-labelledby={`tab-${activeTab.id}`}
      >
        {activeTab.content}
      </div>
    </section>
  );
}
