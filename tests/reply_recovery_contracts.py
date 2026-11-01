"""Delivery receipts must survive uncertainty without replaying successful writes."""
import json
import stat
import subprocess
import time

from script_fixtures import RESPOND, VERIFY, ROOT, ScriptCase

PR = "/repos/acme/demo/pulls/7"
ROOT_REPLY = PR + "/comments/42/replies"
HEAD = "b" * 40


class ReplyRecoveryContracts(ScriptCase):
    def setup_delivery(self, **responses):
        self.respond({"GET /user": {"login": "tester"},
                      "GET " + PR: {"head": {"sha": HEAD}, "base": {"sha": "a" * 40}},
                      "GET " + PR + "/comments": [],
                      "POST " + ROOT_REPLY: {"id": 100, "html_url": "https://example.test/100"},
                      **responses})
        self.body = self.work / "body.txt"
        self.body.write_text("Accepted. Fix is still local.")
        self.receipt = self.work / "receipt.json"

    def deliver(self):
        return self.run_script(RESPOND, "post-reply.sh", "acme", "demo", 7, 42, "review",
                               self.body, self.receipt, "reply-42")

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def test_success_receipt_skips_replay_and_is_private(self):
        self.setup_delivery()
        for _ in range(2):
            result = self.deliver()
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sum(c["key"].startswith("POST ") for c in self.calls()), 1)
        self.assertEqual(json.loads(self.receipt.read_text())["items"]["reply-42"]["state"], "posted")
        self.assertEqual(stat.S_IMODE(self.receipt.stat().st_mode), 0o600)
        self.assertFalse(self.receipt.with_suffix(".json.lock").exists())

    def test_lost_response_is_adopted_from_readback(self):
        self.setup_delivery(**{
            "POST " + ROOT_REPLY: {"_status": 1, "_stdout": "connection lost"},
            "GET " + PR + "/comments#2": [{"id": 100, "html_url": "https://example.test/100",
                "user": {"login": "tester"}, "body": "Accepted. Fix is still local.", "in_reply_to_id": 42}]})
        first = self.deliver()
        self.assertEqual(first.returncode, 6, first.stderr)
        self.assertEqual(self.deliver().returncode, 0)
        self.assertEqual(sum(c["key"].startswith("POST ") for c in self.calls()), 1)

    def test_unreconciled_unknown_is_not_retried(self):
        self.setup_delivery(**{"POST " + ROOT_REPLY: {"_status": 1, "_stdout": "timeout"}})
        self.assertEqual(self.deliver().returncode, 6)
        self.assertEqual(self.deliver().returncode, 6)
        self.assertEqual(sum(c["key"].startswith("POST ") for c in self.calls()), 1)

    def test_definitive_rejection_can_retry(self):
        self.setup_delivery(**{"POST " + ROOT_REPLY + "#1": {
            "_status": 1, "_stdout": "bad request", "_stderr": "gh: rejected (HTTP 422)"}})
        self.assertEqual(self.deliver().returncode, 4)
        second = self.deliver()
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(sum(c["key"].startswith("POST ") for c in self.calls()), 2)

    def test_changed_body_requires_a_new_approved_item(self):
        self.setup_delivery()
        self.assertEqual(self.deliver().returncode, 0)
        self.body.write_text("Different claim")
        result = self.deliver()
        self.assertEqual(result.returncode, 5, result.stderr)
        self.assertEqual(sum(c["key"].startswith("POST ") for c in self.calls()), 1)

    def test_head_change_cannot_be_hidden_by_posted_state(self):
        self.setup_delivery(**{"GET " + PR + "#2": {
            "head": {"sha": "c" * 40}, "base": {"sha": "a" * 40}}})
        self.assertEqual(self.deliver().returncode, 0)
        self.assertEqual(self.deliver().returncode, 5)
        self.assertEqual(sum(c["key"].startswith("POST ") for c in self.calls()), 1)

    def test_lock_is_not_stolen(self):
        self.setup_delivery()
        lock = self.work / "receipt.json.lock"
        lock.mkdir()
        (lock / "owner").write_text("other invocation")
        self.assertEqual(self.deliver().returncode, 7)
        self.assertTrue(lock.exists())
        self.assertFalse(self.log.exists())

    def test_partial_batch_resumes_only_rejected_reply(self):
        self.setup_delivery(**{"POST " + PR + "/comments#1": {"id": 100, "html_url": "https://example.test/100"},
            "POST " + PR + "/comments#2": {"_status": 1, "_stderr": "gh: rejected (HTTP 422)"},
            "POST " + PR + "/comments#3": {"id": 101, "html_url": "https://example.test/101"}})
        directory = self.work / "verdicts"
        self.write_json(directory, "01.json", {"in_reply_to": 42, "body": "Fixed A"})
        self.write_json(directory, "02.json", {"in_reply_to": 43, "body": "Fixed B"})
        args = ("acme", "demo", 7, directory, self.receipt)
        self.assertEqual(self.run_script(VERIFY, "post-thread-replies.sh", *args).returncode, 1)
        result = self.run_script(VERIFY, "post-thread-replies.sh", *args)
        self.assertEqual(result.returncode, 0, result.stderr)
        roots = [c["payload"]["in_reply_to"] for c in self.calls() if c["key"].startswith("POST ")]
        self.assertEqual(roots, [42, 43, 43])

    def test_concurrent_attempt_cannot_enter_active_delivery(self):
        self.setup_delivery(**{"POST " + ROOT_REPLY: {"id": 100, "html_url": "https://example.test/100", "_delay": 1}})
        args = ["/bin/bash", str(ROOT / "skills" / RESPOND / "scripts/post-reply.sh"),
                "acme", "demo", "7", "42", "review", str(self.body), str(self.receipt), "reply-42"]
        process = subprocess.Popen(args, cwd=self.work, env=self.process_environment,
                                   text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if self.log.exists() and any(c["key"].startswith("POST ") for c in self.calls()):
                    break
                time.sleep(0.02)
            self.assertEqual(self.deliver().returncode, 7)
            stdout, stderr = process.communicate(timeout=5)
            self.assertEqual(process.returncode, 0, stderr)
            self.assertIn("html_url=", stdout)
        finally:
            if process.poll() is None:
                process.terminate()
                process.communicate(timeout=5)
        self.assertEqual(sum(c["key"].startswith("POST ") for c in self.calls()), 1)
