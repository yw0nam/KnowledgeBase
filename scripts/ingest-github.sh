#!/usr/bin/env bash
# Ingest CLAUDE.md files and recent issues/PRs from GitHub repos into the
# yuri wiki knowledge base (llm-wiki-agent/data/raw/github/).
#
# Usage: ingest-github.sh owner/repo [owner/repo2 ...]
# Example: ingest-github.sh YoungWoo-Worr/DesktopMatePlus

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
GITHUB_BASE="$(cd "$SCRIPT_DIR/.." && pwd)/data/raw/github"
NOW=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
TODAY=$(date -u +"%Y-%m-%d")
GH_USER=$(gh api /user --jq '.login' 2>/dev/null || echo "unknown")

if [ $# -eq 0 ]; then
    echo "Usage: $0 owner/repo [owner/repo2 ...]"
    exit 1
fi

# Convert a string to a kebab-case slug (max 50 chars)
slugify() {
    echo "$1" \
        | tr '[:upper:]' '[:lower:]' \
        | sed 's/[^a-z0-9]/-/g; s/-\+/-/g; s/^-//; s/-$//' \
        | cut -c1-50 \
        | sed 's/-$//'
}

# Write file only if content changed (ignoring captured_at line)
write_if_changed() {
    local dest="$1" tmp="$2"
    # Normalize to LF
    tr -d '\r' < "$tmp" > "${tmp}.lf" && mv "${tmp}.lf" "$tmp"
    if [ -f "$dest" ]; then
        local tmp_dest tmp_new
        tmp_dest=$(mktemp)
        tmp_new=$(mktemp)
        grep -v '^captured_at:' "$dest" | tr -d '\r' > "$tmp_dest"
        grep -v '^captured_at:' "$tmp"               > "$tmp_new"
        if diff "$tmp_dest" "$tmp_new" > /dev/null 2>&1; then
            rm "$tmp" "$tmp_dest" "$tmp_new"
            return
        fi
        rm "$tmp_dest" "$tmp_new"
    fi
    mv "$tmp" "$dest"
}

# Fetch last comment body for an issue/PR number
last_comment() {
    local repo="$1" num="$2"
    # Strip control chars except TAB(9) and LF(10)
    gh api "repos/$repo/issues/$num/comments" --jq '.[-1].body // ""' 2>/dev/null \
        | tr -d '\000-\010\013-\037' \
        || echo ""
}

last_comment_author() {
    local repo="$1" num="$2"
    gh api "repos/$repo/issues/$num/comments" --jq '.[-1].user.login // ""' 2>/dev/null \
        || echo ""
}

for REPO in "$@"; do
    OWNER=$(echo "$REPO" | cut -d/ -f1)
    NAME=$(echo "$REPO" | cut -d/ -f2)

    REPO_DIR="$GITHUB_BASE/$NAME"
    ISSUE_DIR="$REPO_DIR/issue"
    PR_DIR="$REPO_DIR/pr"
    mkdir -p "$REPO_DIR" "$ISSUE_DIR" "$PR_DIR"

    echo "=== Ingesting $REPO ==="

    # ── CLAUDE.md ──────────────────────────────────────────────────────────
    OUTFILE="$REPO_DIR/${NAME}-claude.md"
    CONTENT=$(gh api "repos/$REPO/contents/CLAUDE.md" --jq '.content' 2>/dev/null || echo "")

    if [ -n "$CONTENT" ]; then
        COMMIT=$(gh api "repos/$REPO/commits?path=CLAUDE.md&per_page=1" --jq '.[0].sha' 2>/dev/null || echo "unknown")
        TMP=$(mktemp)
        {
            echo "---"
            echo "category: github"
            echo "date: \"$TODAY\""
            echo "title: \"$REPO CLAUDE.md\""
            echo "source_url: \"https://github.com/$REPO/blob/main/CLAUDE.md\""
            echo "type: claude_md"
            echo "repo: \"$REPO\""
            echo "captured_at: \"$NOW\""
            echo "commit: \"$COMMIT\""
            echo "contributor: \"$GH_USER\""
            echo "tags: [project]"
            echo "---"
            echo ""
            echo "$CONTENT" | base64 --decode
        } > "$TMP"
        write_if_changed "$OUTFILE" "$TMP"
        echo "  CLAUDE.md -> $OUTFILE"
    else
        echo "  CLAUDE.md not found in $REPO, skipping"
    fi

    # ── Issues ─────────────────────────────────────────────────────────────
    echo "  Fetching issues..."
    gh issue list --repo "$REPO" --state all --limit 30 \
        --json number,title,body,state,labels,createdAt,author 2>/dev/null \
        | jq '[.[] | walk(if type == "string" then (explode | map(select(. == 9 or . == 10 or (. > 31 and . != 127))) | implode) else . end)]' \
        | jq -r '.[] | @base64' | while read -r ITEM; do
        [ -z "$ITEM" ] && continue
        DECODED=$(echo "$ITEM" | base64 --decode)
        NUM=$(echo "$DECODED" | jq -r '.number')
        TITLE=$(echo "$DECODED" | jq -r '.title')
        BODY=$(echo "$DECODED" | jq -r '.body // ""')
        STATE=$(echo "$DECODED" | jq -r '.state')
        CREATED=$(echo "$DECODED" | jq -r '.createdAt')
        DATE_ONLY="${CREATED:0:10}"
        AUTHOR=$(echo "$DECODED" | jq -r '.author.login // "unknown"')
        LABELS=$(echo "$DECODED" | jq -r '[.labels[].name] | join(", ")')

        LAST_COMMENT=$(last_comment "$REPO" "$NUM")
        LAST_COMMENT_AUTHOR=$(last_comment_author "$REPO" "$NUM")

        SLUG=$(slugify "$TITLE")
        ISSUE_FILE="$ISSUE_DIR/${NUM}-${SLUG}.md"
        TMP=$(mktemp)
        {
            echo "---"
            echo "category: github"
            echo "date: \"$DATE_ONLY\""
            echo "title: \"$TITLE\""
            echo "source_url: \"https://github.com/$REPO/issues/$NUM\""
            echo "type: github_issue"
            echo "repo: \"$REPO\""
            echo "issue_number: $NUM"
            echo "state: \"$STATE\""
            echo "labels: \"$LABELS\""
            echo "captured_at: \"$NOW\""
            echo "author: \"$AUTHOR\""
            echo "contributor: \"$GH_USER\""
            echo "tags: [issue]"
            echo "---"
            echo ""
            echo "# $TITLE"
            echo ""
            echo "$BODY"
            if [ -n "$LAST_COMMENT" ]; then
                echo ""
                echo "## Last Comment ($LAST_COMMENT_AUTHOR)"
                echo ""
                echo "$LAST_COMMENT"
            fi
        } > "$TMP"
        write_if_changed "$ISSUE_FILE" "$TMP"
    done
    echo "  Issues done."

    # ── PRs ────────────────────────────────────────────────────────────────
    echo "  Fetching PRs..."
    gh pr list --repo "$REPO" --state all --limit 30 \
        --json number,title,body,state,labels,createdAt,author,mergedAt 2>/dev/null \
        | jq '[.[] | walk(if type == "string" then (explode | map(select(. == 9 or . == 10 or (. > 31 and . != 127))) | implode) else . end)]' \
        | jq -r '.[] | @base64' | while read -r ITEM; do
        [ -z "$ITEM" ] && continue
        DECODED=$(echo "$ITEM" | base64 --decode)
        NUM=$(echo "$DECODED" | jq -r '.number')
        TITLE=$(echo "$DECODED" | jq -r '.title')
        BODY=$(echo "$DECODED" | jq -r '.body // ""')
        MERGED_AT=$(echo "$DECODED" | jq -r '.mergedAt // ""')
        CREATED=$(echo "$DECODED" | jq -r '.createdAt')
        DATE_ONLY="${CREATED:0:10}"
        AUTHOR=$(echo "$DECODED" | jq -r '.author.login // "unknown"')
        LABELS=$(echo "$DECODED" | jq -r '[.labels[].name] | join(", ")')

        if [ -n "$MERGED_AT" ]; then
            STATE="MERGED"
        else
            STATE=$(echo "$DECODED" | jq -r '.state')
        fi

        LAST_COMMENT=$(last_comment "$REPO" "$NUM")
        LAST_COMMENT_AUTHOR=$(last_comment_author "$REPO" "$NUM")

        SLUG=$(slugify "$TITLE")
        PR_FILE="$PR_DIR/${NUM}-${SLUG}.md"
        TMP=$(mktemp)
        {
            echo "---"
            echo "category: github"
            echo "date: \"$DATE_ONLY\""
            echo "title: \"PR #$NUM: $TITLE\""
            echo "source_url: \"https://github.com/$REPO/pull/$NUM\""
            echo "type: github_pr"
            echo "repo: \"$REPO\""
            echo "pr_number: $NUM"
            echo "state: \"$STATE\""
            echo "merged: $([ -n "$MERGED_AT" ] && echo 'true' || echo 'false')"
            if [ -n "$MERGED_AT" ]; then
                echo "merged_at: \"$MERGED_AT\""
            fi
            echo "labels: \"$LABELS\""
            echo "captured_at: \"$NOW\""
            echo "author: \"$AUTHOR\""
            echo "contributor: \"$GH_USER\""
            echo "tags: [pr]"
            echo "---"
            echo ""
            echo "# PR #$NUM: $TITLE"
            echo ""
            echo "$BODY"
            if [ -n "$LAST_COMMENT" ]; then
                echo ""
                echo "## Last Comment ($LAST_COMMENT_AUTHOR)"
                echo ""
                echo "$LAST_COMMENT"
            fi
        } > "$TMP"
        write_if_changed "$PR_FILE" "$TMP"
    done
    echo "  PRs done."

    echo "=== $REPO complete ==="
    echo ""
done

echo "Ingest finished at $NOW"
