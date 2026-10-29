# Severity Rubric

How to classify a finding when aggregating PR-review reports, and how to render each severity as a badge in the inline-comment body.

## Badge mapping (paste verbatim into the comment body)

| Severity | Markdown |
|----------|----------|
| Critical | `![critical](https://img.shields.io/badge/Priority-Critical-red)` |
| Important | `![important](https://img.shields.io/badge/Priority-Important-orange)` |
| Suggestion | `![suggestion](https://img.shields.io/badge/Priority-Suggestion-blue)` |

These shields.io URLs are stable, cached, render on all GitHub clients (web, mobile, terminal), and don't depend on any private CDN.

In the top-level summary's **Findings** list, use emoji prefixes instead (badges are visually heavy when stacked):
- 🔴 **Critical**
- 🟠 **Important**
- 🔵 **Suggestion**

## Critical (blocking)

Stops merge. The PR cannot ship in current state without making the product worse, less safe, or actively misleading.

Examples:
- **Lying UI**: success toast / "saved" indicator on a no-op or failed action.
- **Data corruption**: optimistic update with no rollback on error → permanent client/server divergence.
- **Auth / authz break**: missing token check, broken session handling, leaked credentials in logs.
- **Security hole**: confirmed XSS (rendering unsanitized user HTML), SQL injection, prototype pollution, SSRF.
- **Regressions**: pre-existing feature stops working in this diff.
- **Unhandled rejection in user-visible flow**: `await fn()` with no `.catch`, no `try`, no boundary → blank screen on error.
- **Type unsoundness with runtime fallout**: `as Foo` cast on data the server can return with a wider shape.
- **Wrong-target ID handling**: precision loss / regex narrowness that routes user to wrong record.
- **Crash on common path**: `posts[0].id` with no undefined guard under `noUncheckedIndexedAccess`.

NOT critical:
- "Could be cleaner" / "consider refactor".
- Missing tests (Important unless the logic is risk-bearing).
- Style violations.

## Important (should-fix)

PR can ship without it but quality / maintainability suffers materially. Reviewer should expect a follow-up.

Examples:
- **Pattern violations** flagged by `CLAUDE.md` (e.g., bypassing Zustand source-of-truth, custom query client instead of shared one).
- **Dead code**: exported and never imported, or component mounted but interactive paths commented out.
- **Missing tests on risky logic**: pure functions with template interpolation, optimistic updates, cache-coherence code.
- **Race conditions on uncommon paths**: concurrent mutation snapshots, batch hook overwrites.
- **Error swallowing without user feedback**: `console.error` only, no toast.
- **Weak invariants** in new types: loose strings where discriminated unions would help, optional fields where non-null is required.
- **N+1 fetches**: per-item API calls instead of batch.
- **Memory leaks**: observers not cleaned up, listeners not removed.
- **Hardcoded values that need to flex**: localized strings without i18n, magic numbers in pagination.

## Suggestion (nice-to-have)

Style, polish, opportunistic refactor. Reviewer can land this PR and revisit later.

Examples:
- Leftover `console.log`.
- Naming inconsistencies (kebab vs camel within same feature folder).
- Re-exporting internals that should be private.
- Comment rot — `// TODO from 2 years ago`.
- Whitespace, formatting nits Biome/ESLint will catch.
- "Could extract this into a hook" when the duplication is 2 sites.

## Tie-breakers

When unsure between Critical and Important:
- Does the user **see the wrong thing**? → Critical.
- Does the user **see nothing** (silent failure that fails closed)? → Important unless the action was supposed to confirm success.
- Does it only **affect maintainers** (refactor, dead code)? → Important.
- Does **CI catch it** (lint, type, test)? → Suggestion (pre-existing tooling will warn).

When unsure between Important and Suggestion:
- Does it have a **`file:line` reference** and a concrete fix? → Important.
- Is it a **general observation** without a specific actionable site? → Suggestion (or drop).

## Severity Inflation

Common failure: dumping every reviewer finding into "Critical" because each agent thinks their finding is the most important. Resist.

Rules of thumb:
- Critical count > 8 in one PR → PR is broken; recommend trim/split in your Recommendation section.
- Critical count 0 with Important > 12 → PR is shippable with follow-ups; consider whether you're padding.
- A single reviewer flagging something as "critical" is not enough — verify against code or downgrade.
