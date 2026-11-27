#!/usr/bin/env bash
# Resolve an original thread only after a receipt-backed reply and PR fix verification.
# Usage: resolve-thread.sh owner repo pr root_id receipt reply_key fixed-on-pr --resolve-authorized
# The caller verifies all thread concerns and user authority; flags are not evidence.
set -euo pipefail
umask 077
owner="${1:?owner required}"; repo="${2:?repo required}"; pr="${3:?PR required}"
root="${4:?root comment required}"; receipt="${5:?receipt required}"; key="${6:?reply key required}"
[[ "${7:-}" == fixed-on-pr && "${8:-}" == --resolve-authorized ]] || {
  echo "error: explicit resolve authority and fixed-on-pr verification required" >&2; exit 2;
}
[[ "$owner" =~ ^[A-Za-z0-9][A-Za-z0-9-]*$ && "$repo" =~ ^[A-Za-z0-9_.-]+$ &&
   "$pr" =~ ^[1-9][0-9]*$ && "$root" =~ ^[1-9][0-9]*$ &&
   "$key" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ && -f "$receipt" && ! -L "$receipt" ]] || exit 2
lock="$receipt.lock"; temporary=""
mkdir "$lock" 2>/dev/null || { echo "error: receipt locked" >&2; exit 7; }
printf '%s\n' "$$:resolve" > "$lock/owner"
trap 'rm -f -- "$temporary" "$lock/owner"; rmdir "$lock"' EXIT
trap 'exit 130' INT TERM
endpoint="/repos/$owner/$repo/pulls/$pr/comments/$root/replies"
jq -e --arg key "$key" --arg endpoint "$endpoint" '
  .schema == 1 and .items[$key].state == "posted" and
  .items[$key].binding.endpoint == $endpoint and .items[$key].binding.method == "POST" and
  (.items[$key].result.id | type == "number" and . > 0)
' "$receipt" >/dev/null || { echo "error: original-thread reply must be confirmed posted" >&2; exit 2; }
login="$(gh api /user --jq '.login')" || exit 3
meta="$(gh api "/repos/$owner/$repo/pulls/$pr")" || exit 3
jq -e --arg login "$login" --arg owner "$owner" --arg repo "$repo" --argjson pr "$pr" \
  --argjson meta "$meta" '
  .context == {workflow:"respond",login:$login,owner:$owner,repo:$repo,pr:$pr} and
  (.validated_snapshot.head_sha | test("^[a-fA-F0-9]{40}$")) and
  .validated_snapshot == {head_sha:$meta.head.sha,base_sha:$meta.base.sha}
' "$receipt" >/dev/null || { echo "error: identity/repository/snapshot drift; re-evaluate" >&2; exit 5; }
reply_id="$(jq -r --arg key "$key" '.items[$key].result.id' "$receipt")"
reply="$(gh api "/repos/$owner/$repo/pulls/comments/$reply_id")" || exit 3
jq -e --arg login "$login" --argjson root "$root" --argjson id "$reply_id" '
  .id == $id and .user.login == $login and .in_reply_to_id == $root and (.body | type == "string")
' <<<"$reply" >/dev/null || { echo "error: posted reply target/author mismatch" >&2; exit 5; }
body_hash="$(jq -Sc '{body}' <<<"$reply" | git hash-object --stdin)"
jq -e --arg key "$key" --arg hash "$body_hash" '.items[$key].binding.payload_hash == $hash' \
  "$receipt" >/dev/null || { echo "error: posted reply body changed" >&2; exit 5; }

# Only the outer connection is paginated; first comment identifies the original root.
query='query($owner:String!,$repo:String!,$pr:Int!,$endCursor:String) {
  repository(owner:$owner,name:$repo) { pullRequest(number:$pr) {
    headRefOid baseRefOid reviewThreads(first:100,after:$endCursor) {
      pageInfo { hasNextPage endCursor }
      nodes { id isResolved viewerCanResolve comments(first:1) { nodes { databaseId } } }
    }
  } }
}'
pages="$(gh api graphql --method POST --paginate -f query="$query" -f owner="$owner" -f repo="$repo" -F pr="$pr")" || exit 3
threads="$(jq -ces --slurpfile receipt "$receipt" '
  if length == 0 or any(.[];
    ((.errors // []) | length > 0) or
    .data.repository.pullRequest.headRefOid != $receipt[0].validated_snapshot.head_sha or
    .data.repository.pullRequest.baseRefOid != $receipt[0].validated_snapshot.base_sha or
    (.data.repository.pullRequest.reviewThreads.nodes | type != "array")) or
    .[-1].data.repository.pullRequest.reviewThreads.pageInfo.hasNextPage != false
  then error("incomplete thread data or snapshot drift")
  else [.[].data.repository.pullRequest.reviewThreads.nodes[]] end
' <<<"$pages")" || exit 3
thread="$(jq -ce --argjson root "$root" '
  [.[] | select(.comments.nodes[0].databaseId == $root)] |
  if length == 1 then .[0] else error("original thread missing or ambiguous") end |
  select((.id | type == "string" and length > 0) and (.isResolved | type == "boolean"))
' <<<"$threads")" || exit 3
thread_id="$(jq -r '.id' <<<"$thread")"
previous="$(jq -r --arg key "$key" '.resolutions[$key].state // "prepared"' "$receipt")"
jq -e --arg key "$key" --arg id "$thread_id" '
  .resolutions[$key] == null or .resolutions[$key].thread_id == $id
' "$receipt" >/dev/null || exit 5
save_resolution() {
  temporary="$(mktemp "$receipt.tmp.XXXXXX")"
  jq --arg key "$key" --arg id "$thread_id" --arg state "$1" \
    '.resolutions[$key]={thread_id:$id,state:$state}' "$receipt" > "$temporary"
  mv -- "$temporary" "$receipt"; temporary=""
}
if [[ "$(jq -r '.isResolved' <<<"$thread")" == true ]]; then
  save_resolution resolved
  printf 'thread_id=%s\nresolution=resolved\n' "$thread_id"; exit 0
fi
[[ "$previous" == prepared ]] || {
  echo "error: unresolved after prior resolution attempt; inspect remote state before any retry" >&2; exit 6;
}
[[ "$(jq -r '.viewerCanResolve' <<<"$thread")" == true ]] || {
  echo "error: current account cannot resolve this thread" >&2; exit 4;
}
# Persist uncertainty before the write; resume reads remote state without replaying it.
save_resolution unknown
mutation='mutation($thread:ID!) { resolveReviewThread(input:{threadId:$thread}) { thread { id isResolved } } }'
if ! result="$(gh api graphql --method POST -f query="$mutation" -f thread="$thread_id")"; then
  echo "error: resolution outcome unknown; keep receipt and reconcile read-only" >&2; exit 6
fi
jq -e --arg id "$thread_id" '
  ((.errors // []) | length == 0) and
  .data.resolveReviewThread.thread.id == $id and .data.resolveReviewThread.thread.isResolved == true
' <<<"$result" >/dev/null || {
  echo "error: resolution not confirmed; keep receipt and reconcile read-only" >&2; exit 6;
}
save_resolution resolved
printf 'thread_id=%s\nresolution=resolved\n' "$thread_id"
