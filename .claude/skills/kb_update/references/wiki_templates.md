# Wiki Page Templates

Follow these templates exactly when writing wiki pages.
Maintain field order, indentation, and quoting rules as shown.

---

## Entity Page

File location: `wiki/entities/{subject}/{YYYY-MM}/PascalCase.md`

```markdown
---
type: entity
created: "YYYY-MM-DD"
updated: "YYYY-MM-DD"
sources:
  - raw/github/issues/repo_42.md
aliases: []
tags: []
---

# Page Title

## Overview

[1-2 paragraph summary synthesized from raw sources.]

## Key Details

[Technical details, implementation notes, architecture etc.]

## Relationships

- [[RelatedPage|Related Page Title]] (relation type)
```

---

## Concept Page

File location: `wiki/concepts/Snake_Case.md`

```markdown
---
type: concept
created: "YYYY-MM-DD"
updated: "YYYY-MM-DD"
sources:
  - raw/github/issues/repo_42.md
aliases: []
tags: []
---

# Concept Title

## Overview

[What this concept is and why multiple entities are grouped under it.]

## Components

- [[EntityPage|Entity Title]]

## How They Connect

[Relationships between components, patterns, notable points.]
```

---

## Subject Hub (_index.md)

File location: `wiki/entities/{subject}/_index.md`

```markdown
---
type: entity
created: "YYYY-MM-DD"
updated: "YYYY-MM-DD"
sources: []
aliases: []
tags: [project]
---

# Subject Name

## Pages

### YYYY-MM

- [[PascalCasePage|Page Title]]
```

---

## Daily Report

File location: `wiki/summaries/daily/YYYY/MM/YYYY_MM_DD_daily_report.md`

```markdown
---
type: summary
period: daily
date: "YYYY-MM-DD"
tags: []
---

# Daily Report — YYYY-MM-DD

## Update Summary

- **New raw files processed**: N
- **Pages created**: X
- **Pages updated**: Y
- **Lint result**: PASSED

## Graph Changes

- **Nodes added/updated**: N
- **Edges added/updated**: M

## New Pages

| Page | Subject | Source |
|------|---------|--------|
| [[PageTitle\|Page Title]] | subject_name | `raw/path/to/file.md` |

## Updated Pages

| Page | Changes |
|------|---------|
| [[ExistingPage\|Page Title]] | Added new source, refreshed Key Details |

## Notes

- (any anomalies, warnings, or errors encountered during the run)
```

---

## Frontmatter 규칙

- 날짜는 반드시 따옴표: `"2026-04-16"`
- 스칼라 값은 따옴표 금지: `type: entity` (O), `type: "entity"` (X)
- 리스트는 block style만: `sources:\n  - path` (O), `sources: [path]` (X)
- `sources:`는 반드시 실제 존재하는 raw 파일 경로만 기입
- wikilink: `[[FileName]]` 또는 `[[FileName|Display Text]]` — `.md` 확장자 금지
- 존재하지 않는 페이지로의 wikilink 금지 → plain text 사용
