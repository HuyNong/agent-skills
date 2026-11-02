"""Reject malformed reply bodies before an external write can occur."""
import json
import subprocess
from script_fixtures import RESPOND, ROOT, ScriptCase

BADGES = {
    "Accepted": "blue", "Fixed": "brightgreen", "Rejected": "blue",
    "Partial": "yellow", "Stale": "lightgrey", "Locked": "red",
    "Noted": "lightgrey", "Needs_Info": "orange",
}


def reply(status, text="Verified evidence."):
    label = status.replace("_", " ")
    return f"![{label}](https://img.shields.io/badge/Status-{status}-{BADGES[status]})\n\n{text}"


class ReplyBadgeContracts(ScriptCase):
    def validate(self, text, *args):
        body = self.work / "reply.md"
        body.write_text(text)
        return self.run_script(RESPOND, "validate-reply-body.sh", body, *args)

    def test_canonical_badges_and_verdict_mapping(self):
        for status, verdict, state in [
            ("Accepted", "CORRECT", "planned"), ("Accepted", "CORRECT", "fixed-local"),
            ("Fixed", "CORRECT", "fixed-on-pr"), ("Rejected", "WRONG", ""),
            ("Partial", "PARTIAL", "fixed-on-pr"), ("Stale", "STALE", ""),
            ("Locked", "LOCKED", ""), ("Noted", "OPINION", ""),
            ("Accepted", "OPINION", "planned"), ("Needs_Info", "AMBIGUOUS", "")]:
            with self.subTest(status=status, verdict=verdict, state=state):
                result = self.validate(reply(status), verdict, state)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_missing_malformed_and_mismatched_badges(self):
        for text, args in [
            ("Fixed — done", ()), ("\n" + reply("Fixed"), ()),
            (reply("Fixed").replace("https:", "http:"), ()),
            (reply("Fixed").replace("brightgreen", "red"), ()),
            (reply("Fixed").replace("\n\n", "\n"), ()),
            (reply("Fixed", ""), ()),
            (reply("Fixed"), ("PARTIAL", "fixed-on-pr")),
            (reply("Fixed"), ("CORRECT", "planned")),
            (reply("Accepted"), ("CORRECT", "fixed-on-pr")),
            (reply("Fixed"), ("CORRECT", "")),
            (reply("Partial"), ("UNKNOWN", ""))]:
            with self.subTest(text=text, args=args):
                self.assertEqual(self.validate(text, *args).returncode, 2)

    def test_invalid_post_bodies_stop_before_network_and_receipts(self):
        body = self.work / "reply.md"
        receipt = self.work / "receipt.json"
        for text, verdict, state in [("Fixed — done", "", ""),
                                     (reply("Fixed"), "PARTIAL", "fixed-on-pr")]:
            body.write_text(text)
            for track in [False, True]:
                for script, args in [
                    ("post-reply.sh", ["acme", "demo", 7, 42, "review", body]),
                    ("post-reply.sh", ["acme", "demo", 7, 42, "issue", body]),
                    ("post-new-inline.sh", ["acme", "demo", 7, "b" * 40, "src/a.py", 2, body])]:
                    result = self.run_script(RESPOND, script, *args,
                        receipt if track else "", "reply", verdict, state)
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertFalse(self.log.exists())
                    self.assertFalse(receipt.exists())

    def test_direct_receipt_payload_cannot_bypass_format_check(self):
        payload = self.write_json(self.work, "payload.json", {"body": "Fixed — done"})
        result = subprocess.run(["/bin/bash", "-c",
            'source "$1"; receipt_post "$2" respond acme demo 7 direct /repos/acme/demo/pulls/7/comments "$3"',
            "test", str(ROOT / "skills" / RESPOND / "scripts/review-receipt.sh"),
            str(self.work / "receipt.json"), str(payload)],
            cwd=self.work, env=self.process_environment, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertFalse(self.log.exists())
        self.assertFalse((self.work / "receipt.json").exists())

    def test_valid_partial_body_is_sent_unchanged(self):
        body = self.work / "reply.md"
        text = reply("Partial", "Alternative fix verified on the PR; proposal accepted only in part.")
        body.write_text(text)
        self.respond({"GET /user": {"login": "tester"},
                      "GET /repos/acme/demo/pulls/7": {"head": {"sha": "b" * 40}},
                      "GET /repos/acme/demo/pulls/7/comments": [],
                      "POST /repos/acme/demo/pulls/7/comments/42/replies": {
            "id": 100, "html_url": "https://example.test/100"}})
        result = self.run_script(RESPOND, "post-reply.sh", "acme", "demo", 7,
                                 42, "review", body, self.work / "receipt.json", "reply", "PARTIAL", "fixed-on-pr")
        self.assertEqual(result.returncode, 0, result.stderr)
        writes = [json.loads(line) for line in self.log.read_text().splitlines()
                  if json.loads(line)["key"].startswith("POST ")]
        self.assertEqual(len(writes), 1)
        self.assertEqual(writes[0]["payload"]["body"], text)
