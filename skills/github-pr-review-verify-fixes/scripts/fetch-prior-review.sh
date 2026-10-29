#!/usr/bin/env bash
# Find the current user's most recent submitted review containing inline findings.
# Summary-only follow-ups must not hide the original review on the next run.
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
#        running a fresh code-review workflow + github-pr-review-publish)
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

# Thread replies get their own review records; only root findings identify a review.
reviews_json="$(gh api --paginate "/repos/${owner}/${repo}/pulls/${pr}/reviews" 2>/dev/null)" || {
  echo "error: gh api /pulls/${pr}/reviews failed" >&2
  exit 1
}

finding_reviews="$(gh api --paginate "/repos/${owner}/${repo}/pulls/${pr}/comments" \
  | jq -s '[flatten | .[] | select(.in_reply_to_id == null)
             | .pull_request_review_id | select(. != null)] | unique')" || {
  echo "error: cannot load prior inline findings" >&2
  exit 1
}

prior="$(printf '%s' "$reviews_json" | jq -s --arg login "$current_user" --argjson ids "$finding_reviews" '
  flatten
  | map(select(.user.login == $login and .submitted_at != null))
  | map(select(.id as $id | $ids | index($id) != null))
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
