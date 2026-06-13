---
name: handoff-document
description: Use when writing or updating a DB-backed handoff document — covers export path, filename grammar, canonical body sections, and kb-mcp create_handoff submission.
---

# handoff-document

## DB-Canonical Override

Handoffs are DB rows. Submit handoffs through the kb-mcp `create_handoff` tool.
Markdown under `data/handoffs/` is generated export. If any older instruction below
says to write files or update README as a write gate, prefer the kb-mcp tools.

## Overview

Handoffs are this repo's operational state board. Every task that crosses an
agent boundary, a session, or a workday writes a handoff row through the kb-mcp
`create_handoff` tool. Markdown under `data/handoffs/` is generated export.

**Bundled reference (self-contained — do not consult docs/ at runtime):**
- `reference/templates/task.md` — handoff template (copy this when starting a new handoff)
- `reference/templates/final.md` — task-close `<slug>_final.md` template
- `reference/templates/readme.md` — task `README.md` template

The schema, enum values, and lint rules below are the canonical operational summary. If anything contradicts the lint code (`src/kb/lint/handoff.py`), the lint code wins — file an issue and update this skill.

## Step 0 — Resolve the KB root (run from any repo)

This skill is symlinked into the KB repo, so it self-locates the root — no `cd`, env,
or config needed. Run this first; afterwards every `data/...` path below is relative to
the KB repo and every `uv run kb-*` runs inside the KB project.

```bash
KB_ROOT="${KB_ROOT:-}"
if [ -z "$KB_ROOT" ] && [ -L "$HOME/.claude/skills/handoff-document" ]; then
  KB_ROOT="$(cd "$(dirname "$(readlink -f "$HOME/.claude/skills/handoff-document")")/../.." && pwd)"
fi
[ -n "$KB_ROOT" ] || KB_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
[ -d "$KB_ROOT/data" ] || { echo "KB root not found — set KB_ROOT or run knowledgebase-initialize (install-global-skills.sh)"; exit 1; }
cd "$KB_ROOT"
```

Precedence: `$KB_ROOT` override → global symlink self-location → current git repo.

## When to Use

- Finishing a task (or session) that produced files, decisions, or open questions another agent will pick up
- Updating an existing in-progress handoff (`status: draft` → `ready`)
- Writing the closing `<slug>_final.md` for a multi-handoff task
- Updating a task `README.md`'s Handoff index

**Do NOT use** for: wiki pages (separate skill), raw source files (immutable, never authored by agent), or `data/log.md` appends (free-form prose).

## File Layout

```
data/handoffs/<YYYY>/<MM>/<task-slug>/
├── README.md                              # optional task overview + handoff index
├── [<subject>_]<role>_handoff_<NN>.md     # one per role per task, NN starts 01
└── <task-slug>_final.md                   # optional — written at task close
```

- `<YYYY>/<MM>` = month the task **started** in (not today). All handoffs for one task live in one folder regardless of how long it runs.
- `<task-slug>` = lowercase kebab-case, matches the directory name and the `task_slug:` field.
- `<NN>` = zero-padded 2-digit sequence, monotonic per role per task.

## Filename Grammar — strict regex

```
Handoff:  ^(?:(<subject>)_)?(<role>)_handoff_(<NN>)\.md$
Final:    ^(<task-slug>)_final\.md$
```

- `<subject>` and `<task-slug>`: `[a-z0-9-]+`
- `<role>`: `[a-z][a-z0-9_-]*`
- `<NN>`: exactly two digits

**Underscore-role caveat (the #1 lint failure):**

If `role` contains an underscore (e.g. `claude_code`, `wiki_opencode` is **not** a role), the filename **must** include a subject prefix. Otherwise the filename parser splits `claude_code_handoff_01.md` into `subject=claude, role=code` and the role-match check fails.

| Role | Subject? | Correct filename |
|---|---|---|
| `opencode` | optional | `opencode_handoff_01.md` ✅ or `phase1_opencode_handoff_01.md` ✅ |
| `claude_code` | **required** | `phase1_claude_code_handoff_01.md` ✅ |
| `claude_code` | missing | `claude_code_handoff_01.md` ❌ parses as `subject=claude, role=code` |
| `hermes` | optional | `hermes_handoff_01.md` ✅ |

## Frontmatter — required fields (lint ERROR if missing)

```yaml
---
handoff_id: "<task-slug>:<subject-or-null>:<role>:<NN>"
task_slug: "<task-slug>"
subject: "<subject>"          # or: null  (literal null, unquoted)
role: <role>                  # recommended: opencode | claude_code | hermes | user
handoff_seq: <N>              # integer, matches NN in filename
created: "YYYY-MM-DD"
updated: "YYYY-MM-DD"
status: draft                 # draft | ready | consumed | superseded
security:
  contains_secrets: false     # bool — required
  redaction_status: unchecked # string — required (unchecked | redacted | clean)
promotion: null               # null | skill_candidate | memory | wiki_entity | wiki_concept
---
```

### handoff_id grammar (strict)

```
^[a-z0-9-]+:(?:[a-z0-9-]+|null):[a-z][a-z0-9_-]*:\d{2}$
   task-slug   subject or "null"   role          NN
```

When `subject:` frontmatter is `null`, the `handoff_id` middle segment is the literal string `null` (e.g. `migrate-db:null:opencode:01`).

### Enum constraints

| Field | Values | Violation |
|---|---|---|
| `role` | opencode, claude_code, hermes, user | other values → WARN, not error |
| `status` | draft, ready, consumed, superseded | other → ERROR |
| `promotion` | null, skill_candidate, memory, wiki_entity, wiki_concept | other → ERROR |

### Filename ↔ frontmatter consistency (lint ERROR on mismatch)

- `role:` in frontmatter must equal `<role>` parsed from filename
- `handoff_seq:` integer must equal `<NN>` from filename

## Body — 10 canonical sections

Missing sections → WARN (not ERROR). Keep all 10 even if short.

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

### Tool trace table — 7 columns

Lint counts pipe characters in the header. Must be **8 pipes** (7 columns + 2 outer):

```markdown
| # | Tool | Purpose | Input summary | Output summary | Status | Side effect |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Bash · grep | … | … | … | ok | none |
```

## Security gates (ERROR conditions to know)

| If you set | Then forbidden |
|---|---|
| `security.contains_secrets: true` | `promotion: wiki_entity` or `wiki_concept` |
| `security.redaction_status: unchecked` | `promotion: memory` |
| Any sibling handoff in folder has `contains_secrets: true` | Writing `<slug>_final.md` at all |
| `<slug>_final.md` itself has `contains_secrets: true` | ERROR |

Default for AI-authored handoffs without explicit secrets: `contains_secrets: false`, `redaction_status: unchecked`, `promotion: null`. Promote later by editing the handoff after redaction is verified.

## final.md schema (different from handoff)

`<slug>_final.md` uses `reference/templates/final.md` — **no** `handoff_id`, **no** `role`, **no** `handoff_seq`. It has `type: handoff_final`, `source_handoffs: [list]`, and aggregates decisions. Write final.md only at true task close, not per-session.

## README.md (optional, lint-checked when present)

If the task folder has a `README.md` with a `## Handoff index` section containing a markdown table, every `*.md` filename mentioned in the table must exist on disk (ERROR if missing). On-disk handoffs not listed in the table → WARN.

When you add a new handoff file, append a row to the index table. Bundled template at `reference/templates/readme.md`.

## Workflow

```
1. Confirm task_slug (existing folder?) → pick or create data/handoffs/YYYY/MM/<slug>/
2. Determine role from your agent identity (claude_code|opencode|hermes)
3. Find max <NN> for your role in the folder → use NN+1
4. Pick subject (always required if role contains underscore; otherwise null)
5. Build the structured args for `create_handoff`: `frontmatter` as an object/dict (NOT yaml text), `body_md` as the body WITHOUT the `---` fence, plus `handoff_id`, `task_slug`, `role`, `handoff_seq` (integer), `status` (lifecycle value, e.g. draft/ready), and `export_path`
6. Fill frontmatter with KST dates and matching handoff_id
7. Fill all 10 body sections
8. status: draft while writing; submit ready when done
9. Call the kb-mcp `create_handoff` tool with the structured args
10. Confirm the tool result reports `export.status == success`; on an `error`/`code` result handle it (lint_failed → fix frontmatter/body and retry; conflict → handoff_id already exists)
```

## Validation

Call the kb-mcp `create_handoff` tool with the structured args
(`handoff_id`, `task_slug`, `role`, `handoff_seq` integer, `status`, `frontmatter`
object, `body_md` without the `---` fence, `export_path`; optional `subject`,
`created_at`, `updated_at`). Lint runs inside the tool: a success result returns the
handoff plus `"export": {"status": "success", "written": N}`; a failure returns
`{"error": <msg>, "code": <missing_args|not_found|conflict|lint_failed|export_failed>, "detail": ...}`.

Fix all ERRORs before considering the handoff complete. WARNs are negotiable — missing canonical sections, uncommon role values, on-disk files not in README index.

## Common Mistakes

| Mistake | Symptom | Fix |
|---|---|---|
| `claude_code` role with no subject prefix | "filename role 'code' mismatches frontmatter role 'claude_code'" | Add subject: `phase1_claude_code_handoff_01.md` |
| Subject is `null` but handoff_id has empty middle | "handoff_id format invalid" | Use literal `null` in the id: `task:null:role:01` |
| `created: 2026-05-20` (unquoted) | YAML parses as date object, sometimes OK; quote it to be safe | `created: "2026-05-20"` |
| Forgot `security.redaction_status` | "security.redaction_status missing" | Add `redaction_status: unchecked` |
| Tool trace table has 6 columns | "tool trace table header has 7 pipes, expected 8" | Keep all 7 canonical columns even if cells are `none` |
| Wrote handoff into `YYYY/MM` of today instead of task-start month | Discoverability — splits one task across folders | Use month the task started in |
| `status: in_progress` | "invalid status" | Only 4 values; use `draft` while WIP |
| `role: claude` (assumed shortname) | WARN only | Use `claude_code` (recommended set) |

## Worked Example

Task: pick up `frontend-review-console` from prior agent. Subject `phase-d-3`. Two `claude_code` handoffs already exist (`phase-d-1_claude_code_handoff_02.md`, `phase-d-2_claude_code_handoff_03.md`). Today is 2026-05-20.

File: `data/handoffs/2026/05/frontend-review-console/phase-d-3_claude_code_handoff_04.md`

```yaml
---
handoff_id: "frontend-review-console:phase-d-3:claude_code:04"
task_slug: "frontend-review-console"
subject: "phase-d-3"
role: claude_code
handoff_seq: 4
created: "2026-05-20"
updated: "2026-05-20"
status: draft
security:
  contains_secrets: false
  redaction_status: unchecked
promotion: null
---

# Frontend Review Console — Phase D-3 (...)

## 1. Assignment
…
## 4. Tool trace
| # | Tool | Purpose | Input summary | Output summary | Status | Side effect |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Read | … | … | … | ok | none |
…
## 10. Promotion candidates
…
```

Then flip `status: draft` → `ready` when done. Validation runs inside the kb-mcp `create_handoff` tool (returns `code: lint_failed` on failure). Append README row.

## Red Flags — stop and re-check

- About to put the handoff in `YYYY/MM` of today, but the task folder already exists in a different month → use the existing folder.
- About to use `role: claude_code` without a subject prefix in the filename → won't lint, add subject.
- Writing `final.md` when only your own session's work is done but other sessions/agents are still active → write a numbered handoff instead.
- Setting `promotion: memory` while `redaction_status: unchecked` → either redact + flip, or leave `promotion: null`.
- Tool trace table has fewer than 7 columns → readers expect canonical shape; pad with `none` / `n/a`.
