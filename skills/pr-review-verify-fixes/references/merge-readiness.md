# Read-only readiness observations

Use the bundled collector and retain its raw before/after PR metadata, checks, active rules, classic protection visibility, errors and `readiness.json`. Outputs `eligible`, `blocked` or `unknown` describe observable platform conditions; they do not decide whether unrelated code is correct or authorize an action.

## Facts and boundaries

- `gh pr view` captures base/head, draft/open state, `mergeable`, `mergeStateStatus`, native `reviewDecision`, latest reviews, status rollup and potential test-merge SHA.
- `gh pr checks --required --json bucket,name,state,link,workflow` supplies required-check facts. Exit 8 means pending. API/auth failure is not "no required checks".
- Active branch rules are paginated; evaluate/disabled rules are excluded by GitHub. This is not proof classic branch protection was read. The collector separately checks branch/protection visibility.
- Native approval state is interpreted under the repository's rules. Do not invalidate every older approval by commit-ID inequality; stale-dismissal/latest-push/code-owner requirements determine effectiveness. Missing rule visibility stays unknown.
- Required checks can apply to the corresponding test merge commit rather than the head commit. Keep potential test-merge SHA and base/head association; inspect exact check SHA/source when native facts are ambiguous. Accepted success/skipped/neutral results follow GitHub semantics. Optional failing checks are disclosed separately; never call all CI green from required checks alone.
- Unknown/computing mergeability allows one bounded follow-up read, not a polling loop. Draft/closed/conflicting PR, pending/failed required checks, required reviews, unsupported rules or inaccessible facts cannot establish ready.

The collector conservatively recognizes pull-request/status-check rules and marks other unmodeled rule types unknown. It does not invent a complete policy engine, bypass permissions, infer "unprotected" from a 403/404, enqueue a merge queue, or satisfy a rule itself. Read additional authorized evidence when possible; do not silently override an unknown result.

## Combine with finding verification

Report two separate sections:

1. Selected review coverage, each verdict/evidence and severity, including General notes.
2. CI/approval/mergeability observations, visibility limits and observation snapshot.

Unresolved Critical/Important or unverifiable blocking/Unknown-severity items prevent a ready recommendation. Known Suggestion items remain disclosed nonblocking work. Even with every selected blocker Fixed, platform blocked/unknown prevents claiming ready. Platform eligible does not compensate for missing finding coverage.

When both gates pass, recommend human merge consideration for this observed snapshot and selected scope. Do not approve, request changes, merge, resolve or change settings. Refresh just before posting; changed summary wording requires authority covering the final text. Head stability alone does not establish that reviews/checks/rules remained unchanged. No read sequence is an atomic guarantee.

Sources: [gh checks](https://cli.github.com/manual/gh_pr_checks), [required status checks](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks), [protected branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches), [branch rules](https://docs.github.com/en/rest/repos/rules#get-rules-for-a-branch).
