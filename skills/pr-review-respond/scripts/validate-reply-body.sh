#!/usr/bin/env bash
# Validate display format; optional verdict/state check cannot prove code semantics.
# Usage: validate-reply-body.sh <body-file> [verdict] [fix-state]
set -euo pipefail
body_file="${1:?body file required}"; verdict="${2:-}"; fix_state="${3:-}"
fail() { echo "error: reply badge: $*; see references/reply-templates.md" >&2; exit 2; }
[[ -r "$body_file" ]] || fail "readable nonempty body required"
first=""; second=""; rest=""
{
  IFS= read -r first || true
  IFS= read -r second || true
  rest="$(cat)"
} < "$body_file"
first="${first%$'\r'}"; second="${second%$'\r'}"
[[ -z "$second" && "$rest" =~ [^[:space:]] ]] || fail "badge needs a blank line and substantive reply"
status=""
for candidate in Accepted:blue Fixed:brightgreen Rejected:blue Partial:yellow Stale:lightgrey Locked:red Noted:lightgrey Needs_Info:orange; do
  name="${candidate%:*}"; color="${candidate#*:}"; label="${name//_/ }"
  if [[ "$first" == "![$label](https://img.shields.io/badge/Status-$name-$color)" ]]; then
    status="$name"; break
  fi
done
[[ -n "$status" ]] || fail "first line must be a canonical shields.io status badge"
[[ -z "$fix_state" || "$fix_state" == planned || "$fix_state" == fixed-local || "$fix_state" == fixed-on-pr ]] || fail "unknown fix state"
[[ -n "$verdict" || -z "$fix_state" ]] || fail "fix state needs a verdict"
[[ -n "$verdict" ]] || exit 0
case "$verdict" in
  CORRECT)
    case "$fix_state" in
      planned|fixed-local) expected=Accepted ;;
      fixed-on-pr) expected=Fixed ;;
      *) fail "CORRECT requires planned, fixed-local or fixed-on-pr" ;;
    esac ;;
  WRONG) expected=Rejected ;;
  PARTIAL) expected=Partial ;;
  STALE) expected=Stale ;;
  LOCKED) expected=Locked ;;
  OPINION)
    [[ "$status" == Noted || "$status" == Accepted ]] || fail "OPINION requires Noted or Accepted"
    exit 0 ;;
  AMBIGUOUS) expected=Needs_Info ;;
  *) fail "unknown verdict" ;;
esac
[[ "$status" == "$expected" ]] || fail "$verdict/$fix_state requires $expected, received $status"
