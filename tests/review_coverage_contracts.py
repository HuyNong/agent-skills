"""Selected-review context includes summaries and cross-review thread replies."""
import json
from script_fixtures import VERIFY, ScriptCase

PR = "/repos/acme/demo/pulls/7"


class ReviewCoverageContracts(ScriptCase):
    def collect(self):
        self.respond({"GET " + PR + "/reviews/11": {"id": 11, "body": "General note: caller is unsafe"},
                      "GET " + PR + "/comments": [
                          {"id": 42, "body": "Inline bug", "path": "a.py", "line": 2, "pull_request_review_id": 11},
                          {"id": 43, "body": "Fix moved to caller", "in_reply_to_id": 42, "pull_request_review_id": 12},
                          {"id": 44, "body": "Other review", "pull_request_review_id": 99}]})
        out = self.work / "findings"
        result = self.run_script(VERIFY, "extract-findings.sh", 7, 11, out, "acme", "demo")
        self.assertEqual(result.returncode, 0, result.stderr)
        return out

    def ledger(self):
        return {"scope": {"mode": "linked", "target": "reviews:11", "reason": "Review 11 selected"},
                "sources": [
                    {"key": "reviews:11", "read": True, "disposition": "finding", "finding_ids": ["general"]},
                    {"key": "inline:42", "read": True, "disposition": "finding", "finding_ids": ["inline"]},
                    {"key": "inline:43", "read": True, "disposition": "context", "reason": "Fix discussion", "finding_ids": []}],
                "findings": [
                    {"id": "general", "source_keys": ["reviews:11"], "status": "evaluated", "verdict": "Unaddressed", "evidence": ["caller.py:3 unsafe"]},
                    {"id": "inline", "source_keys": ["inline:42"], "status": "evaluated", "verdict": "Fixed", "evidence": ["caller.py:8 guarded"]}]}

    def test_summary_and_reply_are_preserved_without_extra_roots(self):
        out = self.collect()
        self.assertEqual([p.name for p in out.glob("*.json")], ["42.json"])
        inventory = json.loads((out / ".context/inventory.json").read_text())
        self.assertEqual({s["key"] for s in inventory["records"]}, {"reviews:11", "inline:42", "inline:43"})
        self.assertEqual(json.loads((out / ".context/items/inline-43.json").read_text())["body"], "Fix moved to caller")

    def test_general_note_cannot_be_silently_omitted(self):
        out = self.collect()
        ledger = self.ledger()
        path = self.write_json(self.work, "ledger.json", ledger)
        args = (out / ".context/inventory.json", path)
        self.assertEqual(self.run_script(VERIFY, "validate-review-coverage.sh", *args).returncode, 0)
        ledger["sources"].pop(0)
        path.write_text(json.dumps(ledger))
        self.assertEqual(self.run_script(VERIFY, "validate-review-coverage.sh", *args).returncode, 3)

    def test_summary_only_prior_review_can_be_selected(self):
        self.respond({"GET /user": {"login": "tester"}, "GET " + PR + "/comments": [],
            "GET " + PR + "/reviews": [{"id": 11, "body": "General note: real concern", "user": {"login": "tester"},
                                       "submitted_at": "2026-11-01", "commit_id": "a" * 40}]})
        result = self.run_script(VERIFY, "fetch-prior-review.sh", 7, "acme", "demo", 11)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("review_id=11", result.stdout)

    def test_rebased_anchor_is_not_all_followup_commits(self):
        self.respond({"GET " + PR + "/commits": [{"sha": "b" * 40}]})
        result = self.run_script(VERIFY, "list-followup-commits.sh", 7, "a" * 40, "acme", "demo")
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertEqual(result.stdout, "")
