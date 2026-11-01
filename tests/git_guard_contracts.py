"""Regression contracts for the fixture Git trust boundary."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from consumer_fixtures import build_seed, run_git


class GitGuardContracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="git-guard-contracts-")
        self.addCleanup(self.temp.cleanup)

    def seed(self, **fixture):
        project = Path(self.temp.name) / "project"
        metadata = build_seed(project, {"snapshot": "reviewed", "remote_head": True, **fixture})
        return project, metadata

    def git(self, project: Path, *args: str, input_data=None, env=None):
        return subprocess.run(
            [str(project / "tools" / "git"), *args], cwd=project,
            input=input_data, capture_output=True, text=input_data is None,
            env=env, timeout=10,
        )

    def calls(self, project: Path):
        path = project / "tools" / "git-calls.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text().splitlines()]

    def test_global_c_scopes_reads_and_blocks_branch_and_push_mutations(self):
        project, _ = self.seed()
        self.assertEqual(self.git(project, "-C", str(project), "branch", "--show-current").returncode, 0)
        created = self.git(project, "-C", str(project), "branch", "bypass")
        self.assertEqual(created.returncode, 73)
        self.assertEqual(run_git(project, "branch", "--list", "bypass"), "")
        renamed = self.git(project, "-C", str(project), "branch", "-m", "escaped")
        self.assertEqual(renamed.returncode, 73)
        pushed = self.git(project, "-C", str(project), "push", "origin", "HEAD")
        self.assertEqual(pushed.returncode, 73)
        self.assertEqual(run_git(project, "branch", "--show-current"), "negative-amount-guard")
        outside = self.git(project, "-C", str(project.parent), "branch", "--show-current")
        self.assertEqual(outside.returncode, 73)
        self.assertEqual([row["kind"] for row in self.calls(project)], [
            "git-read", "git-write-blocked", "git-write-blocked", "git-write-blocked", "git-read-blocked",
        ])

    def test_legitimate_read_commands_and_global_operands_remain_usable(self):
        project, metadata = self.seed()
        base, head = metadata["base"], metadata["head"]
        commands = [
            ("status", "--porcelain", "--untracked-files=no"),
            ("log", "--oneline", f"{base}..{head}"),
            ("show", f"{head}:src/consumer.py"),
            ("blame", "-L", "1,3", head, "--", "src/consumer.py"),
            ("diff", "--stat", f"{base}...{head}"),
            ("rev-parse", "--verify", f"{head}^{{commit}}"),
            ("rev-list", "--left-right", "--count", f"{base}...{head}"),
            ("merge-base", "--is-ancestor", base, head),
            ("cat-file", "-e", f"{head}^{{commit}}"),
            ("remote", "-v"),
            ("remote", "get-url", "origin"),
            ("branch", "--show-current"),
            ("branch", "--list"),
            ("config", "--get", "remote.origin.url"),
            ("show-ref",),
            ("for-each-ref", "--format=%(refname)", "refs/heads/"),
            ("ls-tree", head),
            ("grep", "-n", "invoice", "--", "src"),
        ]
        for command in commands:
            with self.subTest(command=command):
                result = self.git(project, *command)
                self.assertEqual(result.returncode, 0, result.stderr)
        hashed = self.git(project, "hash-object", "--stdin", input_data=b"guard\n")
        self.assertEqual(hashed.returncode, 0, hashed.stderr)
        git_dir = "." + "git"
        self.assertEqual(self.git(project, "--git-dir", git_dir, "rev-parse", "HEAD").returncode, 0)
        self.assertEqual(self.git(project, "--work-tree", ".", "status", "--porcelain").returncode, 0)
        self.assertEqual(self.git(project, "-C", str(project), "-c", "core.quotepath=false", "status").returncode, 0)
        self.assertTrue(all(row["kind"] == "git-read" for row in self.calls(project)))

    def test_defensive_global_overrides_require_exact_safe_values(self):
        project, _ = self.seed()
        for override, command in [
            ("safe.bareRepository=explicit", ("rev-parse", "HEAD")),
            ("core.hooksPath=/dev/null", ("remote", "-v")),
            ("core.fsmonitor=false", ("status", "--porcelain")),
        ]:
            with self.subTest(override=override):
                self.assertEqual(self.git(project, "-c", override, *command).returncode, 0)
        for override in [
            "safe.bareRepository=true",
            "core.hooksPath=/tmp/hooks",
            "core.fsmonitor=true",
        ]:
            with self.subTest(override=override):
                self.assertEqual(self.git(project, "-c", override, "status").returncode, 73)

    def test_scope_only_read_denials_are_distinct_from_write_denials(self):
        project, _ = self.seed()
        outside = str(project.parent)
        read = self.git(project, "-C", outside, "status", "--porcelain")
        self.assertEqual(read.returncode, 73)
        write = self.git(project, "-C", outside, "branch", "bypass")
        self.assertEqual(write.returncode, 73)
        outside_push = self.git(project, "-C", outside, "push", "origin", "HEAD")
        self.assertEqual(outside_push.returncode, 73)
        unsupported_url = self.git(project, "ls-remote", "https://github.com/acme/consumer-fixture.git")
        self.assertEqual(unsupported_url.returncode, 73)
        self.assertEqual([row["kind"] for row in self.calls(project)], [
            "git-read-blocked", "git-write-blocked", "git-write-blocked", "git-read-blocked",
        ])

    def test_remote_config_and_hash_writes_are_blocked_without_state_change(self):
        project, _ = self.seed()
        remote_before = run_git(project, "remote", "get-url", "origin")
        user_before = run_git(project, "config", "--get", "user.name")
        objects_before = run_git(project, "count-objects", "-v")
        for command in [
            ("remote", "set-url", "origin", "https://evil.invalid/changed.git"),
            ("config", "user.name", "changed"),
            ("-C", str(project), "remote", "set-url", "origin", "https://evil.invalid/scoped.git"),
            ("-C", str(project), "config", "user.name", "scoped-change"),
            ("hash-object", "-w", "README.md"),
            ("update-ref", "refs/heads/evil", "HEAD"),
        ]:
            with self.subTest(command=command):
                self.assertEqual(self.git(project, *command).returncode, 73)
        self.assertEqual(run_git(project, "remote", "get-url", "origin"), remote_before)
        self.assertEqual(run_git(project, "config", "--get", "user.name"), user_before)
        self.assertEqual(run_git(project, "count-objects", "-v"), objects_before)

    def test_symbolic_ref_only_allows_single_reference_reads(self):
        project, _ = self.seed()
        original = run_git(project, "symbolic-ref", "HEAD")
        for command in [
            ("symbolic-ref", "HEAD"),
            ("symbolic-ref", "--quiet", "HEAD"),
            ("symbolic-ref", "-q", "--short", "HEAD"),
            ("symbolic-ref", "--no-recurse", "HEAD"),
        ]:
            with self.subTest(command=command):
                self.assertEqual(self.git(project, *command).returncode, 0)
        for command in [
            ("symbolic-ref", "HEAD", "refs/heads/bypass"),
            ("symbolic-ref", "--delete", "HEAD"),
            ("symbolic-ref", "--unknown", "HEAD"),
        ]:
            with self.subTest(command=command):
                self.assertEqual(self.git(project, *command).returncode, 73)
                self.assertEqual(run_git(project, "symbolic-ref", "HEAD"), original)

    def test_aliases_and_dangerous_config_overrides_never_execute(self):
        project, _ = self.seed()
        marker = project / "alias-marker"
        ssh_marker = project / "ssh-marker"
        run_git(project, "config", "alias.fixture-escape", f"!touch {marker}")
        for command in [
            ("fixture-escape",),
            ("-c", f"alias.fixture-escape=!touch {marker}", "fixture-escape"),
            ("-c", f"core.sshCommand=touch {ssh_marker}", "status"),
            ("-c", "remote.origin.url=https://evil.invalid", "status"),
        ]:
            with self.subTest(command=command):
                self.assertEqual(self.git(project, *command).returncode, 73)
        self.assertFalse(marker.exists())
        self.assertFalse(ssh_marker.exists())

    def test_forced_push_is_blocked_before_network_and_output_options_are_rejected(self):
        project, _ = self.seed()
        trace = project / "trace.json"
        env = os.environ.copy()
        env["GIT_TRACE2_EVENT"] = str(trace)
        forced = self.git(project, "push", "--force", "origin", "HEAD", env=env)
        self.assertEqual(forced.returncode, 73)
        self.assertFalse(trace.exists())
        external_marker = project / "external-diff-marker"
        run_git(project, "config", "diff.external", f"touch {external_marker}")
        (project / "README.md").write_text("# changed\n")
        self.assertEqual(self.git(project, "diff").returncode, 0)
        self.assertFalse(external_marker.exists())
        for command in [("diff", "--ext-diff"), ("show", "--textconv", "HEAD:README.md"),
                        ("log", "--output", str(project / "log.txt"))]:
            with self.subTest(command=command):
                self.assertEqual(self.git(project, *command).returncode, 73)
        self.assertFalse((project / "log.txt").exists())

    def test_selected_push_uses_only_the_local_bare_fixture(self):
        project, metadata = self.seed(remote_head=False, simulate_push=True)
        result = self.git(project, "-C", str(project), "push", "-u", "origin", "negative-amount-guard")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(run_git(project, "--git-dir=.fixture-push.git", "rev-parse", "negative-amount-guard"), metadata["head"])
        self.assertEqual(self.git(project, "ls-remote", "--heads", "origin", "negative-amount-guard").returncode, 0)
        forced = self.git(project, "-C", str(project), "push", "--force", "origin", "HEAD")
        self.assertEqual(forced.returncode, 73)
        self.assertEqual([row["kind"] for row in self.calls(project)], [
            "git-fixture-push", "git-read", "git-write-blocked",
        ])


if __name__ == "__main__":
    unittest.main(verbosity=2)
