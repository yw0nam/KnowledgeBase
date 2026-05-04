---
name: kb_search
description: KnowledgeBase graph-based question answering skill. Traverses graphify-out/graph.json to generate answers, and optionally saves them to wiki/questions/. Triggered when the user types `/kb_search <question>` or asks about stored knowledge like "what is X", "how is X connected", "tell me about X" etc.
---

# kb_search

KnowledgeBase graph-based question answering.
Traverses `graphify-out/graph.json` to generate answers.

## Usage

```
/kb_search <question>
```

## Steps

### Step 1 — Verify graph exists

```bash
test -f graphify-out/graph.json && echo "OK" || echo "NOT_FOUND"
```

If `NOT_FOUND`: output "Run `/kb_init` first to build the graph." and exit.

### Step 2 — Graph traversal

Run `src/kb_mcp/cli/graph_query.py` directly (no need to invoke graphify skill):

```bash
# BFS — for broad context questions like "what is X connected to"
python3 src/kb_mcp/cli/graph_query.py "<question>" --graph graphify-out/graph.json

# DFS — for tracing specific paths
python3 src/kb_mcp/cli/graph_query.py "<question>" --dfs --graph graphify-out/graph.json
```

BFS/DFS selection criteria:
- BFS: "what is X", "PRs related to X", "things connected to X" — broad exploration
- DFS: "how does X connect to Y", "implementation path of X" — deep tracing

### Step 3 — Synthesize answer

Write an answer based on traversal results:

- Use only information present in the graph. If not found, state "No matching information in the graph."
- Reference related wiki pages using `[[WikiPageName]]` format.
- Cite raw file paths for sourced facts (`source_file`).
- Suggest one natural follow-up question at the end.

### Step 4 — Save answer (after user confirmation)

After outputting the answer, ask the user:

```
Save this answer to wiki/questions/?
```

If user responds `yes` / `save`, write to `wiki/questions/<PascalCaseSlug>.md`. If they decline or don't respond, exit without saving.

Slug rules: PascalCase English, max 5 words capturing the question's essence. For non-English questions, LLM extracts meaning and converts to English PascalCase. Example: "How is the TTS pipeline implemented?" → `TTSPipelineImplementation.md`.

Frontmatter (block-style YAML, dates quoted, scalars unquoted):

```yaml
---
type: question
created: "YYYY-MM-DD"
updated: "YYYY-MM-DD"
sources:
  - raw/...        # raw files encountered during traversal (graph node source_file)
aliases: []
tags:
  - question
---
```

Body structure:

```markdown
# {original question}

## Answer
[answer body]

## Related
- [[WikiPageA]]
- [[WikiPageB]]

## Sources
- raw/github/issues/...
```

Do not run lint after saving (next kb_update handles it). After saving, output one line: `Saved: wiki/questions/<Slug>.md`

Saved pages automatically become entry point candidates for `find_start_nodes` wiki expansion in future kb_search calls.

### Answer format

```
**Answer**
[content]

**Related pages**
- [[PageName]]

**Sources**
- raw/github/issues/repo_42.md

**Further exploration**
> [follow-up question suggestion]
```
