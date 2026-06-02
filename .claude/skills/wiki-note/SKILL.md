---
name: wiki-note
description: Use when you (a human) want to capture a first-party note, insight, or decision directly into the KnowledgeBase wiki — original thinking that does NOT come from a data/raw source. Works from any repo. Not for LLM/cron authoring and not for evidence-derived pages.
---

# wiki-note

## Overview

Capture **first-party** knowledge — something you concluded while working, with no
external `data/raw` evidence behind it — straight into the KnowledgeBase `data/wiki/`.

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
- The page is an `improvement` or `checklist` (extra required fields / `## Items`) →
  use `wiki-authoring`.
- An LLM/automation is authoring → `wiki-authoring` with real sources.

Supported types here: **`concept`, `decision`, `question`, `entity`** (the simple
source-optional schema). Anything else → `wiki-authoring`.

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

| type | path |
|---|---|
| `concept` | `data/wiki/concepts/<stem>.md` |
| `decision` | `data/wiki/decisions/YYYY-MM-DD-<slug>.md` |
| `question` | `data/wiki/questions/<stem>.md` |
| `entity` | `data/wiki/entities/<subject>/YYYY-MM/<stem>.md` |

Use a stable ASCII kebab-case slug.

## Step 3 — Write the page

Copy `reference/templates/note.md` and set `type` + path. Frontmatter:

```yaml
---
type: concept            # concept | decision | question | entity
origin: authored         # marks first-party authorship — REQUIRED for source-less pages
review_status: approved  # born approved is fine (you author and approve); not_processed also OK
created: "YYYY-MM-DD"     # today
updated: "YYYY-MM-DD"
sources: []              # empty is allowed BECAUSE origin: authored
aliases: []              # entity/concept only; harmless elsewhere
tags: []
---
```

Rules:

- `origin: authored` + `sources: []` go together. If you have a real source, you are
  not authoring first-party — use `wiki-authoring` instead.
- `decision` filename must carry the date: `YYYY-MM-DD-<slug>.md`.
- Wikilinks (`[[stem]]`) must target an existing page stem, or use plain text.
- Write real content in the body — a one-line stub will trip the stub warning.

## Step 4 — Regenerate index + lint (both must be 0 errors)

```bash
uv run kb-wiki-index
uv run kb-lint-wiki --check-immutability
```

`kb-wiki-index` must run before lint (an `approved` page must appear in `INDEX.md`).

## Step 5 — Log (optional)

Append to `data/log.md`:

```markdown

## YYYY-MM-DD (wiki note — first-party)

- **authored**: wiki/<type>/<stem>.md  (origin: authored, sources: [])
- **lint**: kb-wiki-index + kb-lint-wiki PASSED
```

## Commit & approval

- Leave the new `data/` page **uncommitted** — it syncs through the normal `data-sync`
  flow (or your manual commit), like any other data change.
- `wiki-promote` (cron) will not touch an already-`approved` page, so first-party notes
  bypass the promotion ladder by design.

## Common Mistakes

| Mistake | Fix |
|---|---|
| `origin: authored` on an LLM/cron page | Automation must cite real sources — use `wiki-authoring` |
| `sources: []` but you actually have a source | Cite it via `wiki-authoring`; don't mark authored |
| `improvement`/`checklist` here | Use `wiki-authoring` (extra required fields) |
| lint before `kb-wiki-index` | Run `kb-wiki-index` first |
| dead `[[wikilink]]` | Link an existing stem or use plain text |
| `decision` filename without date | Rename to `YYYY-MM-DD-<slug>.md` |
