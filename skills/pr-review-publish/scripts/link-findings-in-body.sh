#!/usr/bin/env bash
# Post-submission step: inject direct links to inline comments into the review body.
#
# Usage:
#   link-findings-in-body.sh <owner> <repo> <pr> <review_id> <comments_dir>
#
# How it works:
#   1. Read comment JSONs from <comments_dir> to get {path, line} per finding
#   2. GET /reviews/{id}/comments to get {path, body, html_url} per posted comment
#   3. Match local JSONs to API comments by path + body substring
#   4. Build a map of "basename:line" → html_url
#   5. Replace backtick-wrapped refs in review body with markdown links
#   6. PUT updated body back
#
# The comments_dir must still exist (run BEFORE cleanup in Step 10).
#
# Exit codes:
#   0 — body updated (or no replacements needed)
#   1 — missing args / gh not authenticated
#   2 — API failure
#   3 — API update failure
set -euo pipefail

owner="${1:?owner required}"
repo="${2:?repo required}"
pr="${3:?pr required}"
review_id="${4:?review_id required}"
comments_dir="${5:?comments_dir required}"

if ! gh auth status >/dev/null 2>&1; then
  echo "error: gh not authenticated" >&2; exit 1
fi

[[ -d "$comments_dir" ]] || { echo "error: comments_dir not found: $comments_dir" >&2; exit 1; }

# ── Step 1: Read local comment JSONs → [{path, line, body_prefix}] ───────────

local_comments="$(
  find "$comments_dir" -maxdepth 1 -type f -name '*.json' -print0 \
    | xargs -0 -I{} cat {} \
    | jq -s '[.[] | {
        path: .path,
        line: (.line // 0),
        body_prefix: (.body | split("\n") | map(select(length > 10)) | .[1] // .[0] // "" | .[0:80])
      }]'
)"

num_local="$(echo "$local_comments" | jq 'length')"
if [[ "$num_local" -eq 0 ]]; then
  echo "no local comment files found — nothing to link"
  exit 0
fi

# ── Step 2: Fetch posted review comments → [{path, body, html_url}] ──────────

api_comments="$(gh api "/repos/${owner}/${repo}/pulls/${pr}/reviews/${review_id}/comments" \
  --paginate --jq '[.[] | {path: .path, body: .body, url: .html_url}]' 2>/dev/null)" || {
  echo "error: failed to fetch review comments" >&2; exit 2
}

# ── Step 3: Match local → API by path + body substring → build link map ──────

link_map="$(jq -n \
  --argjson local "$local_comments" \
  --argjson api "$api_comments" '
  # For each local comment, find the matching API comment by path + body_prefix
  reduce ($local | to_entries[]) as $e (
    {};
    ($e.value.path) as $path |
    ($e.value.line | tostring) as $line |
    ($e.value.body_prefix) as $prefix |
    # Find API comment matching path AND containing the body prefix
    ([$api[] | select(.path == $path and (.body | contains($prefix)))] | first) as $match |
    if $match then
      ($path | split("/")) as $parts |
      ($parts | length) as $len |
      # Generate keys at multiple path depths: full, basename, and all intermediate suffixes
      # e.g. "apps/bino-app/src/lib/mqtt.ts:67" → also "lib/mqtt.ts:67", "src/lib/mqtt.ts:67", "mqtt.ts:67"
      reduce range(1; $len + 1) as $i (
        .;
        (($parts[$len - $i:] | join("/")) + ":" + $line) as $key |
        . + {($key): $match.url}
      )
    else . end
  )
')"

num_links="$(echo "$link_map" | jq 'length')"
if [[ "$num_links" -eq 0 ]]; then
  echo "no comments matched — body unchanged"
  exit 0
fi

echo "matched $(( num_links / 2 )) comment(s) to body refs"

# ── Step 4: Fetch current review body ────────────────────────────────────────

current_body="$(gh api "/repos/${owner}/${repo}/pulls/${pr}/reviews/${review_id}" \
  --jq '.body' 2>/dev/null)" || {
  echo "error: failed to fetch review body" >&2; exit 2
}

# ── Step 5: Replace backtick refs with markdown links ────────────────────────
# Pattern: `some/path.ts:123` or `filename.ts:123` → [`filename.ts:123`](url)

patched_body="$(echo "$link_map" | jq -r --arg body "$current_body" '
  . as $map |
  (keys | sort_by(-length)) as $keys |
  reduce $keys[] as $key (
    $body;
    ($key | gsub("(?<c>[./])"; "\\\(.c)")) as $escaped |
    gsub("`" + $escaped + "`"; "[`" + $key + "`](" + $map[$key] + ")")
  )
')"

if [[ "$patched_body" == "$current_body" ]]; then
  echo "no backtick refs matched in body text — body unchanged"
  exit 0
fi

# ── Step 6: Update the review body ───────────────────────────────────────────

if ! gh api "/repos/${owner}/${repo}/pulls/${pr}/reviews/${review_id}" \
  -X PUT \
  --field body="$patched_body" \
  --jq '.html_url' >/dev/null 2>&1; then
  echo "error: failed to update review body" >&2; exit 3
fi

# Count linked refs
linked="$(diff <(echo "$current_body") <(echo "$patched_body") | grep -c "^>" || true)"
echo "linked ${linked} ref(s) → review body updated"
