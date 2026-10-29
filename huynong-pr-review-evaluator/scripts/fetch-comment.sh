#!/usr/bin/env bash
# Fetch a PR review comment (or top-level issue comment) via the gh CLI.
# Usage: fetch-comment.sh <owner> <repo> <comment_id> <kind>
#   kind = review | issue
# Output: a single JSON object on stdout.
set -euo pipefail

owner="${1:?owner required}"
repo="${2:?repo required}"
comment_id="${3:?comment_id required}"
kind="${4:?kind required (review|issue)}"

if ! command -v gh >/dev/null 2>&1; then
  echo "error: gh CLI not installed" >&2; exit 1
fi
if ! gh auth status >/dev/null 2>&1; then
  echo "error: gh not authenticated. Run: gh auth login" >&2; exit 1
fi

case "$kind" in
  review)
    # Pulls review-comment endpoint — has path/line/diff_hunk/in_reply_to_id
    gh api \
      -H "Accept: application/vnd.github+json" \
      "/repos/${owner}/${repo}/pulls/comments/${comment_id}" \
      --jq '{
        kind: "review",
        id: .id,
        author: .user.login,
        body: .body,
        path: .path,
        line: (.line // .original_line),
        start_line: (.start_line // .original_start_line),
        side: .side,
        commit_id: .commit_id,
        original_commit_id: .original_commit_id,
        diff_hunk: .diff_hunk,
        in_reply_to_id: .in_reply_to_id,
        pull_request_url: .pull_request_url,
        html_url: .html_url,
        created_at: .created_at,
        updated_at: .updated_at
      }'
    ;;
  issue)
    # Issue-comment endpoint — no inline anchor; can't be threaded.
    gh api \
      -H "Accept: application/vnd.github+json" \
      "/repos/${owner}/${repo}/issues/comments/${comment_id}" \
      --jq '{
        kind: "issue",
        id: .id,
        author: .user.login,
        body: .body,
        html_url: .html_url,
        created_at: .created_at,
        updated_at: .updated_at
      }'
    ;;
  *)
    echo "error: unknown kind: $kind (expected: review | issue)" >&2
    exit 2
    ;;
esac
