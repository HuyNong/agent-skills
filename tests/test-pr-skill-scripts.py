"""Regression tests for the shipped scripts, run directly to support this filename."""

import json
import re
import unittest

from script_fixtures import PUBLISH, RESPOND, ROOT, VERIFY, ScriptCase
from feedback_coverage_contracts import FeedbackCoverageContracts

FILES = "/repos/acme/demo/pulls/7/files"
COMMENTS = "/repos/acme/demo/pulls/7/comments"
REVIEWS = "/repos/acme/demo/pulls/7/reviews"
FINDING = {"path": "src/a.py", "line": 2, "side": "RIGHT", "body": "Lỗi\n```suggestion\nx\n```"}
PATCH = "@@ -1,3 +1,3 @@\n unchanged\n-old\n+new\n end\n"


class Contracts(ScriptCase):
    def payload(self, contents):
        directory = self.work / "comment files"
        directory.mkdir(exist_ok=True)
        for previous in directory.glob("*.json"):
            previous.unlink()
        for name, text in contents.items():
            (directory / name).write_text(text)
        body = self.work / "body.md"
        body.write_text("## Review\nĐã kiểm chứng\n")
        return self.run_script(PUBLISH, "build-review-payload.sh", "a" * 40, body, directory)

    def test_payload_roundtrip_and_empty(self):
        for contents, expected in [({}, []), ({"a space.json": json.dumps(FINDING)}, [FINDING])]:
            with self.subTest(contents=contents):
                result = self.payload(contents)
                self.assertEqual(result.returncode, 0, result.stderr)
                data = json.loads(result.stdout)
                self.assertEqual(data["comments"], expected)
                self.assertEqual(data["event"], "COMMENT")
                self.assertIn("Đã kiểm chứng", data["body"])

    def test_payload_rejects_invalid_json(self):
        for invalid in ["{", "", json.dumps(FINDING) * 2]:
            with self.subTest(invalid=invalid):
                result = self.payload({"good.json": json.dumps(FINDING), "bad.json": invalid})
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")

    def test_payload_rejects_invalid_fields(self):
        for bad in [{}, dict(FINDING, line=0), dict(FINDING, body={}), dict(FINDING, side="OTHER")]:
            with self.subTest(bad=bad):
                result = self.payload({"bad.json": json.dumps(bad)})
                self.assertNotEqual(result.returncode, 0)

    def test_anchor_sides_ranges_and_rejections(self):
        self.respond({"GET " + FILES: [{"filename": "src/a.py", "patch": PATCH}]})
        for fields, expected in [({}, 0), ({"side": "LEFT"}, 0),
                                 ({"start_line": 1, "line": 3}, 0), ({"line": 9}, 1),
                                 ({"start_line": 1, "start_side": "LEFT"}, 1)]:
            with self.subTest(fields=fields):
                directory = self.work / "anchors"
                self.write_json(directory, "finding.json", dict(FINDING, **fields))
                result = self.run_script(PUBLISH, "validate-anchors.sh", 7, directory, "acme", "demo")
                self.assertEqual(result.returncode, expected, result.stderr)

    def test_anchor_multirange_cannot_cross_hunks(self):
        patch = PATCH + "@@ -20 +20 @@\n-old\n+new\n"
        self.respond({"GET " + FILES: [{"filename": "src/a.py", "patch": patch}]})
        directory = self.work / "anchors"
        self.write_json(directory, "finding.json", dict(FINDING, start_line=2, line=20))
        result = self.run_script(PUBLISH, "validate-anchors.sh", 7, directory, "acme", "demo")
        self.assertEqual(result.returncode, 1, result.stderr)

    def test_extract_paginated_findings_and_unicode(self):
        comment = dict(FINDING, id=42, pull_request_review_id=11, original_line=2,
                       html_url="https://github.com/acme/demo/pull/7#discussion_r42")
        self.respond({"GET " + COMMENTS: {"_stdout": json.dumps([comment]) + "\n" + json.dumps([dict(comment, id=43)])}})
        output = self.work / "findings"
        result = self.run_script(VERIFY, "extract-findings.sh", 7, 11, output, "acme", "demo")
        self.assertEqual(result.returncode, 0, result.stderr)
        files = sorted(output.glob("*.json"))
        self.assertEqual(len(files), 2)
        self.assertEqual(json.loads(files[0].read_text())["body"], FINDING["body"])

    def test_extract_empty_and_malformed_response(self):
        for response, success in [([], True), ({"_stdout": "{"}, False)]:
            with self.subTest(response=response):
                self.respond({"GET " + COMMENTS: response})
                result = self.run_script(VERIFY, "extract-findings.sh", 7, 11, self.work / "out", "acme", "demo")
                self.assertEqual(result.returncode == 0, success, result.stderr)

    def test_prior_review_ignores_summary_and_thread_reply_reviews(self):
        original = {"id": 11, "user": {"login": "tester"}, "submitted_at": "2026-01-01", "commit_id": "a" * 40, "state": "COMMENTED"}
        summary = dict(original, id=12, submitted_at="2026-01-02")
        reply = dict(original, id=13, submitted_at="2026-01-03", commit_id="b" * 40)
        self.respond({"GET /user": {"login": "tester"}, "GET " + REVIEWS: [original, summary, reply],
                      "GET " + COMMENTS: [{"pull_request_review_id": 11},
                                          {"pull_request_review_id": 13, "in_reply_to_id": 42}]})
        result = self.run_script(VERIFY, "fetch-prior-review.sh", 7, "acme", "demo")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("review_id=11\n", result.stdout)

    def test_prior_without_inline_findings_is_explicit(self):
        self.respond({"GET /user": {"login": "tester"}, "GET " + REVIEWS: [], "GET " + COMMENTS: []})
        result = self.run_script(VERIFY, "fetch-prior-review.sh", 7, "acme", "demo")
        self.assertEqual(result.returncode, 3, result.stderr)

    def test_thread_partial_failure_preserves_counts(self):
        directory = self.work / "verdicts"
        self.write_json(directory, "01.json", {"in_reply_to": 42, "body": "Fixed\nĐã sửa"})
        self.write_json(directory, "02.json", {"in_reply_to": 43, "body": "Not yet"})
        self.respond({"POST " + COMMENTS + "#1": {"id": 100},
                      "POST " + COMMENTS + "#2": {"_status": 1, "_stdout": "deleted comment"}})
        result = self.run_script(VERIFY, "post-thread-replies.sh", "acme", "demo", 7, directory)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("total=2 ok=1 fail=1", result.stdout)
        self.assertEqual(json.loads(self.log.read_text().splitlines()[0])["payload"]["body"], "Fixed\nĐã sửa")

    def test_invalid_thread_does_not_hide_other_results(self):
        directory = self.work / "verdicts"
        self.write_json(directory, "01.json", {})
        self.write_json(directory, "02.json", {"in_reply_to": 43, "body": "Fixed"})
        self.respond({"POST " + COMMENTS: {"id": 100}})
        result = self.run_script(VERIFY, "post-thread-replies.sh", "acme", "demo", 7, directory)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("total=2 ok=1 fail=1", result.stdout)

    def test_missing_github_cli_has_actionable_failure(self):
        (self.bin / "gh").unlink()
        self.process_environment["PATH"] = str(self.bin)
        result = self.run_script(VERIFY, "post-thread-replies.sh", "acme", "demo", 7, self.work)
        self.assertEqual(result.returncode, 2)
        self.assertIn("gh required", result.stderr)

    def test_post_review_exposes_api_error_body(self):
        payload = self.write_json(self.work, "payload.json", {"event": "COMMENT"})
        self.respond({"POST " + REVIEWS: {"_status": 1, "_stdout": "anchor could not be resolved"}})
        result = self.run_script(PUBLISH, "post-review.sh", "acme", "demo", 7, payload)
        self.assertEqual(result.returncode, 4, result.stderr)
        self.assertIn("anchor could not be resolved", result.stderr)

    def test_review_urls_and_untrusted_hosts(self):
        for url, expected in [("https://github.com/acme/demo/pull/7#discussion_r42", 0),
                              ("https://github.com/acme/demo/pull/7?diff=split#discussion_r42", 0),
                              ("https://api.github.com/repos/acme/demo/pulls/7/comments/42", 0),
                              ("https://notgithub.com/acme/demo/pull/7#discussion_r42", 1)]:
            with self.subTest(url=url):
                result = self.run_script(RESPOND, "parse-review-url.sh", url)
                self.assertEqual(result.returncode, expected, result.stderr)
                if expected == 0:
                    self.assertIn("comment_id=42\n", result.stdout)

    def test_release_packages_are_self_contained(self):
        names = {"github-pr-create", PUBLISH, RESPOND, VERIFY}
        self.assertEqual({p.name for p in (ROOT / "skills").iterdir() if p.is_dir()}, names)
        for name in names:
            folder = ROOT / "skills" / name
            self.assertEqual((folder / "LICENSE").read_text(), (ROOT / "LICENSE").read_text())
            body = (folder / "SKILL.md").read_text()
            self.assertIn("name: " + name + "\n", body)
            self.assertNotRegex(body, r"CLAUDE_JOB_DIR|AskUserQuestion|~/.claude|huynong[-:]")
            for relative in set(re.findall(r"(?:scripts|references)/[a-z0-9-]+\.(?:sh|md|json)", body)):
                self.assertTrue((folder / relative).is_file(), relative)


if __name__ == "__main__":
    unittest.main(verbosity=2)
