# Selected-review source accounting

Read the complete files indexed by `.context/inventory.json`. It contains the selected summary, original inline roots and replies linked to those roots even when their review IDs differ. Adjacent reviews or issue comments are not children of the selected review.

Create a ledger at the invocation scratch root. Example:

```json
{
  "scope": {"mode": "linked", "target": "reviews:11", "reason": "Verify selected review URL 11"},
  "sources": [
    {"key": "reviews:11", "read": true, "disposition": "finding", "finding_ids": ["general"]},
    {"key": "inline:42", "read": true, "disposition": "finding", "finding_ids": ["inline"]},
    {"key": "inline:43", "read": true, "disposition": "context", "reason": "Discussion explains caller fix", "finding_ids": []}
  ],
  "findings": [
    {"id": "general", "source_keys": ["reviews:11"], "status": "evaluated", "verdict": "Unaddressed", "evidence": ["tests/test_flow.py:12 - missing regression"]},
    {"id": "inline", "source_keys": ["inline:42"], "status": "evaluated", "verdict": "Fixed", "evidence": ["caller.py:8 - guarded input reaches unchanged callee safely"]}
  ]
}
```

Every inventory record appears once. Context needs a reason. Multiple concerns in a body map to separate findings; a summary/inline duplicate maps to the same finding only after semantic verification. Evidence records actual code at the evaluated snapshot, not only a developer's claim. Keep pending/blocked until inspected; incomplete selected work prevents a completed batch.

Default linked scope cannot omit its summary, original findings or thread context. Use explicit mode only for a user-limited subset with exact exclusions/reason. Whole-PR mode is not the verifier's default; do not expand to every review merely because other records exist.

Run `scripts/validate-review-coverage.sh` before the completed preview and before posting. It accepts Fixed, Partial, Unaddressed and Cannot Verify and verifies complete transport, source/finding accounting and evidence presence. It does not prove that the model discovered every natural-language concern or that verdicts are correct.

Summary-only findings have no inline root. Include their verdict/evidence in the top-level follow-up table. For inline findings, prepare one reply to the original root; contextual replies are not additional original findings unless they introduce an independent selected concern.

Unknown severity remains explicit. Do not omit an unanchored or unknown-severity concern from coverage or readiness simply because the original publisher could not attach it inline.
