---
name: data-sync
description: Deprecated. DB-canonical KnowledgeBase no longer syncs data/ via Git; use database backup/export tooling instead.
---

# data-sync

This skill is deprecated for runtime use.

KnowledgeBase is DB-canonical: `data/` is generated Markdown export and
inspection output, not the source of truth. Agents and cron jobs must not use
the legacy work-branch → PR sync flow.

## Current Rule

- Do not run `sync-data.sh`, `merge-data-pr.sh`, or setup scripts for normal operation.
- Do not ask agents or cron jobs to commit `data/`.
- Use DB write APIs for durable state and DB backup tooling for backup/sync.
- Markdown export may be committed manually as a snapshot, but it is not sync authority.

## Legacy Scripts

The scripts in this directory are retained only for historical recovery while
the migration branch is in flight. They should not be referenced by cron or
runtime skills.
