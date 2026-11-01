#!/usr/bin/env bash
# Post a threaded reply to a PR review comment (or a top-level fallback comment).
# Usage: post-reply.sh <owner> <repo> <pr> <comment_id> <kind> <body_file>
#   kind = review | issue
# Body is read from <body_file> to avoid shell-escaping pain.
# On success prints: html_url=<new_comment_url>
set -euo pipefail

owner="${1:?owner required}"
repo="${2:?repo required}"
pr="${3:?pr required}"
comment_id="${4:?comment_id required}"
kind="${5:?kind required (review|issue)}"
body_file="${6:?body_file required}"

[[ -r "$body_file" ]] || { echo "error: body_file not readable: $body_file" >&2; exit 2; }
body="$(cat "$body_file")"
[[ -n "$body" ]] || { echo "error: body is empty" >&2; exit 2; }

case "$kind" in
  review)
    # Threaded reply under the original review comment.
    # `--jq` runs jq on the response inside gh, so we just ask for html_url back.
    html_url="$(gh api \
      --method POST \
      -H "Accept: application/vnd.github+json" \
      "/repos/${owner}/${repo}/pulls/${pr}/comments/${comment_id}/replies" \
      -F "body=@${body_file}" \
      --jq '.html_url')"
    ;;
  issue)
    html_url="$(gh api \
      --method POST \
      -H "Accept: application/vnd.github+json" \
      "/repos/${owner}/${repo}/issues/${pr}/comments" \
      -F "body=@${body_file}" \
      --jq '.html_url')"
    echo "warn: kind=issue does not support threaded replies; posted top-level instead" >&2
    ;;
  *)
    echo "error: unknown kind: $kind" >&2; exit 2 ;;
esac

[[ -n "$html_url" ]] || { echo "error: post succeeded but html_url missing" >&2; exit 3; }
echo "html_url=${html_url}"
