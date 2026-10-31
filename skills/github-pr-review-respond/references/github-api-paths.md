# GitHub API: Review Comments vs Issue Comments

GitHub has TWO comment systems on a PR. The skill must pick the right one or threading breaks.

## Review comments (inline, anchored to a diff line)

URL form in browser:
```
https://github.com/<owner>/<repo>/pull/<n>#discussion_r<id>
https://github.com/<owner>/<repo>/pull/<n>/files#r<id>
```

API endpoints:

| Action | Endpoint | Method |
|--------|----------|--------|
| Fetch one | `/repos/{owner}/{repo}/pulls/comments/{id}` | GET |
| Threaded reply | `/repos/{owner}/{repo}/pulls/{pr}/comments/{id}/replies` | POST |
| List all on PR | `/repos/{owner}/{repo}/pulls/{pr}/comments` | GET |

Threaded-reply body:
```json
{ "body": "your reply text" }
```

The `{id}/replies` endpoint automatically threads under the original — no `in_reply_to` field needed in the body (GitHub used to require `in_reply_to`; the `/replies` shortcut is now the canonical path).

Fields on the fetched comment that matter:
- `path` — file the comment is on
- `line` / `start_line` — line range (may be multi-line)
- `side` — `LEFT` (original) or `RIGHT` (new); usually `RIGHT`
- `commit_id` — the commit the comment is anchored to (may be older than HEAD)
- `diff_hunk` — the patch snippet the reviewer was looking at
- `in_reply_to_id` — present if this is itself a reply (rare; usually null)
- `original_line` / `original_start_line` — line at the time of comment (use as fallback when reviewer is looking at older code)

## Issue comments (top-level PR comments)

URL form in browser:
```
https://github.com/<owner>/<repo>/pull/<n>#issuecomment-<id>
```

API endpoints:

| Action | Endpoint | Method |
|--------|----------|--------|
| Fetch one | `/repos/{owner}/{repo}/issues/comments/{id}` | GET |
| Post new | `/repos/{owner}/{repo}/issues/{pr}/comments` | POST |

Issue comments have no native reply thread, but their source type does not decide placement. If the specific finding has an original inline thread, use it. Otherwise prefer a new inline comment at the exact relevant diff anchor; use a quoted top-level comment only when no valid relevant anchor exists. Choose this automatically, then show the reply and target for posting confirmation.

(In the API, a PR is also an issue — that's why the issue endpoint works on a PR number.)

## Detecting which kind from a URL

| Fragment | Kind |
|----------|------|
| `#discussion_r<id>` | review |
| `#r<id>` | review (from /files view) |
| `#issuecomment-<id>` | issue |

If no fragment is present, the URL points to the PR overall, not a specific comment — ask the user to copy the specific comment URL.

## `gh` CLI invocation patterns

Fetch a review comment:
```bash
gh api /repos/owner/repo/pulls/comments/12345
```

Post a threaded reply:
```bash
gh api -X POST /repos/owner/repo/pulls/678/comments/12345/replies \
  -f body="your reply"
```

Post a top-level PR comment:
```bash
gh api -X POST /repos/owner/repo/issues/678/comments \
  -f body="your reply"
```

For long replies, prefer piping a file to avoid shell-escaping pain:
```bash
gh api -X POST <url> --input - < body.txt
```

Or use the `-F` field to read from file:
```bash
gh api -X POST <url> -F "body=@body.txt"
```

The skill's `post-reply.sh` reads the body with `-F "body=@<body_file>"`.

## New inline comment (no thread to reply to)

When a finding in a review summary or issue comment has no original inline thread, choose a fresh anchor before asking to post.

### Resolve the anchor against the current PR

1. Fetch `/repos/{owner}/{repo}/pulls/{pr}` for `head.sha`, and all pages of `/repos/{owner}/{repo}/pulls/{pr}/files` for canonical `filename`, `previous_filename` and `patch` values. Check the cited code at that head, not an unrelated local working-tree line.
2. Trace the specific claim to its code. Resolve renamed paths to the current diff filename and remap old source line numbers when code moved. Do not anchor to another finding or an unrelated changed line in the same file.
3. In a hunk `@@ -old_start,old_count +new_start,new_count @@`, context advances both line counters, `-` advances the old counter, and `+` advances the new counter. Use the blob line number, not the line's ordinal position within the patch. Use RIGHT for current additions/context, or LEFT for a claim about deleted code.
4. Prefer one precise line. If a range is necessary, its endpoints must belong to the same relevant hunk with valid `start_line`/`start_side` and `line`/`side`. A readable source line outside the shown hunks is not a valid inline anchor.
5. If the relevant patch is unavailable, the target is outside the diff, or the mapping remains uncertain, select a quoted top-level fallback. Explain the reason in the preview; do not ask the user to choose the posting style or force an unrelated anchor.
6. Show the final reply, source URL and selected anchor/head for posting confirmation. Recheck `head.sha` before posting; if the approved target is invalidated, remap and present the updated target for confirmation rather than posting against a stale line.

New inline/fallback bodies include the badge, a short quote of this finding, its source-comment link and the evidence-backed response; see `references/reply-templates.md` relative to the skill root.

After confirmation, a single RIGHT-side anchor uses:

```bash
gh api -X POST /repos/owner/repo/pulls/N/comments \
  -f "commit_id=<full-40-char-sha>" \
  -f "path=src/foo.swift" \
  -F "line=42" \
  -f "side=RIGHT" \
  -F "body=@reply.txt"
```

Required fields: `commit_id`, `path`, `line`, `side`. Optional for multi-line: `start_line`, `start_side`.

**Critical pre-condition: `commit_id` MUST already be pushed to origin AND be part of the PR's commit history.** GitHub validates this and returns:
```
422 Validation Failed
"commit_id is not part of the pull request"
```
if you reference a local-only commit. Pre-flight check:
```bash
gh api /repos/owner/repo/pulls/N/commits --jq '.[].sha' | grep -qx "<full-sha>"
```
If it is not there, do not push automatically. Prefer the verified current PR head when it contains the relevant code; if the approved anchor really requires the local commit, obtain push authorization first.

Threaded-reply posts do NOT have this restriction — they inherit the parent comment's anchor.

The bundled `post-new-inline.sh` sets `side=RIGHT` and a single `line`. For a LEFT-side or multi-line anchor, build an API payload with the actual validated side/range instead of passing it to that helper. API field meanings: [GitHub review-comment documentation](https://docs.github.com/en/rest/pulls/comments#create-a-review-comment-for-a-pull-request).

## Common failure modes

- **403** — token lacks `repo` scope, or commenter doesn't have access. Tell user to `gh auth refresh -s repo`.
- **404** — wrong comment ID or wrong endpoint (e.g. using `/pulls/comments/...` on an issue-comment ID). Re-check the URL fragment.
- **422 (validation)** — body empty, or `commit_id is not part of the pull request` (commit not pushed; see above), or multi-line anchor with `start_side != side`. Show user the response error for diagnosis.

## Feedback inventory and coverage

Collect all three sources even when the entry URL is one issue comment. UI adjacency does not make a separate review its child. Use `scripts/fetch-pr-feedback.sh` relative to the skill root; the single-comment helper does not discover other feedback.

| Source | Paginated endpoint | Inventory kind |
|---|---|---|
| Review submissions and summary bodies | `/repos/{owner}/{repo}/pulls/{pr}/reviews` | `reviews` |
| Inline roots and replies, with full anchors | `/repos/{owner}/{repo}/pulls/{pr}/comments` | `inline` |
| General PR comments and bot reports | `/repos/{owner}/{repo}/issues/{pr}/comments` | `issues` |

The output directory must be new so stale data cannot appear current. The helper saves raw page streams/error logs, normalized source arrays, `items/<kind>-<id>.json` files and `inventory.json`. Its stdout contains counts and a path, not body previews. HTTP/pagination failure, invalid JSON/body or a missing inline root leaves `complete=false` and exits 3; successful sources remain available. A transport-complete inventory does not mean its findings have been read or evaluated.

Match the entry URL against its kind and ID in `inventory.records`. A deleted/wrong-PR target needs investigation; do not substitute another comment silently. Read each selected `body_file` relative to the inventory directory. Preserve complete bodies, code blocks, HTML tables/details, `pull_request_review_id`, `in_reply_to_id` and anchors. If output is truncated, read the remaining sections before marking that source read.

Default to scope mode `linked`, with `scope.target` set to the input inventory key, for example `issues:42`, `inline:73` or `reviews:11`. A comment selects all its body concerns and its root/reply context. A review selects its summary and every root comment with that review ID, plus replies to those roots even when attached to different review records. List other sources with author, URL/path and a short subject, without assigning verdicts or fixes. This listing does not require interpreting unrelated bodies as in-scope findings.

Use mode `pr` for a bare PR URL or an explicit all-PR request, and inspect all records. Use mode `explicit` for a user-selected subset such as specific finding IDs/reviewers and record the limitation verbatim. Context-only/empty review records, praise and already-answered discussion need a reason, not silent deletion; a selected reply introducing a new concern still needs its own finding.

Build a semantic ledger at the invocation scratch root as `coverage.json`. Example for one independent finding repeated in a summary and an inline root:

```json
{
  "scope": {"mode": "pr", "reason": "Evaluate all PR feedback"},
  "sources": [
    {"key": "reviews:11", "read": true, "disposition": "context", "reason": "Empty review body", "finding_ids": []},
    {"key": "inline:73", "read": true, "disposition": "finding", "finding_ids": ["F1"]},
    {"key": "issues:42", "read": true, "disposition": "finding", "finding_ids": ["F1"]}
  ],
  "findings": [
    {"id": "F1", "source_keys": ["inline:73", "issues:42"], "status": "evaluated", "verdict": "CORRECT", "evidence": ["src/example.go:12 — observed defect"]}
  ]
}
```

Use one source entry for every inventory record, with exact keys. Multiple defects in one body map to multiple finding IDs. Duplicate summaries map to the same finding only after verifying the claim and affected code; similar wording alone is insufficient. Prefer the original inline root for that finding, not a new duplicate thread.

Every source within scope has `read=true` and disposition `finding` or `context`. Context needs a reason and no finding IDs. Modes `linked` and `explicit` permit disposition `out_of_scope` for unrelated records, with a reason and no finding IDs. Mode `linked` cannot exclude the target, its root/replies or any findings belonging to the selected review. Mode `pr` permits no exclusions. Quote the user request or target URL in `scope.reason`.

Each finding lists all of its source keys. Keep `status=pending` while unread/unverified and `status=blocked` for an unresolved LOCKED/low-confidence decision. Use `evaluated` only after producing a supported verdict/evidence; the ledger does not authorize a fix or post.

Run `scripts/validate-feedback-coverage.sh` with inventory and ledger paths before the fix/reply approval preview and before posting. It requires complete transport, every source accounted exactly once, all structurally related sources within a linked scope read, consistent source/finding references and evaluated verdicts with evidence. It exits 3 on incomplete coverage. It validates accounting, not whether the semantic judgment is correct; verify claims against code using the playbook.

Report both source counts and unique findings, for example: `6 sources read; 4 unique findings; 4 evaluated; 0 pending; 0 exclusions`. Do not count a duplicate summary or a contextual reply as another defect. Never call 1 of 4 evaluated findings a completed batch. On failure, show exact missing work and retain artifacts; do not treat an API error as an empty review.
