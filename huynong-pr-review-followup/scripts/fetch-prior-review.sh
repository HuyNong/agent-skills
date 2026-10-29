#!/usr/bin/env bash
# Find the most recent review on a PR submitted by the currently-authenticated
# `gh` user, and emit its key metadata for the followup workflow.
#
# Usage:
#   fetch-prior-review.sh <pr> [<owner> <repo>]
#
# Output (KEY=VALUE, one per line):
#   review_id=<numeric review id>
#   review_state=<COMMENTED|APPROVED|CHANGES_REQUESTED|DISMISSED>
#   review_commit_id=<SHA the prior review was anchored to>
#   review_submitted_at=<ISO8601 timestamp>
#   review_html_url=<link>
#   owner=<...>
#   repo=<...>
#   pr=<...>
#   current_user=<login>
#
# Exit codes:
#   0  — found a prior review by current user
#   1  — generic failure
#   2  — bad args / missing deps
#   3  — no prior review by current user on this PR (caller should suggest
#        running /pr-review-toolkit:review-pr + huynong-post-pr-review-comment)
set -euo pipefail

pr="${1:?pr number required}"
owner="${2:-}"
repo="${3:-}"

command -v gh >/dev/null || { echo "error: gh required" >&2; exit 2; }
command -v jq >/dev/null || { echo "error: jq required" >&2; exit 2; }

if [[ -z "$owner" || -z "$repo" ]]; then
  meta="$(gh repo view --json owner,name 2>/dev/null)" || {
    echo "error: cannot infer owner/repo — pass them explicitly" >&2
    exit 2
  }
  owner="$(jq -r '.owner.login' <<<"$meta")"
  repo="$(jq -r '.name' <<<"$meta")"
fi

current_user="$(gh api /user --jq '.login' 2>/dev/null || true)"
[[ -n "$current_user" ]] || { echo "error: cannot identify current user — run 'gh auth login'" >&2; exit 1; }

# Reviews are returned oldest-first; pick the last one by current user.
reviews_json="$(gh api --paginate "/repos/${owner}/${repo}/pulls/${pr}/reviews" 2>/dev/null)" || {
  echo "error: gh api /pulls/${pr}/reviews failed" >&2
  exit 1
}

# `--paginate` can produce concatenated arrays; normalise via `jq -s`.
prior="$(printf '%s' "$reviews_json" | jq -s --arg login "$current_user" '
  flatten
  | map(select(.user.login == $login))
  | sort_by(.submitted_at)
  | last
' 2>/dev/null)"

if [[ -z "$prior" || "$prior" == "null" ]]; then
  echo "no_prior_review_by=${current_user}" >&2
  exit 3
fi

review_id="$(jq -r '.id' <<<"$prior")"
review_state="$(jq -r '.state' <<<"$prior")"
review_commit_id="$(jq -r '.commit_id' <<<"$prior")"
review_submitted_at="$(jq -r '.submitted_at' <<<"$prior")"
review_html_url="$(jq -r '.html_url' <<<"$prior")"

echo "review_id=${review_id}"
echo "review_state=${review_state}"
echo "review_commit_id=${review_commit_id}"
echo "review_submitted_at=${review_submitted_at}"
echo "review_html_url=${review_html_url}"
echo "owner=${owner}"
echo "repo=${repo}"
echo "pr=${pr}"
echo "current_user=${current_user}"
