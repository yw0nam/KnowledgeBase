# Periodic Memory Workflow

Updated: 2026-05-18

## 1. Synopsis

- **Purpose**: Run daily, weekly, and monthly long-term memory management from `data/` without relying on session memory.
- **I/O**: `data/raw/` + `data/handoffs/` + prior summaries -> validated `data/wiki/` pages + updated handoffs + `data/log.md`.

## 2. Core Logic

### Fresh Session Contract

Every cron agent starts with no trusted session context. Before changing files, read:

- `CLAUDE.md`
- `docs/workflows/pipeline.md`
- `docs/reference/frontmatter.md`
- `docs/reference/wiki-categories.md`
- `docs/workflows/handoff-system.md`
- this document
- relevant files under `data/handoffs/`
- relevant prior summaries under `data/wiki/summaries/`

Do not assume previous chat context, user memory, or unresolved work unless it is recorded in `data/handoffs/`, `data/log.md`, or `data/wiki/`.

### Memory Layers

Use each layer for one job only:

| Layer | Purpose | Update Rule |
|---|---|---|
| `data/raw/` | Immutable source evidence | Create only; never edit existing raw files |
| `data/handoffs/` | Operational state and next actions | Update every periodic run |
| `data/wiki/` | Durable long-term knowledge | Create/update only when backed by sources |
| `data/wiki/summaries/YYYY/MM/` | Time-bounded summaries | One file per summary kind and period |
| `data/log.md` | Append-only operation record | Append every run |

### Promotion Criteria

Promote information only when it meets the target category standard:

| Target | Promote When | Do Not Promote When |
|---|---|---|
| `entities/` | Named project, repo, PR, issue, person, tool, or event needs future lookup | It is a one-off mention with no reusable context |
| `concepts/` | Same idea appears across sources or explains a reusable pattern | It is just a task note or temporary wording |
| `decisions/` | A decision is closed, has rationale, and should constrain future work | The user still needs to decide |
| `questions/` | A useful Q&A should be preserved for future retrieval | The answer is incomplete or speculative |
| `improvements/` | There is an actionable but not-yet-closed improvement | It is already implemented or too vague |
| `checklists/` | A repeatable operational procedure exists | It is a one-time task plan |
| `summaries/` | Time-bounded synthesis is needed | It duplicates an existing summary without new signal |

Every promoted wiki page must cite source paths in frontmatter `sources:` relative to `data/`.

### Handoff Handling

Handoffs are the cron agent's state board. Use them for:

- processed raw files
- skipped raw files and reasons
- unresolved review items
- promotion candidates
- failed lint or blocked actions
- next run instructions

Recommended paths:

```text
data/handoffs/YYYY/MM/wiki-daily-build/wiki_opencode_handoff_NN.md
data/handoffs/YYYY/MM/wiki-weekly-build/wiki_opencode_handoff_NN.md
data/handoffs/YYYY/MM/wiki-monthly-maintenance/wiki_opencode_handoff_NN.md
```

When a weekly or monthly run consumes earlier handoffs, update the consumed handoff status to `consumed` only if the follow-up action was actually handled. Otherwise leave it `ready` and mention the blocker in the new handoff.

## 3. Usage

### Daily Run

Goal: capture yesterday's new information, create a daily memory snapshot, and leave clear next actions.

Daily memory synthesis is the only combined interpretation layer. It may read multiple source-specific usage reports, but deterministic usage report CLIs must stay source-specific.

Run window: usually early morning for the previous calendar day.

Steps:

1. Read the Fresh Session Contract documents.
2. Identify new or unprocessed `data/raw/` files for the target date.
3. Read current ready handoffs for `wiki-daily-build`.
4. Create or update `data/wiki/summaries/YYYY/MM/YYYY-MM-DD-memory.md`.
5. Create or update only necessary entity, question, improvement, or concept pages.
6. Write a new daily handoff with processed, skipped, promoted, and open items.
7. Append `data/log.md` with target date, sources, wiki pages, handoff path, and lint result.
8. Run `kb-lint-wiki --check-immutability` and `kb-lint-handoff`.
9. If lint passes, commit changes in the nested `data/` repo.

Daily promotion standard:

- Prefer summary and triage over deep restructuring.
- Create atomic pages only when the source has clear future value.
- Leave uncertain items in the handoff instead of inventing structure.

Daily handoff body must include:

```text
Processed:
- raw/...

Updated:
- wiki/...

Skipped:
- raw/... -- reason

Promotion Candidates:
- concept: ... -- evidence

Open Items:
- ...

Next Run:
- ...
```

### Weekly Run

Goal: turn daily captures into patterns, durable concepts, improvements, and checklists.

Run window: weekly, after all seven daily runs exist or after documenting missing days.

Steps:

1. Read the Fresh Session Contract documents.
2. Read the seven target daily summaries.
3. Read ready daily handoffs from the week.
4. Create or update `data/wiki/summaries/YYYY/MM/YYYY-WNN-weekly.md`.
5. Promote repeated patterns into concepts, improvements, checklists, or decisions.
6. Mark consumed daily handoffs as `consumed` only for handled items.
7. Write a weekly handoff with unresolved items and monthly candidates.
8. Append `data/log.md`.
9. Run `kb-lint-wiki --check-immutability` and `kb-lint-handoff`.
10. If lint passes, commit changes in the nested `data/` repo.

Weekly promotion standard:

- Promote only signals repeated across multiple days or strongly supported by one important source.
- Convert recurring operational mistakes into checklist candidates.
- Convert unresolved but actionable work into improvements.
- Convert closed architectural or workflow choices into decisions.
- Use `templates/wiki/summaries/weekly.md` for weekly synthesis structure.

### Monthly Run

Goal: maintain wiki quality, reduce duplication, and close long-running memory loops.

Run window: monthly, after weekly summaries for the month are available.

Steps:

1. Read the Fresh Session Contract documents.
2. Read monthly weekly summaries and monthly maintenance handoffs.
3. Review orphan pages, duplicate concepts, stale improvements, and open decision candidates.
4. Create or update `data/wiki/summaries/YYYY/MM/YYYY-MM-monthly.md`.
5. Consolidate duplicated concepts only when sources support the merge.
6. Close or defer stale improvements with rationale.
7. Promote stable repeated procedures into checklists.
8. Write a monthly handoff with remaining structural issues and skill candidates.
9. Append `data/log.md`.
10. Run `kb-lint-wiki --strict` and `kb-lint-handoff`.
11. If lint passes, commit changes in the nested `data/` repo.

Monthly promotion standard:

- Prefer cleanup and consolidation over adding new pages.
- Do not merge pages if their source evidence differs in meaning.
- Mark reusable automation workflows as `promotion: skill_candidate` in handoff.
- Leave human-decision items open instead of turning them into ADRs.

### Failure Handling

If a run cannot finish:

1. Do not modify existing `data/raw/` files.
2. Keep completed wiki edits only if they are source-backed and lintable.
3. Write or update a handoff with the failure, blocker, and safe next command.
4. Append `data/log.md` with `status: failed` or clear prose equivalent.
5. Do not commit a broken wiki state.

### Commit Message Convention

Use short nested `data/` repo commit messages:

```text
daily: build memory summary for YYYY-MM-DD
weekly: synthesize memory for YYYY-WNN
monthly: maintain memory wiki for YYYY-MM
```

---

## Appendix

### A. Cron Prompt Skeleton

```text
Run the KnowledgeBase <daily|weekly|monthly> memory workflow for <period>.

Read the Fresh Session Contract in docs/workflows/periodic-memory-workflow.md first.
Follow the target run steps exactly.
Never edit existing data/raw files.
Only create wiki pages with source-backed frontmatter.
Use data/handoffs as the operational state board.
Append data/log.md.
Run the required lint commands.
Commit the nested data repo only if lint passes.
```

### B. PatchNote

- 2026-05-18: Initial periodic memory workflow for fresh-session cron agents.
