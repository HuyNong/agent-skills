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
