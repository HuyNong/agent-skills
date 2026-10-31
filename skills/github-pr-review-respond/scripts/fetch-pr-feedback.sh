#!/usr/bin/env bash
# Collect every feedback source without printing/truncating its body.
# Usage: fetch-pr-feedback.sh <owner> <repo> <pr> <new-output-directory>
set -euo pipefail

owner="${1:?owner required}"
repo="${2:?repo required}"
pr="${3:?pr required}"
out="${4:?new output directory required}"
command -v gh >/dev/null || { echo "error: gh required" >&2; exit 2; }
command -v jq >/dev/null || { echo "error: jq required" >&2; exit 2; }
[[ "$owner" =~ ^[A-Za-z0-9][A-Za-z0-9-]*$ && "$repo" =~ ^[A-Za-z0-9_.-]+$ && "$pr" =~ ^[1-9][0-9]*$ ]] || {
  echo "error: invalid owner/repo/PR" >&2; exit 2;
}
[[ ! -e "$out" && ! -L "$out" ]] || { echo "error: output directory already exists" >&2; exit 2; }
mkdir -p "$out/items"

fetch_source() {
  local name="$1" endpoint="$2"
  printf '[]\n' > "$out/$name.json"
  if ! gh api --paginate -H "Accept: application/vnd.github+json" "$endpoint" \
      > "$out/$name-pages.json" 2> "$out/$name-error.log"; then
    echo "error: $name fetch incomplete; see $out/$name-error.log" >&2
    return 1
  fi
  # Slurp the page stream; reject non-array responses and partial/invalid bodies.
  if ! jq -e -s --arg kind "$name" '
    if length == 0 or any(.[]; type != "array") then error("expected array pages")
    else add | if any(.[];
      type != "object" or (.id | type != "number") or .id <= 0 or
      (.body | type != "string" and ($kind != "reviews" or . != null)))
      then error("invalid feedback record") else unique_by(.id) end end
  ' "$out/$name-pages.json" > "$out/$name-validated.json" 2>> "$out/$name-error.log"; then
    echo "error: $name response invalid; retained raw pages in $out" >&2
    return 1
  fi
  mv "$out/$name-validated.json" "$out/$name.json"
}

reviews_ok=false; inline_ok=false; issues_ok=false
fetch_source reviews "/repos/$owner/$repo/pulls/$pr/reviews" && reviews_ok=true
fetch_source inline "/repos/$owner/$repo/pulls/$pr/comments" && inline_ok=true
fetch_source issues "/repos/$owner/$repo/issues/$pr/comments" && issues_ok=true

for kind in reviews inline issues; do
  while IFS= read -r record; do
    id="$(printf '%s' "$record" | jq -r '.id')"
    printf '%s\n' "$record" > "$out/items/$kind-$id.json"
  done < <(jq -c '.[]' "$out/$kind.json")
done

jq -n --arg owner "$owner" --arg repo "$repo" --argjson pr "$pr" \
  --argjson reviews_ok "$reviews_ok" --argjson inline_ok "$inline_ok" --argjson issues_ok "$issues_ok" \
  --slurpfile reviews "$out/reviews.json" --slurpfile inline "$out/inline.json" --slurpfile issues "$out/issues.json" '
  def records($kind; $items): $items | map({
    key: ($kind + ":" + (.id | tostring)), kind: $kind, id,
    body_file: ("items/" + $kind + "-" + (.id | tostring) + ".json"),
    author: .user.login, html_url, review_id: .pull_request_review_id,
    root_comment_id: (if $kind == "inline" then (.in_reply_to_id // .id) else null end),
    is_reply: (.in_reply_to_id != null)
  });
  ($inline[0] | map(.id)) as $ids |
  ($inline[0] | map(select(.in_reply_to_id != null) | .in_reply_to_id) | unique - $ids) as $missing_roots |
  {
    owner: $owner, repo: $repo, pr: $pr,
    complete: ($reviews_ok and $inline_ok and $issues_ok and ($missing_roots | length == 0)),
    sources: {reviews: $reviews_ok, inline: $inline_ok, issues: $issues_ok},
    missing_root_ids: $missing_roots,
    counts: {reviews: ($reviews[0] | length), inline: ($inline[0] | length),
      issues: ($issues[0] | length), root_threads: ($inline[0] | map(select(.in_reply_to_id == null)) | length)},
    records: (records("reviews"; $reviews[0]) + records("inline"; $inline[0]) + records("issues"; $issues[0]))
  }
' > "$out/inventory.json"
jq '{complete, sources, counts, missing_root_ids}' "$out/inventory.json"
printf 'inventory=%s/inventory.json\n' "$out"
jq -e '.complete' "$out/inventory.json" >/dev/null || exit 3
