# Wiki Page Templates

wiki 페이지 작성 시 아래 템플릿을 정확히 따른다.
frontmatter 필드 순서, 들여쓰기, 따옴표 규칙을 그대로 유지한다.

---

## Entity 페이지

파일 위치: `data/wiki/entities/{subject}/{YYYY-MM}/PascalCase.md`

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

[1-2단락 요약. raw 소스에서 종합해 작성.]

## Key Details

[기술적 세부사항, 구현 내용, 아키텍처 등.]

## Relationships

- [[RelatedPage|Related Page Title]] (relation type)
```

---

## Concept 페이지

파일 위치: `data/wiki/concepts/Snake_Case.md`

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

[이 개념이 무엇인지, 왜 여러 entity가 이 개념으로 묶이는지.]

## Components

- [[EntityPage|Entity Title]]

## How They Connect

[구성 요소들 간의 관계, 패턴, 특이점.]
```

---

## Subject Hub (_index.md)

파일 위치: `data/wiki/entities/{subject}/_index.md`

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

## Frontmatter 규칙

- 날짜는 반드시 따옴표: `"2026-04-16"`
- 스칼라 값은 따옴표 금지: `type: entity` (O), `type: "entity"` (X)
- 리스트는 block style만: `sources:\n  - path` (O), `sources: [path]` (X)
- `sources:`는 반드시 실제 존재하는 raw 파일 경로만 기입
- wikilink: `[[FileName]]` 또는 `[[FileName|Display Text]]` — `.md` 확장자 금지
- 존재하지 않는 페이지로의 wikilink 금지 → plain text 사용
