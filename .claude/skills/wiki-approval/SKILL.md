---
name: wiki-approval
description: Use when promoting DB-backed wiki pages from not_processed to pending_for_approve — approving or rejecting pages, running TTL sweep, updating approved pages, and writing wiki-promote handoffs/logs through the DB API.
---

# Wiki Approval

## DB-Canonical Override

Approval state lives in DB pages. Use the HTTP DB API with
`Authorization: Bearer $KB_API_TOKEN` for promote/approve/reject/TTL sweep,
handoffs, and operation logs. Markdown under `data/` is generated export. If
any older instruction below says to lint as a write gate or commit `data/`,
prefer the DB API.

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

Use the DB write API with `Authorization: Bearer $KB_API_TOKEN`:

```bash
KB_API_URL="${KB_API_URL:-http://127.0.0.1:8765}"
curl -fsS "$KB_API_URL/api/queue"
curl -fsS -X POST "$KB_API_URL/api/pages/<slug>/promote" -H "Authorization: Bearer $KB_API_TOKEN" -H "Content-Type: application/json" --data '{"feedback":"","source":"agent"}'
curl -fsS -X POST "$KB_API_URL/api/pages/<slug>/approve" -H "Authorization: Bearer $KB_API_TOKEN" -H "Content-Type: application/json" --data '{"feedback":"","source":"user"}'
curl -fsS -X POST "$KB_API_URL/api/pages/<slug>/reject" -H "Authorization: Bearer $KB_API_TOKEN" -H "Content-Type: application/json" --data '{"feedback":"","source":"user"}'
curl -fsS -X POST "$KB_API_URL/api/pages/ttl-sweep?days=7" -H "Authorization: Bearer $KB_API_TOKEN"
```

`<stem>` is the filename without `.md`.

## Reserved Body Section

`## User Feedback` is CLI-owned. Never use that exact heading as normal wiki content. Use `## Feedback`, `## Reviewer Notes`, or another heading for authored content.

## Promotion Workflow

Use this for the daily `wiki-promote` cron or a manual promotion run.

1. Check the recent DB-backed queue/output first:
   ```bash
   curl -fsS -X POST "$KB_API_URL/api/pages" -H "Authorization: Bearer $KB_API_TOKEN" -H "Content-Type: application/json" --data '{"type":"wiki","status":"not_processed"}'
   # Or use: uv run kb-lint wiki
   ```
2. Prioritize recent `not_processed` pages.
3. Promote only when all are true:
   - source paths are clear, real, and verifiable
   - future lookup value exists
   - page is durable knowledge, not a raw event dump
4. Promote worthy pages:
   ```bash
   curl -fsS -X POST "$KB_API_URL/api/pages/<slug>/promote" -H "Authorization: Bearer $KB_API_TOKEN" -H "Content-Type: application/json" --data '{"feedback":"","source":"agent"}'
   ```
5. Leave borderline pages untouched. Do not reject manually from an agent promotion run.
6. Confirm each API response reports `export.status: success`.
7. Write a promotion handoff via `POST /api/handoffs`.
8. Append the operation note via `POST /api/operation-logs`.
9. Do not commit `data/`; it is generated export.

## Human Approval / Rejection

For user-requested page review:

1. List pending pages:
   ```bash
   curl -fsS "$KB_API_URL/api/queue"
   ```
2. Read the page and its `sources:` files.
3. Approve when the page is correct and useful:
   ```bash
   curl -fsS -X POST "$KB_API_URL/api/pages/<slug>/approve" -H "Authorization: Bearer $KB_API_TOKEN" -H "Content-Type: application/json" --data '{"feedback":"...","source":"user"}'
   ```
4. Reject only when the user has decided it should not enter the wiki:
   ```bash
   curl -fsS -X POST "$KB_API_URL/api/pages/<slug>/reject" -H "Authorization: Bearer $KB_API_TOKEN" -H "Content-Type: application/json" --data '{"feedback":"...","source":"user"}'
   ```
5. Confirm the API response reports `export.status: success`.

Rejected pages are marked in DB with `review_status: rejected`, `rejected_at`,
and `rejected_by`; export writes them under `data/rejected/...`.

## TTL Sweep

Cron-safe deterministic cleanup:

```bash
curl -fsS -X POST "$KB_API_URL/api/pages/ttl-sweep?days=7" -H "Authorization: Bearer $KB_API_TOKEN"
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

Use a filename that passes DB API handoff validation (POST /api/handoffs validates on submission), for example:

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
- **db_write**: promoted pages + handoff + operation log exported successfully
```

## Red Flags

- About to reject during promotion run: stop. Agents promote or leave; users reject.
- About to use `## User Feedback` as authored content: rename the heading.
- About to commit from the outer repo: stop. Do not commit data/; DB is canonical.
- About to approve without reading sources: read the cited files first.
