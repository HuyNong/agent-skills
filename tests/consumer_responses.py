"""Prepare offline GitHub observations from an isolated fixture repository."""
from __future__ import annotations
import json
import os
from pathlib import Path
import shutil
from consumer_git import run_git

def _write_transport(
    seed: Path,
    base: str,
    reviewed: str,
    head: str,
    diff: str,
    fixture: dict[str, object],
) -> None:
    files = []
    git_head = run_git(seed, "rev-parse", "HEAD")
    for name in run_git(seed, "diff", "--name-only", f"{base}...{git_head}").splitlines():
        file_diff = run_git(seed, "diff", f"{base}...{git_head}", "--", name)
        files.append({"filename": name, "patch": file_diff[file_diff.find("@@"):]})
    patch = next((item["patch"] for item in files if item["filename"] == "src/consumer.py"), "")
    inline = {
        "id": 101,
        "body": "Negative amounts reach billing; reject them before calculating totals.",
        "path": "src/consumer.py",
        "line": 4,
        "original_line": 4,
        "side": "RIGHT",
        "commit_id": reviewed,
        "pull_request_review_id": 501,
        "diff_hunk": patch,
        "user": {"login": "reviewer"},
        "html_url": "https://github.com/acme/consumer-fixture/pull/7#discussion_r101",
    }
    if fixture.get("claim"):
        inline["body"] = fixture["claim"]
    other = dict(inline)
    other.update(
        id=202,
        body="Consider renaming render_summary for clarity.",
        line=5,
        original_line=5,
        pull_request_review_id=502,
        html_url="https://github.com/acme/consumer-fixture/pull/7#discussion_r202",
    )
    review = {
        "id": 501,
        "body": "## Code Review\n\nGeneral notes: add a regression test for negative input.",
        "state": "COMMENTED",
        "commit_id": reviewed,
        "user": {"login": "fixture-user"},
        "submitted_at": "2026-11-01T01:00:00Z",
        "html_url": "https://github.com/acme/consumer-fixture/pull/7#pullrequestreview-501",
    }
    pr = {
        "number": 7,
        "title": "Guard invoice totals",
        "body": "Offline fixture",
        "state": "OPEN",
        "draft": False,
        "isDraft": False,
        "commits": 1 if head == reviewed else 2,
        "headRefOid": head,
        "baseRefOid": base,
        "headRefName": "negative-amount-guard",
        "baseRefName": "main",
        "url": "https://github.com/acme/consumer-fixture/pull/7",
        "mergeable": "UNKNOWN" if fixture.get("platform_unknown") else "MERGEABLE",
        "mergeStateStatus": "UNKNOWN" if fixture.get("platform_unknown") else "CLEAN",
        "reviewDecision": None,
        "latestReviews": [], "statusCheckRollup": [], "potentialMergeCommit": None,
        "headRepositoryOwner": {"login": "acme"},
        "headRepository": {"name": "consumer-fixture", "nameWithOwner": "acme/consumer-fixture"},
        "isCrossRepository": False,
        "head": {"sha": head, "ref": "negative-amount-guard", "repo": {"full_name": "acme/consumer-fixture"}},
        "base": {"sha": base, "ref": "main", "repo": {"full_name": "acme/consumer-fixture"}},
        "user": {"login": "author"},
        "html_url": "https://github.com/acme/consumer-fixture/pull/7",
    }
    prefix = "/repos/acme/consumer-fixture"
    responses = {
        "current_pr_exists": fixture.get("existing_pr", True),
        "repo": {"name": "consumer-fixture", "nameWithOwner": "acme/consumer-fixture", "owner": {"login": "acme"}},
        "diff": diff,
        "/user": {"login": "fixture-user"},
        f"{prefix}/pulls": [],
        f"{prefix}/pulls/7": pr,
        f"{prefix}/pulls/comments/101": inline,
        f"{prefix}/pulls/comments/202": other,
        f"{prefix}/pulls/7/comments": [inline, other],
        f"{prefix}/issues/7/comments": [{"id": 303, "body": "Unrelated release question", "user": {"login": "maintainer"}, "html_url": "https://github.com/acme/consumer-fixture/pull/7#issuecomment-303"}],
        f"{prefix}/pulls/7/reviews": [review, dict(review, id=502, body="Other review", user={"login": "other-reviewer"})],
        f"{prefix}/pulls/7/reviews/501": review,
        f"{prefix}/pulls/7/reviews/501/comments": [inline],
        f"{prefix}/pulls/7/files": files,
        f"{prefix}/pulls/7/commits": [{"sha": reviewed}] + ([] if head == reviewed else [{"sha": head}]),
        f"{prefix}/commits/{head}/status": {"state": "pending", "statuses": []},
        f"{prefix}/commits/{head}/check-runs": {"total_count": 0, "check_runs": []},
        f"{prefix}/rules/branches/main": [],
        f"{prefix}/branches/main": {"protected": False},
    }
    (seed / "tools" / "responses.json").write_text(json.dumps(responses), encoding="utf-8")
    gh_source = Path(__file__).with_name("consumer_offline_gh.py")
    shutil.copy2(gh_source, seed / "tools" / "gh")
    os.chmod(seed / "tools" / "gh", 0o755)
    git_source = Path(__file__).with_name("consumer_guarded_git.py")
    shutil.copy2(git_source, seed / "tools" / "git")
    os.chmod(seed / "tools" / "git", 0o755)
    shutil.copy2(Path(__file__).with_name("consumer_git_policy.py"), seed / "tools/consumer_git_policy.py")
