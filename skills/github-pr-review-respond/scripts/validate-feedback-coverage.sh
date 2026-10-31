#!/usr/bin/env bash
# Check source/finding accounting; semantic truth still needs code verification.
# Usage: validate-feedback-coverage.sh <inventory.json> <coverage.json>
set -euo pipefail
inventory="${1:?inventory required}"
coverage="${2:?coverage required}"
command -v jq >/dev/null || { echo "error: jq required" >&2; exit 2; }

if ! jq -e -n --slurpfile inventory "$inventory" --slurpfile coverage "$coverage" '
  def require($condition; $message): if $condition then . else error($message) end;
  def text: type == "string" and length > 0;
  require(($inventory | length == 1) and ($coverage | length == 1); "expected one JSON document per file") |
  $inventory[0] as $i | $coverage[0] as $c |
  require($i.complete == true; "feedback inventory is incomplete") |
  require((["pr","linked","explicit"] | index($c.scope.mode) != null) and ($c.scope.reason | text);
    "scope needs mode pr/linked/explicit and its user-request reason") |
  require(($c.sources | type == "array") and ($c.findings | type == "array"); "sources/findings must be arrays") |
  ($i.records | map(.key) | sort) as $keys |
  ($c.sources | map(.key) | sort) as $covered |
  ($c.findings | map(.id)) as $finding_ids |
  require($covered == $keys and ($covered | unique | length) == ($covered | length);
    "account for every inventory record exactly once") |
  (if $c.scope.mode == "linked" then
    ($i.records | map(select(.key == $c.scope.target))) as $targets |
    require(($targets | length == 1); "linked target is not in the inventory") |
    $targets[0] as $t |
    (if $t.kind == "reviews" then
      [$i.records[] | select(.kind == "inline" and .review_id == $t.id and .is_reply == false) | .id]
     elif $t.kind == "inline" then [$t.root_comment_id] else [] end) as $roots |
    [$i.records[] | select(.key == $t.key or
      (.kind == "inline" and (.root_comment_id as $id | $roots | index($id) != null))) | .key]
   else [] end) as $required |
  require(all($c.sources[]; .key as $key |
    if ($required | index($key) != null) then .read == true and .disposition != "out_of_scope" else true end);
    "linked scope omits its target, a review finding, or thread context") |
  require(($finding_ids | all(.[]; text)) and ($finding_ids | unique | length) == ($finding_ids | length);
    "finding ids must be unique nonempty strings") |
  require(all($c.sources[];
    if .disposition == "out_of_scope" then
      $c.scope.mode != "pr" and (.reason | text) and (.finding_ids == [])
    else .read == true and (.finding_ids | type == "array") and
      (if .disposition == "finding" then (.finding_ids | length > 0)
       elif .disposition == "context" then (.finding_ids == []) and (.reason | text)
       else false end)
    end); "unread source, invalid exclusion, or missing finding mapping") |
  require(all($c.sources[]; all(.finding_ids[]; . as $id | $finding_ids | index($id) != null));
    "source references an unknown finding") |
  require(all($c.findings[];
    . as $f | (.source_keys | type == "array" and length > 0) and
    (.source_keys | unique | length) == (.source_keys | length) and
    all(.source_keys[]; . as $key | any($c.sources[];
      .key == $key and .disposition == "finding" and (.finding_ids | index($f.id) != null))));
    "finding sources must point back to their source mappings") |
  require(all($c.sources[]; . as $s | all(.finding_ids[]; . as $id |
    any($c.findings[]; .id == $id and (.source_keys | index($s.key) != null))));
    "source/finding mappings disagree") |
  require(all($c.findings[]; .status == "evaluated" and
    (.verdict as $v | ["CORRECT","WRONG","PARTIAL","STALE","OPINION","AMBIGUOUS","LOCKED"] | index($v) != null) and
    (.evidence | type == "array" and length > 0 and all(.[]; text)));
    "pending/blocked findings or missing verdict/evidence") |
  {complete: true, scope: $c.scope.mode, sources: ($keys | length),
    read: ($c.sources | map(select(.read == true)) | length),
    excluded: ($c.sources | map(select(.disposition == "out_of_scope")) | length),
    findings: ($c.findings | length), evaluated: ($c.findings | length)}
'; then
  echo "error: feedback coverage incomplete; retain artifacts and report missing work" >&2
  exit 3
fi
