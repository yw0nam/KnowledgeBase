// Center column — the focused page. Frontmatter strip + rendered
// markdown body. Companion tabs (Raw / Lint) defer to Phase B.

import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { pageTitle } from '../api';
import type { ReviewPage } from '../types';
import { CompanionTabs } from './CompanionTabs';
import { FeedbackTab } from './FeedbackTab';
import { Frontmatter } from './Frontmatter';
import styles from './PageDetail.module.css';

interface Props {
  page: ReviewPage;
}

// Strip a single leading H1 from the body when it matches the title
// we already render in the header — wiki pages routinely start with
// `# {title}` and rendering it twice is just noise.
function stripDuplicateH1(body: string, title: string): string {
  const match = body.match(/^\s*#\s+(.+?)\s*$/m);
  if (!match || match.index === undefined) return body;
  const headingText = match[1]?.trim().toLowerCase();
  if (!headingText) return body;
  if (headingText !== title.trim().toLowerCase()) return body;
  return body.slice(match.index + match[0].length).replace(/^\s*\n/, '');
}

export function PageDetail({ page }: Props) {
  const title = pageTitle(page);
  const body = stripDuplicateH1(page.body, title);
  const [activeTab, setActiveTab] = useState<string>('feedback');
  return (
    <article className={styles.detail} aria-labelledby="page-title">
      <header className={styles.header}>
        <p className={styles.path}>{page.rel_path}</p>
        <h2 id="page-title" className={styles.title}>
          {title}
        </h2>
      </header>
      <Frontmatter fm={page.frontmatter} />
      <div className={styles.body}>
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{body}</ReactMarkdown>
      </div>
      <CompanionTabs
        active={activeTab}
        onActiveChange={setActiveTab}
        tabs={[
          {
            id: 'feedback',
            label: 'Feedback',
            content: <FeedbackTab stem={page.stem} />,
          },
        ]}
      />
    </article>
  );
}
