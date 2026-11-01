"""Expected behavior for current-head and historical inline anchors."""
from script_fixtures import RESPOND, ScriptCase

PR = "/repos/acme/demo/pulls/7"
HEAD = "b" * 40


class InlineMembershipContracts(ScriptCase):
    def inline(self, metadata=None, **responses):
        self.respond({"GET " + PR: metadata or {"head": {"sha": HEAD}, "base": {"sha": "a" * 40}, "commits": 300},
                      "POST " + PR + "/comments": {"id": 12, "html_url": "https://example.test/reply"}, **responses})
        body = self.work / "body.txt"
        body.write_text("Verified reply")
        return body

    def test_current_head_does_not_enumerate_capped_commits(self):
        body = self.inline()
        result = self.run_script(RESPOND, "post-new-inline.sh", "acme", "demo", 7, HEAD, "src/a.py", 2, body)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("/commits", self.log.read_text())

    def test_historical_unknown_does_not_hint_push(self):
        body = self.inline()
        result = self.run_script(RESPOND, "post-new-inline.sh", "acme", "demo", 7, "c" * 40, "src/a.py", 2, body)
        self.assertEqual(result.returncode, 4, result.stderr)
        self.assertIn("indeterminate", result.stderr)
        self.assertNotIn("POST ", self.log.read_text())

    def test_metadata_failure_is_not_nonmembership(self):
        body = self.inline(**{"GET " + PR: {"_status": 1, "_stdout": "unavailable"}})
        result = self.run_script(RESPOND, "post-new-inline.sh", "acme", "demo", 7, HEAD, "src/a.py", 2, body)
        self.assertEqual(result.returncode, 3, result.stderr)

    def test_changed_head_stops_before_post(self):
        body = self.inline(**{"GET " + PR + "#2": {"head": {"sha": "c" * 40}}})
        result = self.run_script(RESPOND, "post-new-inline.sh", "acme", "demo", 7, HEAD, "src/a.py", 2, body)
        self.assertEqual(result.returncode, 5, result.stderr)
        self.assertNotIn("POST ", self.log.read_text())

    def test_invalid_sha_stops_before_network(self):
        body = self.inline()
        result = self.run_script(RESPOND, "post-new-inline.sh", "acme", "demo", 7, "z" * 40, "src/a.py", 2, body)
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.log.exists())

    def test_historical_anchor_on_second_complete_page_can_post(self):
        historical = "c" * 40
        body = self.inline(metadata={"head": {"sha": HEAD}, "base": {"sha": "a" * 40}, "commits": 2},
            **{"GET " + PR + "/commits": {"_stdout": '[{"sha":"' + HEAD + '"}]\n[{"sha":"' + historical + '"}]'}})
        result = self.run_script(RESPOND, "post-new-inline.sh", "acme", "demo", 7, historical, "src/a.py", 2, body)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_partial_historical_list_is_indeterminate_even_when_sha_present(self):
        historical = "c" * 40
        body = self.inline(metadata={"head": {"sha": HEAD}, "base": {"sha": "a" * 40}, "commits": 40},
            **{"GET " + PR + "/commits": [{"sha": historical}]})
        result = self.run_script(RESPOND, "post-new-inline.sh", "acme", "demo", 7, historical, "src/a.py", 2, body)
        self.assertEqual(result.returncode, 4, result.stderr)
        self.assertNotIn("POST ", self.log.read_text())
