#!/usr/bin/env bash
# Single RIGHT-side inline post. Optional receipt and item key enable recovery.
set -euo pipefail
owner="${1:?owner required}"; repo="${2:?repo required}"; pr="${3:?pr required}"
commit_sha="${4:?commit SHA required}"; path="${5:?path required}"
line="${6:?line required}"; body_file="${7:?body file required}"
receipt_file="${8:-}"; item_key="${9:-inline}"
[[ "$commit_sha" =~ ^[a-fA-F0-9]{40}$ && "$line" =~ ^[1-9][0-9]*$ ]] || {
  echo "error: full hexadecimal SHA and positive line required" >&2; exit 2;
}
[[ -r "$body_file" && -s "$body_file" ]] || { echo "error: readable nonempty body required" >&2; exit 2; }
bash "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/validate-reply-body.sh" "$body_file" "${10:-}" "${11:-}"
command -v jq >/dev/null || { echo "error: jq required" >&2; exit 2; }
gh auth status >/dev/null 2>&1 || { echo "error: run gh auth login" >&2; exit 1; }
endpoint="/repos/$owner/$repo/pulls/$pr"
meta="$(gh api "$endpoint")" || { echo "error: PR metadata unavailable; membership unknown" >&2; exit 3; }
head="$(jq -er '.head.sha | select(type == "string" and test("^[a-fA-F0-9]{40}$"))' <<<"$meta")" || exit 3
base="$(jq -r '.base.sha // empty' <<<"$meta")"
member=false
if [[ "$commit_sha" == "$head" ]]; then
  member=true
elif [[ "$base" =~ ^[a-fA-F0-9]{40}$ ]] &&
    git cat-file -e "$head^{commit}" 2>/dev/null && git cat-file -e "$base^{commit}" 2>/dev/null &&
    git merge-base --is-ancestor "$commit_sha" "$head" 2>/dev/null &&
    ! git merge-base --is-ancestor "$commit_sha" "$base" 2>/dev/null; then
  member=true
else
  count="$(jq -r '.commits // 251' <<<"$meta")"
  if [[ "$count" =~ ^[0-9]+$ ]] && (( count <= 250 )); then
    pages="$(gh api --paginate "$endpoint/commits")" || {
      echo "error: commit collection failed; membership unknown" >&2; exit 3;
    }
    if jq -e -s --arg sha "$commit_sha" --argjson count "$count" '
      length > 0 and all(.[]; type == "array") and
      ((add | length) == $count) and any(add[]; .sha == $sha)
    ' <<<"$pages" >/dev/null; then member=true; fi
  fi
fi
[[ "$member" == true ]] || {
  echo "error: historical membership is absent or indeterminate; use the verified PR head. This does not establish a need to push." >&2
  exit 4
}
current="$(gh api "$endpoint" --jq '.head.sha')" || exit 3
[[ "$current" == "$head" ]] || { echo "error: PR head changed; re-evaluate the approved anchor" >&2; exit 5; }
payload="$(mktemp "${TMPDIR:-/tmp}/pr-inline.XXXXXX")"
trap 'rm -f -- "$payload"' EXIT
jq -n --arg commit_id "$commit_sha" --arg path "$path" --argjson line "$line" --rawfile body "$body_file" \
  '{commit_id:$commit_id,path:$path,line:$line,side:"RIGHT",body:$body}' > "$payload"
if [[ -n "$receipt_file" ]]; then
  source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/review-receipt.sh"
  receipt_post "$receipt_file" respond "$owner" "$repo" "$pr" "$item_key" "$endpoint/comments" "$payload" "$head"
else
  html_url="$(gh api --method POST "$endpoint/comments" --input "$payload" --jq '.html_url')" || exit 4
  [[ -n "$html_url" && "$html_url" != null ]] || { echo "error: submission outcome unknown; inspect existing comments before retry" >&2; exit 3; }
  printf 'html_url=%s\n' "$html_url"
fi
