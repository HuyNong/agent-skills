"""Opt-in real local bare-remote push; never uses a network transport."""
import json
from pathlib import Path
import shutil
import subprocess
import sys


def setup_push(seed):
    bare = seed / ".fixture-push.git"
    subprocess.run(["/usr/bin/git", "init", "--bare", "-q", str(bare)], check=True)
    subprocess.run(["/usr/bin/git", "-C", str(seed), "push", "-q", str(bare),
                    "refs/remotes/origin/main:refs/heads/main"], check=True)
    with (seed / ".git/info/exclude").open("a") as out:
        out.write("\n.fixture-push.git/\n")
    (seed / "tools/push-permission.json").write_text(json.dumps({
        "bare": ".fixture-push.git", "remote": "origin", "branch": "negative-amount-guard"}))
    target = seed / "tools/simulate-push.py"
    shutil.copy2(Path(__file__), target)
    target.chmod(0o755)


def simulate():
    root = Path(__file__).resolve().parent
    project = root.parent
    args = sys.argv[1:]
    permission = json.loads((root / "push-permission.json").read_text())
    branch = permission["branch"]
    words = [arg for arg in args[1:] if not arg.startswith("-")]
    flags = [arg for arg in args[1:] if arg.startswith("-")]
    refs = {branch, "HEAD", "HEAD:" + branch, "HEAD:refs/heads/" + branch,
            branch + ":" + branch, branch + ":refs/heads/" + branch,
            "refs/heads/" + branch, "refs/heads/" + branch + ":refs/heads/" + branch}
    allowed = (args[0] == "push" and len(words) in (1, 2) and words[0] == permission["remote"]
               and (len(words) == 1 or words[1] in refs)
               and all(flag in ("-u", "--set-upstream", "--porcelain", "--verbose", "--progress") for flag in flags))
    event = {"args": args, "kind": "git-write-blocked"}
    if not allowed:
        print("offline fixture: only the selected ordinary origin push is permitted", file=sys.stderr)
        rc = 73
    else:
        def git(*values):
            return subprocess.check_output(["/usr/bin/git", *values], cwd=project, text=True).strip()
        head = git("rev-parse", "HEAD")
        bare = project / permission["bare"]
        result = subprocess.run(["/usr/bin/git", "push", str(bare), "HEAD:refs/heads/" + branch], cwd=project)
        rc = result.returncode
        remote_head = git("--git-dir=" + str(bare), "rev-parse", "refs/heads/" + branch) if rc == 0 else None
        event = {"args": args, "kind": "git-fixture-push", "success": rc == 0 and remote_head == head,
                 "head": head, "remote_head": remote_head}
        # workspace-write keeps the checkout's .git read-only. Verify the real
        # bare ref; the transport serves it without editing local tracking refs.
    with (root / "git-calls.jsonl").open("a") as out:
        out.write(json.dumps(event) + "\n")
    return rc


if __name__ == "__main__":
    raise SystemExit(simulate())
