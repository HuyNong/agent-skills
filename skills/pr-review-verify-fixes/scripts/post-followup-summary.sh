#!/usr/bin/env bash
# Summary-only COMMENT. Required receipt makes a partial batch resumable.
set -euo pipefail
owner="${1:?owner}"; repo="${2:?repo}"; pr="${3:?pr}"
head="${4:?head SHA}"; body="${5:?body file}"; receipt="${6:?receipt}"
[[ "$head" =~ ^[a-fA-F0-9]{40}$ && -s "$body" ]] || exit 2
payload="$(mktemp "${TMPDIR:-/tmp}/pr-followup.XXXXXX")"
trap 'rm -f -- "$payload"' EXIT
jq -n --arg commit_id "$head" --rawfile body "$body" \
  '{commit_id:$commit_id,event:"COMMENT",body:$body,comments:[]}' > "$payload"
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/review-receipt.sh"
receipt_post "$receipt" verify-fixes "$owner" "$repo" "$pr" summary "/repos/$owner/$repo/pulls/$pr/reviews" "$payload" "$head"
