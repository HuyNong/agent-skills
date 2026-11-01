#!/usr/bin/env bash
# Post-submission step: inject direct links to inline comments into the review body.
#
# Usage:
#   link-findings-in-body.sh <owner> <repo> <pr> <review_id> <comments_dir>
#
# The review is already created when this helper runs. It never creates another
# review: a failed or partial link pass retains the review ID and unresolved
# findings so the same pass can be resumed after the API state is reconciled.
#
# Matching is deliberately strict. A local finding must match one posted
# comment by its complete body and complete path/side/range anchor. When the
# review-scoped endpoint omits anchor fields, the PR-wide comments endpoint is
# used to hydrate the same response IDs before matching.
#
# Exit codes:
#   0 — body updated, unchanged, or partially linked with unresolved findings
#   1 — missing args / gh not authenticated
#   2 — API or local-data failure
#   3 — API update failure
set -euo pipefail

owner="${1:?owner required}"
repo="${2:?repo required}"
pr="${3:?pr required}"
review_id="${4:?review_id required}"
comments_dir="${5:?comments_dir required}"
receipt_file="${6:-}"

echo "review_id=${review_id}"

if ! gh auth status >/dev/null 2>&1; then
  echo "error: gh not authenticated" >&2
  exit 1
fi

[[ -d "$comments_dir" ]] || {
  echo "error: comments_dir not found: $comments_dir" >&2
  exit 1
}
command -v jq >/dev/null || {
  echo "error: jq required" >&2
  exit 2
}

shopt -s nullglob
comment_files=("$comments_dir"/*.json)

# Keep the complete local body and anchor. Do not reduce the body to a prefix:
# two findings commonly share badges and opening explanation text.
local_comments='[]'
if (( ${#comment_files[@]} > 0 )); then
  if ! local_comments="$(
    for comment_file in "${comment_files[@]}"; do
      jq -c '.' -- "$comment_file"
    done | jq -s '
      map({
        body: (.body // ""),
        anchor: {
          path: (.path // ""),
          side: (.side // .original_side // "RIGHT"),
          line: (.line // .original_line // null),
          start_side: (.start_side // .original_start_side // .side // .original_side // "RIGHT"),
          start_line: (.start_line // .original_start_line // null)
        },
        # A local `id` can be a finding ID rather than a GitHub response ID;
        # only explicitly named response-id fields participate in matching.
        response_id: (.review_comment_id // .comment_id // .response_id // null)
      })'
  )"; then
    echo "error: failed to parse local comment JSON" >&2
    exit 2
  fi
fi

num_local="$(printf '%s' "$local_comments" | jq 'length')"
if [[ "$num_local" -eq 0 ]]; then
  echo "matched=0 unresolved=0 linked=0"
  exit 0
fi

review_comments_file="$(mktemp -t pr-review-comments.XXXXXX)"
pr_comments_file=""
review_body_file=""
trap 'rm -f "$review_comments_file" ${pr_comments_file:+"$pr_comments_file"} ${review_body_file:+"$review_body_file"}' EXIT

# Do not use --jq here. With --paginate, gh emits one JSON array per page;
# jq -s + flatten below normalizes the complete stream before it is passed to
# --argjson or further matching.
if ! gh api \
  "/repos/${owner}/${repo}/pulls/${pr}/reviews/${review_id}/comments" \
  --paginate >"$review_comments_file" 2>/dev/null; then
  echo "error: failed to fetch review comments for review_id=${review_id}" >&2
  exit 2
fi

if ! api_comments="$(jq -e -s 'if length > 0 and all(.[]; type == "array" and all(.[]; type == "object")) then add else error("invalid pages") end' "$review_comments_file")"; then
  echo "error: malformed paginated review comments for review_id=${review_id}" >&2
  exit 2
fi

# Review-scoped responses can omit line/side/range fields. Fetch the canonical
# PR-wide records only when needed, then merge by response ID. A multi-line
# local finding also requires this fallback when the review response omits its
# start range.
needs_pr_wide="$(jq -n --argjson local "$local_comments" --argjson api "$api_comments" '
  (any($api[]; (.line == null and .original_line == null) or
                   (.side == null and .original_side == null))) or
  ((any($local[]; .anchor.start_line != null)) and
   (any($api[]; .start_line == null and .original_start_line == null)))
')"

if [[ "$needs_pr_wide" == "true" ]]; then
  pr_comments_file="$(mktemp -t pr-pr-comments.XXXXXX)"
  if ! gh api \
    "/repos/${owner}/${repo}/pulls/${pr}/comments" \
    --paginate >"$pr_comments_file" 2>/dev/null; then
    echo "error: failed to fetch PR-wide comments for review_id=${review_id}" >&2
    exit 2
  fi

  if ! pr_comments="$(jq -e -s 'if length > 0 and all(.[]; type == "array" and all(.[]; type == "object")) then add else error("invalid pages") end' "$pr_comments_file")"; then
    echo "error: malformed paginated PR-wide comments for review_id=${review_id}" >&2
    exit 2
  fi

  if ! api_comments="$(jq -n --argjson review "$api_comments" --argjson wide "$pr_comments" '
    ($wide
      | map(select(.id != null) | {key: (.id | tostring), value: .})
      | from_entries) as $by_id
    | $review
    | map(
        . as $item
        | ($item.id // $item.comment_id // null) as $id
        | if $id == null or $by_id[($id | tostring)] == null
          then $item
          else ($item * $by_id[($id | tostring)])
          end
      )
  ')"; then
    echo "error: failed to hydrate review comments for review_id=${review_id}" >&2
    exit 2
  fi
fi

# Match each local finding to at most one API comment. A match requires the
# entire body and every anchor component. Ambiguous or missing matches remain
# unresolved; the old first-prefix behavior is intentionally forbidden.
match_result="$(jq -n --argjson local "$local_comments" --argjson api "$api_comments" '
  def response_id($value):
    ($value | (.review_comment_id // .comment_id // .response_id // .id // null))
    | if . == null then null else tostring end;
  def anchor($value):
    ($value | {
      path: (.path // ""),
      side: (.side // .original_side // "RIGHT"),
      line: (.line // .original_line // null),
      start_side: (.start_side // .original_start_side // .side // .original_side // "RIGHT"),
      start_line: (.start_line // .original_start_line // null)
    });
  def scalar_equal($left; $right): ($left | tostring) == ($right | tostring);
  def same_anchor($left; $right):
    ($left.path == $right.path) and
    ($left.side == $right.side) and
    scalar_equal($left.line; $right.line) and
    ($left.start_side == $right.start_side) and
    scalar_equal($left.start_line; $right.start_line);

  reduce ($local | to_entries[]) as $entry (
    {matched: [], unresolved: [], used: []};
    . as $state
    | ($entry.value) as $finding
    | ($finding.anchor) as $target
    | [
        $api
        | to_entries[]
        | . as $api_entry
        | select(($state.used | index($api_entry.key)) == null)
        | ($api_entry.value) as $comment
        | select(($finding.response_id == null) or
                 (response_id($comment) == ($finding.response_id | tostring)))
        | select(($comment.body // "") == ($finding.body // ""))
        | select(same_anchor(anchor($comment); $target))
        | select(($comment.html_url // $comment.url // "") != "")
      ] as $candidates
    | if ($candidates | length) == 1 then
        ($candidates[0]) as $candidate
        | .used += [$candidate.key]
        | .matched += [{
            local_index: $entry.key,
            path: $target.path,
            side: $target.side,
            line: $target.line,
            start_side: $target.start_side,
            start_line: $target.start_line,
            url: ($candidate.value.html_url // $candidate.value.url)
          }]
      else
        .unresolved += [{
          local_index: $entry.key,
          path: $target.path,
          side: $target.side,
          line: $target.line,
          start_side: $target.start_side,
          start_line: $target.start_line,
          reason: (if ($candidates | length) == 0 then "no exact match" else "ambiguous exact match" end)
        }]
      end
  )
')"

link_result="$(jq -n --argjson matches "$match_result" '
  def alias_keys($item):
    ($item.path | split("/")) as $parts
    | [range(1; ($parts | length) + 1) as $count
       | (($parts[(($parts | length) - $count):] | join("/")) + ":" + ($item.line | tostring))];

  ([
    $matches.matched[]
    | . as $item
    | alias_keys($item)[]
    | {key: ., record: $item.local_index, url: $item.url}
  ]) as $aliases
  | ($aliases
     | group_by(.key)
     | map(select(([.[] | .record] | unique | length) == 1)
           | {key: .[0].key, record: .[0].record, url: .[0].url})) as $unique
  | ([$unique[].record] | unique) as $linkable
  | {
      map: ($unique | reduce .[] as $item ({}; .[$item.key] = $item.url)),
      matched: ($matches.matched | length),
      unresolved: ($matches.unresolved + [$matches.matched[]
        | select(.local_index as $id | $linkable | index($id) == null)
        | . + {reason: "ambiguous summary alias; retain exact side/range and use explicit comment URLs"}]),
      aliases: ($unique | length)
    }
')"

link_map="$(printf '%s' "$link_result" | jq -c '.map')"
matched_count="$(printf '%s' "$link_result" | jq '.matched')"
unresolved_count="$(printf '%s' "$link_result" | jq '.unresolved | length')"
alias_count="$(printf '%s' "$link_result" | jq '.aliases')"

echo "matched=${matched_count} unresolved=${unresolved_count} aliases=${alias_count}"
if [[ "$unresolved_count" -gt 0 ]]; then
  printf '%s' "$link_result" | jq -r '.unresolved[] |
    "unresolved[\(.local_index)] \(.path):\(.line) side=\(.side)" +
    (if .start_line == null then "" else " range=\(.start_side):\(.start_line)-\(.line)" end) +
    " — \(.reason)"'
fi

# Nothing can be linked, so do not fetch or write the body. The review ID and
# unresolved ledger above are the resumable handoff; no second review is made.
if [[ "$alias_count" -eq 0 ]]; then
  echo "linked=0"
  exit 0
fi

review_body_file="$(mktemp -t pr-review-body.XXXXXX)"
if ! gh api "/repos/${owner}/${repo}/pulls/${pr}/reviews/${review_id}" \
  >"$review_body_file" 2>/dev/null; then
  echo "error: failed to fetch review body for review_id=${review_id}" >&2
  exit 2
fi

if ! current_body="$(jq -r '.body // ""' "$review_body_file")"; then
  echo "error: malformed review body for review_id=${review_id}" >&2
  exit 2
fi

# Scan literal backtick-delimited code spans instead of interpolating finding
# paths into a regular expression. This handles `[`, `+`, Unicode and other
# regex metacharacters. Existing markdown links are recognized by their
# surrounding `[` and `](` and are left unchanged, making a second invocation
# a no-op rather than a nested rewrite.
replacement="$(jq -n --arg body "$current_body" --argjson links "$link_map" '
  def link_body($text; $map):
    ($text | split("`")) as $parts
    | reduce range(0; ($parts | length)) as $i
        ({body: "", linked: 0};
         if (($i % 2) == 0) then
           .body += $parts[$i]
         elif $i == (($parts | length) - 1) then
           .body += ("`" + $parts[$i])
         else
           ($parts[$i]) as $code
           | (($parts[$i - 1] | endswith("[")) and
              ($parts[$i + 1] | startswith("]("))) as $already_linked
           | if ($map | has($code)) and ($already_linked | not) then
               (.body += ("[`" + $code + "`](" + $map[$code] + ")"))
               | .linked += 1
             else
               .body += ("`" + $code + "`")
             end
        end);
  link_body($body; $links)
')"
patched_body="$(printf '%s' "$replacement" | jq -r '.body')"
linked_count="$(printf '%s' "$replacement" | jq '.linked')"

if [[ "$patched_body" == "$current_body" && -z "$receipt_file" ]]; then
  echo "linked=0 (body unchanged)"
  exit 0
fi

if [[ -n "$receipt_file" ]]; then
  payload_file="$(mktemp "${TMPDIR:-/tmp}/pr-linked-body.XXXXXX")"
  jq -n --arg body "$patched_body" '{body:$body}' > "$payload_file"
  source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/review-receipt.sh"
  if receipt_post "$receipt_file" publish "$owner" "$repo" "$pr" "review-$review_id-links" "/repos/$owner/$repo/pulls/$pr/reviews/$review_id" "$payload_file" "" PUT; then
    rm -f -- "$payload_file"
    echo "linked=$linked_count review_id=$review_id body updated or reconciled"
    exit 0
  else
    status=$?; rm -f -- "$payload_file"; exit "$status"
  fi
fi

if ! gh api "/repos/${owner}/${repo}/pulls/${pr}/reviews/${review_id}" \
  -X PUT \
  --field body="$patched_body" \
  --jq '.html_url' >/dev/null 2>&1; then
  echo "error: failed to update review body for review_id=${review_id}" >&2
  exit 3
fi

echo "linked=${linked_count} review_id=${review_id} body updated"
