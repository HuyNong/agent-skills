#!/usr/bin/env bash
# Fetch PR head SHA + branch in one shot.
# Usage: get-pr-head.sh [<pr-number>]
#   If pr-number omitted, uses gh's current-branch detection.
# Output: KEY=VALUE lines for owner, repo, pr, head_sha, head_branch, base_branch
set -euo pipefail

pr="${1:-}"
fields="number,headRefOid,headRefName,baseRefName,url"

if [[ -n "$pr" ]]; then
  json="$(gh pr view "$pr" --json "$fields")"
else
  json="$(gh pr view --json "$fields")"
fi

# Extract owner/repo from URL (https://github.com/owner/repo/pull/N)
url="$(printf '%s' "$json" | jq -r '.url')"
if [[ "$url" =~ github\.com/([^/]+)/([^/]+)/pull/([0-9]+) ]]; then
  owner="${BASH_REMATCH[1]}"
  repo="${BASH_REMATCH[2]}"
else
  echo "error: could not parse owner/repo from URL: $url" >&2; exit 1
fi

cat <<EOF
owner=$owner
repo=$repo
pr=$(printf '%s' "$json" | jq -r '.number')
head_sha=$(printf '%s' "$json" | jq -r '.headRefOid')
head_branch=$(printf '%s' "$json" | jq -r '.headRefName')
base_branch=$(printf '%s' "$json" | jq -r '.baseRefName')
EOF
