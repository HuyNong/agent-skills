"""Review creation and link updates are separate resumable delivery items."""
import json
from script_fixtures import PUBLISH, VERIFY, ScriptCase

PR = "/repos/acme/demo/pulls/7"
REVIEWS = PR + "/reviews"
HEAD = "b" * 40


class PublishRecoveryContracts(ScriptCase):
    def prepare(self, **overrides):
        self.finding = {"path": "a.py", "line": 2, "side": "RIGHT", "body": "Important defect"}
        self.body = "Check `a.py:2`."
        self.payload = self.write_json(self.work, "payload.json", {
            "commit_id": HEAD, "event": "COMMENT", "body": self.body, "comments": [self.finding]})
        self.receipt = self.work / "receipt.json"
        self.directory = self.work / "comments"
        self.write_json(self.directory, "01.json", self.finding)
        self.review = {"id": 11, "body": self.body, "state": "COMMENTED", "commit_id": HEAD,
                       "user": {"login": "tester"}, "html_url": "https://example.test/review/11"}
        self.comment = {**self.finding, "id": 101, "pull_request_review_id": 11,
                        "html_url": "https://example.test/comment/101"}
        self.respond({"GET /user": {"login": "tester"},
            "GET " + PR: {"head": {"sha": HEAD}, "base": {"sha": "a" * 40}},
            "GET " + REVIEWS: [], "POST " + REVIEWS: self.review,
            "GET " + REVIEWS + "/11/comments": [self.comment],
            "GET " + REVIEWS + "/11": self.review,
            "PUT " + REVIEWS + "/11": self.review, **overrides})

    def post(self):
        return self.run_script(PUBLISH, "post-review.sh", "acme", "demo", 7, self.payload, self.receipt)

    def link(self):
        return self.run_script(PUBLISH, "link-findings-in-body.sh", "acme", "demo", 7, 11,
                               self.directory, self.receipt)

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def test_link_rejection_resumes_without_another_review(self):
        self.prepare(**{"PUT " + REVIEWS + "/11#1": {"_status": 1, "_stderr": "HTTP 422"}})
        self.assertEqual(self.post().returncode, 0)
        self.assertEqual(self.link().returncode, 4)
        self.assertEqual(self.post().returncode, 0)
        retry = self.link()
        self.assertEqual(retry.returncode, 0, retry.stderr)
        writes = [call["key"] for call in self.calls() if call["key"].startswith(("POST ", "PUT "))]
        self.assertEqual(writes, ["POST " + REVIEWS, "PUT " + REVIEWS + "/11", "PUT " + REVIEWS + "/11"])

    def test_lost_review_response_requires_exact_inline_set(self):
        self.prepare()
        responses = json.loads(self.responses.read_text())
        responses.update({"POST " + REVIEWS: {"_status": 1, "_stderr": "connection lost"},
            "GET " + REVIEWS + "#2": [self.review], "GET " + PR + "/comments": [self.comment]})
        self.respond(responses)
        self.assertEqual(self.post().returncode, 6)
        result = self.post()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("reply_id=11", result.stdout)
        self.assertEqual(sum(c["key"] == "POST " + REVIEWS for c in self.calls()), 1)

    def test_malformed_collection_cannot_authorize_a_new_write(self):
        self.prepare(**{"GET " + REVIEWS: {"unexpected": "not a page"}})
        self.assertEqual(self.post().returncode, 3)
        self.assertFalse(any(c["key"].startswith("POST ") for c in self.calls()))

    def test_changed_source_manifest_blocks_resume(self):
        self.prepare()
        self.assertEqual(self.post().returncode, 0)
        receipt = json.loads(self.receipt.read_text())
        receipt["sources"] = [{"key": "review:55", "body_hash": "changed"}]
        self.receipt.write_text(json.dumps(receipt))
        self.assertEqual(self.post().returncode, 5)

    def test_followup_summary_is_comment_only_and_resumable(self):
        self.prepare()
        body = self.work / "summary.md"
        body.write_text("## Follow-up Review\nSelected findings fixed; platform unknown.")
        args = ("acme", "demo", 7, HEAD, body, self.receipt)
        for _ in range(2):
            result = self.run_script(VERIFY, "post-followup-summary.sh", *args)
            self.assertEqual(result.returncode, 0, result.stderr)
        writes = [c for c in self.calls() if c["key"].startswith("POST ")]
        self.assertEqual(len(writes), 1)
        self.assertEqual(writes[0]["payload"]["event"], "COMMENT")
        self.assertEqual(writes[0]["payload"]["comments"], [])
