# Product

## Register

product

## Users

A single owner-operator (the repo author) running KnowledgeBase as a personal LLM-fed wiki and operations system. The user already lives in the CLI (`kb-lint-wiki`, `kb-wiki-review`, daily report scripts) and reads finished wiki pages inside Antigravity or Obsidian — those tools own the reading experience.

The user comes to this frontend in short, focused sessions, usually after the daily ingest/fill cron has produced new candidate wiki pages, rejections, and handoff updates. The job is to:

1. Review pending AI-written wiki pages and approve, reject, or send back for revision.
2. Track handoff documents in flight — what's open, what's been promoted, what's stalled.
3. Read the dashboard for rejection and acceptance patterns: which wiki types get rejected most, which sources produce noisy raw data, which rejected pages are about to be deleted by the TTL sweep.

Context of use: desktop browser on a local network, alongside an editor and terminal. Sessions are minutes long, not hours. No phone use, no on-the-go review.

## Product Purpose

A precise, calm review-and-insights surface for an LLM-fed wiki the user has already built around `kb-wiki-review`, handoff documents, and lint. The frontend exists to:

- Replace the parts of `kb-wiki-review` that are slow or blind in a terminal: side-by-side review of pending pages with their raw sources, batch decisions, and the "what's about to expire" view.
- Make handoff status legible at a glance instead of grepping `data/handoffs/`.
- Surface the patterns in accept / reject decisions that no individual page review can show: rejection rate by wiki type, by source, by author-agent, by time-of-week; TTL countdown for rejected pages; what's about to be permanently deleted.

Out of scope for now: wiki page reading (Antigravity/Obsidian do this), editing wiki bodies, raw source browsing, content authoring, multi-user collaboration, mobile.

Success looks like: a one-screen weekly read tells the user *"the AI is over-producing concept pages from conversation sources and 60% are getting rejected for thin sourcing"* — a finding the CLI cannot produce, and that changes upstream prompts.

## Brand Personality

Calm, precise, expert-tool. Three words: **considered, accurate, quiet**.

The reference cluster is Linear, Raycast, Stripe Dashboard, Plausible — interfaces that respect the user's existing expertise, do not explain themselves, and earn trust through restraint and accuracy rather than personality. The voice in the UI is short, factual, second-person only when necessary. No mascots, no encouragement, no exclamation marks, no "Awesome!" empty states.

Emotionally the frontend should feel like a well-organized workshop bench: tools laid out, surfaces clean, nothing decorative. The user should never feel marketed to by their own tool.

## Anti-references

What this must explicitly NOT look or feel like:

- **Heavy admin frameworks** — Django Admin, Filament, Retool, generic CRUD UIs. Tell-tale signs: dense uniform tables, generic action menus, framework-default forms, no opinion about what matters on a screen. KnowledgeBase has strong opinions about wiki types and handoff lifecycle; the UI must reflect that, not flatten it into rows.
- **Generic SaaS dashboard clichés** — big hero metric cards (Total / Active / +12% MoM), three identical KPI tiles in a row, gradient accents, "Welcome back, user!" greetings, illustration-heavy empty states, Vercel/Tailwind-template hero blocks. Specifically banned shapes: the four-up KPI strip, the giant-number-with-trend-arrow card, decorative sparklines.
- **Notion / WYSIWYG editor energy** — slash commands, drag handles, block menus. This is a *review* surface, not an editing surface.
- **Consumer-warm notebook aesthetics** — soft pastels, rounded-everything, friendly illustrations, cozy serif headings paired with playful sans body. Wrong register for an operations tool.

## Design Principles

1. **Review, don't read.** Wiki reading lives in Antigravity and Obsidian. Every screen here is for *deciding* (approve / reject / inspect a pattern), not for consuming long-form content. If a screen starts looking like a reader, it has drifted out of scope.

2. **Patterns over piles.** A list of rejected pages is the floor, not the ceiling. The dashboard's real job is to make the *shape* of decisions legible — rejection rate by type, by source, by time — so the user can fix upstream prompts and ingestion, not just clear a queue.

3. **Precision over polish.** A correctly chosen number, a sharp diff, a real TTL countdown are worth more than animated charts and gradient cards. Borrow the Linear/Stripe rule: if you can't justify a visual element to the operator-user, remove it.

4. **One user, no shims.** This is a single-operator tool. No role badges, no "your team" copy, no shared-cursor presence, no permission UI. Designing for a hypothetical future team would inject SaaS clichés the user explicitly rejected.

5. **Lint-grade honesty.** The wiki is enforced by lint; the UI must match that ethos. No fake totals, no rounded-down counts that hide errors, no skeleton placeholders that imply data exists when it doesn't, no "Everything looks great!" empty states when the cron actually failed at 03:17.

## Implementation Stack

- **Frontend:** Vite + React + TypeScript. Single-page application loaded locally; no SSR, no SEO.
- **Backend:** small FastAPI service inside the existing `src/kb_mcp/` Python tree. Read-mostly endpoints over the markdown content of `data/wiki/`, `data/handoffs/`, `data/log.md`, and over `kb-wiki-review` actions for approve / reject / TTL queries.
- **Data:** the markdown files in `data/` remain the source of truth. The API reads them with frontmatter parsing on demand; no separate database. Approve / reject mutations go through the existing `kb-wiki-review` machinery, not a parallel write path.
- **Runtime posture:** local-only, single user, single machine. Same privacy stance as the rest of the repo: never deployed, never exposed beyond localhost.
- **Why this stack over HTMX:** the review console's keyboard-first interactions (command palette, multi-select queue actions, optimistic approve / reject with TTL hint motion) and tabular data with live filters are native in React and possible-but-grafted in HTMX. The two-runtime cost (uv + npm) is accepted in exchange for that fit.

This is the only place this decision is recorded. No separate ADR.

## Accessibility & Inclusion

- WCAG 2.1 AA as the floor: 4.5:1 contrast on body text, 3:1 on UI components and large text, visible focus rings on every interactive element, semantic landmarks, labelled form controls, error messages tied to inputs with `aria-describedby`.
- `prefers-reduced-motion: reduce` honored throughout. Default motion is already minimal (no parallax, no hero animations); the reduced variant removes the few remaining transitions and uses opacity/instant state changes only.
- Keyboard navigable across all primary flows (review queue, handoff list, dashboard filters). Standard tab order, no keyboard traps.
- No reliance on color alone to convey status — accepted / rejected / pending / expiring also carry a glyph, label, or position.
- Body text never below 14px effective; line length capped at 65–75ch.
