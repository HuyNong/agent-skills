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

There is NO threading. If you want to "reply" to a top-level comment, you post a new top-level comment. The skill should warn the user that threading wasn't possible.

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

(The skill's `post-reply.sh` uses `-f body="$body"` which works fine for multi-line strings as long as they're properly quoted in shell — but we read the body from a file, so this is safe.)

## New inline comment (no thread to reply to)

When the finding lives in the review's body text (suppressed-low-confidence sections, deferred notes), there's no `comment_id`. Post a fresh anchor:

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
If it's not there, push first (`git push` / `but push <branch>`), then retry.

Threaded-reply posts do NOT have this restriction — they inherit the parent comment's anchor.

## Common failure modes

- **403** — token lacks `repo` scope, or commenter doesn't have access. Tell user to `gh auth refresh -s repo`.
- **404** — wrong comment ID or wrong endpoint (e.g. using `/pulls/comments/...` on an issue-comment ID). Re-check the URL fragment.
- **422 (validation)** — body empty, or `commit_id is not part of the pull request` (commit not pushed; see above), or multi-line anchor with `start_side != side`. Show user the response error for diagnosis.
