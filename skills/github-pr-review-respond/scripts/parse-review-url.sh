#!/usr/bin/env bash
# Parse a GitHub PR review-comment URL into structured fields.
# Usage: parse-review-url.sh <url>
# Output (one KEY=VALUE per line): owner, repo, pr, comment_id, kind
#   kind = review | issue | unknown
set -euo pipefail

url="${1:-}"
[[ -z "$url" ]] && { echo "usage: $0 <github-pr-comment-url>" >&2; exit 2; }

# Strip the query from the path without discarding the comment fragment.
url_no_q="${url%%#*}"
url_no_q="${url_no_q%%\?*}"

# owner/repo/pull/N
if [[ "$url_no_q" =~ ^https://github\.com/([^/]+)/([^/]+)/(pull|pulls|issues)/([0-9]+)(/|$) ]]; then
  owner="${BASH_REMATCH[1]}"
  repo="${BASH_REMATCH[2]}"
  pr="${BASH_REMATCH[4]}"
elif [[ "$url_no_q" =~ ^https://api\.github\.com/repos/([^/]+)/([^/]+)/(pulls|issues)/([0-9]+)(/|$) ]]; then
  owner="${BASH_REMATCH[1]}"
  repo="${BASH_REMATCH[2]}"
  pr="${BASH_REMATCH[4]}"
else
  echo "error: not a recognised GitHub PR URL: $url" >&2
  exit 1
fi

# Fragment: #discussion_rXXX, #r<id>, #issuecomment-<id>
frag="${url##*#}"
[[ "$frag" == "$url" ]] && frag=""

kind="unknown"
comment_id=""

if [[ "$frag" =~ ^discussion_r([0-9]+)$ ]]; then
  kind="review"; comment_id="${BASH_REMATCH[1]}"
elif [[ "$frag" =~ ^r([0-9]+)$ ]]; then
  kind="review"; comment_id="${BASH_REMATCH[1]}"
elif [[ "$frag" =~ ^issuecomment-([0-9]+)$ ]]; then
  kind="issue"; comment_id="${BASH_REMATCH[1]}"
fi

# Also support API-style: .../pulls/N/comments/<id> (review) or .../issues/N/comments/<id>
if [[ -z "$comment_id" ]]; then
  if [[ "$url_no_q" =~ /pulls/[0-9]+/comments/([0-9]+) ]]; then
    kind="review"; comment_id="${BASH_REMATCH[1]}"
  elif [[ "$url_no_q" =~ /issues/[0-9]+/comments/([0-9]+) ]]; then
    kind="issue"; comment_id="${BASH_REMATCH[1]}"
  fi
fi

if [[ -z "$comment_id" ]]; then
  echo "error: could not extract comment id from URL: $url" >&2
  echo "  expected fragment like #discussion_r123, #r123, or #issuecomment-123" >&2
  exit 1
fi

cat <<EOF
owner=$owner
repo=$repo
pr=$pr
comment_id=$comment_id
kind=$kind
EOF
