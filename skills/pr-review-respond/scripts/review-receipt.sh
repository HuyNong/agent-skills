#!/usr/bin/env bash
# Package-local delivery state. This library records execution, not authorization.
# receipt_post receipt workflow owner repo pr item endpoint payload [head] [method]
receipt_post() (
  set -euo pipefail
  umask 077
  rrfile="${1:?receipt}"; rrworkflow="${2:?workflow}"; rrowner="${3:?owner}"
  rrrepo="${4:?repo}"; rrpr="${5:?pr}"; rrkey="${6:?item}"
  rrendpoint="${7:?endpoint}"; rrpayload="${8:?payload}"
  rrexpected="${9:-}"; rrmethod="${10:-POST}"
  [[ "$rrkey" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ && "$rrpr" =~ ^[1-9][0-9]*$ &&
     "$rrowner" =~ ^[A-Za-z0-9][A-Za-z0-9-]*$ && "$rrrepo" =~ ^[A-Za-z0-9_.-]+$ &&
     "$rrendpoint" == "/repos/$rrowner/$rrrepo/"* ]] || exit 2
  [[ "$rrmethod" == POST || "$rrmethod" == PUT ]] || exit 2
  [[ ! -L "$rrfile" && -d "$(dirname "$rrfile")" ]] || { echo "error: receipt needs an owned regular path" >&2; exit 2; }
  jq -e 'type == "object" and (.body | type == "string" and length > 0)' "$rrpayload" >/dev/null || exit 2
  rrlock="$rrfile.lock"; rrtmp=""; rrresponse=""; rrerror=""
  mkdir "$rrlock" 2>/dev/null || { echo "error: receipt locked; inspect its owner before recovery" >&2; exit 7; }
  rrtoken="$$:$RANDOM"; printf '%s\n' "$rrtoken" > "$rrlock/owner"
  trap 'rm -f -- "${rrtmp:-}" "${rrresponse:-}" "${rrerror:-}"; if [[ -f "$rrlock/owner" && "$(cat "$rrlock/owner")" == "$rrtoken" ]]; then rm -f -- "$rrlock/owner"; rmdir "$rrlock"; fi' EXIT
  trap 'exit 130' INT TERM
  rrlogin="$(gh api /user --jq '.login')" || exit 3
  [[ -n "$rrlogin" && "$rrlogin" != null ]] || exit 3
  rrmeta="$(gh api "/repos/$rrowner/$rrrepo/pulls/$rrpr")" || exit 3
  rrhead="$(jq -er '.head.sha | select(test("^[a-fA-F0-9]{40}$"))' <<<"$rrmeta")" || exit 3
  rrbase="$(jq -r '.base.sha // ""' <<<"$rrmeta")"
  [[ -z "$rrexpected" || "$rrexpected" == "$rrhead" ]] || { echo "error: head drift; re-evaluate before posting" >&2; exit 5; }
  rrcontext="$(jq -cn --arg workflow "$rrworkflow" --arg login "$rrlogin" --arg owner "$rrowner" --arg repo "$rrrepo" --argjson pr "$rrpr" '{workflow:$workflow,login:$login,owner:$owner,repo:$repo,pr:$pr}')"
  rrsnapshot="$(jq -cn --arg head "$rrhead" --arg base "$rrbase" '{head_sha:$head,base_sha:$base}')"
  rrhash="$(jq -Sc . "$rrpayload" | git hash-object --stdin)" || exit 2
  if [[ ! -e "$rrfile" ]]; then
    rrtmp="$(mktemp "$rrfile.tmp.XXXXXX")"
    printf '%s\n' '{"schema":1,"sources":[],"items":{}}' > "$rrtmp"
    mv -- "$rrtmp" "$rrfile"; rrtmp=""
  fi
  jq -e '.schema == 1 and (.sources | type == "array") and (.items | type == "object")' "$rrfile" >/dev/null || exit 2
  rrstored="$(jq -c '.context // null' "$rrfile")"
  if [[ "$rrstored" == null ]]; then
    jq -e '.items | length == 0' "$rrfile" >/dev/null || exit 2
    jq -e --argjson snapshot "$rrsnapshot" '(.validated_snapshot // $snapshot) == $snapshot' "$rrfile" >/dev/null || {
      echo "error: evaluated snapshot changed before first write" >&2; exit 5;
    }
    rrtmp="$(mktemp "$rrfile.tmp.XXXXXX")"
    jq --argjson context "$rrcontext" --argjson snapshot "$rrsnapshot" \
      '.context=$context | .approved_snapshot=(.approved_snapshot // $snapshot) | .validated_snapshot=$snapshot' "$rrfile" > "$rrtmp"
    mv -- "$rrtmp" "$rrfile"; rrtmp=""
  else
    jq -e --argjson context "$rrcontext" --argjson snapshot "$rrsnapshot" \
      '.context == $context and .validated_snapshot == $snapshot' "$rrfile" >/dev/null || {
      echo "error: receipt identity/repository/snapshot mismatch; retain it and revalidate" >&2; exit 5;
    }
  fi
  rrbinding="$(jq -cn --arg endpoint "$rrendpoint" --arg method "$rrmethod" --arg hash "$rrhash" \
    --slurpfile receipt "$rrfile" '{endpoint:$endpoint,method:$method,payload_hash:$hash,sources:$receipt[0].sources}')"
  rrstate="$(jq -r --arg key "$rrkey" '.items[$key].state // "prepared"' "$rrfile")"
  rrprevious="$(jq -c --arg key "$rrkey" '.items[$key].binding // null' "$rrfile")"
  if [[ "$rrprevious" != null ]]; then
    jq -e --argjson binding "$rrbinding" --arg key "$rrkey" '.items[$key].binding == $binding' "$rrfile" >/dev/null || {
      echo "error: approved body/target/source changed; preserve this item and preview a new one" >&2; exit 5;
    }
  fi
  rr_save() {
    local state="$1" result="${2:-null}"
    rrtmp="$(mktemp "$rrfile.tmp.XXXXXX")"
    jq --arg key "$rrkey" --arg state "$state" --argjson binding "$rrbinding" --argjson result "$result" \
      '.items[$key]={binding:$binding,state:$state,result:$result}' "$rrfile" > "$rrtmp" || return 2
    jq -e . "$rrtmp" >/dev/null || return 2
    mv -- "$rrtmp" "$rrfile"; rrtmp=""
  }
  rr_emit() { jq -r '"reply_id=\(.id)\nhtml_url=\(.html_url)"' <<<"$1"; }
  if [[ "$rrstate" == posted ]]; then
    rr_emit "$(jq -c --arg key "$rrkey" '.items[$key].result' "$rrfile")"; exit 0
  fi
  case "$rrstate" in prepared|posting|failed|unknown) ;; *) echo "error: invalid receipt state" >&2; exit 2;; esac
  # Read-back runs before a new write too, covering receipts lost between sessions.
  rrlookup="$rrendpoint"; rrroot=""
  if [[ "$rrendpoint" == */replies ]]; then
    rrroot="${rrendpoint%/replies}"; rrroot="${rrroot##*/}"
    rrlookup="/repos/$rrowner/$rrrepo/pulls/$rrpr/comments"
  fi
  rrremote="$(gh api --paginate "$rrlookup")" || { echo "error: cannot reconcile existing writes" >&2; exit 3; }
  if [[ "$rrmethod" == PUT ]]; then
    jq -e -s 'length == 1 and (.[0] | type == "object" and (.id | type == "number"))' <<<"$rrremote" >/dev/null || exit 3
  else
    jq -e -s 'length > 0 and all(.[]; type == "array" and all(.[]; type == "object"))' <<<"$rrremote" >/dev/null || {
      echo "error: incomplete or malformed read-back pages; no write" >&2; exit 3;
    }
  fi
  rrmatches="$(jq -c -s --arg login "$rrlogin" --arg root "$rrroot" --slurpfile payload "$rrpayload" '
    flatten | map(select(.user.login == $login and .body == $payload[0].body)) |
    map(select(if $root != "" then .in_reply_to_id == ($root|tonumber)
      elif $payload[0].in_reply_to != null then .in_reply_to_id == $payload[0].in_reply_to
      elif $payload[0].path != null then
        .in_reply_to_id == null and .path == $payload[0].path and
        (.line // .original_line) == $payload[0].line and .side == $payload[0].side and
        (.start_line // .original_start_line) == $payload[0].start_line and .start_side == $payload[0].start_side and
        .commit_id == $payload[0].commit_id
      elif $payload[0].commit_id != null then .commit_id == $payload[0].commit_id and
        .state == ({COMMENT:"COMMENTED",APPROVE:"APPROVED",REQUEST_CHANGES:"CHANGES_REQUESTED"}[$payload[0].event] // .state)
      else true end)) |
    map(select((.id | type == "number") and (.html_url | type == "string" and length > 0)))
  ' <<<"$rrremote")" || exit 3
  if jq -e '(.comments // []) | length > 0' "$rrpayload" >/dev/null && [[ "$(jq 'length' <<<"$rrmatches")" != 0 ]]; then
    rrcomments="$(gh api --paginate "/repos/$rrowner/$rrrepo/pulls/$rrpr/comments")" || exit 3
    jq -e -s 'length > 0 and all(.[]; type == "array" and all(.[]; type == "object"))' <<<"$rrcomments" >/dev/null || exit 3
    rrmatches="$(jq -c -n --argjson matches "$rrmatches" --slurpfile payload "$rrpayload" \
      --argjson comments "$(jq -s 'flatten' <<<"$rrcomments")" '
      def anchors: map({path,body,line:(.line // .original_line),side:(.side // "RIGHT"),
        start_line:(.start_line // .original_start_line),start_side:(.start_side // .side // "RIGHT")}) | sort_by(.path,.side,.line,.body);
      ($payload[0].comments | anchors) as $expected |
      $matches | map(. as $review | select(([$comments[] | select(.pull_request_review_id == $review.id and .in_reply_to_id == null)] | anchors) == $expected))
    ')" || exit 3
  fi
  rrnumber="$(jq 'length' <<<"$rrmatches")"
  if [[ "$rrnumber" == 1 ]]; then
    rrresult="$(jq -c '.[0] | {id,html_url}' <<<"$rrmatches")"
    rr_save posted "$rrresult"; rr_emit "$rrresult"; exit 0
  fi
  if [[ "$rrnumber" != 0 || "$rrstate" == unknown || "$rrstate" == posting ]]; then
    rr_save unknown
    echo "error: submission unknown or duplicate matches; no automatic retry" >&2; exit 6
  fi
  # An update can only modify the active identity's review.
  if [[ "$rrmethod" == PUT ]]; then
    jq -e -s --arg login "$rrlogin" 'length == 1 and .[0].user.login == $login' <<<"$rrremote" >/dev/null || exit 5
  fi
  rr_save posting
  rrresponse="$(mktemp "$rrfile.response.XXXXXX")"; rrerror="$(mktemp "$rrfile.error.XXXXXX")"
  if gh api --method "$rrmethod" "$rrendpoint" --input "$rrpayload" > "$rrresponse" 2> "$rrerror"; then
    if rrresult="$(jq -ce 'select((.id | type == "number") and (.html_url | type == "string" and length > 0)) | {id,html_url}' "$rrresponse")"; then
      rr_save posted "$rrresult"; rr_emit "$rrresult"; exit 0
    fi
  elif grep -Eq 'HTTP (400|401|403|404|405|410|422)' "$rrerror"; then
    rr_save failed; cat "$rrerror" >&2; exit 4
  fi
  # Retain the raw response under the owned receipt directory on uncertain writes.
  cp -- "$rrresponse" "$rrfile.$rrkey.response.json"
  cp -- "$rrerror" "$rrfile.$rrkey.error.log"
  rr_save unknown
  echo "error: write outcome unknown; retained response and receipt for read-back" >&2
  exit 6
)
