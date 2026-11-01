#!/usr/bin/env bash
# Post verdict comments as replies to original finding threads.
# Usage: post-thread-replies.sh <owner> <repo> <pr> <verdicts_dir>
#
# Each JSON file in <verdicts_dir> must have:
#   - in_reply_to  (integer — original comment ID)
#   - body         (string — verdict markdown)
#
# Outputs: one line per verdict: "ok <comment_id> <reply_id>" or "fail <comment_id> <reason>"
# Exit 0 if all succeeded, exit 1 if any failed.

set -euo pipefail

owner="${1:?owner required}"
repo="${2:?repo required}"
pr="${3:?pr number required}"
verdicts_dir="${4:?verdicts directory required}"

command -v gh >/dev/null || { echo "error: gh required" >&2; exit 2; }
command -v jq >/dev/null || { echo "error: jq required" >&2; exit 2; }

if [ ! -d "$verdicts_dir" ]; then
  echo "error: verdicts directory not found: $verdicts_dir" >&2
  exit 2
fi

files=("$verdicts_dir"/*.json)
if [ ${#files[@]} -eq 0 ] || [ ! -f "${files[0]}" ]; then
  echo "error: no JSON files in $verdicts_dir" >&2
  exit 2
fi

ok=0
fail=0

for f in "${files[@]}"; do
  if ! jq -e 'type == "object" and
      (.in_reply_to | type == "number" and . > 0 and floor == .) and
      (.body | type == "string" and length > 0)' "$f" >/dev/null 2>&1; then
    echo "fail ? invalid_fields_in_$(basename "$f")"
    fail=$((fail + 1))
    continue
  fi
  comment_id=$(jq -r '.in_reply_to' "$f")

  tmpfile=$(mktemp)
  jq '{body, in_reply_to}' "$f" > "$tmpfile"

  http_code=$(gh api \
    "repos/${owner}/${repo}/pulls/${pr}/comments" \
    --method POST \
    --input "$tmpfile" \
    --jq '.id' 2>"${tmpfile}.err") && rc=0 || rc=$?

  rm -f "$tmpfile"

  if [ $rc -eq 0 ] && [ -n "$http_code" ]; then
    echo "ok $comment_id $http_code"
    ok=$((ok + 1))
  else
    reason=$(cat "${tmpfile}.err" 2>/dev/null | head -1 || echo "unknown")
    echo "fail $comment_id $reason"
    fail=$((fail + 1))
  fi
  rm -f "${tmpfile}.err"
done

echo "---"
echo "total=$((ok + fail)) ok=$ok fail=$fail"

if [ $fail -gt 0 ]; then
  exit 1
fi
exit 0
