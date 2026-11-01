"""The acceptance harness must not manufacture failures or leak expected answers."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from consumer_fixtures import build_seed, install_catalog, run_git, tree_hash
from script_fixtures import ROOT
from consumer_runtime import runtime_outcome


class ConsumerHarnessContracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="consumer-harness-")
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)

    def seed(self, name="seed", **fixture):
        project = self.work / name
        metadata = build_seed(project, {"snapshot": "reviewed", "remote_head": True, **fixture})
        return project, metadata

    def gh(self, project, *args):
        return subprocess.run([str(project / "tools/gh"), *args], cwd=project,
                              capture_output=True, text=True, timeout=10)

    def test_seeds_have_identical_commits_and_transport_bytes(self):
        left, lm = self.seed("left")
        right, rm = self.seed("right")
        self.assertEqual(lm, rm)
        self.assertEqual(tree_hash(left / "tools"), tree_hash(right / "tools"))

    def test_catalog_does_not_install_evaluation_answers(self):
        project, _ = self.seed()
        install_catalog(ROOT, project)
        self.assertFalse(list((project / ".agents/skills").glob("*/evals")))
        self.assertEqual(len(list((project / ".agents/skills").glob("*/SKILL.md"))), 4)

    def test_guard_allows_branch_reads_and_seed_fetch_but_blocks_push(self):
        project, _ = self.seed()
        git = str(project / "tools/git")
        for args in [("branch", "--show-current"), ("fetch", "origin", "main")]:
            self.assertEqual(subprocess.run([git, *args], cwd=project, capture_output=True).returncode, 0)
        self.assertEqual(subprocess.run([git, "push", "origin", "HEAD"], cwd=project, capture_output=True).returncode, 73)
        self.assertEqual(run_git(project, "branch", "--show-current"), "negative-amount-guard")

    def test_current_branch_pr_can_be_missing_without_hiding_numbered_pr(self):
        project, _ = self.seed(existing_pr=False)
        self.assertEqual(self.gh(project, "pr", "view", "--json", "number").returncode, 1)
        self.assertEqual(self.gh(project, "pr", "view", "7", "--json", "number").returncode, 0)

    def test_review_post_and_put_are_visible_to_later_readback(self):
        project, meta = self.seed()
        endpoint = "/repos/acme/consumer-fixture/pulls/7/reviews"
        payload = self.work / "payload.json"
        payload.write_text(json.dumps({"event": "COMMENT", "commit_id": meta["head"], "body": "Finding",
            "comments": [{"path": "src/consumer.py", "line": 4, "side": "RIGHT", "body": "Negative input"}]}))
        self.assertEqual(self.gh(project, "api", "--method", "POST", endpoint, "--input", str(payload)).returncode, 0)
        review = json.loads(self.gh(project, "api", endpoint + "/700").stdout)
        self.assertEqual(review["body"], "Finding")
        comments = json.loads(self.gh(project, "api", endpoint + "/700/comments").stdout)
        self.assertEqual(comments[0]["line"], 4)
        payload.write_text(json.dumps({"body": "Linked finding"}))
        self.assertEqual(self.gh(project, "api", "--method", "PUT", endpoint + "/700", "--input", str(payload)).returncode, 0)
        self.assertEqual(json.loads(self.gh(project, "api", endpoint + "/700").stdout)["body"], "Linked finding")

    def test_provider_quota_is_not_a_completed_skill_evaluation(self):
        trace = self.work / "trace.jsonl"
        trace.write_text(json.dumps({"type": "turn.failed", "error": {"message": "You have hit your usage limit"}}))
        self.assertEqual(runtime_outcome(trace, 1, False), "runtime-blocked")
        trace.write_text(json.dumps({"type": "turn.completed"}))
        self.assertEqual(runtime_outcome(trace, 0, False), "completed")
        self.assertEqual(runtime_outcome(trace, -15, True), "timeout")

    def test_fork_uses_a_distinct_upstream_base(self):
        project, metadata = self.seed(branch_case="fork", existing_pr=False)
        self.assertNotEqual(run_git(project, "rev-parse", "main"), metadata["base"])
        self.assertEqual(run_git(project, "rev-parse", "upstream/main"), metadata["base"])
        result = subprocess.run([str(project / "tools/git"), "ls-remote", "upstream", "main"],
                                cwd=project, capture_output=True, text=True, check=True)
        self.assertIn(metadata["base"], result.stdout)
        repo = json.loads(self.gh(project, "repo", "view", "fixture-user/consumer-fixture").stdout)
        self.assertEqual(repo["owner"]["login"], "fixture-user")

    def test_detached_case_has_no_current_branch(self):
        project, _ = self.seed(branch_case="detached", existing_pr=False)
        self.assertEqual(run_git(project, "branch", "--show-current"), "")

    def test_diverged_case_has_commits_on_both_sides(self):
        project, _ = self.seed(branch_case="diverged", existing_pr=False)
        self.assertEqual(run_git(project, "rev-list", "--left-right", "--count",
                                 "origin/negative-amount-guard...HEAD").split(), ["1", "1"])

    def test_opt_in_push_uses_local_bare_remote_and_rejects_force(self):
        project, meta = self.seed(remote_head=False, simulate_push=True)
        git = str(project / "tools/git")
        command = [git, "push", "-u", "origin", "negative-amount-guard"]
        result = subprocess.run(command, cwd=project, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(run_git(project, "--git-dir=.fixture-push.git", "rev-parse", "negative-amount-guard"), meta["head"])
        remote = subprocess.run([git, "ls-remote", "--heads", "origin", "negative-amount-guard"],
                                cwd=project, capture_output=True, text=True, check=True)
        self.assertIn(meta["head"], remote.stdout)
        qualified = "refs/heads/negative-amount-guard:refs/heads/negative-amount-guard"
        self.assertEqual(subprocess.run([git, "push", "-u", "origin", qualified], cwd=project,
                                       capture_output=True).returncode, 0)
        self.assertEqual(subprocess.run([git, "push", "--force", "origin", "HEAD"], cwd=project, capture_output=True).returncode, 73)

    def test_fixture_ignores_inherited_git_identity_and_repo_overrides(self):
        _, expected = self.seed("ordinary")
        environment = dict(os.environ, GIT_AUTHOR_NAME="Different", GIT_AUTHOR_EMAIL="different@example.invalid",
            GIT_COMMITTER_NAME="Different", GIT_COMMITTER_EMAIL="different@example.invalid",
            GIT_DIR=str(self.work / "wrong-repo"), GIT_CONFIG_COUNT="1",
            GIT_CONFIG_KEY_0="commit.gpgsign", GIT_CONFIG_VALUE_0="true")
        script = ("import json,sys; from pathlib import Path; "
                  "from consumer_fixtures import build_seed; "
                  "print(json.dumps(build_seed(Path(sys.argv[1]), {'snapshot':'reviewed','remote_head':True})))")
        child = subprocess.run([sys.executable, "-c", script, str(self.work / "overridden")],
            cwd=ROOT / "tests", env=environment, text=True, capture_output=True, check=True)
        self.assertEqual(json.loads(child.stdout), expected)
