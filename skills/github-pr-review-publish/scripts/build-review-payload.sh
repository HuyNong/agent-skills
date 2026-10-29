#!/usr/bin/env bash
# Assemble a GitHub PR review payload from a top-level body file + a comments
# directory (one .json file per inline comment).
#
# Usage:
#   build-review-payload.sh <head_sha> <body_file> <comments_dir> [event] > payload.json
#
# Arguments:
#   head_sha      — the commit SHA to anchor comments to (PR HEAD)
#   body_file     — file containing the top-level review summary markdown
#   comments_dir  — directory of per-finding JSON files (see schema below)
#   event         — COMMENT (default) | REQUEST_CHANGES | APPROVE
#
# Each file in comments_dir must be a JSON object like:
#   {
#     "path": "src/foo.ts",
#     "line": 42,
#     "side": "RIGHT",
#     "body": "![important](...)\n\nProblem...\n\n```suggestion\nfixed\n```"
#   }
# or for multi-line:
#   {
#     "path": "src/foo.ts",
#     "start_line": 38,
#     "start_side": "RIGHT",
#     "line": 42,
#     "side": "RIGHT",
#     "body": "..."
#   }
set -euo pipefail

head_sha="${1:?head_sha required}"
body_file="${2:?body_file required}"
comments_dir="${3:?comments_dir required}"
event="${4:-COMMENT}"

[[ -r "$body_file" ]] || { echo "error: body_file not readable: $body_file" >&2; exit 2; }
[[ -d "$comments_dir" ]] || { echo "error: comments_dir not a directory: $comments_dir" >&2; exit 2; }

case "$event" in
  COMMENT|REQUEST_CHANGES|APPROVE) ;;
  *) echo "error: invalid event: $event" >&2; exit 2 ;;
esac

# Expand filenames without losing spaces; an empty directory is a valid summary.
command -v jq >/dev/null || { echo "error: jq required" >&2; exit 2; }
shopt -s nullglob
comment_files=("$comments_dir"/*.json)
comments_json='[]'
if (( ${#comment_files[@]} > 0 )); then
  if ! comments_json="$(
    for comment_file in "${comment_files[@]}"; do
      jq -es 'if length == 1 then .[0] else error("expected one JSON object per file") end' \
        -- "$comment_file" || exit 3
    done | jq -s '.'
  )"; then
    echo "error: cannot parse comment files; no payload produced" >&2
    exit 3
  fi
fi

# Validate each comment has the required fields.
errors="$(printf '%s' "$comments_json" | jq -r '
  def positive_integer: type == "number" and . >= 1 and floor == .;
  def valid_comment:
    if type != "object" then false else
      (.path | type == "string" and length > 0) and
      (.body | type == "string" and length > 0) and
      (.line | positive_integer) and
      ((.side // "RIGHT") | . == "LEFT" or . == "RIGHT") and
      (if has("start_line") then
        (.start_line | positive_integer) and (.start_line <= .line) and
        ((.start_side // .side // "RIGHT") == (.side // "RIGHT"))
       else true end)
    end;
  to_entries | .[] | select(.value | valid_comment | not)
  | "comment[\(.key)] has invalid path/body/line/side fields"
')"
if [[ -n "$errors" ]]; then
  printf '%s\n' "$errors" >&2
  exit 3
fi

jq -n \
  --arg commit_id "$head_sha" \
  --arg event "$event" \
  --rawfile body "$body_file" \
  --argjson comments "$comments_json" \
  '{
    commit_id: $commit_id,
    event: $event,
    body: $body,
    comments: $comments
  }'
