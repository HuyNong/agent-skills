"""Real Git topology variants for create consumers; all remotes remain offline."""
import json
from pathlib import Path
from consumer_git import run_git


def branch_topology(seed, fixture, metadata):
    mode = fixture["branch_case"]
    base, head = metadata["base"], metadata["head"]
    if mode == "detached":
        run_git(seed, "checkout", "--detach", "-q", head)
    elif mode == "diverged":
        remote = run_git(seed, "commit-tree", base + "^{tree}", "-p", base, "-m", "test: remote branch work")
        run_git(seed, "update-ref", "refs/remotes/origin/negative-amount-guard", remote)
        metadata["response_head"] = remote
    elif mode == "fork":
        run_git(seed, "remote", "set-url", "origin", "https://github.com/fixture-user/consumer-fixture.git")
        run_git(seed, "remote", "add", "upstream", "https://github.com/acme/consumer-fixture.git")
        base = run_git(seed, "commit-tree", base + "^{tree}", "-p", base, "-m", "test: upstream base maintenance")
        run_git(seed, "update-ref", "refs/remotes/upstream/main", base)
        metadata["base"] = base
    else:
        raise ValueError("unsupported branch_case: " + mode)


def transport_topology(seed, fixture, metadata):
    """Only branch variants get these wrappers; ordinary fixture bytes stay stable."""
    mode = fixture["branch_case"]
    tools = seed / "tools"
    path = tools / "responses.json"
    data = json.loads(path.read_text())
    pr = data["/repos/acme/consumer-fixture/pulls/7"]
    if mode == "fork":
        pr["isCrossRepository"] = True
        pr["headRepositoryOwner"] = {"login": "fixture-user"}
        pr["headRepository"]["nameWithOwner"] = "fixture-user/consumer-fixture"
        pr["head"]["repo"] = {"full_name": "fixture-user/consumer-fixture", "owner": {"login": "fixture-user"}}
        data["fork_repo"] = {"name": "consumer-fixture", "nameWithOwner": "fixture-user/consumer-fixture",
                             "owner": {"login": "fixture-user"}, "defaultBranchRef": {"name": "main"}}
        data["/repos/fixture-user/consumer-fixture"] = data["fork_repo"]
    data["/repos/acme/consumer-fixture"] = data["repo"]
    path.write_text(json.dumps(data))
    original = tools / "gh"
    original.rename(tools / "gh-base")
    original.write_text(GH_WRAPPER)
    original.chmod(0o755)

GH_WRAPPER = '''#!/usr/bin/env python3
import json, os, pathlib, subprocess, sys
root = pathlib.Path(__file__).resolve().parent
args = sys.argv[1:]
if args[:2] == ["repo","view"] and "fixture-user/consumer-fixture" in args:
    data = json.loads((root/"responses.json").read_text())["fork_repo"]
    with (root/"calls.jsonl").open("a") as out:
        out.write(json.dumps({"args":args,"kind":"repo-read"})+"\\n")
    if "--jq" in args:
        sys.exit(subprocess.run(["jq","-r",args[args.index("--jq")+1]],input=json.dumps(data),text=True).returncode)
    print(json.dumps(data)); sys.exit(0)
os.execv(str(root/"gh-base"),[str(root/"gh-base"),*args])
'''
