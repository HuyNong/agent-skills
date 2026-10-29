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

# Slurp comment files into a JSON array, sorted by filename for stable order.
comments_json="$(
  find "$comments_dir" -maxdepth 1 -type f -name '*.json' -print0 \
    | xargs -0 -I{} cat {} \
    | jq -s '.' 2>/dev/null \
    || echo '[]'
)"

# Validate each comment has the required fields.
errors="$(printf '%s' "$comments_json" | jq -r '
  to_entries | map(
    . as $e
    | (.value | if (has("path") and has("body") and has("line")) then empty
        else "comment[" + ($e.key|tostring) + "] missing path/line/body" end)
  ) | .[]
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
