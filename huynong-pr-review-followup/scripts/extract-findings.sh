#!/usr/bin/env bash
# Extract inline comments from a specific PR review and dump each as a JSON
# file under an output directory — one finding per file. This is the canonical
# input for the verdict-judgement loop and for build-followup-payload.sh.
#
# Usage:
#   extract-findings.sh <pr> <review_id> <out_dir> [<owner> <repo>]
#
# Output: one file per inline comment named `NN-<comment_id>.json` with:
#   {
#     "comment_id": <number>,
#     "path": "<file path>",
#     "original_line": <number>,        // line at time of original review
#     "side": "RIGHT" | "LEFT",
#     "start_line": <number|null>,
#     "start_side": "RIGHT" | "LEFT" | null,
#     "severity": "Critical" | "Important" | "Suggestion" | "Unknown",
#     "body": "<full original body>",
#     "diff_hunk": "<short context shown in original comment>",
#     "html_url": "<link to original comment>"
#   }
#
# Severity is parsed from the GitHub-shields badge in the body:
#   ![important](https://img.shields.io/badge/Priority-Important-orange)
set -euo pipefail

pr="${1:?pr number required}"
review_id="${2:?review_id required}"
out_dir="${3:?out_dir required}"
owner="${4:-}"
repo="${5:-}"

command -v gh >/dev/null || { echo "error: gh required" >&2; exit 2; }
command -v jq >/dev/null || { echo "error: jq required" >&2; exit 2; }

if [[ -z "$owner" || -z "$repo" ]]; then
  meta="$(gh repo view --json owner,name 2>/dev/null)" || {
    echo "error: cannot infer owner/repo — pass them explicitly" >&2; exit 2;
  }
  owner="$(jq -r '.owner.login' <<<"$meta")"
  repo="$(jq -r '.name' <<<"$meta")"
fi

mkdir -p "$out_dir"

# The per-review comments endpoint (`/reviews/{id}/comments`) omits line
# fields. Use the PR-wide review-comments endpoint (`/pulls/{n}/comments`)
# which returns full line data, then filter by `pull_request_review_id`.
comments_json="$(gh api --paginate \
  "/repos/${owner}/${repo}/pulls/${pr}/comments" 2>/dev/null)" || {
  echo "error: gh api /pulls/${pr}/comments failed" >&2
  exit 1
}

# Pagination may concatenate arrays — flatten, then keep only this review's.
mapfile -t comments < <(printf '%s' "$comments_json" \
  | jq -c -s --argjson rid "$review_id" \
      'flatten | map(select(.pull_request_review_id == $rid)) | .[]' 2>/dev/null)

if (( ${#comments[@]} == 0 )); then
  echo "warning: no inline comments on review ${review_id}" >&2
  exit 0
fi

idx=0
for c in "${comments[@]}"; do
  idx=$((idx + 1))
  cid="$(jq -r '.id' <<<"$c")"
  path="$(jq -r '.path' <<<"$c")"
  # original_line = anchor in the prior review's commit (what we need for verdict);
  # line          = anchor re-resolved against current head (may be null if drifted out)
  line="$(jq -r '.original_line // .line // empty' <<<"$c")"
  side="$(jq -r '.side // "RIGHT"' <<<"$c")"
  start_line="$(jq -r '.original_start_line // .start_line // empty' <<<"$c")"
  start_side="$(jq -r '.start_side // empty' <<<"$c")"
  body="$(jq -r '.body' <<<"$c")"
  diff_hunk="$(jq -r '.diff_hunk // ""' <<<"$c")"
  html_url="$(jq -r '.html_url' <<<"$c")"

  # Severity: scan body for the shields.io badge pattern.
  severity="Unknown"
  case "$body" in
    *Priority-Critical*) severity="Critical" ;;
    *Priority-Important*) severity="Important" ;;
    *Priority-Suggestion*) severity="Suggestion" ;;
  esac

  out_file="$(printf "%s/%02d-%s.json" "$out_dir" "$idx" "$cid")"

  jq -n \
    --argjson cid "$cid" \
    --arg path "$path" \
    --argjson line "${line:-null}" \
    --arg side "$side" \
    --arg start_line "${start_line:-}" \
    --arg start_side "${start_side:-}" \
    --arg severity "$severity" \
    --arg body "$body" \
    --arg diff_hunk "$diff_hunk" \
    --arg html_url "$html_url" \
    '{
      comment_id: $cid,
      path: $path,
      original_line: $line,
      side: $side,
      start_line: (if $start_line == "" then null else ($start_line|tonumber) end),
      start_side: (if $start_side == "" then null else $start_side end),
      severity: $severity,
      body: $body,
      diff_hunk: $diff_hunk,
      html_url: $html_url
    }' > "$out_file"
done

echo "extracted ${idx} finding(s) to ${out_dir}"
