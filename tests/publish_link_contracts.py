"""Expected-behavior contracts for the publisher body linker."""

import json

from script_fixtures import PUBLISH, ScriptCase


REVIEW = "/repos/acme/demo/pulls/7/reviews/11"
REVIEW_COMMENTS = REVIEW + "/comments"
PR_COMMENTS = "/repos/acme/demo/pulls/7/comments"


class PublishLinkContracts(ScriptCase):
    def review_comments_response(self, pages):
        return {"_stdout": "\n".join(json.dumps(page, ensure_ascii=False) for page in pages)}

    def run_linker(self, directory):
        return self.run_script(PUBLISH, "link-findings-in-body.sh", "acme", "demo", 7, 11, directory)

    def put_body(self):
        calls = [json.loads(line) for line in self.log.read_text().splitlines()]
        put = next(call for call in calls if call["key"] == "PUT " + REVIEW)
        return next(argument[5:] for argument in put["args"] if argument.startswith("body="))

    def test_paginated_arrays_flatten_and_link_more_than_thirty_comments(self):
        directory = self.work / "comments"
        local = []
        posted = []
        for number in range(1, 32):
            path = f"src/file-{number}.py"
            body = f"Finding {number}"
            finding = {"path": path, "line": number, "side": "RIGHT", "body": body}
            self.write_json(directory, f"{number:02d}.json", finding)
            local.append(finding)
            posted.append({**finding, "id": 1000 + number,
                           "html_url": f"https://example.test/comment-{number}"})

        self.respond({
            "GET " + REVIEW_COMMENTS: self.review_comments_response([posted[:30], posted[30:]]),
            "GET " + REVIEW: {"body": "Check `src/file-1.py:1` and `src/file-31.py:31`."},
            "PUT " + REVIEW: {"html_url": "https://example.test/review/11"},
        })
        result = self.run_linker(directory)

        self.assertEqual(result.returncode, 0, result.stderr)
        body = self.put_body()
        self.assertIn("[`src/file-1.py:1`](https://example.test/comment-1)", body)
        self.assertIn("[`src/file-31.py:31`](https://example.test/comment-31)", body)
        self.assertIn("review_id=11", result.stdout)
        self.assertIn("unresolved=0", result.stdout)

    def test_same_prefix_requires_full_body_and_anchor(self):
        directory = self.work / "comments"
        shared = "![important](badge)\n\n" + "Shared explanation context " * 5
        local = []
        posted = []
        for line, suffix in [(2, "first independent defect"), (3, "second independent defect")]:
            finding = {"path": "src/a.py", "line": line, "side": "RIGHT",
                       "body": shared + suffix}
            self.write_json(directory, f"{line}.json", finding)
            local.append(finding)
            posted.append({**finding, "id": 200 + line,
                           "html_url": f"https://example.test/comment-{line}"})

        self.respond({
            "GET " + REVIEW_COMMENTS: [posted[1], posted[0]],
            "GET " + REVIEW: {"body": "Check `a.py:2` and `a.py:3`."},
            "PUT " + REVIEW: {"html_url": "https://example.test/review/11"},
        })
        result = self.run_linker(directory)

        self.assertEqual(result.returncode, 0, result.stderr)
        body = self.put_body()
        self.assertIn("[`a.py:2`](https://example.test/comment-2)", body)
        self.assertIn("[`a.py:3`](https://example.test/comment-3)", body)
        self.assertNotIn("[`a.py:3`](https://example.test/comment-2)", body)

    def test_missing_review_anchors_are_recovered_from_pr_wide_comments(self):
        directory = self.work / "comments"
        body = "Same explanation"
        first = {"path": "src/a.py", "start_line": 10, "start_side": "RIGHT",
                 "line": 12, "side": "RIGHT", "body": body}
        second = {"path": "src/a.py", "start_line": 11, "start_side": "RIGHT",
                  "line": 13, "side": "RIGHT", "body": body}
        self.write_json(directory, "01.json", first)
        self.write_json(directory, "02.json", second)
        review_records = [
            {"id": 301, "path": "src/a.py", "body": body},
            {"id": 302, "path": "src/a.py", "body": body},
        ]
        full_records = [
            {**first, "id": 301, "html_url": "https://example.test/comment-range-1"},
            {**second, "id": 302, "html_url": "https://example.test/comment-range-2"},
        ]
        self.respond({
            "GET " + REVIEW_COMMENTS: review_records,
            "GET " + PR_COMMENTS: full_records,
            "GET " + REVIEW: {"body": "Check `a.py:12` and `a.py:13`."},
            "PUT " + REVIEW: {"html_url": "https://example.test/review/11"},
        })
        result = self.run_linker(directory)

        self.assertEqual(result.returncode, 0, result.stderr)
        body = self.put_body()
        self.assertIn("[`a.py:12`](https://example.test/comment-range-1)", body)
        self.assertIn("[`a.py:13`](https://example.test/comment-range-2)", body)
        calls = [json.loads(line) for line in self.log.read_text().splitlines()]
        self.assertIn("GET " + PR_COMMENTS, [call["key"] for call in calls])

    def test_duplicate_basename_keeps_ambiguous_alias_unlinked(self):
        directory = self.work / "comments"
        findings = [
            {"path": "src/one/config.py", "line": 8, "side": "RIGHT", "body": "One"},
            {"path": "src/two/config.py", "line": 8, "side": "RIGHT", "body": "Two"},
        ]
        for index, finding in enumerate(findings):
            self.write_json(directory, f"{index}.json", finding)
        posted = [{**finding, "id": 400 + index,
                   "html_url": f"https://example.test/comment-{index}"}
                  for index, finding in enumerate(findings)]
        self.respond({
            "GET " + REVIEW_COMMENTS: posted,
            "GET " + REVIEW: {"body": "Short `config.py:8`; full `src/one/config.py:8` and `src/two/config.py:8`."},
            "PUT " + REVIEW: {"html_url": "https://example.test/review/11"},
        })
        result = self.run_linker(directory)

        self.assertEqual(result.returncode, 0, result.stderr)
        body = self.put_body()
        self.assertIn("Short `config.py:8`", body)
        self.assertIn("[`src/one/config.py:8`](https://example.test/comment-0)", body)
        self.assertIn("[`src/two/config.py:8`](https://example.test/comment-1)", body)
        self.assertIn("unresolved=0", result.stdout)

    def test_unicode_regex_path_is_literal_and_relinking_is_idempotent(self):
        directory = self.work / "comments"
        finding = {"path": "src/[a+b] café.py", "line": 4, "side": "RIGHT", "body": "Unicode"}
        self.write_json(directory, "unicode.json", finding)
        posted = {**finding, "id": 500, "html_url": "https://example.test/unicode"}
        self.respond({
            "GET " + REVIEW_COMMENTS: [posted],
            "GET " + REVIEW + "#1": {"body": "Review `src/[a+b] café.py:4`."},
            "GET " + REVIEW + "#2": {"body": "Review [`src/[a+b] café.py:4`](https://example.test/unicode)."},
            "PUT " + REVIEW: {"html_url": "https://example.test/review/11"},
        })

        first = self.run_linker(directory)
        self.assertEqual(first.returncode, 0, first.stderr)
        linked_body = self.put_body()
        self.assertIn("[`src/[a+b] café.py:4`](https://example.test/unicode)", linked_body)

        second = self.run_linker(directory)
        self.assertEqual(second.returncode, 0, second.stderr)
        calls = [json.loads(line) for line in self.log.read_text().splitlines()]
        puts = [call for call in calls if call["key"] == "PUT " + REVIEW]
        self.assertEqual(len(puts), 1)
        self.assertIn("linked=0", second.stdout)

    def test_ambiguous_exact_matches_remain_unresolved_and_retain_review_id(self):
        directory = self.work / "comments"
        finding = {"path": "src/same.py", "line": 9, "side": "RIGHT", "body": "Duplicate"}
        self.write_json(directory, "01.json", finding)
        self.write_json(directory, "02.json", finding)
        posted = [
            {**finding, "id": 601, "html_url": "https://example.test/duplicate-1"},
            {**finding, "id": 602, "html_url": "https://example.test/duplicate-2"},
        ]
        self.respond({
            "GET " + REVIEW_COMMENTS: posted,
            "GET " + REVIEW: {"body": "Leave `same.py:9` unchanged."},
        })
        result = self.run_linker(directory)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("review_id=11", result.stdout)
        self.assertIn("unresolved=2", result.stdout)
        self.assertIn("same.py:9", result.stdout)
        calls = [json.loads(line) for line in self.log.read_text().splitlines()]
        self.assertFalse(any(call["key"] == "PUT " + REVIEW for call in calls))
