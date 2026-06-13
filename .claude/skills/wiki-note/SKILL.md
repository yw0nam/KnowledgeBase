---
name: wiki-note
description: Use when you (a human) want to capture a first-party note, insight, or decision directly into the KnowledgeBase wiki — original thinking that does NOT come from a data/raw source. Works from any repo. Not for LLM/cron authoring and not for evidence-derived pages.
---

# wiki-note

## DB-Canonical Override

Wiki notes are DB pages. Submit first-party notes through the kb-mcp `upsert_page`
tool. Markdown under `data/wiki/` is generated export. If any older instruction below
says to write files or lint as a write gate, prefer the kb-mcp tools.

**Prerequisite:** the `kb-mcp` MCP server must be registered in your client (e.g. your
opencode / Claude Code MCP config) so its tools are available.

## Overview

Capture **first-party** knowledge — something you concluded while working, with no
external `data/raw` evidence behind it — into the DB-backed KnowledgeBase wiki.

Normal wiki pages must cite `sources:`. That rule exists to **ground LLM-generated
content in evidence**. A note you author yourself has different, valid provenance:
*you wrote it*. This skill is the sanctioned exception — pages are marked
`origin: authored` with `sources: []` and may be born `approved`.

**Core split — never blur it:**

- **You, a human, thinking** → `origin: authored`, no source. **This skill.**
- **An LLM / cron summarizing captured evidence** → MUST cite real `data/raw` sources.
  Use `wiki-authoring`. Automation must NEVER set `origin: authored`.

## When to Use

- "I should write this down" mid-work — a decision you made, a principle you learned,
  a reusable concept, a named thing worth a lookup later.
- You are working in **another repo** and want it in your KB without `cd` ceremony.

**Do NOT use when:**

- The knowledge comes from a captured source (issue, chat, doc, web clip) → use
  `wiki-authoring` and cite it. Faking `origin: authored` to skip a real citation
  defeats the grounding the wiki depends on.
- An LLM/automation is authoring → `wiki-authoring` with real sources.

Supported types here: **`concept`, `decision`, `entity`, `checklist`, `improvement`** —
one bundled template per type in `reference/templates/`, each pre-set with the
first-party frontmatter (`origin: authored`, `review_status: approved`, `sources: []`).

## Step 1 — Resolve the KB root (works from any repo)

The global skill is a symlink into the KB repo, so it self-locates the root. No `cd`,
env, or config needed.

```bash
KB_ROOT="${KB_ROOT:-}"
if [ -z "$KB_ROOT" ] && [ -L "$HOME/.claude/skills/wiki-note" ]; then
  KB_ROOT="$(cd "$(dirname "$(readlink -f "$HOME/.claude/skills/wiki-note")")/../.." && pwd)"
fi
[ -n "$KB_ROOT" ] || KB_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
[ -d "$KB_ROOT/data/wiki" ] || { echo "KB root not found — set KB_ROOT or run knowledgebase-initialize (install-global-skills.sh)"; exit 1; }
cd "$KB_ROOT"
```

Precedence: `$KB_ROOT` override → global symlink self-location → current git repo.
All `uv run kb-*` below now run inside the KB project.

## Step 2 — Choose type + path

| type | path | template |
|---|---|---|
| `concept` | `data/wiki/concepts/<stem>.md` | `reference/templates/concept.md` |
| `decision` | `data/wiki/decisions/YYYY-MM-DD-<slug>.md` | `reference/templates/decision.md` |
| `entity` | `data/wiki/entities/<subject>/YYYY-MM/<stem>.md` | `reference/templates/entity.md` |
| `checklist` | `data/wiki/checklists/<stem>.md` | `reference/templates/checklist.md` |
| `improvement` | `data/wiki/improvements/YYYY-MM/<stem>.md` | `reference/templates/improvement.md` |

Use a stable ASCII kebab-case slug. To keep KB-specific notes grouped, a subfolder is
fine (e.g. `data/wiki/concepts/knowledgebase/<stem>.md`) — DB-backed lint finds nested
pages and does not require concepts to be flat.

## Step 3 — Write the page through the kb-mcp upsert_page tool

Use the matching `reference/templates/<type>.md` as the schema reference and submit
the final page through the kb-mcp `upsert_page` tool with structured args.
Every template already carries the first-party frontmatter — set the dates and `tags`,
keep the rest:

```yaml
---
type: concept            # matches the template you copied
origin: authored         # first-party authorship — keep this; it's why sources can be empty
review_status: approved  # born approved (you author and approve); not_processed also valid
created: "YYYY-MM-DD"     # today
updated: "YYYY-MM-DD"
sources: []              # empty is allowed BECAUSE origin: authored
aliases: []              # entity/concept templates only
tags: []
---
```

Rules:

- `origin: authored` + `sources: []` go together. If you have a real source, you are
  not authoring first-party — use `wiki-authoring` instead.
- `decision` filename must carry the date: `YYYY-MM-DD-<slug>.md`.
- `improvement` keeps its extra fields (`kind`, `observed_at`, `domain`, `severity`,
  `issue_status`, `related`) — fill the enums per the template comments. `checklist`
  must keep a filled `## Items` task list.
- **Links go in a `## Related` section** as `- [[stem]] — one line on why it's related`
  (see the template), not scattered inline. Wikilinks must target an existing page
  stem; otherwise use plain text.
- Write real content in the body — a one-line stub trips the stub warning, and an empty
  `## Related` (no bullets) trips an empty-section warning, so fill it or drop it.

## Step 4 — Submit + verify export

Call the kb-mcp `upsert_page` tool with structured args — pass the frontmatter as an
object/dict (not YAML text) and the body **without** the `---` fence:

- `slug` — the stable kebab-case stem from Step 2
- `type` — `concept` | `decision` | `entity` | `checklist` | `improvement`
- `export_path` — the path from the Step 2 table (e.g. `data/wiki/concepts/<stem>.md`)
- `frontmatter` — the object from Step 3 (`origin: "authored"`, `sources: []`, dates,
  `tags`, and any type-specific fields)
- `body_md` — the page body with no frontmatter fence
- `origin` — `"authored"` (first-party authorship; keep it — it's why `sources` can be empty)
- `review_status` — `"approved"` if born approved, else `"not_processed"`

If you author the page born approved, you may instead pass `review_status="not_processed"`
and then call the kb-mcp `approve_page` tool with the same `slug` — keep whichever
lifecycle you chose in Step 3.

On success the tool returns the page plus `"export": {"status": "success", "written": N}`,
confirming Markdown was exported immediately. On failure it returns
`{"error": ..., "code": ...}` (e.g. `lint_failed`, `conflict`) — fix and resubmit.

## Step 5 — Log (optional)

Write through the kb-mcp `create_operation_log` tool:

```markdown

## YYYY-MM-DD (wiki note — first-party)

- **authored**: wiki/<type>/<stem>.md  (origin: authored, sources: [])
- **db_write**: page export succeeded
```

## Commit & approval

- Do not commit `data/`; it is generated export.
- `wiki-promote` (cron) will not touch an already-`approved` page, so first-party notes
  bypass the promotion ladder by design.

## Common Mistakes

| Mistake | Fix |
|---|---|
| `origin: authored` on an LLM/cron page | Automation must cite real sources — use `wiki-authoring` |
| `sources: []` but you actually have a source | Cite it via `wiki-authoring`; don't mark authored |
| `improvement` enum left blank/invalid | Fill `kind`/`domain`/`severity`/`issue_status` per template comments |
| links scattered inline instead of `## Related` | Collect them as `- [[stem]] — why` in `## Related` |
| dead `[[wikilink]]` | Link an existing stem or use plain text |
| `decision` filename without date | Rename to `YYYY-MM-DD-<slug>.md` |
