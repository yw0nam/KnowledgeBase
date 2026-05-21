# Wiki Categories Reference

Updated: 2026-05-20

## 1. Synopsis

- **Purpose**: Human taxonomy reference for `data/wiki/`.
- **Runtime**: Use `.claude/skills/wiki-authoring/SKILL.md`.

## 2. Categories

| Type | Path shape | Meaning |
|---|---|---|
| `entity` | `entities/{subject}/{YYYY-MM}/{stem}.md` | named project, repo, PR, issue, person, tool, event |
| `concept` | `concepts/{stem}.md` | reusable idea, pattern, protocol |
| `decision` | `decisions/YYYY-MM-DD-{slug}.md` | closed choice with rationale |
| `question` | `questions/{stem}.md` | preserved Q&A |
| `improvement` | `improvements/{YYYY-MM}/{stem}.md` | open issue, proposal, improvement |
| `checklist` | `checklists/{stem}.md` | repeatable procedure |
| `summary` | `summaries/YYYY/MM/{period}-{kind}.md` | time-bounded rollup |

## 3. Wikilinks

- Use `[[FileStem]]` or `[[FileStem|Display Text]]`.
- Do not include `.md`.
- The target must match an existing filename stem.
- `aliases:` help humans but do not satisfy lint.
- If a page does not exist, use plain text.

## Appendix

### PatchNote

- 2026-05-20: Reduced to human taxonomy reference; runtime rules moved to `wiki-authoring`.
