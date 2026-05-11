# Document Authoring Guide

Updated: 2026-05-08

All documents focus on **Actionability** and **Modularity**.

## 1. Core Principles

| Principle | Description |
|-----------|-------------|
| **Hard Limit 200** | Core content must not exceed 200 lines. Physical limit for agent context windows and human attention span. |
| **Lazy Loading (Appendix)** | Edge cases and detailed configs go into Appendix for on-demand reference. |

## 2. Standard Document Structure

```markdown
# [Document Title]

Updated: YYYY-MM-DD

## 1. Synopsis
- **Purpose**: One-line summary
- **I/O**: Input → Output

## 2. Core Logic
- [Step 1]: Implementation method
- [Constraints]: Rules that must be followed

## 3. Usage
- Happy Path example (brief)
```

## 3. Writing Rules

**200-Line Rule:** Main body (`## 1` through `## 3`) must never exceed 200 lines. Remove background context, optimize snippets, use directive language ("Do X" not "It's recommended to do X").

**Splitting Strategy:** When approaching 200 lines, split by functional units. Manage splits as a thin index document.

**Appendix:** Move edge cases, full references, and error catalogs here. Keep main body focused on the happy path.

**PatchNote:** Always add a dated patch note to Appendix when updating a document.

## 4. Quality Checklist

- [ ] Main body under 200 lines?
- [ ] Can someone write code immediately after reading?
- [ ] Edge cases moved to Appendix?
- [ ] Writing is directive and unambiguous?
