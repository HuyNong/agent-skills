#!/usr/bin/env bash
# Submit a multi-comment PR review via the GitHub API.
# Usage: post-review.sh <owner> <repo> <pr> <payload.json>
# Returns: html_url=<review-url>
#
# On failure, prints the full GitHub error response body to stderr so
# diagnostic messages like {"errors":["Line could not be resolved"]} reach
# the caller — not just the bare HTTP status.
set -euo pipefail

owner="${1:?owner required}"
repo="${2:?repo required}"
pr="${3:?pr required}"
payload="${4:?payload.json required}"

[[ -r "$payload" ]] || { echo "error: payload not readable: $payload" >&2; exit 2; }

if ! gh auth status >/dev/null 2>&1; then
  echo "error: gh not authenticated. Run: gh auth login" >&2; exit 1
fi

# Capture full response so we can show the error body if submission fails.
# `gh api` writes the response JSON to stdout regardless of success/failure,
# and exits non-zero on HTTP >= 400.
response_file="$(mktemp -t gh-review-response.XXXXXX)"
trap 'rm -f "$response_file"' EXIT

if ! gh api \
    --method POST \
    -H "Accept: application/vnd.github+json" \
    "/repos/${owner}/${repo}/pulls/${pr}/reviews" \
    --input "$payload" \
    >"$response_file" 2>&1; then
  echo "error: gh api POST /pulls/${pr}/reviews failed" >&2
  echo "--- response body ---" >&2
  cat "$response_file" >&2
  echo "--- end response ---" >&2
  exit 4
fi

html_url="$(jq -r '.html_url // empty' "$response_file" 2>/dev/null || true)"
[[ -n "$html_url" ]] || {
  echo "error: post succeeded but html_url missing in response" >&2
  cat "$response_file" >&2
  exit 3
}
echo "html_url=${html_url}"
