#!/usr/bin/env bash
# Preflight: verify every comment's anchor line falls inside a diff hunk on
# the target PR. Without this, the GitHub API rejects the whole review with
# HTTP 422 "Line could not be resolved" — and there's no built-in way to tell
# which comment is the offender.
#
# Usage:
#   validate-anchors.sh <pr> <comments_dir>
#   validate-anchors.sh <pr> <comments_dir> <owner> <repo>
#
# Arguments:
#   pr             — pull request number
#   comments_dir   — directory of per-finding JSON files (same format as
#                    build-review-payload.sh expects)
#   owner, repo    — optional; inferred from current repo via `gh` if omitted
#
# Behavior:
#   - Fetch the canonical per-file patches via `gh api /repos/{o}/{r}/pulls/{n}/files`
#     (this is the raw unified-diff source GitHub itself uses for line
#     resolution; it is NOT affected by local `gh pr diff` output rewriters).
#   - For each *.json in comments_dir: read `path`, `line`, optional
#     `start_line`, `side` (default RIGHT), `start_side` (default same as side).
#   - For each comment, look up the file's patch, extract hunk ranges from
#     `@@ -A,B +C,D @@` headers, and verify the anchor lines fall inside.
#   - Multi-line: enforce `start_side == side` (GitHub 422s when they differ).
#   - Print a report and exit non-zero if any anchors are out of range.
set -euo pipefail

pr="${1:?pr number required}"
comments_dir="${2:?comments_dir required}"
owner="${3:-}"
repo="${4:-}"

[[ -d "$comments_dir" ]] || { echo "error: comments_dir not a directory: $comments_dir" >&2; exit 2; }
command -v jq >/dev/null || { echo "error: jq required" >&2; exit 2; }
command -v gh >/dev/null || { echo "error: gh required" >&2; exit 2; }

# Infer owner/repo from current git remote if not provided.
if [[ -z "$owner" || -z "$repo" ]]; then
  if ! repo_meta="$(gh repo view --json owner,name 2>/dev/null)"; then
    echo "error: cannot infer owner/repo — pass them explicitly: validate-anchors.sh <pr> <dir> <owner> <repo>" >&2
    exit 2
  fi
  owner="$(jq -r '.owner.login' <<<"$repo_meta")"
  repo="$(jq -r '.name' <<<"$repo_meta")"
fi

# Pull every file's patch in one paginated call. Result schema per file:
#   { "filename": "...", "patch": "@@ -A,B +C,D @@\n ... \n@@ ..." }
files_json="$(mktemp "${TMPDIR:-/tmp}/pr-files.XXXXXX")"
trap 'rm -f "$files_json"' EXIT

if ! gh api --paginate "/repos/${owner}/${repo}/pulls/${pr}/files" >"$files_json" 2>/dev/null; then
  echo "error: gh api /repos/${owner}/${repo}/pulls/${pr}/files failed" >&2
  exit 3
fi

# Slurp all pages before looking up the patch, producing one result per path.
patch_for_path() {
  local p="$1"
  jq -rs --arg p "$p" '
    flatten
    | map(select(.filename == $p))
    | .[0].patch // empty
  ' "$files_json" 2>/dev/null
}

# extract_ranges <patch_text> <side>
# Emits "<start>:<end>" pairs (inclusive) for each hunk on the requested side.
extract_ranges() {
  local patch="$1"
  local side="$2"
  if [[ -z "$patch" ]]; then return 0; fi
  if [[ "$side" == "RIGHT" ]]; then
    printf '%s\n' "$patch" \
      | grep -E '^@@ ' \
      | sed -nE 's/^@@ -[0-9]+(,[0-9]+)? \+([0-9]+)(,([0-9]+))? @@.*/\2 \4/p' \
      | awk '{ start=$1; len=($2==""?1:$2); if (len==0) next; printf "%d:%d\n", start, start+len-1 }'
  else
    printf '%s\n' "$patch" \
      | grep -E '^@@ ' \
      | sed -nE 's/^@@ -([0-9]+)(,([0-9]+))? \+[0-9]+(,[0-9]+)? @@.*/\1 \3/p' \
      | awk '{ start=$1; len=($2==""?1:$2); if (len==0) next; printf "%d:%d\n", start, start+len-1 }'
  fi
}

in_range() {
  local n="$1"; shift
  local r
  for r in "$@"; do
    local lo="${r%%:*}"
    local hi="${r##*:}"
    (( n >= lo && n <= hi )) && return 0
  done
  return 1
}

total=0
bad=0
declare -a bad_reports=()

shopt -s nullglob
for json in "$comments_dir"/*.json; do
  total=$((total + 1))
  name="$(basename "$json")"

  path="$(jq -r '.path // empty' "$json")"
  line="$(jq -r '.line // empty' "$json")"
  side="$(jq -r '.side // "RIGHT"' "$json")"
  start_line="$(jq -r '.start_line // empty' "$json")"
  start_side="$(jq -r '.start_side // empty' "$json")"

  if [[ -z "$path" || -z "$line" ]]; then
    bad=$((bad + 1))
    bad_reports+=("$name: missing required field path or line")
    continue
  fi

  if [[ ! "$line" =~ ^[1-9][0-9]*$ ]] ||
     [[ -n "$start_line" && ! "$start_line" =~ ^[1-9][0-9]*$ ]] ||
     [[ "$side" != LEFT && "$side" != RIGHT ]]; then
    bad=$((bad + 1))
    bad_reports+=("$name: line/start_line must be positive integers and side must be LEFT or RIGHT")
    continue
  fi

  if [[ -n "$start_line" && -z "$start_side" ]]; then
    start_side="$side"
  fi
  if [[ -n "$start_line" && "$start_side" != "$side" ]]; then
    bad=$((bad + 1))
    bad_reports+=("$name [$path L$start_line-$line]: start_side ($start_side) != side ($side) — GitHub will 422")
    continue
  fi

  patch="$(patch_for_path "$path")"
  if [[ -z "$patch" ]]; then
    bad=$((bad + 1))
    bad_reports+=("$name [$path L$line]: file not in PR diff (renamed? wrong path?)")
    continue
  fi

  ranges=()
  while IFS= read -r range; do
    ranges+=("$range")
  done < <(extract_ranges "$patch" "$side")
  if (( ${#ranges[@]} == 0 )); then
    bad=$((bad + 1))
    bad_reports+=("$name [$path L$line side=$side]: no hunks on this side")
    continue
  fi

  if ! in_range "$line" "${ranges[@]}"; then
    bad=$((bad + 1))
    bad_reports+=("$name [$path L$line side=$side]: line outside hunks [$(IFS=,; echo "${ranges[*]}")]")
    continue
  fi
  if [[ -n "$start_line" ]]; then
    same_hunk=0
    for range in "${ranges[@]}"; do
      if (( start_line <= line && start_line >= ${range%%:*} && line <= ${range##*:} )); then
        same_hunk=1
        break
      fi
    done
    if (( same_hunk == 0 )); then
      bad=$((bad + 1))
      bad_reports+=("$name [$path L$start_line-$line]: range must fit within one hunk")
    fi
  fi
done

echo "validated $total comment(s): $((total - bad)) ok, $bad out-of-range"
if (( bad > 0 )); then
  echo "" >&2
  echo "out-of-range anchors:" >&2
  for r in "${bad_reports[@]}"; do
    echo "  - $r" >&2
  done
  echo "" >&2
  echo "fix: re-anchor each flagged comment to a line inside a diff hunk," >&2
  echo "      or move it to the top-level body's 'General notes' section." >&2
  exit 1
fi
