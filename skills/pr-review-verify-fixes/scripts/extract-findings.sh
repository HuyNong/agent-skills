#!/usr/bin/env bash
# Extract original roots; full summary/thread source accounting lives in .context.
set -euo pipefail
pr="${1:?PR}"; review_id="${2:?review ID}"; out="${3:?new output directory}"
owner="${4:-}"; repo="${5:-}"
command -v jq >/dev/null || exit 2
command -v gh >/dev/null || exit 2
if [[ -z "$owner" || -z "$repo" ]]; then
  meta="$(gh repo view --json owner,name)" || exit 2
  owner="$(jq -r '.owner.login' <<<"$meta")"; repo="$(jq -r '.name' <<<"$meta")"
fi
[[ ! -e "$out" && ! -L "$out" ]] || { echo "error: output exists; use a fresh directory" >&2; exit 2; }
mkdir -p "$out/.context/items"
prefix="/repos/$owner/$repo/pulls/$pr"
printf '%s\n' '{"complete":false,"records":[]}' > "$out/.context/inventory.json"
gh api "$prefix/reviews/$review_id" > "$out/.context/review.json" || exit 1
gh api --paginate "$prefix/comments" > "$out/.context/pages.json" || exit 1
jq -e --argjson rid "$review_id" '.id == $rid and (.body | type == "string" or . == null)' "$out/.context/review.json" >/dev/null || exit 1
jq -e -s 'if length == 0 or any(.[]; type != "array") then error("expected pages")
 else add | if any(.[]; (.id | type != "number") or (.body | type != "string"))
 then error("invalid comment") else . end end' "$out/.context/pages.json" > "$out/.context/all-comments.json" || exit 1
jq --argjson rid "$review_id" '
  [.[] | select(.pull_request_review_id == $rid and .in_reply_to_id == null)] as $roots |
  ($roots | map(.id)) as $ids |
  [.[] | select((.id as $id | $ids | index($id) != null) or
    (.in_reply_to_id as $id | $ids | index($id) != null))] |
  unique_by(.id)
' "$out/.context/all-comments.json" > "$out/.context/selected.json"
# A selected-review reply whose root vanished makes transport incomplete.
missing="$(jq --argjson rid "$review_id" '
  (map(.id)) as $ids | [.[] | select(.pull_request_review_id == $rid and .in_reply_to_id != null)
    | .in_reply_to_id | select(. as $id | $ids | index($id) == null)] | unique
' "$out/.context/all-comments.json")"
cp "$out/.context/review.json" "$out/.context/items/reviews-$review_id.json"
while IFS= read -r item; do
  id="$(jq -r '.id' <<<"$item")"
  printf '%s\n' "$item" > "$out/.context/items/inline-$id.json"
  if jq -e '.in_reply_to_id == null' <<<"$item" >/dev/null; then
    jq '{
      comment_id:.id,path,original_line:(.original_line // .line),side:(.side // "RIGHT"),
      start_line:(.original_start_line // .start_line),start_side,
      severity:(if (.body | contains("Priority-Critical")) then "Critical"
        elif (.body | contains("Priority-Important")) then "Important"
        elif (.body | contains("Priority-Suggestion")) then "Suggestion" else "Unknown" end),
      body,diff_hunk,html_url
    }' <<<"$item" > "$out/$id.json"
  fi
done < <(jq -c '.[]' "$out/.context/selected.json")
jq -n --arg owner "$owner" --arg repo "$repo" --argjson pr "$pr" --argjson rid "$review_id" \
  --argjson missing "$missing" --slurpfile selected "$out/.context/selected.json" '
  {owner:$owner,repo:$repo,pr:$pr,review_id:$rid,complete:($missing|length==0),missing_root_ids:$missing,
   records:([{key:("reviews:"+($rid|tostring)),kind:"reviews",id:$rid,body_file:("items/reviews-"+($rid|tostring)+".json")}] +
     [$selected[0][] | {key:("inline:"+(.id|tostring)),kind:"inline",id,review_id:.pull_request_review_id,
       root_comment_id:(.in_reply_to_id // .id),is_reply:(.in_reply_to_id != null),
       body_file:("items/inline-"+(.id|tostring)+".json")}])}
' > "$out/.context/inventory.json"
jq -e '.complete' "$out/.context/inventory.json" >/dev/null || { echo "error: selected root missing" >&2; exit 3; }
printf 'inventory=%s/.context/inventory.json\n' "$out"
