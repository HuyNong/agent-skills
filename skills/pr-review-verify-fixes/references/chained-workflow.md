# Chained workflow

Use a fresh code-review workflow to discover findings, `pr-review-publish` to
publish them, and this skill to verify the selected prior review after changes.
Each package supplies its own helpers; no companion installation is required.

## Entry and scope

- Preserve an explicit review ID. Otherwise choose the active identity's substantive
  original review; inspect summary-only reviews semantically before selecting.
- Collect its full summary, General notes, original inline roots and cross-review
  replies. Validate the selected-review ledger before a completed preview or post.
- If the reviewed SHA is still the current head, report no new commits and stop a
  new batch. An incomplete previously approved batch can still resume.
- If the reviewed SHA disappeared after a rebase or history is capped, report
  follow-up history as indeterminate. A bounded comparison of current behavior may
  still be possible; do not invent a commit count or infer Fixed from an empty diff.
- Check the pinned current PR behavior through callers, dependencies, configuration,
  moves and tests. Do not expand this into a fresh review of unrelated code.

## Two independent conclusions

Report each selected finding as Fixed, Partial, Unaddressed or Cannot Verify.
Critical and Important findings require Fixed; Suggestions retain their nonblocking
policy. Unknown severity needs an explicit decision and must not become Suggestion.

Then collect read-only platform facts using
[merge-readiness.md](merge-readiness.md). A merge recommendation requires both gates:
the selected blocking findings are addressed AND applicable checks, effective approval,
rules, draft/state and mergeability are established for the stable evaluated snapshot.
An old approval can remain effective; required CI may run on a test merge SHA.
Missing or unsupported facts mean limited/unknown, even when all findings are Fixed.
The skill never approves, requests changes, resolves threads, merges, or edits code.

## Deliver and resume

Preview the complete findings table, evidence, readiness limits, exact reply bodies
and original thread targets. Obtain post authority or reuse it for unchanged text
and targets already authorized in the session.

Use this package's `post-followup-summary.sh` (COMMENT, no new inline comments)
and `post-thread-replies.sh` with one private receipt. See
[delivery-receipts.md](delivery-receipts.md). Summary-only findings stay in the table;
inline findings reply to their original roots.

Treat summary and every reply as separate items. A summary existing at this head
does not prove its replies succeeded. Resume posted items without resending them,
retry definitive rejections only after the cause is repaired, and reconcile unknown
writes by exact identity/body/target before retry. Unknown or ambiguous matches stop.
Do not reset a receipt to bypass a mismatch.

Read all pages when reconciling an existing follow-up. An unrelated review by the
same identity is not a duplicate. For an already complete, identical verdict set,
return its URLs rather than posting again. New text or targets need a new preview
and authority; snapshot drift needs re-evaluation before resuming.

## Failure handoff

| Condition | Report and next step |
|---|---|
| No substantive prior review | Ask for the intended review or use a fresh review workflow when requested. |
| No new commits, no partial batch | Report no new work; do not post another follow-up. |
| Incomplete collection or ledger | Retain artifacts and identify missing sources/verdicts; no completed-batch claim. |
| Deleted original thread | Keep its verdict in the summary, report reply failure explicitly; don't silently retarget. |
| Summary posted, some replies failed | Return the summary URL plus posted/failed/unknown items and receipt; resume missing items only. |
| Rules, CI or mergeability inaccessible | Keep finding verdicts; platform readiness remains limited/unknown. |
| Snapshot/body/identity/target drift | Stop, refresh affected evidence and reconfirm only changed wording or targets. |
