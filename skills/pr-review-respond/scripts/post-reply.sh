#!/usr/bin/env bash
# Post a threaded reply to a PR review comment (or a top-level fallback comment).
# Usage: post-reply.sh <owner> <repo> <pr> <comment_id> <kind> <body_file>
# Optional: <receipt> <item-key> <verdict> <fix-state>
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
receipt_file="${7:-}"
item_key="${8:-reply}"

# Legacy calls validate format; new workflows also supply verdict/fix state.
bash "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/validate-reply-body.sh" "$body_file" "${9:-}" "${10:-}"

[[ -r "$body_file" ]] || { echo "error: body_file not readable: $body_file" >&2; exit 2; }
body="$(cat "$body_file")"
[[ -n "$body" ]] || { echo "error: body is empty" >&2; exit 2; }

if [[ -n "$receipt_file" ]]; then
  case "$kind" in
    review) endpoint="/repos/$owner/$repo/pulls/$pr/comments/$comment_id/replies" ;;
    issue) endpoint="/repos/$owner/$repo/issues/$pr/comments" ;;
    *) echo "error: unknown kind: $kind" >&2; exit 2 ;;
  esac
  payload="$(mktemp "${TMPDIR:-/tmp}/pr-reply.XXXXXX")"
  trap 'rm -f -- "$payload"' EXIT
  jq -n --rawfile body "$body_file" '{body:$body}' > "$payload"
  source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/review-receipt.sh"
  receipt_post "$receipt_file" respond "$owner" "$repo" "$pr" "$item_key" "$endpoint" "$payload"
  exit $?
fi

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
