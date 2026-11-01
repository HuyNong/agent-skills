"""Review-discovered boundaries: outbound fields, alias identity, complete pages."""
import json
from script_fixtures import PUBLISH, VERIFY, ScriptCase

PR = "/repos/acme/demo/pulls/7"


class ReviewBoundaryContracts(ScriptCase):
    def test_receipt_reply_never_posts_local_metadata(self):
        self.respond({"GET /user": {"login": "tester"},
            "GET " + PR: {"head": {"sha": "b" * 40}, "base": {"sha": "a" * 40}},
            "GET " + PR + "/comments": [],
            "POST " + PR + "/comments": {"id": 101, "html_url": "https://example.test/reply"}})
        verdicts = self.work / "verdicts"
        self.write_json(verdicts, "42.json", {"body": "Fixed with evidence", "in_reply_to": 42,
            "private_evidence": "LOCAL-ONLY-SENTINEL", "resolution": "fixed-on-pr"})
        result = self.run_script(VERIFY, "post-thread-replies.sh", "acme", "demo", 7,
                                 verdicts, self.work / "receipt.json")
        self.assertEqual(result.returncode, 0, result.stderr)
        posted = [json.loads(row)["payload"] for row in self.log.read_text().splitlines()
                  if json.loads(row)["key"].startswith("POST ")]
        self.assertEqual(posted, [{"body": "Fixed with evidence", "in_reply_to": 42}])

    def test_same_end_line_with_distinct_sides_or_ranges_stays_unresolved(self):
        variants = [("sides", [{"side": "LEFT"}, {"side": "RIGHT"}]),
                    ("ranges", [{"side": "RIGHT", "start_side": "RIGHT", "start_line": 1},
                                {"side": "RIGHT", "start_side": "RIGHT", "start_line": 2}])]
        for label, anchors in variants:
            with self.subTest(label=label):
                comments = self.work / label
                posted = []
                for i, anchor in enumerate(anchors):
                    finding = {"body": "Same claim", "path": "src/a.py", "line": 4, **anchor}
                    self.write_json(comments, f"{i}.json", finding)
                    posted.append({**finding, "id": 101 + i, "html_url": f"https://example.test/{101+i}"})
                self.respond({"GET " + PR + "/reviews/11/comments": posted})
                result = self.run_script(PUBLISH, "link-findings-in-body.sh", "acme", "demo", 7, 11, comments)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("unresolved=2", result.stdout)
                self.assertIn("ambiguous summary alias", result.stdout)
                self.assertNotIn("PUT ", self.log.read_text())

    def test_malformed_review_page_is_not_no_prior_review(self):
        self.respond({"GET /user": {"login": "tester"},
            "GET " + PR + "/reviews": {"_stdout": "null"}, "GET " + PR + "/comments": []})
        result = self.run_script(VERIFY, "fetch-prior-review.sh", 7, "acme", "demo")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("malformed", result.stderr)
        self.assertNotIn("no_prior_review", result.stderr)

    def test_malformed_comment_page_is_not_no_prior_review(self):
        self.respond({"GET /user": {"login": "tester"},
            "GET " + PR + "/reviews": [], "GET " + PR + "/comments": {"_stdout": "null"}})
        result = self.run_script(VERIFY, "fetch-prior-review.sh", 7, "acme", "demo")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("malformed", result.stderr)
