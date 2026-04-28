## Summary

<!-- 1–3 bullets: what changed and why. Reference issues with `Fixes #N` / `Refs #N`. -->

-
-

## Component(s) touched

<!-- Check all that apply. -->

- [ ] `scripts/` (ingest-github.sh / kb_update.sh / lint.sh)
- [ ] `src/kb_mcp/` (core / tools / server)
- [ ] `test/`
- [ ] `.github/` (CI / templates)
- [ ] `CLAUDE.md` / docs
- [ ] Data pipeline behavior (Ingest → Graph → Fill → Lint → Log)

## Test plan

- [ ] `uv run pytest` — all green
- [ ] `uv run kb-lint-wiki` — 0 errors (wiki lint)
- [ ] Manual smoke: <!-- describe the flow you ran, or write N/A -->

## Notes for reviewer

<!-- Optional: design rationale, tradeoffs, follow-ups, etc. -->
