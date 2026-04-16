#!/usr/bin/env bash
# Ingest CLAUDE.md files and recent issues/PRs from GitHub repos.
# Usage: ./scripts/ingest-github.sh owner/repo [owner/repo2 ...]
# Example: ./scripts/ingest-github.sh YoungWoo-Worr/DesktopMatePlus

set -euo pipefail

BASEDIR="$(cd "$(dirname "$0")/.." && pwd)"
DATADIR="$BASEDIR/data"
CLAUDE_MD_DIR="$DATADIR/raw/github/claude-md"
ISSUES_DIR="$DATADIR/raw/github/issues"
NOW=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

if [ $# -eq 0 ]; then
    echo "Usage: $0 owner/repo [owner/repo2 ...]"
    exit 1
fi

for REPO in "$@"; do
    OWNER=$(echo "$REPO" | cut -d/ -f1)
    NAME=$(echo "$REPO" | cut -d/ -f2)
    SLUG="${OWNER}_${NAME}"

    echo "=== Ingesting $REPO ==="

    # --- CLAUDE.md ---
    OUTFILE="$CLAUDE_MD_DIR/${SLUG}_CLAUDE.md"
    CONTENT=$(gh api "repos/$REPO/contents/CLAUDE.md" --jq '.content' 2>/dev/null || echo "")

    if [ -n "$CONTENT" ]; then
        COMMIT=$(gh api "repos/$REPO/commits?path=CLAUDE.md&per_page=1" --jq '.[0].sha' 2>/dev/null || echo "unknown")
        {
            echo "---"
            echo "source_url: \"https://github.com/$REPO/blob/main/CLAUDE.md\""
            echo "type: claude_md"
            echo "repo: \"$REPO\""
            echo "captured_at: \"$NOW\""
            echo "commit: \"$COMMIT\""
            echo "contributor: \"nam-young-woo\""
            echo "tags: [project]"
            echo "---"
            echo ""
            echo "$CONTENT" | base64 --decode
        } > "$OUTFILE"
        echo "  CLAUDE.md -> $OUTFILE"
    else
        echo "  CLAUDE.md not found in $REPO, skipping"
    fi

    # --- Issues ---
    echo "  Fetching issues..."
    gh issue list --repo "$REPO" --state all --limit 30 \
        --json number,title,body,state,labels,createdAt,author \
        --jq '.[] | @base64' 2>/dev/null | while read -r ITEM; do
        DECODED=$(echo "$ITEM" | base64 --decode)
        NUM=$(echo "$DECODED" | jq -r '.number')
        TITLE=$(echo "$DECODED" | jq -r '.title')
        BODY=$(echo "$DECODED" | jq -r '.body // ""')
        STATE=$(echo "$DECODED" | jq -r '.state')
        CREATED=$(echo "$DECODED" | jq -r '.createdAt')
        AUTHOR=$(echo "$DECODED" | jq -r '.author.login // "unknown"')
        LABELS=$(echo "$DECODED" | jq -r '[.labels[].name] | join(", ")')

        ISSUE_FILE="$ISSUES_DIR/${NAME}_${NUM}.md"
        {
            echo "---"
            echo "source_url: \"https://github.com/$REPO/issues/$NUM\""
            echo "type: github_issue"
            echo "repo: \"$REPO\""
            echo "issue_number: $NUM"
            echo "state: \"$STATE\""
            echo "labels: \"$LABELS\""
            echo "captured_at: \"$NOW\""
            echo "created_at: \"$CREATED\""
            echo "author: \"$AUTHOR\""
            echo "contributor: \"nam-young-woo\""
            echo "tags: [issue]"
            echo "---"
            echo ""
            echo "# $TITLE"
            echo ""
            echo "$BODY"
        } > "$ISSUE_FILE"
    done
    echo "  Issues done."

    # --- PRs ---
    echo "  Fetching PRs..."
    gh pr list --repo "$REPO" --state all --limit 30 \
        --json number,title,body,state,labels,createdAt,author \
        --jq '.[] | @base64' 2>/dev/null | while read -r ITEM; do
        DECODED=$(echo "$ITEM" | base64 --decode)
        NUM=$(echo "$DECODED" | jq -r '.number')
        TITLE=$(echo "$DECODED" | jq -r '.title')
        BODY=$(echo "$DECODED" | jq -r '.body // ""')
        STATE=$(echo "$DECODED" | jq -r '.state')
        CREATED=$(echo "$DECODED" | jq -r '.createdAt')
        AUTHOR=$(echo "$DECODED" | jq -r '.author.login // "unknown"')
        LABELS=$(echo "$DECODED" | jq -r '[.labels[].name] | join(", ")')

        PR_FILE="$ISSUES_DIR/${NAME}_PR${NUM}.md"
        {
            echo "---"
            echo "source_url: \"https://github.com/$REPO/pull/$NUM\""
            echo "type: github_pr"
            echo "repo: \"$REPO\""
            echo "pr_number: $NUM"
            echo "state: \"$STATE\""
            echo "labels: \"$LABELS\""
            echo "captured_at: \"$NOW\""
            echo "created_at: \"$CREATED\""
            echo "author: \"$AUTHOR\""
            echo "contributor: \"nam-young-woo\""
            echo "tags: [pr]"
            echo "---"
            echo ""
            echo "# PR #$NUM: $TITLE"
            echo ""
            echo "$BODY"
        } > "$PR_FILE"
    done
    echo "  PRs done."

    echo "=== $REPO complete ==="
    echo ""
done

echo "Ingest finished at $NOW"
