# Optional Global Digest

The morning global digest is optional but recommended once `kb-cron-wrapup` is producing stable daily summaries.

## Purpose

Create one morning notification that reports the previous night's KnowledgeBase pipeline state without re-reading KnowledgeBase internals.

The digest should consume only:

- `data/wiki/summaries/YYYY/MM/YYYY-MM-DD-cron-wrapup.md`
- The fixed H2 sections: `Status`, `Insights`, `Action Items`, `Anomalies`, `Counters`, `Links`

It should not read:

- `data/wiki/summaries/.../*-memory.md`
- `data/raw/`
- `.cron/logs/`
- individual usage report pages

## Recommended Schedule

```text
morning-slack-digest: 09:00 every day
```

Run it after the `05:00` `kb-cron-wrapup` job so the digest has a single stable artifact to parse.

## Setup Guidance

Use whatever scheduler or agent runtime the user already uses for notifications. Keep the job global rather than KnowledgeBase-owned, because it is a delivery concern, not a KB data-generation step.

Recommended prompt shape:

```text
Read the latest KnowledgeBase cron wrap-up summary for yesterday. Summarize only the fixed H2 contract sections: Status, Insights, Action Items, Anomalies, Counters, and Links. Do not inspect memory pages, raw data, usage pages, or cron logs directly. Send a concise morning status digest.
```

## Dependency

Set this up only after at least one `*-cron-wrapup.md` file exists and follows the fixed H2 contract.
