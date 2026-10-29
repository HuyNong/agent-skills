#!/usr/bin/env bash
# List commits added to a PR after a given anchor SHA (typically the
# commit_id of the prior review). Used to decide whether there's anything
# new to verify — if zero commits, the skill should exit without posting.
#
# Usage:
#   list-followup-commits.sh <pr> <since_sha> [<owner> <repo>]
#
# Output: tab-separated `<sha>\t<subject>\t<author>` per follow-up commit,
# oldest-first. Exit code is 0 even if zero commits were found; caller
# distinguishes via the line count.
set -euo pipefail

pr="${1:?pr number required}"
since_sha="${2:?since_sha required}"
owner="${3:-}"
repo="${4:-}"

command -v gh >/dev/null || { echo "error: gh required" >&2; exit 2; }
command -v jq >/dev/null || { echo "error: jq required" >&2; exit 2; }

if [[ -z "$owner" || -z "$repo" ]]; then
  meta="$(gh repo view --json owner,name 2>/dev/null)" || {
    echo "error: cannot infer owner/repo — pass them explicitly" >&2; exit 2;
  }
  owner="$(jq -r '.owner.login' <<<"$meta")"
  repo="$(jq -r '.name' <<<"$meta")"
fi

commits_json="$(gh api --paginate "/repos/${owner}/${repo}/pulls/${pr}/commits" 2>/dev/null)" || {
  echo "error: gh api /pulls/${pr}/commits failed" >&2
  exit 1
}

# Walk commits in order; emit those that come strictly AFTER since_sha.
printf '%s' "$commits_json" | jq -r -s --arg since "$since_sha" '
  flatten
  | (map(.sha) | index($since)) as $idx
  | if $idx == null then
      # since_sha isn'\''t in the current PR commit list — assume all commits
      # are follow-ups (defensive: anchor commit was rebased away).
      .
    else
      .[($idx+1):]
    end
  | .[]
  | [.sha, (.commit.message | split("\n")[0]), (.commit.author.name // "?")]
  | @tsv
'
