# Wiki Categories & Conventions

Updated: 2026-05-08

## 1. Synopsis

- **Purpose**: Classify wiki pages, name them consistently, and link them safely.
- **I/O**: Subject + content type → category folder + filename + valid wikilinks + tags.

## 2. Core Logic

### Categories

#### Entities
Named objects grouped by subject and month. Path: `entities/{subject}/{YYYY-MM}/PascalCase.md`.

#### Concepts
Abstract ideas, patterns, protocols. Flat directory. Path: `concepts/Snake_Case.md`.

#### Decisions
Architecture Decision Records. Closed/finalized. Path: `decisions/ADR_{number}.md`.

#### Questions
Saved Q&A. Path: `questions/{YYYY-MM}/Question_Title.md`.

#### Improvements
Open-ended improvement ideas. Status: draft, in_progress, proposed, deferred. Path: `improvements/{YYYY-MM}/Improvement_Title.md`.

#### Checklists
Operational checklists. Path: `checklists/Checklist_Name.md`.

#### Summaries
Time/subject rollups. Path: `summaries/{daily|weekly|monthly|migration}/{YYYY-MM-DD|YYYY-Www|YYYY-MM}.md`.

### Naming

**Raw files:**
- GitHub: `{repo}_{issue_number}.md`
- Conversations: `chat_{ISO_timestamp}.md`
- Calendar: `event_{date}_{slug}.md`
- Handoffs: `{subject}_{role}_handoff_{seq}.md` or `{role}_handoff_{seq}.md`

**Wiki entities:** `{subject}/{YYYY-MM}/PascalCase.md` (e.g., `DesktopMatePlus/2026-04/PR36_HumanInTheLoopApprovalGate.md`)

**Wiki concepts:** `Snake_Case.md` (flat, e.g., `Agent_Middleware_Implementation_Stack.md`)

**Wiki summaries:** ISO date/week (e.g., `2026-W16.md`, `2026-04.md`)

### Wikilinks

- Use `[[FileName]]` or `[[FileName|Display Text]]`. Never include `.md` extension.
- Only link to pages that exist. If a concept has no wiki page, use plain text.
- Raw sources are cited in frontmatter `sources:` array, never as inline links.

### Tags

Flat namespace. Common: project, tool, pattern, decision, person, event, migration.

## 3. Usage

**Creating a new entity page:**
Pick a subject (e.g., DesktopMatePlus), add the current month folder (2026-05), and use PascalCase for the filename. Example: `entities/DesktopMatePlus/2026-05/NewFeature.md`.

**Creating a new concept:**
Use Snake_Case in the flat `concepts/` directory. Example: `concepts/Agent_Middleware_Implementation_Stack.md`. No subject folders.

**Adding a wikilink:**
Reference an existing page with `[[FileName]]` (no `.md`). If linking to a concept, use `[[Agent_Middleware_Implementation_Stack]]`. If the page doesn't exist, write plain text instead.

**Choosing tags:**
Pick from the flat namespace. Common choices: project (for project-specific pages), tool (for tooling), pattern (for design patterns), decision (for ADRs), person (for people), event (for events), migration (for migration-related content).

---

## Appendix

### A. Troubleshooting

**Putting a concept inside a subject folder**
Concepts are flat. Move the file from `concepts/SomeSubject/Concept.md` to `concepts/Concept.md`.

**Forgetting the `{YYYY-MM}` segment in entity paths**
Entity paths must include the month. Use `entities/Subject/2026-05/Page.md`, not `entities/Subject/Page.md`.

**Including `.md` extension inside wikilinks**
Wikilinks never include the extension. Use `[[FileName]]`, not `[[FileName.md]]`.

**Linking to a page that doesn't exist**
Check that the target page exists before creating the link. If it doesn't, use plain text instead of a wikilink.

**Using non-flat tags**
Tags are flat. Use `project`, not `projects/myproject`. Use `tool`, not `tools/python`.

### B. PatchNote

- 2026-05-08: Initial restructure from CLAUDE.md. Reorganized to follow Standard Document Structure (Synopsis, Core Logic, Usage, Appendix). All 7 categories, naming rules, wikilink rules, and tag conventions preserved verbatim.
