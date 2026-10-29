---
name: huynong:pr-review-evaluator
description: Evaluate whether a GitHub PR review comment is correct before responding. Use this skill whenever the user pastes a GitHub PR review comment URL (https://github.com/owner/repo/pull/N#discussion_rXXXX or .../files#r... or .../pulls/N/comments/...), asks to "adjudicate / evaluate / validate / check this review", asks to reply to a reviewer, says "is this reviewer right", or wants help deciding whether to accept or push back on PR feedback. The skill verifies the reviewer's claim against the current code, classifies the verdict, drafts an inline reply, and waits for go-ahead before posting. Never edits code, never commits, never posts without explicit approval.
---

# PR Review Evaluator

Adjudicate GitHub PR review comments. Verify the reviewer's claim against the actual codebase, classify the verdict, draft a reply, post inline (threaded) once the user approves.

## When this triggers

- User pastes a GitHub PR review comment URL.
- User says: "is this reviewer right?", "evaluate this review", "should I accept this?", "reply to this comment", "adjudicate this".
- User wants to push back on a review and asks for help framing it.

## Scope (do / don't)

| Do | Don't |
|----|-------|
| Verify claim against current code | Auto-edit / auto-commit anything |
| Read git blame + commit message | Commit without explicit user approval |
| Run grep / build / tests to confirm claim | Auto-post the reply |
| Draft fix + draft reply, show both, wait for go-ahead | Silently reverse a user-confirmed decision |
| For `CORRECT`/`PARTIAL`: commit AFTER approval, then quote SHA in reply | Reply with a placeholder/fake SHA |
| Reply inline (threaded) to the exact comment | Reply on a top-level PR comment when an inline thread exists |

## Workflow

### Step 1 — Parse the URL

Accept any of these forms:
- `https://github.com/<owner>/<repo>/pull/<n>#discussion_r<comment_id>` (single inline comment — threaded reply)
- `https://github.com/<owner>/<repo>/pull/<n>/files#r<comment_id>` (same, from /files view)
- `https://github.com/<owner>/<repo>/pull/<n>#issuecomment-<comment_id>` (top-level — no threading)
- `https://github.com/<owner>/<repo>/pull/<n>#pullrequestreview-<review_id>` (whole review submission — multiple inline comments)

Use `scripts/parse-review-url.sh <url>` to extract `owner`, `repo`, `pr`, `comment_id`, `kind` (`review` | `issue`).

For `#pullrequestreview-<id>`: parse-review-url.sh will reject; fall back to listing all inline comments in that review (`gh api /repos/{o}/{r}/pulls/{pr}/reviews/{review_id}/comments` plus filtering `/pulls/{pr}/comments` by `pull_request_review_id`) and ask the user which to evaluate (one, several, or all sequentially).

For a review whose body contains a "suppressed-low-confidence" / "deferred" section with findings the bot did NOT post as real inline comments: those have no `comment_id`. Treat them as findings to acknowledge via a NEW inline comment (Step 10b), not a threaded reply.

If the URL form is unrecognised, ask the user for clarification — do not guess.

### Step 2 — Fetch the comment + context

Run `scripts/fetch_comment.sh <owner> <repo> <comment_id> <kind>`. It prints:
- `body` — the reviewer's text
- `path` — file the comment is on (review kind only)
- `line` / `start_line` — the line range (review kind only; can be a multi-line range)
- `commit_id` — the commit the comment was anchored to
- `diff_hunk` — the patch context the reviewer was looking at
- `in_reply_to_id` — present if this is itself a reply (rare; usually null)
- `author` — reviewer's GitHub handle

### Step 3 — Verify the claim (Scout-first, ask-second)

Apply `references/verification-playbook.md`. At minimum:

1. **Read current file at `path` around `line`.** Confirm the code in HEAD matches what the reviewer is critiquing. If the code has changed since the review, flag as `STALE`.
2. **Grep for related call sites / patterns** the reviewer references ("this is also done in X", "breaks Y consumer").
3. **`git blame` + commit message** for the change. Look for hints that the current shape is intentional (e.g. plan reference, "per user decision").
4. **Run build / tests only if** the reviewer claims a concrete compile or runtime failure. Skip for style/opinion comments.

Self-rate confidence (0–100%). If <85%, ask the user before drafting a verdict.

### Step 4 — Classify the verdict

Pick exactly one. Definitions live in `references/verdict-taxonomy.md`.

| Verdict | Meaning | Default reply tone |
|---------|---------|--------------------|
| `CORRECT` | Reviewer right, code should change | Acknowledge + agree + state planned fix |
| `WRONG` | Reviewer misread / misunderstands | Polite pushback with file:line evidence |
| `PARTIAL` | Real issue, wrong fix | Agree on issue + propose alternative |
| `STALE` | Code already changed | Link to commit / current state |
| `LOCKED` | Touches a user-confirmed decision (STOP — escalate to user before drafting) | n/a — ask user first |
| `OPINION` | Style / preference, no objective answer | Note trade-off + defer or hold position |
| `AMBIGUOUS` | Need more info from reviewer | Ask a clarifying question |

### Step 5 — Decision guard (LOCKED verdict)

Before finalising any verdict, check whether the reviewer's recommendation would reverse a decision the user has explicitly confirmed (in commit messages, plans/ folder, prior chat, project memory).

If yes → verdict is `LOCKED`. Do not draft a reply. Surface to user:
- the user's original decision verbatim (with source: `file:line` or commit SHA)
- the reviewer's reasoning
- the trade-off
- explicit ask: "keep / change per reviewer / hybrid?"

This is non-negotiable. Auditor / reviewer bias leans YAGNI/minimalism — their input is a recommendation, not an order.

### Step 6 — Draft the fix (only for `CORRECT` / `PARTIAL`)

For verdicts that involve a code change, draft the diff in memory and show it to the user as a unified diff or fenced code block. Do NOT write to disk yet.

For `WRONG` / `STALE` / `OPINION` / `AMBIGUOUS` / `LOCKED`: skip this step (no fix needed, or fix already exists, or decision is locked).

### Step 7 — Show plan, wait for first go-ahead

Print:
```
Verdict: <verdict>
Confidence: <%>
Evidence:
  - <path:line> — <fact>
  - ...

Planned fix (CORRECT / PARTIAL only):
---
<unified diff or code snippet>
---

Planned reply (will quote commit SHA once committed):
---
<reply draft — MUST start with shields.io verdict badge per references/reply-templates.md>
---
```

**Reply badge rule:** Every posted reply MUST start with a shields.io verdict badge on its own line (e.g. `![Fixed](https://img.shields.io/badge/Status-Fixed-brightgreen)`). See `references/reply-templates.md` → "Verdict badges" table for the full mapping.

**STOP.** Wait for the user to say "go" / "commit + reply" / "apply" / "ship".

If the user edits either the diff or the reply, use their version verbatim.

### Step 8 — Apply fix + commit (only for `CORRECT` / `PARTIAL`)

After approval:

1. Apply the edits to the working tree (Edit / Write).
2. Run project-local format / lint (e.g. `make format && make lint`, `npm run lint`, `swiftlint --fix`) IF the project's CLAUDE.md / makefile signals one is expected. Skip if no obvious convention.
3. Commit using the project's tooling:
   - If `but` (GitButler) is available AND the repo uses it (detect: `.git/gitbutler` directory, or `but status` exits 0) → use `but` per project's gitbutler skill if loaded; otherwise plain `git`.
   - Otherwise → plain `git commit`.
4. Use conventional commit format: `fix(scope): <one-liner addressing the review>`.
5. Capture the resulting full SHA via `git rev-parse HEAD` (or `git rev-parse <branch>` when GitButler virtualises the workspace — see "GitButler note" below).
6. Substitute `<SHA-PENDING>` in the draft reply with a **clickable markdown link**:
   ```
   [<short-sha>](https://github.com/<owner>/<repo>/commit/<full-sha>)
   ```
   Bare SHAs in inline review-comment threads do NOT auto-link — they render as plain text. Always use the markdown link form.

**GitButler note:** `git rev-parse HEAD` returns the workspace merge commit, not the branch tip. After `but commit`, the branch tip lives at `git rev-parse <branch-name>`. Use the branch-tip SHA — it's the one GitHub will display when the branch is pushed.

For `WRONG` / `STALE` / `OPINION` / `AMBIGUOUS` / `LOCKED-hold`: no commit; proceed to Step 9 directly.

### Step 9 — Show finalised reply, wait for second go-ahead

Print:
```
Reply (final, with SHA inlined):
---
<final reply text>
---
Posting via: <endpoint>
Threading: yes/no (yes for kind=review, no for kind=issue)
```

**STOP.** Wait for "post" / "send" / "ship it".

### Step 10 — Post

Pick the right post mode based on what you're acknowledging.

#### 10a. Threaded reply (most common)

When you have a real `comment_id` from an existing inline review comment:

- **`kind=review`** → threaded reply via `POST /repos/{owner}/{repo}/pulls/{pr}/comments/{comment_id}/replies`.
  Use `scripts/post-reply.sh <owner> <repo> <pr> <comment_id> review <body_file>`.
- **`kind=issue`** → new top-level PR comment (threading not available for top-level). Warn the user.

Threaded replies do NOT need `commit_id`. The reply inherits the anchor of the original comment, so local-only commits referenced by SHA in the body text are fine — they only need to be reachable when the user clicks the markdown link.

#### 10b. New inline comment (no thread to reply to)

When the finding lives in a review's body text (e.g. "Comments suppressed due to low confidence" sections, deferred-review notes, top-level PR comments that reference a file) and there is NO `comment_id` to thread under — post a fresh inline anchor:

```bash
scripts/post-new-inline.sh <owner> <repo> <pr> <full_commit_sha> <path> <line> <body_file>
```

**Critical pre-condition: the commit anchor MUST be pushed to origin first.** GitHub validates that `commit_id` is part of the PR, and a local-only SHA returns `422 commit_id is not part of the pull request`. The script pre-flights via `gh api /pulls/{pr}/commits` and refuses with a clear error if the commit isn't on origin.

If pushing the fix-commit first conflicts with the "no push without go-ahead" memory rule, surface to the user: "to anchor this new inline comment I need to push first — go?"

### Step 11 — Push reminder (for any case with a local-only commit)

If Step 8 made a commit AND Step 10 used `post-reply.sh` (threaded), the commit is still local — markdown link in the reply body will 404 until pushed. Tell the user:

```
Local commit <sha> not yet pushed. The markdown link in the reply will 404 until you push: `but push <branch>` / `git push`.
```

If Step 10 used `post-new-inline.sh`, the push already happened in Step 10b (required by pre-flight) — note that the push went through, separately from the comment confirmation.

Do NOT auto-push under the "threaded reply" path.

### Step 11 — Push (optional, only if committed)

If a commit was made in Step 8, the commit is local only. Remind the user:
```
Local commit <sha> not yet pushed. Push when ready: `but push <branch>` / `git push`.
```

Do NOT auto-push. (Push is a separate "shared-state" action — per the "no commit without go-ahead" memory rule, also no push without go-ahead.)

## Inputs

| Input | Required | Source |
|-------|----------|--------|
| Review comment URL | Yes | User message |
| Working repo | Auto | CWD; must match URL's `owner/repo` or ask user |
| `gh` CLI authenticated | Yes | `gh auth status` |

If `gh auth status` fails, prompt the user to run `gh auth login` themselves — do not attempt to authenticate on their behalf.

If CWD repo ≠ URL repo, ask the user whether to `cd` into the right checkout or proceed anyway (verification will be weaker).

## Output contract

Every invocation produces, in order:
1. **Parsed input** (one line): `owner/repo#PR comment <id> by @author on <path>:<line>`
2. **Verification log** (bulleted facts with `path:line` citations)
3. **Verdict block** (verdict, confidence, evidence)
4. **Draft reply** (plain text, ready to copy-paste)
5. **Wait for approval**
6. **Post + return URL** (after approval)

## Security policy

This skill handles GitHub PR review evaluation. It does NOT handle:
- Posting comments without explicit user approval
- Editing repository code based on reviewer suggestions
- Authenticating against GitHub (delegate to `gh` CLI / user)
- Evaluating reviews on private code the user has not granted access to

Refuse to:
- Post a reply that disparages the reviewer (rewrite to be neutral first).
- Apply changes inferred from a review to working tree or git.
- Bypass the LOCKED check when a user-confirmed decision is at stake.
- Echo secrets that appear in a review comment back into the reply — redact tokens / keys / emails before quoting.

## References (load as needed)

- `references/verdict-taxonomy.md` — full criteria for each verdict
- `references/reply-templates.md` — copy-paste reply skeletons per verdict
- `references/verification-playbook.md` — checklist for verifying claims
- `references/github-api-paths.md` — review-comment vs issue-comment API differences

## Scripts

- `scripts/parse-review-url.sh` — URL → owner/repo/pr/comment_id/kind
- `scripts/fetch-comment.sh` — pull comment body, diff hunk, path/line, author
- `scripts/post-reply.sh` — threaded reply under an existing inline comment (Step 10a)
- `scripts/post-new-inline.sh` — fresh inline comment anchored to a `file:line` (Step 10b). Requires the commit to be pushed first; script pre-flights via `gh api /pulls/{pr}/commits` and exits 4 with a hint if not.
