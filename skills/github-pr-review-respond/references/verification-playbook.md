# Verification Playbook

Before classifying a verdict, run these checks. Skip any step only if it's clearly irrelevant to the reviewer's claim (e.g. don't run tests for a style nit).

## 1. Read the current code at `path:line` (always)

- `Read` the file at the cited path, focused around the line range from `fetch-comment.sh`.
- Compare what you see to `diff_hunk` in the comment payload. If they differ, the comment is anchored to an older commit — possibly `STALE`.
- Quote 2–4 lines of current code in your verification log so the user can sanity-check without re-reading the file.

## 2. Grep for related call sites / cross-file claims

Trigger when the reviewer says any of:
- "this is also done in X"
- "breaks the Y consumer"
- "elsewhere we do Z"
- "what about <other-file>"
- "all callers handle this differently"

Run `grep -rn <symbol> <relevant-dirs>` to verify. If the reviewer is right that other call sites do something different, that affects verdict (often pushes toward `CORRECT`).

## 3. `git blame` + commit message for the change

- `git blame -L <start>,<end> <path>` on the cited range.
- Look at the most-recent commit message that touched these lines.
- Red flags that push toward `LOCKED`:
  - Commit message mentions "per user decision" / "intentional" / "decided to X"
  - Commit references a plan file in `plans/`
  - Commit is small + focused, suggesting deliberate choice
- Red flags that push toward `CORRECT`:
  - Commit message says "TODO" / "quick fix" / "revisit"
  - Commit is a bulk rename / mechanical change where this case wasn't considered

## 4. Build / test (only when reviewer claims runtime failure)

Trigger when the reviewer says:
- "this won't compile"
- "this crashes on X"
- "the test for Y will fail"
- "this breaks at runtime when Z"

Don't trigger for:
- Style preferences
- Readability nits
- Architecture opinions
- "I think this is slow" without a benchmark

When triggering, prefer narrowly scoped runs:
- Single test file: `<project test runner> --filter <name>` — not the whole suite
- Single target build: `xcodebuild -target <X>` / `cargo check -p <X>` / etc.

If the build/test passes contrary to the reviewer's claim → strong evidence toward `WRONG`. If it fails as claimed → strong evidence toward `CORRECT`.

## 5. Check session context for user-confirmed decisions

For `LOCKED` detection, look for:
- Recent commits where the user explicitly chose a value/design (last 30 commits on branch).
- Any plan file in `plans/` that names the disputed element.
- Project memory entries (e.g. `.remember/`, memory/) mentioning the choice.
- Prior chat in the current session.

When in doubt, surface to user — false negatives on `LOCKED` are much costlier than false positives.

## 6. Compose the verification log

Every entry is one line:
```
- <path:line> — <fact, neutrally stated>
```

Example:
```
- KeychainTokenStorage.swift:42 — `setAccessToken` returns Void, not throws (reviewer claimed it could throw)
- AuthInterceptor.swift:118 — refresh path catches OSStatus errors via `do/try`, matches reviewer's assertion
- commit a1dd486 — added `Logger.isNetworkLoggingEnabled` toggle deliberately (user chose default=false)
```

Five short lines beats one long paragraph. The user should be able to skim the log and reach the same verdict.
