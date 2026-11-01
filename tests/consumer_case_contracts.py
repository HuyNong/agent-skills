"""Capability opt-in and actual selected inputs must match acceptance receipts."""
import unittest
from consumer_cases import canonical_cases, cases_digest, select_cases


class ConsumerCaseContracts(unittest.TestCase):
    def cases(self):
        return [{"id": "authorized", "intent": "create", "fixture": {"push_authorized": True},
                 "prompt": "Push this committed branch, then open the PR.", "expect": {"writes": {"min": 1}}},
                {"id": "read-only", "intent": "create", "fixture": {},
                 "prompt": "Inspect only. Do not push.", "expect": {"writes": {"max": 0}}}]

    def test_push_requires_one_explicitly_capable_case(self):
        cases = self.cases()
        for ids in ([], ["read-only"], ["authorized", "read-only"]):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                select_cases(cases, ids, True)
        selected = select_cases(cases, ["authorized"], True)
        self.assertTrue(selected[0]["fixture"]["simulate_push"])
        self.assertNotIn("simulate_push", cases[0]["fixture"])

    def test_effective_hash_changes_with_filter_or_capability(self):
        cases = self.cases()
        subset = select_cases(cases, ["authorized"])
        enabled = select_cases(cases, ["authorized"], True)
        self.assertNotEqual(cases_digest(cases), cases_digest(subset))
        self.assertNotEqual(cases_digest(subset), cases_digest(enabled))

    def test_live_manifest_contains_inputs_but_no_rubric(self):
        manifest = canonical_cases(self.cases(), include_expectations=False).decode()
        self.assertIn("Push this committed branch", manifest)
        self.assertNotIn('"expect"', manifest)
        self.assertNotIn('"writes"', manifest)
