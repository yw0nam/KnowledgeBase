# Handoff System v0

Updated: 2026-05-10

## 1. Synopsis

- **Purpose**: Track work delegation and decision-making across agent roles via versioned handoff documents.
- **I/O**: Agent role + task context → handoff markdown file in `data/handoffs/` with required frontmatter.

## 2. Core Logic

### Roles

The `role` field identifies which agent authored the handoff. Recommended values:

- **opencode** — Open-source coding agent (Gemini CLI, opencode, etc.)
- **claude_code** — Claude Code / Anthropic API based agent
- **hermes** — Hermes agent
- **user** — Direct human action

`role` is free-string `[a-z][a-z0-9_-]*`; non-recommended values trigger a lint WARN. Add new agent identities to `RECOMMENDED_ROLES` as you adopt them.

### Status

Each handoff moves through a lifecycle:

- **draft** — In progress
- **ready** — Ready for next agent
- **consumed** — Received and acted upon
- **superseded** — Replaced by newer handoff

### Promotion

Handoffs can be marked for escalation to other systems:

- **skill_candidate** — Reusable workflow for future automation
- **memory** — Important decision or pattern to preserve
- **wiki_entity** — Becomes a wiki page
- **wiki_concept** — Becomes a concept page

### Frontmatter

Handoff documents use this frontmatter structure:

```yaml
---
handoff_id: <task-slug>:<subject>:<role>:01
task_slug: <task-slug>
subject: <subject-or-null>
role: opencode | claude_code | hermes | user
handoff_seq: 1
status: draft | ready | consumed | superseded
security:
  contains_secrets: false
  redaction_status: unchecked
promotion: null | skill_candidate | memory | wiki_entity | wiki_concept
---
```

`role` accepts any free-string matching `[a-z][a-z0-9_-]*`. The values listed above are recommended; lint emits a WARN (not ERROR) for non-recommended values.

**Filename caveat for underscore roles**: If `role` contains underscores (e.g. `claude_code`), the filename MUST include the `<subject>_` prefix to disambiguate parsing. A subject-less filename like `claude_code_handoff_01.md` is parsed as `subject=claude, role=code` by the filename regex, which then fails the filename↔frontmatter role-match check. Workaround: always include subject for underscore roles, or use hyphenated custom roles (e.g. `my-role`).

## 3. Usage

### Happy Path Example

A task has 1+ agents contributing 1+ handoffs. Each agent drafts its own
handoff file. At task close, optionally write `<slug>_final.md` to
aggregate all handoffs into one record.

**Single-handoff task**

One agent does the work end-to-end:
`data/handoffs/2026/05/some-task/docs_opencode_handoff_01.md`
with `role: opencode`, `status: ready`. Done.

**Multi-handoff task**

Agent A drafts:
`data/handoffs/2026/05/some-task/docs_claude_code_handoff_01.md`
with `role: claude_code`, `status: ready`.

Agent B picks up, drafts:
`data/handoffs/2026/05/some-task/docs_opencode_handoff_02.md`
with `role: opencode`, `status: ready`. Marks the previous file
`status: consumed`.

Continue until task closes. Optionally write `docs_final.md` summarizing.

---

## Appendix

### A. Troubleshooting

**handoff_id collisions**

Use format `task_slug:subject:role:NN` consistently. Increment `NN` per role per task. Example: `some-task:docs:claude_code:01`, `some-task:docs:opencode:02`.

**Forgetting to bump status**

Always set `status: ready` before handing off to the next role. Draft handoffs block downstream work.

**Setting promotion without follow-up**

Promotion flags (`skill_candidate`, `memory`, `wiki_entity`, `wiki_concept`) must trigger a follow-up action. Don't mark without a plan to act on it.

**Including secrets**

If a handoff contains secrets (API keys, passwords, tokens), set `security.contains_secrets: true` and redact sensitive values. Set `redaction_status: redacted`. Never commit unredacted handoffs.

### B. PatchNote

- 2026-05-10 (phase 2): Reframed `role` from 5-phase pipeline (main_gateway/research/structuring/execution/verification) to agent identity (opencode/claude_code/hermes/user). Collapsed 5 phase-role templates into 1 universal `templates/handoff.md`. Multi-handoff per task and `final.md` aggregation pattern preserved.
- 2026-05-10 (revision): Reverted unrequested lint hacks (untracked-skip,
  filename role override). Documented filename caveat for underscore roles.
- 2026-05-10: Relaxed `role` to free-string with WARN-only recommended enum.
  Moved handoffs from `data/raw/handoffs/` to `data/handoffs/` (handoffs are
  authored operational records, not immutable raw sources). Fixed Step 2
  happy-path example to create a new file per role rather than updating the
  prior one (aligns with filename↔frontmatter role-match enforcement).
- 2026-05-08: Initial split from CLAUDE.md and restructured to follow docs/CLAUDE.md Standard Document Structure. Preserved all 5 roles, 4 statuses, 4 promotions, and frontmatter YAML verbatim.

## Reference

For the complete handoff system specification, see `/home/spow12/hermes_optimize/handoff.md`.
