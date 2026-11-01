"""Execute detached installed helpers from a consuming CWD using offline API data."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from script_fixtures import GH_FIXTURE


def smoke(folder, project):
    with tempfile.TemporaryDirectory(prefix="installed-helper-", dir=project) as scratch:
        work = Path(scratch)
        bin_dir = work / "bin"
        bin_dir.mkdir()
        gh = bin_dir / "gh"
        gh.write_text(GH_FIXTURE)
        gh.chmod(0o755)
        responses = work / "responses.json"
        log = work / "calls.jsonl"
        environment = dict(os.environ, PATH=str(bin_dir) + os.pathsep + os.environ["PATH"],
                           TEST_GH_RESPONSES=str(responses), TEST_GH_LOG=str(log))
        head = "b" * 40
        pr = "/repos/acme/demo/pulls/7"
        api = {"GET /user": {"login": "tester"}, "GET " + pr: {
            "head": {"sha": head}, "base": {"sha": "a" * 40}},
            "GET " + pr + "/reviews": [], "GET " + pr + "/comments": [],
            "POST " + pr + "/reviews": {"id": 11, "html_url": "https://example.test/review/11"},
            "POST " + pr + "/comments/42/replies": {"id": 12, "html_url": "https://example.test/reply/12"}}
        responses.write_text(json.dumps(api))

        def run(name, *args):
            return subprocess.run(["/bin/bash", str(folder / "scripts" / name), *map(str, args)],
                                  cwd=project, env=environment, text=True, capture_output=True, check=True)

        body = work / "body.md"
        body.write_text("Accepted; planned, no fix on PR yet.\n")
        receipt = work / "receipt.json"
        name = folder.name
        if name == "pr-create":
            assert not (folder / "scripts").exists(), "create is an instruction-only package"
        elif name == "pr-review-publish":
            comments = work / "comments"
            comments.mkdir()
            payload = work / "payload.json"
            payload.write_text(run("build-review-payload.sh", head, body, comments).stdout)
            run("post-review.sh", "acme", "demo", 7, payload, receipt)
            run("post-review.sh", "acme", "demo", 7, payload, receipt)
        elif name == "pr-review-respond":
            result = run("parse-review-url.sh", "https://github.com/acme/demo/pull/7#discussion_r42")
            assert "comment_id=42" in result.stdout
            run("post-reply.sh", "acme", "demo", 7, 42, "review", body, receipt, "reply-42")
            run("post-reply.sh", "acme", "demo", 7, 42, "review", body, receipt, "reply-42")
        elif name == "pr-review-verify-fixes":
            run("post-followup-summary.sh", "acme", "demo", 7, head, body, receipt)
            verdicts = work / "verdicts"
            verdicts.mkdir()
            (verdicts / "42.json").write_text(json.dumps({"in_reply_to": 42, "body": "Fixed with verified evidence."}))
            api["POST " + pr + "/comments"] = {"id": 12, "html_url": "https://example.test/reply/12"}
            responses.write_text(json.dumps(api))
            run("post-thread-replies.sh", "acme", "demo", 7, verdicts, receipt)
            run("post-followup-summary.sh", "acme", "demo", 7, head, body, receipt)
            run("post-thread-replies.sh", "acme", "demo", 7, verdicts, receipt)
        if log.exists():
            writes = [json.loads(row) for row in log.read_text().splitlines() if json.loads(row)["key"].startswith("POST ")]
            assert len(writes) == (2 if name == "pr-review-verify-fixes" else 1), writes


if __name__ == "__main__":
    smoke(Path(sys.argv[1]).absolute(), Path(sys.argv[2]).absolute())
