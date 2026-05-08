# Handoff System v0

Updated: 2026-05-08

## 1. Synopsis

- **Purpose**: Track work delegation and decision-making across agent roles via versioned handoff documents.
- **I/O**: Agent role + task context → handoff markdown file in `data/raw/handoffs/` with required frontmatter.

## 2. Core Logic

### Roles

Handoff documents specify which agent role handles each stage of work:

- **main_gateway** — User request interpretation, delegation decision, final response
- **research** — Source survey, evidence gathering, conflicting claims
- **structuring** — Schema design, content merging, editorial decisions
- **execution** — Implementation, file changes, test results
- **verification** — Criteria definition, findings, pass/fail decision

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
role: main_gateway | research | structuring | execution | verification
handoff_seq: 1
status: draft | ready | consumed | superseded
security:
  contains_secrets: false
  redaction_status: unchecked
promotion: null | skill_candidate | memory | wiki_entity | wiki_concept
---
```

## 3. Usage

### Happy Path Example

**Step 1: main_gateway drafts**

Create `data/raw/handoffs/claude-md-split_docs_main_gateway_01.md`:

```yaml
---
handoff_id: claude-md-split:docs:main_gateway:01
task_slug: claude-md-split
subject: docs
role: main_gateway
handoff_seq: 1
status: ready
security:
  contains_secrets: false
  redaction_status: unchecked
promotion: null
---

User requested restructuring docs/handoff-system.md to follow Standard Document Structure.
Delegating to research role for content audit.
```

**Step 2: research consumes and hands off**

Update same file, set `status: ready`, increment `handoff_seq: 2`, change `role: research`:

```yaml
handoff_id: claude-md-split:docs:research:02
handoff_seq: 2
role: research
status: ready
```

Append findings to body. Hand off to structuring.

**Step 3: structuring merges and designs**

Create new file with `role: structuring`, `handoff_seq: 3`, `status: ready`. Design the new structure, hand off to execution.

**Step 4: execution implements**

Create new file with `role: execution`, `handoff_seq: 4`. Implement changes, set `status: ready`, hand off to verification.

**Step 5: verification validates**

Create new file with `role: verification`, `handoff_seq: 5`. Confirm criteria met, set `status: consumed`. Mark eligible handoffs with `promotion: memory` or `promotion: skill_candidate`.

---

## Appendix

### A. Troubleshooting

**handoff_id collisions**

Use format `task_slug:subject:role:NN` consistently. Increment `NN` per role per task. Example: `claude-md-split:docs:main_gateway:01`, `claude-md-split:docs:research:02`.

**Forgetting to bump status**

Always set `status: ready` before handing off to the next role. Draft handoffs block downstream work.

**Setting promotion without follow-up**

Promotion flags (`skill_candidate`, `memory`, `wiki_entity`, `wiki_concept`) must trigger a follow-up action. Don't mark without a plan to act on it.

**Including secrets**

If a handoff contains secrets (API keys, passwords, tokens), set `security.contains_secrets: true` and redact sensitive values. Set `redaction_status: redacted`. Never commit unredacted handoffs.

### B. PatchNote

- 2026-05-08: Initial split from CLAUDE.md and restructured to follow docs/CLAUDE.md Standard Document Structure. Preserved all 5 roles, 4 statuses, 4 promotions, and frontmatter YAML verbatim.

## Reference

For the complete handoff system specification, see `/home/spow12/hermes_optimize/handoff.md`.
