# Verdict Rubric

The verdict is the heart of this skill. A bad verdict — especially a false-positive **Fixed** — destroys reviewer credibility and lets defects ship. Apply this rubric strictly.

## Four verdicts

| Verdict | Use when | Visual |
|---------|----------|--------|
| **Fixed** | The specific concern from the original comment is no longer reachable in the current code at the anchored location (or wherever it moved). | 🟢 green |
| **Partial** | The original defect is mitigated but a closely-related variant still exists, OR only some bullets of a multi-point finding were addressed. | 🟡 yellow |
| **Unaddressed** | No relevant change since the prior review's commit, OR the change does not affect the original concern. | 🔴 red |
| **Cannot Verify** | Evidence is ambiguous, the file/anchor was removed/refactored beyond recognition, or relevant context is unavailable. | ⚪ grey |

## Decision procedure

For each prior finding:

1. **Read the original finding body** — identify the *specific* defect (the noun phrase that came after "Bug:" / "Problem:" / similar). NOT the surrounding prose.
2. **Open the current file at the anchored path** (`git show <current_head>:<path>`). If the file is gone, jump to step 5.
3. **Read the diff** `git diff <prior_review_commit_id>..<current_head> -- <path>`. If empty → **Unaddressed**.
4. **Apply the test for each verdict in order:**
   - Is the original defect present in the current file? If yes → **Unaddressed** (even if the line changed).
   - Is the defect gone AND no related variant introduced? → **Fixed**.
   - Defect mitigated but a near-miss still reachable (e.g., one of three call sites still broken)? → **Partial**.
5. **If you can't determine:** file gone, refactored unrecognisably, behaviour now lives in a file you can't locate, or original finding too vague to verify → **Cannot Verify**.

## Hard rules

- **Line-change ≠ Fixed.** A rename, reformat, comment edit, or unrelated tweak at the anchor with the same defect still present is **Unaddressed**, not Fixed.
- **Moved fix is still Fixed.** If the relevant code moved to a different line / file and the defect is gone there too → Fixed; note the new location in the verdict body.
- **Removed path is Fixed.** If the entire code path containing the defect was deleted (function gone, branch unreachable) → Fixed with explanation "code path removed".
- **Refactor without verification is Cannot Verify.** "They restructured this whole module" is not evidence the defect is fixed — it's evidence you need to find where the behaviour went. If you can't find it → Cannot Verify.
- **Suggestion-block diff-apply alone is not Fixed.** If the original comment included a `suggestion` block and the dev committed it, you still verify the result reads correctly — sometimes a suggestion is partial.
- **One Critical Unaddressed blocks merge-readiness.** Recommend "Not yet" regardless of how many Fixed there are.

## Worked examples

### Example A — clear Fixed

**Original finding (Important):**
> Bare `catch {}` swallows retry-fetch errors. The retry `await doFetch(...)` inside the `try` block is also caught, so network failures during the retry are silently dropped.

**Code before fix (anchor `deferred-request.ts:149`):**
```ts
try {
  const clone = response.clone();
  const json = await clone.json();
  if (isPersistedQueryNotFound(json.errors)) {
    response = await doFetch('hash-query');   // ← inside catch scope
  }
} catch { /* ignore */ }
```

**Code after fix (anchor moved to `deferred-request.ts:142`):**
```ts
let probe: { errors?: ... } | null = null;
try {
  probe = await response.clone().json();
} catch {
  // probe failed; proceed with original response
}
if (probe?.errors && isPersistedQueryNotFound(probe.errors)) {
  response = await doFetch('hash-query');   // ← outside catch scope
}
```

**Verdict: Fixed.** The retry `doFetch` is now outside the catch block; its errors will propagate. The specific concern (swallowed retry errors) is no longer reachable.

### Example B — Partial

**Original finding (Important):**
> Two `ApiReportedPhone` types coexist: a broad codegen-derived one in `reported-phones.query.ts:15` and a slim manual one in `shared-types.ts:15`. Consumers split between them.

**Code after fix:**
- `shared-types.ts:15` deleted ✓
- `reported-phones.query.ts:15` unchanged ✓
- BUT `phone-search.query.ts` still imports `ApiReportedPhoneSummary` (a third type added during the fix) with overlapping shape.

**Verdict: Partial.** Original collision resolved; a near-variant introduced. Recommend follow-up to consolidate `ApiReportedPhoneSummary` with `ApiReportedPhone` or rename to make distinction explicit.

### Example C — Unaddressed

**Original finding (Important):**
> `as { total?: number }` cast laundered the type regression introduced by removing `ReportHistoriesPage` re-export.

**Code after follow-up commit:**
- File touched but only to remove an unrelated console.log.
- The `as { total?: number }` cast is still present unchanged.

**Verdict: Unaddressed.** The dev's commit doesn't touch this anchor or the concern. Re-flag.

### Example D — Cannot Verify

**Original finding (Important):**
> `report-histories.query.ts:99-106` — null upstream fabricates an empty page indistinguishable from "no reports".

**Code after follow-up:**
- Entire `report-histories.query.ts` deleted.
- A new `report-histories-v2.query.ts` exists with similar but reorganised logic.
- Cannot find the null-handling branch in the new file within reasonable search.

**Verdict: Cannot Verify.** Honest signal that human review is needed. In the verdict body, point reviewer to the new file and ask whether the null-handling concern still applies.

## Severity → merge-readiness

Compute merge recommendation from verdict counts:

| Open Critical | Open Important | Open Suggestion | Cannot Verify | Recommendation |
|---------------|----------------|-----------------|---------------|----------------|
| 0 | 0 | * | 0 | ✅ All clear — recommend merge |
| 0 | 0 | * | >0 | ⚠️ Cannot verify N items — human review needed |
| >0 | * | * | * | ⏳ Critical(s) open — block merge |
| 0 | >0 | * | * | ⏳ Important(s) open — re-run after next push |

Suggestion-level findings never block merge. They can ship as "shippable with N polish items tracked".

## Anti-patterns to refuse

- Marking a finding **Fixed** without reading the new code (just because the dev replied "done").
- Treating a passing CI run as evidence of correctness for a defect CI doesn't test.
- Inflating Partial to Fixed because the user wants the PR to merge.
- Demoting Critical Unaddressed to "advisory" to unblock merge — escalate to human instead.
