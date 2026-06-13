---
name: wiki-approval
description: Use when promoting DB-backed wiki pages from not_processed to pending_for_approve — approving or rejecting pages, running TTL sweep, updating approved pages, and writing wiki-promote handoffs/logs through kb-mcp tools.
---

# Wiki Approval

## DB-Canonical Override

Approval state lives in DB pages. Use the kb-mcp tools (`promote_page`,
`approve_page`, `reject_page`, `ttl_sweep_pages`, `create_handoff`,
`create_operation_log`) for promote/approve/reject/TTL sweep, handoffs, and
operation logs. Markdown under `data/` is generated export. If any older
instruction below says to lint as a write gate or commit `data/`, prefer the
kb-mcp tools.

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

**Reads** go directly to Postgres (set `DATABASE_URL`; schema + recipes in
`docs/db_informations/state-db-schema-reference.md`). The read-only kb-mcp
`query_sql` tool is an equivalent alternative:

```bash
psql "${DATABASE_URL/+psycopg/}" -tAc \
  "SELECT slug, type, created_at FROM pages WHERE review_status='not_processed' ORDER BY updated_at DESC;"
```

**Writes** go through the kb-mcp tools:

- call the kb-mcp `promote_page` tool with `slug=<slug>`, `feedback=""`, `source="agent"`
- call the kb-mcp `approve_page` tool with `slug=<slug>`, `feedback=""`, `source="user"`
- call the kb-mcp `reject_page` tool with `slug=<slug>`, `feedback=""`, `source="user"`
- call the kb-mcp `ttl_sweep_pages` tool with `days=7`

State machine: `promote_page` requires the page be in `not_processed`, `approve_page`
requires `pending_for_approve`, and `reject_page` works from `pending_for_approve`
or `not_processed`. A tool result with `code: conflict` means the page was not in
the expected `review_status` for that transition.

`<stem>` is the filename without `.md`.

## Reserved Body Section

`## User Feedback` is CLI-owned. Never use that exact heading as normal wiki content. Use `## Feedback`, `## Reviewer Notes`, or another heading for authored content.

## Promotion Workflow

Use this for the daily `wiki-promote` cron or a manual promotion run.

1. List the not_processed queue (direct Postgres read):
   ```bash
   psql "${DATABASE_URL/+psycopg/}" -tAc \
     "SELECT slug, type, created_at FROM pages WHERE review_status='not_processed' ORDER BY updated_at DESC;"
   ```
2. Prioritize recent `not_processed` pages.
3. Promote only when all are true:
   - source paths are clear, real, and verifiable
   - future lookup value exists
   - page is durable knowledge, not a raw event dump
4. Promote worthy pages: call the kb-mcp `promote_page` tool with `slug=<slug>`,
   `feedback=""`, `source="agent"`. The page must be in `not_processed`; a
   `code: conflict` result means it was not.
5. Leave borderline pages untouched. Do not reject manually from an agent promotion run.
6. Confirm each tool result reports `export.status == success`; on an `error`/`code`
   result handle it (conflict → page not in the expected `review_status`;
   not_found → wrong slug).
7. Write a promotion handoff via the kb-mcp `create_handoff` tool.
8. Append the operation note via the kb-mcp `create_operation_log` tool.
9. Do not commit `data/`; it is generated export.

## Human Approval / Rejection

For user-requested page review:

1. List pending pages (direct Postgres read):
   ```bash
   psql "${DATABASE_URL/+psycopg/}" -tAc \
     "SELECT slug, type FROM pages WHERE review_status='pending_for_approve';"
   ```
2. Read the page and its `sources:` files.
3. Approve when the page is correct and useful: call the kb-mcp `approve_page`
   tool with `slug=<slug>`, `feedback="..."`, `source="user"`. The page must be
   in `pending_for_approve`; a `code: conflict` result means it was not.
4. Reject only when the user has decided it should not enter the wiki: call the
   kb-mcp `reject_page` tool with `slug=<slug>`, `feedback="..."`, `source="user"`.
   This works from `pending_for_approve` or `not_processed`.
5. Confirm the tool result reports `export.status == success`; on an `error`/`code`
   result handle it (conflict → page not in the expected `review_status`;
   not_found → wrong slug).

Rejected pages are marked in DB with `review_status: rejected`, `rejected_at`,
and `rejected_by`; export writes them under `data/rejected/...`.

## TTL Sweep

Cron-safe deterministic cleanup: call the kb-mcp `ttl_sweep_pages` tool with `days=7`.

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

Use a filename that passes handoff validation (the kb-mcp `create_handoff` tool validates on submission), for example:

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

Submit through the kb-mcp `create_operation_log` tool (export may update `data/log.md`, but the DB row is canonical):

```markdown

## YYYY-MM-DD (wiki promotion)

- **promoted**: <stems or none>
- **left**: <borderline stems or none>
- **handoff**: handoffs/YYYY/MM/wiki-promote/<file>.md
- **db_write**: promoted pages + handoff + operation log exported successfully
```

## Red Flags

- About to reject during promotion run: stop. Agents promote or leave; users reject.
- About to use `## User Feedback` as authored content: rename the heading.
- About to commit from the outer repo: stop. Do not commit data/; DB is canonical.
- About to approve without reading sources: read the cited files first.
