# Verdict Taxonomy

Pick exactly one verdict per review comment. Each has clear entry criteria — if more than one matches, prefer the one higher in this list (it's roughly ordered by signal strength).

---

## `CORRECT`

**Entry criteria** — ALL must hold:
- The reviewer points at real code that currently exists at the cited `path:line`.
- The claimed behaviour/risk reproduces when traced through the code (grep / read).
- The proposed fix (or an equivalent) is the right shape.
- The change does NOT touch a user-confirmed decision (see `LOCKED`).

**Action:** Acknowledge concisely and state the planned fix. Apply/commit it only with user authorization, following the skill workflow.

---

## `WRONG`

**Entry criteria** — at least one must hold:
- Code at cited line does not behave the way the reviewer claims.
- The reviewer references a symbol/file/API that doesn't exist (or has different shape).
- The "bug" cannot be reproduced through any code path you can trace.
- The reviewer's mental model maps to a different language / framework / project.

**Action:** Polite pushback. Cite `path:line` for every counter-claim. Avoid more than ~3 short paragraphs — if you're writing more, reconsider (see "think before defending" rule).

---

## `PARTIAL`

**Entry criteria**:
- The reviewer identifies a real issue, BUT
- The proposed fix is wrong, incomplete, or introduces a worse problem.

**Action:** Agree the underlying issue exists. Explain why their fix doesn't work. Propose alternative with `path:line` evidence.

---

## `STALE`

**Entry criteria**:
- The code at `path:line` no longer matches the `diff_hunk` the reviewer was looking at.
- The change has been addressed in a later commit on the branch.

**Action:** Link to the commit / current state. Quote the current code. Ask reviewer to re-check.

---

## `LOCKED`

**Entry criteria** — any one is sufficient:
- The reviewer's recommendation would change a value/design the user explicitly confirmed:
  - commit message says "per user decision" / "decided to X" / "user chose Y"
  - plans/ or docs/ has the decision recorded
  - core/recent memory contains the decision
  - prior chat in this session contains the user's explicit choice
- The reviewer asks to remove a feature/field/column the user mentioned explicitly.
- The reviewer asks to swap a library, threshold, or schema you know the user picked.

**Action:** STOP. Do not draft a reply. Surface to user:
- the user's original decision verbatim (with source: `file:line` or commit SHA or memory entry)
- the reviewer's reasoning
- the trade-off in 1-2 lines
- explicit ask: "keep current / change per reviewer / hybrid?"

Only after the user answers do you proceed to draft.

---

## `OPINION`

**Entry criteria**:
- The review is a style / preference / taste call.
- No objective evidence either way (e.g. "I'd inline this" vs "I'd extract a helper").
- Project doesn't have an enforced rule that resolves it (lint, style guide, code-standards.md).

**Action:** Acknowledge the trade-off in one sentence. Default to holding the current shape if change is non-trivial; defer to reviewer if change is trivial. Either way, no defending in paragraphs.

---

## `AMBIGUOUS`

**Entry criteria**:
- Reviewer's text is too short / unclear to evaluate (e.g. "?", "really?", "hmm").
- Reviewer references context only they have (a private discussion, a ticket you can't access).

**Action:** Ask one specific clarifying question. Don't speculate at length about what they meant.

---

## Confidence heuristics

Self-rate confidence per verdict 0–100%. Threshold for proceeding without asking the user:

| Verdict | Min confidence to proceed |
|---------|---------------------------|
| `CORRECT` | 85% |
| `WRONG` | 90% (higher bar — pushback is socially costlier than agreement) |
| `PARTIAL` | 85% |
| `STALE` | 95% (must be verifiable via commit log) |
| `LOCKED` | 70% (low bar — when unsure if a decision is locked, treat as locked and ask) |
| `OPINION` | 75% |
| `AMBIGUOUS` | n/a — always ask the reviewer, not the user |

If below threshold, surface the ambiguity to the user instead of forcing a verdict.
