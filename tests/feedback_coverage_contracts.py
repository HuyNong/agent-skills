"""Feedback collection and source-accounting regressions; no GitHub writes."""
import copy
import json

from script_fixtures import RESPOND, ScriptCase

PREFIX = "/repos/acme/demo"
REVIEWS = PREFIX + "/pulls/7/reviews"
INLINE = PREFIX + "/pulls/7/comments"
ISSUES = PREFIX + "/issues/7/comments"


class FeedbackCoverageContracts(ScriptCase):
    def feedback(self):
        review = {"id": 11, "body": "", "user": {"login": "reviewer"}}
        comments = [{"id": 73 + i, "body": f"Concern {i + 1}", "path": "src/a.py",
                     "line": i + 1, "pull_request_review_id": 11} for i in range(4)]
        issue = {"id": 42, "body": "<details><summary>Concern 1</summary>Full details</details>"}
        return {"GET " + REVIEWS: [review], "GET " + INLINE: comments, "GET " + ISSUES: [issue]}

    def collect(self, responses=None):
        self.respond(self.feedback() if responses is None else responses)
        out = self.work / "feedback"
        result = self.run_script(RESPOND, "fetch-pr-feedback.sh", "acme", "demo", 7, out)
        return result, out

    def coverage(self, out):
        inventory = json.loads((out / "inventory.json").read_text())
        sources = []
        findings = [{"id": f"F{i + 1}", "source_keys": [f"inline:{73 + i}"],
                     "status": "evaluated", "verdict": "CORRECT", "evidence": [f"src/a.py:{i + 1}"]}
                    for i in range(4)]
        findings[0]["source_keys"].append("issues:42")
        for record in inventory["records"]:
            key = record["key"]
            ids = [f["id"] for f in findings if key in f["source_keys"]]
            sources.append({"key": key, "read": True,
                            "disposition": "finding" if ids else "context",
                            "reason": "Review metadata or existing discussion", "finding_ids": ids})
        return {"scope": {"mode": "pr", "reason": "Handle all PR feedback"},
                "sources": sources, "findings": findings}

    def validate(self, out, value):
        path = self.write_json(self.work, "coverage.json", value)
        return self.run_script(RESPOND, "validate-feedback-coverage.sh", out / "inventory.json", path)

    def test_collects_all_pages_and_preserves_full_bodies(self):
        responses = self.feedback()
        comments = responses["GET " + INLINE]
        comments.extend({"id": 100 + i, "body": f"Extra finding {i}", "pull_request_review_id": 11}
                        for i in range(31))
        comments[0]["body"] = "Đầy đủ\n" + "Long body <details> quote \\\"\n" * 2500
        responses["GET " + INLINE] = {"_stdout": json.dumps(comments[:2]) + "\n" + json.dumps(comments[2:])}
        result, out = self.collect(responses)
        self.assertEqual(result.returncode, 0, result.stderr)
        inventory = json.loads((out / "inventory.json").read_text())
        self.assertTrue(inventory["complete"])
        self.assertEqual(inventory["counts"], {"reviews": 1, "inline": 35, "issues": 1, "root_threads": 35})
        self.assertEqual(json.loads((out / "items/inline-73.json").read_text())["body"], comments[0]["body"])
        self.assertNotIn("Long body", result.stdout)
        calls = [json.loads(line) for line in self.log.read_text().splitlines()]
        self.assertEqual(len(calls), 3)
        self.assertTrue(all("--paginate" in call["args"] and call["key"].startswith("GET ") for call in calls))

    def test_failed_later_page_retains_incomplete_state(self):
        responses = self.feedback()
        partial = json.dumps(responses["GET " + INLINE][:2])
        responses["GET " + INLINE] = {"_status": 1, "_stdout": partial}
        result, out = self.collect(responses)
        self.assertEqual(result.returncode, 3)
        inventory = json.loads((out / "inventory.json").read_text())
        self.assertFalse(inventory["complete"])
        self.assertFalse(inventory["sources"]["inline"])
        self.assertTrue(inventory["sources"]["issues"])
        self.assertEqual((out / "inline-pages.json").read_text(), partial)
        self.assertNotEqual(self.validate(out, self.coverage(out)).returncode, 0)

    def test_invalid_page_or_body_cannot_appear_empty_complete(self):
        for i, response in enumerate([{"_stdout": "{"}, {"_stdout": ""}, {"_stdout": "{}"}, [{"id": 73}]]):
            with self.subTest(response=response):
                responses = self.feedback()
                responses["GET " + INLINE] = response
                self.respond(responses)
                out = self.work / f"invalid-{i}"
                result = self.run_script(RESPOND, "fetch-pr-feedback.sh", "acme", "demo", 7, out)
                self.assertEqual(result.returncode, 3, result.stderr)
                self.assertFalse(json.loads((out / "inventory.json").read_text())["complete"])

    def test_reply_records_retain_root_and_missing_root_is_incomplete(self):
        responses = self.feedback()
        responses["GET " + INLINE].append({"id": 80, "body": "Discussion", "in_reply_to_id": 73})
        result, out = self.collect(responses)
        self.assertEqual(result.returncode, 0, result.stderr)
        inventory = json.loads((out / "inventory.json").read_text())
        reply = next(r for r in inventory["records"] if r["id"] == 80)
        self.assertEqual(reply["root_comment_id"], 73)
        self.assertTrue(reply["is_reply"])
        self.assertEqual(self.validate(out, self.coverage(out)).returncode, 0)
        responses["GET " + INLINE] = responses["GET " + INLINE][1:]
        self.respond(responses)
        missing = self.work / "missing"
        result = self.run_script(RESPOND, "fetch-pr-feedback.sh", "acme", "demo", 7, missing)
        self.assertEqual(result.returncode, 3)
        self.assertEqual(json.loads((missing / "inventory.json").read_text())["missing_root_ids"], [73])

    def test_existing_inventory_is_not_overwritten(self):
        result, out = self.collect()
        original = (out / "inventory.json").read_bytes()
        result = self.run_script(RESPOND, "fetch-pr-feedback.sh", "acme", "demo", 7, out)
        self.assertEqual(result.returncode, 2)
        self.assertEqual((out / "inventory.json").read_bytes(), original)

    def test_coverage_accepts_four_findings_with_duplicate_summary(self):
        result, out = self.collect()
        result = self.validate(out, self.coverage(out))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["findings"], 4)
        self.assertEqual(json.loads(result.stdout)["read"], 6)

    def test_missing_unread_pending_and_unmapped_findings_are_rejected(self):
        _, out = self.collect()
        good = self.coverage(out)
        bad = []
        omitted = copy.deepcopy(good); omitted["sources"].pop(); bad.append(omitted)
        unread = copy.deepcopy(good); unread["sources"][0]["read"] = False; bad.append(unread)
        pending = copy.deepcopy(good); pending["findings"][1]["status"] = "pending"; bad.append(pending)
        unmapped = copy.deepcopy(good); unmapped["findings"][0]["source_keys"] = []; bad.append(unmapped)
        unknown = copy.deepcopy(good); unknown["sources"][1]["finding_ids"] = ["unknown"]; bad.append(unknown)
        duplicate = copy.deepcopy(good); duplicate["sources"].append(duplicate["sources"][0]); bad.append(duplicate)
        for value in bad:
            with self.subTest(value=value):
                self.assertEqual(self.validate(out, value).returncode, 3)

    def test_explicit_scope_excludes_other_findings_but_pr_scope_cannot(self):
        _, out = self.collect()
        coverage = self.coverage(out)
        coverage["scope"] = {"mode": "explicit", "reason": "Only evaluate Concern 1"}
        coverage["findings"] = coverage["findings"][:1]
        for source in coverage["sources"]:
            if source["finding_ids"] and source["finding_ids"] != ["F1"]:
                source.update(disposition="out_of_scope", read=False, finding_ids=[], reason="User selected only Concern 1")
        result = self.validate(out, coverage)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["excluded"], 3)
        coverage["scope"]["mode"] = "pr"
        self.assertEqual(self.validate(out, coverage).returncode, 3)

    def test_review_submission_and_pr_urls_keep_target_identity(self):
        for suffix, expected in [("#pullrequestreview-11", "kind=review-summary\n"),
                                 ("", "kind=pr\n"), ("/files", "kind=pr\n"),
                                 ("#discussion_r73", "comment_id=73\n")]:
            with self.subTest(suffix=suffix):
                result = self.run_script(RESPOND, "parse-review-url.sh", "https://github.com/acme/demo/pull/7" + suffix)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(expected, result.stdout)
                if "pullrequestreview" in suffix:
                    self.assertIn("review_id=11\n", result.stdout)
        invalid = self.run_script(RESPOND, "parse-review-url.sh", "https://github.com/acme/demo/pull/7#unrecognised")
        self.assertNotEqual(invalid.returncode, 0)

    def test_linked_review_cannot_exclude_one_of_its_findings(self):
        _, out = self.collect()
        coverage = self.coverage(out)
        coverage["scope"] = {"mode": "linked", "target": "reviews:11", "reason": "Review URL 11"}
        self.assertEqual(self.validate(out, coverage).returncode, 0)
        selected = next(s for s in coverage["sources"] if s["key"] == "inline:75")
        selected.update(disposition="out_of_scope", read=False, finding_ids=[], reason="Skip this comment")
        coverage["findings"] = [f for f in coverage["findings"] if f["id"] != "F3"]
        result = self.validate(out, coverage)
        self.assertEqual(result.returncode, 3)
        self.assertIn("linked scope omits", result.stderr)

    def test_linked_comment_allows_other_feedback_exclusions_but_keeps_target(self):
        _, out = self.collect()
        coverage = self.coverage(out)
        coverage["scope"] = {"mode": "linked", "target": "issues:42", "reason": "Issue comment URL 42"}
        coverage["findings"] = coverage["findings"][:1]
        for source in coverage["sources"]:
            if source["finding_ids"] and source["finding_ids"] != ["F1"]:
                source.update(disposition="out_of_scope", read=False, finding_ids=[], reason="Outside linked comment")
        self.assertEqual(self.validate(out, coverage).returncode, 0)
        coverage["scope"]["target"] = "issues:999"
        self.assertEqual(self.validate(out, coverage).returncode, 3)
