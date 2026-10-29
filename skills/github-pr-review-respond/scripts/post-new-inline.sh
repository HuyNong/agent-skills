#!/usr/bin/env bash
# Post a NEW inline comment on a PR (not a threaded reply to an existing comment).
# Use this when the finding to acknowledge is in a review body's "suppressed"
# section or in a top-level PR comment — i.e. there is no comment_id to thread
# under.
#
# GOTCHA: GitHub validates that `commit_id` belongs to the PR. If the commit is
# only local (not pushed), POST fails with 422 "commit_id is not part of the
# pull request". Push the branch BEFORE running this script.
#
# Usage: post-new-inline.sh <owner> <repo> <pr> <commit_sha> <path> <line> <body_file>
#   commit_sha — full SHA (40 chars) of a commit that is on origin AND part of
#                the PR (typically the current PR head)
#   path       — file path as it appears in the PR diff (case-sensitive)
#   line       — 1-based line number in the new-file side
#   body_file  — markdown body
#
# For multi-line anchors, use the GitHub API directly — this script does single-line only.
set -euo pipefail

owner="${1:?owner required}"
repo="${2:?repo required}"
pr="${3:?pr required}"
commit_sha="${4:?commit_sha required}"
path="${5:?path required}"
line="${6:?line required}"
body_file="${7:?body_file required}"

[[ -r "$body_file" ]] || { echo "error: body_file not readable: $body_file" >&2; exit 2; }
[[ ${#commit_sha} -ge 40 ]] || { echo "error: commit_sha must be the full 40-char SHA" >&2; exit 2; }

if ! gh auth status >/dev/null 2>&1; then
  echo "error: gh not authenticated. Run: gh auth login" >&2; exit 1
fi

# Pre-flight: verify the commit is reachable on origin for this PR. Catches
# the "local-only commit" foot-gun before the POST 422s.
if ! gh api "/repos/${owner}/${repo}/pulls/${pr}/commits" --jq '.[].sha' 2>/dev/null \
     | grep -qx "$commit_sha"; then
  echo "error: commit ${commit_sha} is not on PR #${pr} (not pushed yet?)" >&2
  echo "hint: push the branch first (e.g. 'but push <branch>' or 'git push')" >&2
  exit 4
fi

html_url="$(gh api \
  --method POST \
  -H "Accept: application/vnd.github+json" \
  "/repos/${owner}/${repo}/pulls/${pr}/comments" \
  -f "commit_id=${commit_sha}" \
  -f "path=${path}" \
  -F "line=${line}" \
  -f "side=RIGHT" \
  -F "body=@${body_file}" \
  --jq '.html_url')"

[[ -n "$html_url" ]] || { echo "error: post succeeded but html_url missing" >&2; exit 3; }
echo "html_url=${html_url}"
