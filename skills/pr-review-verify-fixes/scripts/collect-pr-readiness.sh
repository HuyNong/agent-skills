#!/usr/bin/env bash
# Read-only platform observations. No request approves, resolves, or merges a PR.
set -euo pipefail
owner="${1:?owner}"; repo="${2:?repo}"; pr="${3:?PR}"; out="${4:?new output directory}"
[[ ! -e "$out" && ! -L "$out" ]] || { echo "error: output exists" >&2; exit 2; }
umask 077; mkdir -p "$out"
fields="headRefOid,baseRefOid,baseRefName,state,isDraft,mergeable,mergeStateStatus,reviewDecision,statusCheckRollup,latestReviews,potentialMergeCommit"
gh pr view "$pr" -R "$owner/$repo" --json "$fields" > "$out/before.json" || exit 3
if [[ "$(jq -r '.mergeable' "$out/before.json")" == UNKNOWN ]]; then
  gh pr view "$pr" -R "$owner/$repo" --json "$fields" > "$out/recomputed.json" || exit 3
  cp "$out/recomputed.json" "$out/before.json"
fi
checks_rc=0
gh pr checks "$pr" -R "$owner/$repo" --required --json bucket,name,state,link,workflow \
  > "$out/checks.json" 2> "$out/checks-error.log" || checks_rc=$?
checks_ok=false
checks_none=false
if [[ "$checks_rc" == 0 || "$checks_rc" == 8 ]] && jq -e 'type == "array"' "$out/checks.json" >/dev/null 2>&1; then checks_ok=true; fi
if [[ "$checks_rc" == 1 ]] && grep -Eiq '^no (required )?checks (reported|found)' "$out/checks-error.log"; then checks_none=true; fi
[[ "$checks_ok" == true ]] || printf '[]\n' > "$out/checks.json"
branch="$(jq -er '.baseRefName' "$out/before.json")" || exit 3
encoded="$(jq -nr --arg branch "$branch" '$branch|@uri')"
rules_ok=false; classic_ok=false
if gh api --paginate "/repos/$owner/$repo/rules/branches/$encoded" > "$out/rules-pages.json" 2> "$out/rules-error.log" &&
   jq -e -s 'length>0 and all(.[]; type=="array")' "$out/rules-pages.json" >/dev/null; then
  jq -s 'add' "$out/rules-pages.json" > "$out/rules.json"; rules_ok=true
else printf '[]\n' > "$out/rules.json"; fi
if gh api "/repos/$owner/$repo/branches/$encoded" > "$out/branch.json" 2> "$out/branch-error.log"; then
  if jq -e '.protected == false' "$out/branch.json" >/dev/null; then
    printf '{}\n' > "$out/classic.json"; classic_ok=true
  elif gh api "/repos/$owner/$repo/branches/$encoded/protection" > "$out/classic.json" 2> "$out/classic-error.log" &&
       jq -e 'type=="object" and has("required_status_checks")' "$out/classic.json" >/dev/null; then classic_ok=true; fi
fi
[[ "$classic_ok" == true ]] || printf '{}\n' > "$out/classic.json"
gh pr view "$pr" -R "$owner/$repo" --json "$fields" > "$out/after.json" || exit 3
jq -n --slurpfile before "$out/before.json" --slurpfile after "$out/after.json" --slurpfile checks "$out/checks.json" \
  --slurpfile rules "$out/rules.json" --slurpfile classic "$out/classic.json" --argjson checks_ok "$checks_ok" \
  --argjson rules_ok "$rules_ok" --argjson classic_ok "$classic_ok" --argjson checks_exit "$checks_rc" --argjson checks_none "$checks_none" '
  $after[0] as $p | $rules[0] as $rules |
  ($before[0] == $p) as $stable |
  ($rules | any(.[]; .type != "pull_request" and .type != "required_status_checks")) as $unsupported |
  (($classic[0].required_pull_request_reviews.required_approving_review_count // 0) > 0 or
    $classic[0].required_pull_request_reviews.require_code_owner_reviews == true or
    $classic[0].required_pull_request_reviews.require_last_push_approval == true or
    any($rules[]; .type == "pull_request" and ((.parameters.required_approving_review_count // 0) > 0 or
      .parameters.require_code_owner_review == true or .parameters.require_last_push_approval == true))) as $review_required |
  (($classic[0].required_status_checks.contexts // [] | length) > 0 or
    ($classic[0].required_status_checks.checks // [] | length) > 0 or
    any($rules[]; .type == "required_status_checks")) as $checks_required |
  ($checks[0] | any(.[]; .bucket == "fail" or .bucket == "pending" or .bucket == "cancel")) as $bad_checks |
  ($p.state != "OPEN" or $p.isDraft == true or $p.mergeable == "CONFLICTING" or $bad_checks or
    $p.reviewDecision == "CHANGES_REQUESTED" or $p.reviewDecision == "REVIEW_REQUIRED") as $blocked |
  ($stable and $rules_ok and $classic_ok and ($unsupported|not) and
    ($p.headRefOid | type=="string" and test("^[a-fA-F0-9]{40}$")) and
    ($p.baseRefOid | type=="string" and test("^[a-fA-F0-9]{40}$")) and $p.isDraft == false and
    ($checks_ok or ($checks_none and ($checks_required|not))) and
    (if $checks_required then ($checks[0]|length>0) else true end) and
    all($checks[0][]; .bucket == "pass" or .bucket == "skipping") and
    ($p.reviewDecision == "APPROVED" or (($review_required|not) and $p.reviewDecision == null)) and
    $p.mergeable == "MERGEABLE" and $p.mergeStateStatus == "CLEAN") as $eligible |
  {snapshot:{head_sha:$p.headRefOid,base_sha:$p.baseRefOid,test_merge_sha:($p.potentialMergeCommit.oid // null)},
   observations:$p,required_checks:$checks[0],checks_exit:$checks_exit,
   visibility:{checks:$checks_ok,no_checks_reported:$checks_none,rules:$rules_ok,classic:$classic_ok,unsupported_rules:$unsupported},
   stable:$stable,platform:(if ($stable|not) then "unknown" elif $blocked then "blocked" elif $eligible then "eligible" else "unknown" end),
   limits:"Read-only observation, not an atomic guarantee or a fresh code review. Finding verdicts are a separate gate."}
' > "$out/readiness.json"
cat "$out/readiness.json"
