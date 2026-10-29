# Chained Workflow

`github-pr-review-verify-fixes` is one node in a multi-skill review pipeline. Use this reference to understand entry points, exit conditions, and how to avoid spamming the PR.

## Full chain

```
                              fresh PR
                                 │
                                 ▼
                  a fresh code-review workflow <N>           [runs adversarial agents,
                                 │                            saves findings to plans/reports/]
                                 ▼
                  github-pr-review-publish                     [aggregates + classifies findings,
                                 │                            validates anchors,
                                 │                            posts ONE review with inline comments]
                                 ▼
                  ┌──── dev pushes follow-up commits ────┐
                  │                                       │
                  ▼                                       │
                  github-pr-review-verify-fixes                      │
                                 │                        │
                                 ▼                        │
                       ┌── all Fixed? ──┐                 │
                       │                │                 │
                      Yes               No                │
                       │                │                 │
                       ▼                └─────────────────┘
              human clicks Approve
                       │
                       ▼
                     merge
```

## Entry points

- **Fresh PR, no prior review by you:** start at a fresh code-review workflow.
- **You already reviewed but dev hasn't pushed yet:** wait. Nothing to do. (`list-followup-commits.sh` will return zero commits — the skill exits cleanly.)
- **You reviewed AND dev pushed at least one commit since:** start here, at `github-pr-review-verify-fixes`.
- **You reviewed, dev pushed, you already posted ONE follow-up for the current head SHA:** skill should ask before posting a duplicate. If the dev hasn't pushed since the last follow-up, there's nothing new to verify.

## Exit conditions

A `github-pr-review-verify-fixes` run ends in one of three states:

| State | Output | Next action |
|-------|--------|-------------|
| **All clear** | "Recommend merge" in top-level body | Human reviewer clicks Approve in GitHub UI. Skill does NOT auto-approve. |
| **Open items** | Per-finding Unaddressed/Partial comments + "Re-run after next commit batch" | Dev pushes more fixes, user re-invokes the skill. |
| **Cannot verify** | "Human review needed" + list of unverifiable items | User reads the listed items, decides whether to investigate manually or accept the ambiguity. |

The skill NEVER:
- Auto-loops or polls for new commits (the user controls cadence).
- Auto-approves (per safety policy).
- Auto-merges (out of scope).
- Edits code to "fix" remaining findings (out of scope — use a code-implementation skill).

## Anti-spam rules

Before posting, the skill MUST:

1. Check whether a prior follow-up review by the current user already exists for the CURRENT head SHA:
   ```bash
   gh api /repos/{owner}/{repo}/pulls/{pr}/reviews \
     --jq '.[] | select(.user.login == "<login>" and .commit_id == "<current_head>")'
   ```
   If present → ask the user whether to post a NEW follow-up review or amend the existing one (the latter is usually not needed; just exit and tell them the existing one is current).

2. Confirm `list-followup-commits.sh` returned ≥1 commit. If zero → exit without posting (nothing to say).

3. Confirm at least one finding produced a NEW verdict vs the prior follow-up (if any). If the verdict set hasn't changed → exit; reposting identical verdicts is spam.

## Decision matrix: when to re-run

| Since last follow-up… | New commits? | Same verdicts as last follow-up? | Re-run? |
|----------------------|--------------|----------------------------------|---------|
| No prior follow-up exists | yes | n/a | **Yes** |
| Prior follow-up exists | no | n/a | **No** — nothing changed |
| Prior follow-up exists | yes | yes (no progress) | Ask user — usually skip |
| Prior follow-up exists | yes | no (some Fixed) | **Yes** — celebrate progress, list remaining |

## Composition with companion skills

`github-pr-review-verify-fixes` uses a two-step submission:

1. **Top-level review** — assembles its own summary-only payload with jq (`event: COMMENT`, empty comments array), then submits through `gh api --input` as shown in SKILL.md. No publisher skill installation is required.
2. **Thread replies** — uses its own `post-thread-replies.sh` to post each verdict as an `in_reply_to` reply to the original finding comment. No anchor validation needed.

This eliminates the anchor re-validation step entirely. Verdicts appear threaded under the original findings, giving reviewers context in one place.

## Failure handoff

If this skill cannot proceed (no prior review, no commits, anchor explosion), tell the user the specific reason and the next action — don't bounce them around without direction.

| Reason | Tell the user |
|--------|---------------|
| No prior findings by current user | Run a fresh code-review workflow, then publish its findings with `github-pr-review-publish`. |
| Zero follow-up commits | Dev hasn't pushed yet. Re-run after they push. |
| Original comment deleted (thread reply fails) | Finding covered by top-level summary table. No action needed. |
| Duplicate follow-up for current head | Existing follow-up still applies. Re-run after next push. |
