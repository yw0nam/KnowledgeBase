---
name: wiki-approval
description: Self-contained KnowledgeBase wiki approval workflow. Use when promoting AI-authored wiki pages from not_processed to pending_for_approve, approving or rejecting pages, running TTL sweep, updating approved pages, writing wiki-promote handoffs/logs, or configuring the wiki approval cron. Also covers the legacy workflow name wiki_approval.
---

# Wiki Approval

Use this skill as the runtime contract for the KnowledgeBase review lifecycle. Do not look for a workflow doc during execution; this skill is the complete operating surface.

## Status Model

Applies only to wiki page types `entity`, `concept`, `decision`, `improvement`, `checklist`, and `question`.

| Status | Meaning | Next |
|---|---|---|
| `not_processed` | AI wrote or semantically changed the page | promote or TTL reject |
| `pending_for_approve` | Waiting for human review | approve or reject |
| `approved` | Official wiki content | semantic edit self-resets to `not_processed` |
| `rejected` | Preserved outside wiki under `data/rejected/` | terminal |

`summary` and `index` pages are outside the approval lifecycle.

## Commands

Run from the outer repo root:

```bash
uv run kb-wiki-review list [--status not_processed|pending_for_approve|approved|all] [--counts]
uv run kb-wiki-review promote <stem>
uv run kb-wiki-review approve <stem> [--feedback "..."]
uv run kb-wiki-review reject <stem> [--feedback "..."]
uv run kb-wiki-review ttl-sweep --days 7
uv run kb-wiki-index
uv run kb-lint-wiki --check-immutability
uv run kb-lint-handoff
```

`<stem>` is the filename without `.md`.

## Reserved Body Section

`## User Feedback` is CLI-owned. Never use that exact heading as normal wiki content. Use `## Feedback`, `## Reviewer Notes`, or another heading for authored content.

## Promotion Workflow

Use this for the daily `wiki-promote` cron or a manual promotion run.

1. Check the recent daily build output first:
   ```bash
   git -C data status --short
   uv run kb-wiki-review list --status not_processed
   ```
2. Prioritize newly uncommitted wiki pages, then older `not_processed` pages.
3. Promote only when all are true:
   - source paths are clear, real, and verifiable
   - future lookup value exists
   - page is durable knowledge, not a raw event dump
4. Promote worthy pages:
   ```bash
   uv run kb-wiki-review promote <stem>
   ```
5. Leave borderline pages untouched. Do not reject manually from an agent promotion run.
6. Run validation:
   ```bash
   uv run kb-wiki-index
   uv run kb-lint-wiki --check-immutability
   uv run kb-lint-handoff
   ```
7. Write a promotion handoff and append `data/log.md`.
8. If at least one page was promoted, commit only the nested `data/` repo:
   ```bash
   cd data
   git add wiki rejected handoffs log.md
   git commit -m "promote: YYYY-MM-DD wiki promotion"
   ```
   Do not push.

## Human Approval / Rejection

For user-requested page review:

1. List pending pages:
   ```bash
   uv run kb-wiki-review list --status pending_for_approve
   ```
2. Read the page and its `sources:` files.
3. Approve when the page is correct and useful:
   ```bash
   uv run kb-wiki-review approve <stem> --feedback "..."
   ```
4. Reject only when the user has decided it should not enter the wiki:
   ```bash
   uv run kb-wiki-review reject <stem> --feedback "..."
   ```
5. Regenerate index and lint.

Rejected pages move to `data/rejected/<original wiki path>` with `review_status: rejected`, `rejected_at`, and `rejected_by`.

## TTL Sweep

Cron-safe deterministic cleanup:

```bash
uv run kb-wiki-review ttl-sweep --days 7
```

It rejects `not_processed` pages older than the threshold with `rejected_by: auto_ttl`. The wrapper may run this directly without an agent because no judgment is needed.

## Editing Approved Pages

When an agent edits an `approved` page:

- typo, formatting, link-only cleanup: keep `review_status: approved`
- factual change, new information, changed conclusion, changed scope: set `review_status: not_processed`

There is no deterministic drift detector. The editing agent must make this call.

## Subject Hub Rule

`INDEX.md` is generated. Subject `_index.md` hub files are not auto-synchronized. After approval, a user or companion agent may add a manual `- [[<stem>]]` line where useful. Missing hub entries are warnings, not blockers.

## Handoff Quick Contract

Promotion runs write under:

```text
data/handoffs/YYYY/MM/wiki-promote/
```

Use a filename that passes `kb-lint-handoff`, for example:

```text
wiki-promote_opencode_handoff_01.md
```

Required frontmatter:

```yaml
---
handoff_id: "wiki-promote:wiki-promote:opencode:01"
task_slug: "wiki-promote"
subject: "wiki-promote"
role: opencode
handoff_seq: 1
created: "YYYY-MM-DD"
updated: "YYYY-MM-DD"
status: ready
security:
  contains_secrets: false
  redaction_status: unchecked
promotion: null
---
```

Include these body sections:

```markdown
## 1. Assignment
## 2. Context received
## 3. Work performed
## 4. Tool trace
## 5. Findings / decisions
## 6. Outputs
## 7. Verification
## 8. Risks / uncertainties
## 9. Next handoff instructions
## 10. Promotion candidates
```

`## 4. Tool trace` table must have 7 columns:

```markdown
| # | Tool | Purpose | Input summary | Output summary | Status | Side effect |
| --- | --- | --- | --- | --- | --- | --- |
```

## Log Format

Append to `data/log.md`:

```markdown

## YYYY-MM-DD (wiki promotion)

- **promoted**: <stems or none>
- **left**: <borderline stems or none>
- **handoff**: handoffs/YYYY/MM/wiki-promote/<file>.md
- **lint**: kb-wiki-index + kb-lint-wiki + kb-lint-handoff PASSED
- **commit**: <hash or "none">
```

## Red Flags

- About to reject during promotion run: stop. Agents promote or leave; users reject.
- About to use `## User Feedback` as authored content: rename the heading.
- About to commit from the outer repo: stop. Promotion commits only inside `data/`.
- About to approve without reading sources: read the cited files first.
