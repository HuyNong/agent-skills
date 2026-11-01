# Top-Level Review Summary

The body posted as the review's overall message (above the inline comments). Keep it tight — details belong inline.

## Required structure

```markdown
## Code Review

<one paragraph: scope, top-line verdict, which reviewer agents ran>

### Findings
- 🔴 **<N> Critical** — must fix before merge
- 🟠 **<N> Important** — should fix
- 🔵 **<N> Suggestions** — nice-to-have

### Strengths
- <what works well>
- <pattern worth keeping>

### Recommendation
<ship as-is / trim scope / fix-then-merge / split PR>. Estimated remediation: <X hours/days>.

### Open Questions
- **<role>** (Backend / Product / Frontend Lead): <question>
- ...

### General notes (optional)
- <findings that couldn't be anchored to a specific file:line>
```

## Rules

- Start at `##` not `#`. GitHub renders `#` as oversized.
- Total length ≤ 30 lines. If longer, you're putting finding details in the wrong place — move them inline.
- Counts in **Findings** must match the number of inline comments by severity. The skill auto-derives these.
- **Strengths** is required — pure-negative reviews provoke defensive responses.
- **Recommendation** is required — gives a clear next-action.
- **Never use finding IDs (F1, F2, etc.) in the summary or recommendation.** GitHub reorders inline comments by file path — numbered IDs lose their meaning. Reference findings by descriptive name + `file:line` instead (e.g. "Fix the reconnect race (`mqtt.ts:67`) before merge").
- **Open Questions** only when there's genuine ambiguity needing stakeholder input. Skip if no questions.
- **General notes** only when a finding can't be anchored (file renamed in diff, cross-cutting concern, etc.). Most findings should be inline.

## Worked example

```markdown
## Code Review

Multi-agent review of PR #220 (notifications + tabs refactor): `code-reviewer`, `type-design-analyzer`, `silent-failure-hunter`, `pr-test-analyzer`. Tabs refactor is a clear win. Notifications feature has shippable bones but several user-visible silent failures and one likely-buggy ID regex block merge.

### Findings
- 🔴 **2 Critical** — must fix before merge
- 🟠 **4 Important** — should fix
- 🔵 **3 Suggestions** — nice-to-have

### Strengths
- Tabs refactor unifies 5 ad-hoc implementations — clear DRY win.
- DOMPurify correctly applied at render boundary.
- Query keys follow hierarchical convention from CLAUDE.md.

### Recommendation
Trim scope to **read-only notifications + tabs refactor**: remove the `NotificationMoreMenu` mount and friend-request buttons (or convert to disabled "coming soon" stubs), fix the lying success toast (`Notifications.tsx:46`) and the ID regex mismatch (`utils.ts:12`), add unit tests for `utils.ts`. Defer Zustand-store alignment to a follow-up. Estimated: 4–6 hours senior engineer.

### Open Questions
- **Backend**: is `markAsRead` server-side complete? Are `success: false` paths expected, or always-true in practice?
- **Product**: is this PR "view-only notifications" or "full interaction"?

### General notes
- The `notifications/api/index.ts` re-export surface couldn't be anchored to a single line — it spans the entire file. Consider marking GraphQL strings internal-only.
```

## Anti-patterns

- Mid-sentence severity badges in the summary. Badges belong on the per-finding inline comments, not the summary.
- Inlining the full text of every finding into the summary. The inline comments ARE the findings — the summary is just the orientation.
- "TL;DR" / "Executive summary" pleasantries. Get straight to verdict.
- Skipping Strengths "to save space". The 3 lines of positive framing are what makes the Critical items land.
- Using finding IDs like "F1", "F2" to reference inline comments. GitHub reorders by file path — the reader can't map IDs to comments. Use descriptive name + `file:line` instead.
