---
name: huynong:create-pr
description: Create a GitHub pull request for the current branch with a structured body (summary, changes, test plan, risk, breaking changes). Use this skill when the user says "create pr", "open pr", "make pr", "submit pr", "push and pr", "/pr", wants to ship their work, or says "ready for review". Reads the project memory for the correct base branch (e.g. develop vs main). Supports GitButler (`but push`) and plain git workflows.
---

# Create PR

Create a well-structured GitHub pull request from the current session's work.

## Scope

| Do | Don't |
|----|-------|
| Analyze all commits on the branch | Auto-merge or approve |
| Generate structured PR body | Commit uncommitted changes |
| Push branch if needed (with approval) | Force-push without asking |
| Read project memory for base branch | Guess the base branch |
| Create PR via `gh pr create` | Add labels/reviewers automatically |

## Workflow

### Step 1 — Determine Base Branch

1. Search project memory files for `pr-base-branch` or keywords `base branch`, `PR target`:
   ```bash
   find "$(pwd)/.claude" "$HOME/.claude/projects" -name "*.md" -exec grep -li "base.branch\|PR.*target\|pr-base-branch" {} \; 2>/dev/null
   ```
2. If found, extract the branch name (e.g. `develop`).
3. If NOT found, use `AskUserQuestion`:
   - Question: "What branch should this PR target?"
   - Options: `main`, `develop`, `Other`
4. Store the resolved base branch for Step 5.

### Step 2 — Check Working Tree

1. Run `git status --porcelain` (or `but status -fv` if GitButler project).
2. If uncommitted changes exist, **warn the user** and ask whether to proceed or wait.
3. Do NOT commit on their behalf.

### Step 3 — Gather Commits

1. Get current branch: `git branch --show-current` (or parse from `but status`).
2. List commits on this branch vs base:
   ```bash
   git log --oneline {base}..HEAD
   ```
3. Get the full diff for analysis:
   ```bash
   git diff {base}...HEAD --stat
   ```
4. If zero commits ahead, abort: "No commits to create a PR for."

### Step 4 — Check Remote & Push

1. Check if branch has a remote tracking ref:
   ```bash
   git rev-parse --abbrev-ref @{upstream} 2>/dev/null
   ```
2. Check if local is ahead of remote:
   ```bash
   git rev-list @{upstream}..HEAD --count 2>/dev/null
   ```
3. If no remote or local is ahead, ask user:
   - "Branch `{name}` is not pushed (or has {N} unpushed commits). Push now?"
   - If yes: use `but push {branch}` (GitButler) or `git push -u origin {branch}` (plain git).
   - If no: abort — can't create PR without remote branch.

### Step 5 — Generate PR Content

Analyze ALL commits (not just the latest) via `git log {base}..HEAD --format="%s%n%b"` and `git diff {base}...HEAD`.

#### Title Rules
- Under 70 chars. Lead with the highest-impact change, not a laundry list.
- Use conventional commit prefix matching the dominant change type.
- Bad: `perf: deduplicate cold-launch API calls and batch N+1 queries` (buries the lead)
- Good: `perf: fix 2x HTTP duplication, batch N+1 API calls`

#### Body Quality Rules

**Summary:**
- Lead with quantified before/after impact numbers (e.g. "Cold launch: ~70 HTTP calls → 14").
- 1-3 bullets on WHAT and WHY after the numbers.

**Changes:**
- Group by theme, NOT one row per file. Reviewers scan, not read.
- Bad: 14-row table listing every file individually.
- Good: 4-5 themed groups (e.g. "Feed/Profile reducers: batch stats + asset cache").
- Use inline code for file names within the description.

**Test plan:**
- Include HOW to verify, not just WHAT to verify. If verification requires a tool or setting (e.g. network logging, simulator config), say so.
- Bad: `- [ ] Verify ~14 HTTP calls` (how?)
- Good: `- [ ] Enable network logging (SCLogger .network category). Cold launch → feed: ~14 calls in console`

**Risk assessment:**
- Only claim mitigations that actually exist in the code. Never fabricate safeguards.
- Bad: "Timeout via Task.sleep(3s) fallback" when no such timeout exists.
- Good: "`markBatchCompleted()` always called in response handler (success or error path)"

**Breaking changes:**
- "None." if none. Otherwise list with migration steps.

#### Body Template

```markdown
## Summary

{1-line quantified impact.} {Optional second line of context.}

- {Bullet 1: highest-impact change}
- {Bullet 2}
- {Bullet 3 if needed}

## Changes

**{Theme 1}:**
- `File.swift` — {change}
- `OtherFile.swift` — {change}

**{Theme 2}:**
- `File.swift` — {change}

## Test plan

{1-line on how to observe/verify (tooling, logging, environment).}

- [ ] {Specific verifiable scenario with expected outcome}
- [ ] {Another scenario}

## Risk assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| {risk} | L/M/H | L/M/H | {mitigation that actually exists in code} |

## Breaking changes

None.
```

### Step 6 — Create PR

```bash
gh pr create --base {base_branch} --title "{title}" --body "$(cat <<'EOF'
{body}
EOF
)"
```

- Do NOT use `--draft` (always regular PR).
- Do NOT add `--label`, `--reviewer`, or `--assignee`.
- Print the returned PR URL to the user.

### Step 7 — Confirm

Report: PR URL, title, base branch, number of commits included.

## GitButler Detection

Check for GitButler workspace:
```bash
git log --oneline -1 --format="%s" | grep -q "GitButler"
```

If GitButler project:
- Use `but push {branch}` instead of `git push`
- Use `but status -fv` instead of `git status`
- Branch name from `but status` output (parse applied branches)

## Error Handling

| Error | Action |
|-------|--------|
| `gh` not installed | "Install GitHub CLI: https://cli.github.com/" |
| Not authenticated | "Run `gh auth login` first" |
| No commits ahead | "No commits to create a PR for" |
| PR already exists | Show existing PR URL, ask if user wants to update |
| Push rejected | Show error, suggest pull/rebase |
| Base branch not found on remote | Ask user to verify base branch name |

## Security

- Never include secrets, tokens, or credentials in PR body
- Redact file paths that contain `.env`, `credentials`, `secrets` from the Changes table
- This skill creates PRs. Does NOT merge, approve, or modify repository settings.
