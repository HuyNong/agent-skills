"""Platform facts are read-only, snapshot-bound, and conservative on visibility."""
import json
from script_fixtures import VERIFY, ScriptCase


class ReadinessContracts(ScriptCase):
    def readiness(self, **responses):
        pr = {"headRefOid": "b" * 40, "baseRefOid": "a" * 40, "baseRefName": "main", "state": "OPEN",
              "isDraft": False, "mergeable": "MERGEABLE", "mergeStateStatus": "CLEAN", "reviewDecision": "APPROVED",
              "latestReviews": [{"state": "APPROVED", "commit": {"oid": "c" * 40}}],
              "potentialMergeCommit": {"oid": "d" * 40}, "statusCheckRollup": []}
        self.respond({"GET /fixture/pr/view": pr,
                      "GET /fixture/pr/checks": [{"bucket": "pass", "name": "tests"}],
                      "GET /repos/acme/demo/rules/branches/main": [{"type": "pull_request", "parameters": {"required_approving_review_count": 1}}],
                      "GET /repos/acme/demo/branches/main": {"protected": False}, **responses})
        result = self.run_script(VERIFY, "collect-pr-readiness.sh", "acme", "demo", 7, self.work / "ready")
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_native_approval_is_not_rejected_just_for_old_commit(self):
        data = self.readiness()
        self.assertEqual(data["platform"], "eligible")
        self.assertEqual(data["snapshot"]["test_merge_sha"], "d" * 40)
        calls = [json.loads(line) for line in self.log.read_text().splitlines()]
        self.assertTrue(all(call["key"].startswith("GET ") for call in calls))

    def test_pending_exit_eight_is_a_fact_not_transport_failure(self):
        data = self.readiness(**{"GET /fixture/pr/checks": {"_status": 8, "_stdout": '[{"bucket":"pending","name":"tests"}]'}})
        self.assertEqual(data["platform"], "blocked")
        self.assertTrue(data["visibility"]["checks"])
        self.assertEqual(data["checks_exit"], 8)

    def test_inaccessible_rules_do_not_establish_readiness(self):
        data = self.readiness(**{"GET /repos/acme/demo/rules/branches/main": {"_status": 1, "_stdout": "forbidden"}})
        self.assertEqual(data["platform"], "unknown")

    def test_auth_failure_is_not_no_required_checks(self):
        data = self.readiness(**{"GET /fixture/pr/checks": {"_status": 1, "_stderr": "authentication failed"}})
        self.assertEqual(data["platform"], "unknown")

    def test_snapshot_drift_prevents_ready(self):
        data = self.readiness(**{"GET /fixture/pr/view#2": {"headRefOid": "f" * 40}})
        self.assertFalse(data["stable"])
        self.assertEqual(data["platform"], "unknown")

    def test_known_no_required_checks_is_distinct_from_missing_access(self):
        data = self.readiness(**{"GET /fixture/pr/checks": {
            "_status": 1, "_stderr": "no checks reported on the branch"}})
        self.assertTrue(data["visibility"]["no_checks_reported"])
        self.assertEqual(data["platform"], "eligible")

    def test_skipped_required_check_keeps_native_passing_policy(self):
        data = self.readiness(**{"GET /fixture/pr/checks": [{"bucket": "skipping", "state": "SKIPPED", "name": "tests"}]})
        self.assertEqual(data["platform"], "eligible")

    def test_unsupported_merge_queue_rule_is_unknown(self):
        data = self.readiness(**{"GET /repos/acme/demo/rules/branches/main": [{"type": "merge_queue"}]})
        self.assertTrue(data["visibility"]["unsupported_rules"])
        self.assertEqual(data["platform"], "unknown")

    def test_dismissed_approval_and_conflicts_are_blocking_facts(self):
        base = {"headRefOid": "b" * 40, "baseRefOid": "a" * 40, "baseRefName": "main", "state": "OPEN",
                "isDraft": False, "mergeable": "CONFLICTING", "mergeStateStatus": "DIRTY", "reviewDecision": "REVIEW_REQUIRED"}
        data = self.readiness(**{"GET /fixture/pr/view": base})
        self.assertEqual(data["platform"], "blocked")

    def test_classic_code_owner_requirement_needs_effective_approval(self):
        pr = {"headRefOid": "b" * 40, "baseRefOid": "a" * 40, "baseRefName": "main", "state": "OPEN",
              "isDraft": False, "mergeable": "MERGEABLE", "mergeStateStatus": "CLEAN", "reviewDecision": None}
        data = self.readiness(**{"GET /fixture/pr/view": pr,
            "GET /repos/acme/demo/rules/branches/main": [],
            "GET /repos/acme/demo/branches/main": {"protected": True},
            "GET /repos/acme/demo/branches/main/protection": {"required_status_checks": None,
                "required_pull_request_reviews": {"required_approving_review_count": 0, "require_code_owner_reviews": True}}})
        self.assertEqual(data["platform"], "unknown")
