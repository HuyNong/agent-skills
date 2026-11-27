"""Optional resolution follows a proven reply without replaying uncertain writes."""
import copy
import json

from reply_recovery_contracts import HEAD, PR, ROOT_REPLY
from script_fixtures import RESPOND, ScriptCase

BODY = "![Fixed](https://img.shields.io/badge/Status-Fixed-brightgreen)\n\nVerified on the PR."


class ThreadResolutionContracts(ScriptCase):
    def setup_resolution(self, resolved=False, permission=True):
        self.body = self.work / "body.txt"
        self.body.write_text(BODY)
        self.receipt = self.work / "receipt.json"
        self.thread = {"id": "PRRT_42", "isResolved": resolved, "viewerCanResolve": permission,
                       "comments": {"nodes": [{"databaseId": 42}]}}
        self.page = {"data": {"repository": {"pullRequest": {
            "headRefOid": HEAD, "baseRefOid": "a" * 40,
            "reviewThreads": {"nodes": [self.thread],
                              "pageInfo": {"hasNextPage": False, "endCursor": None}}}}}}
        self.responses_map = {
            "GET /user": {"login": "tester"},
            "GET " + PR: {"head": {"sha": HEAD}, "base": {"sha": "a" * 40}},
            "GET " + PR + "/comments": [],
            "POST " + ROOT_REPLY: {"id": 100, "html_url": "https://example.test/100"},
            "GET /repos/acme/demo/pulls/comments/100": {
                "id": 100, "body": BODY, "user": {"login": "tester"}, "in_reply_to_id": 42},
            "POST /graphql#1": self.page,
            "POST /graphql#2": {"data": {"resolveReviewThread": {
                "thread": {"id": "PRRT_42", "isResolved": True}}}},
        }
        self.respond(self.responses_map)
        result = self.run_script(RESPOND, "post-reply.sh", "acme", "demo", 7, 42, "review",
                                 self.body, self.receipt, "reply-42", "CORRECT", "fixed-on-pr")
        self.assertEqual(result.returncode, 0, result.stderr)

    def resolve(self, state="fixed-on-pr", authority="--resolve-authorized"):
        self.respond(self.responses_map)
        return self.run_script(RESPOND, "resolve-thread.sh", "acme", "demo", 7, 42,
                               self.receipt, "reply-42", state, authority)

    def mutations(self):
        return [c for c in self.calls() if any("mutation(" in a for a in c["args"])]

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def test_resolve_after_reply_preserves_delivery_and_skips_already_resolved(self):
        self.setup_resolution()
        result = self.resolve()
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(self.receipt.read_text())
        self.assertEqual(data["items"]["reply-42"]["state"], "posted")
        self.assertEqual(data["resolutions"]["reply-42"]["state"], "resolved")
        self.responses_map["POST /graphql#3"] = copy.deepcopy(self.page)
        self.responses_map["POST /graphql#3"]["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"][0]["isResolved"] = True
        self.assertEqual(self.resolve().returncode, 0)
        self.assertEqual(len(self.mutations()), 1)
        self.assertEqual(sum(c["key"] == "POST " + ROOT_REPLY for c in self.calls()), 1)

    def test_no_authority_or_only_local_fix_stops_before_api(self):
        self.setup_resolution()
        count = len(self.calls())
        for state, authority in [("fixed-on-pr", ""), ("fixed-local", "--resolve-authorized"),
                                 ("planned", "--resolve-authorized")]:
            self.assertEqual(self.resolve(state, authority).returncode, 2)
        self.assertEqual(len(self.calls()), count)

    def test_unposted_or_top_level_reply_cannot_resolve(self):
        for change in ["unknown", "failed", "issue"]:
            with self.subTest(change=change):
                self.setup_resolution()
                data = json.loads(self.receipt.read_text())
                if change == "issue":
                    data["items"]["reply-42"]["binding"]["endpoint"] = "/repos/acme/demo/issues/7/comments"
                else:
                    data["items"]["reply-42"]["state"] = change
                self.receipt.write_text(json.dumps(data))
                self.assertEqual(self.resolve().returncode, 2)
                self.assertEqual(self.mutations(), [])
                self.receipt.unlink()

    def test_identity_snapshot_or_live_reply_drift_stops_resolution(self):
        self.setup_resolution()
        original = copy.deepcopy(self.responses_map)
        variants = [("GET /user", {"login": "someone-else"}),
                    ("GET " + PR, {"head": {"sha": "c" * 40}, "base": {"sha": "a" * 40}}),
                    ("GET /repos/acme/demo/pulls/comments/100", {
                        "id": 100, "body": BODY + " edited", "in_reply_to_id": 42,
                        "user": {"login": "tester"}})]
        for endpoint, response in variants:
            self.responses_map = {**original, endpoint: response}
            result = self.resolve()
            self.assertEqual(result.returncode, 5, result.stderr)
        self.assertEqual(self.mutations(), [])

    def test_missing_root_permission_and_graphql_errors_fail_closed(self):
        for variant in ["root", "permission", "errors", "incomplete"]:
            with self.subTest(variant=variant):
                self.setup_resolution()
                if variant == "root":
                    self.thread["comments"]["nodes"][0]["databaseId"] = 99
                elif variant == "permission":
                    self.thread["viewerCanResolve"] = False
                elif variant == "errors":
                    self.page["errors"] = [{"message": "partial GraphQL result"}]
                else:
                    self.page["data"]["repository"]["pullRequest"]["reviewThreads"]["pageInfo"]["hasNextPage"] = True
                # Numbered responses only belong to this invocation.
                self.log.unlink()
                result = self.resolve()
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.mutations(), [])
                self.receipt.unlink()

    def test_paginated_thread_lookup_finds_original_root_on_later_page(self):
        self.setup_resolution()
        first = copy.deepcopy(self.page)
        first["data"]["repository"]["pullRequest"]["reviewThreads"] = {
            "nodes": [], "pageInfo": {"hasNextPage": True, "endCursor": "next"}}
        self.responses_map["POST /graphql#1"] = {"_stdout": json.dumps(first) + "\n" + json.dumps(self.page)}
        result = self.resolve()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.mutations()), 1)

    def test_unknown_resolution_reconciles_without_mutation_replay(self):
        self.setup_resolution()
        self.responses_map["POST /graphql#2"] = {"_status": 1, "_stderr": "connection lost"}
        self.assertEqual(self.resolve().returncode, 6)
        self.responses_map["POST /graphql#3"] = self.page
        self.assertEqual(self.resolve().returncode, 6)
        resolved = copy.deepcopy(self.page)
        resolved["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"][0]["isResolved"] = True
        self.responses_map["POST /graphql#4"] = resolved
        self.assertEqual(self.resolve().returncode, 0)
        self.assertEqual(len(self.mutations()), 1)

    def test_graphql_mutation_errors_do_not_claim_resolved(self):
        self.setup_resolution()
        self.responses_map["POST /graphql#2"] = {"data": None, "errors": [{"message": "forbidden"}]}
        self.assertEqual(self.resolve().returncode, 6)
        self.assertEqual(json.loads(self.receipt.read_text())["resolutions"]["reply-42"]["state"], "unknown")
