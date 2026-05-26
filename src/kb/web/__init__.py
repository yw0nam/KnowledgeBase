"""kb-web — local-only FastAPI service for the review console.

Read-mostly endpoints over `data/wiki/` and `data/handoffs/`. Mutations
shell out to the existing `kb-wiki-review` machinery so the markdown
files remain the single source of truth.
"""
