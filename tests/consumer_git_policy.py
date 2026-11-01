"""Fixture-scoped Git command policy used by the copied ``tools/git`` guard."""

from __future__ import annotations

import fnmatch
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import NoReturn


BLOCKED = 73
READ_COMMANDS = {
    "blame", "branch", "cat-file", "config", "count-objects", "describe", "diff",
    "diff-files", "diff-index", "diff-tree", "for-each-ref", "grep", "hash-object", "log",
    "ls-files", "ls-remote", "ls-tree", "merge-base", "name-rev", "remote", "rev-list",
    "rev-parse", "show", "show-ref", "shortlog", "status", "symbolic-ref",
    "verify-commit", "verify-tag",
}
SAFE_GLOBAL = {"-P", "--no-pager", "--no-replace-objects", "--no-lazy-fetch", "--no-optional-locks", "--no-advice"}
SAFE_CONFIG = {
    "color.ui", "core.abbrev", "core.quotepath", "diff.algorithm", "diff.context",
    "diff.interhunkcontext", "diff.renames", "format.pretty", "log.date",
    "status.branch", "status.showuntrackedfiles",
}
BRANCH_MUTATIONS = {
    "-c", "-C", "-d", "-D", "-f", "-m", "-M", "--copy", "--delete", "--edit-description",
    "--create-reflog", "--force", "--move", "--no-track", "--recurse-submodules",
    "--set-branch-description", "--set-upstream-to", "--track", "--unset-upstream",
}
BRANCH_READ_FLAGS = {
    "--abbrev", "--all", "--color", "--column", "--contains", "--format", "--list",
    "--merged", "--no-merged", "--omit-empty", "--points-at", "--remotes", "--show-current",
    "--sort", "-a", "-l", "-r", "-v", "-vv",
}
SYMBOLIC_REF_READ_FLAGS = {"-q", "--quiet", "--short", "--no-recurse"}
DEFENSIVE_CONFIG = {
    "safe.barerepository": "explicit",
    "core.hookspath": "/dev/null",
    "core.fsmonitor": "false",
}
CONFIG_READ = {"--get", "--get-all", "--get-regexp", "--list", "-l", "--local", "--name-only", "--null", "--show-scope"}
UNSAFE_GLOBAL = {"--bare", "--exec-path", "--html-path", "--info-path", "--man-path", "--paginate", "-p", "--config-env", "--help", "-h", "--version"}
UNSAFE_ARGS = {
    "--external-diff", "--ext-diff", "--filters", "--no-index", "--pathspec-file-nul", "--pathspec-from-file",
    "--paginate", "--pager", "--open-files-in-pager", "--recurse-submodules", "--server-option", "--textconv",
    "--upload-pack", "--receive-pack", "--exec-path", "--config-env", "--includes", "--show-origin",
    "--output", "-o", "--contents", "--path", "--stdin-paths",
}
REMOTE_NAME = re.compile(r"^[A-Za-z0-9._-]+$")
NAMESPACE = re.compile(r"^[A-Za-z0-9._/-]+$")


class ReadDenied(ValueError):
    """A syntactically valid read that must stay inside the fixture boundary."""


def under(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def log(root: Path, args: list[str], kind: str) -> None:
    with (root / "git-calls.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"args": args, "kind": kind}) + "\n")


def deny(root: Path, args: list[str], reason: str) -> NoReturn:
    log(root, args, "git-write-blocked")
    print("consumer fixture: " + reason, file=sys.stderr)
    raise SystemExit(BLOCKED)


def deny_read(root: Path, args: list[str], reason: str) -> NoReturn:
    log(root, args, "git-read-blocked")
    print("consumer fixture: " + reason, file=sys.stderr)
    raise SystemExit(BLOCKED)


def env_without_git(root: Path) -> dict[str, str]:
    env = os.environ.copy()
    for key in list(env):
        if key.startswith("GIT_") or key in {"PAGER", "LESS", "PYTHONPATH"}:
            env.pop(key, None)
    env["PATH"] = os.pathsep.join(part for part in env.get("PATH", "").split(os.pathsep)
                                   if part and Path(part).resolve() != root)
    env.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_PAGER": "cat", "PAGER": "cat", "GIT_TERMINAL_PROMPT": "0",
                "GIT_OPTIONAL_LOCKS": "0"})
    return env


def safe_path(raw: str, base: Path) -> Path:
    if not raw or "\x00" in raw or raw.startswith("~"):
        raise ValueError("invalid path operand")
    return (Path(raw) if Path(raw).is_absolute() else base / raw).resolve()


def permitted_bare(root: Path, project: Path) -> Path | None:
    permission = root / "push-permission.json"
    if not permission.is_file():
        return None
    try:
        data = json.loads(permission.read_text(encoding="utf-8"))
        bare = safe_path(str(data["bare"]), project)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None
    return bare if under(bare, project) and bare.is_dir() else None


def parse(argv: list[str], root: Path, project: Path) -> dict[str, object]:
    scope = Path.cwd().resolve()
    forwarded: list[str] = []
    git_dir: Path | None = None
    work_tree: Path | None = None
    scope_denied = False
    index = 0

    def take(position: int, option: str) -> tuple[str, int]:
        if position >= len(argv) or argv[position].startswith("-"):
            raise ValueError(option + " needs an operand")
        return argv[position], position + 1

    while index < len(argv):
        arg = argv[index]
        if arg == "-C" or (arg.startswith("-C") and len(arg) > 2):
            raw, index = take(index + 1, "-C") if arg == "-C" else (arg[2:], index + 1)
            scope = safe_path(raw, scope)
            if not under(scope, project):
                scope_denied = True
            forwarded += ["-C", raw] if arg == "-C" else [arg]
            continue
        if arg == "--git-dir" or arg.startswith("--git-dir="):
            raw, index = take(index + 1, "--git-dir") if arg == "--git-dir" else (arg.split("=", 1)[1], index + 1)
            git_dir = safe_path(raw, scope)
            allowed = {project / ".git"}
            bare = permitted_bare(root, project)
            if bare:
                allowed.add(bare)
            if git_dir not in allowed:
                scope_denied = True
            forwarded += ["--git-dir", raw] if arg == "--git-dir" else [arg]
            continue
        if arg == "--work-tree" or arg.startswith("--work-tree="):
            raw, index = take(index + 1, "--work-tree") if arg == "--work-tree" else (arg.split("=", 1)[1], index + 1)
            work_tree = safe_path(raw, scope)
            if work_tree != project:
                scope_denied = True
            forwarded += ["--work-tree", raw] if arg == "--work-tree" else [arg]
            continue
        if arg == "--namespace" or arg.startswith("--namespace="):
            raw, index = take(index + 1, "--namespace") if arg == "--namespace" else (arg.split("=", 1)[1], index + 1)
            if not NAMESPACE.fullmatch(raw) or ".." in raw:
                raise ValueError("unsafe namespace")
            forwarded += ["--namespace", raw] if arg == "--namespace" else [arg]
            continue
        if arg == "-c" or (arg.startswith("-c") and len(arg) > 2):
            raw, index = take(index + 1, "-c") if arg == "-c" else (arg[2:], index + 1)
            key, separator, value = raw.partition("=")
            normalized = key.lower()
            if not separator or normalized not in SAFE_CONFIG and normalized not in DEFENSIVE_CONFIG:
                raise ValueError("config override is not read-only")
            if normalized in DEFENSIVE_CONFIG and value != DEFENSIVE_CONFIG[normalized]:
                raise ValueError("defensive config override has an unsafe value")
            forwarded += ["-c", raw] if arg == "-c" else [arg]
            continue
        if arg in SAFE_GLOBAL:
            forwarded.append(arg)
            index += 1
            continue
        if arg in UNSAFE_GLOBAL or arg.startswith(("--exec-path=", "--config-env=")):
            raise ValueError("unsafe global option")
        if arg.startswith("-"):
            raise ValueError("unknown global option")
        return {"command": arg, "args": argv[index + 1:], "forwarded": forwarded + [arg] + argv[index + 1:],
                "scope": scope, "git_dir": git_dir, "work_tree": work_tree,
                "scope_denied": scope_denied or not under(scope, project)}
    raise ValueError("missing Git command")


def validate(command: str, args: list[str], root: Path, project: Path, scope: Path) -> None:
    for arg in args:
        if arg in UNSAFE_ARGS or arg.startswith(("--external-diff=", "--ext-diff=", "--output=", "--textconv=", "--path=")):
            raise ValueError("unsafe command option")
        if arg in {"--git-dir", "--work-tree", "--namespace", "-C", "-c"}:
            raise ValueError("global option must precede the command")
    if command == "branch":
        if any(arg in BRANCH_MUTATIONS or arg.startswith("--set-upstream-to=") for arg in args):
            raise ValueError("branch mutation is not allowed")
        positional = [arg for arg in args if not arg.startswith("-")]
        read_form = any(arg in BRANCH_READ_FLAGS or arg.startswith(("--abbrev=", "--color=", "--column=", "--format=", "--sort=")) for arg in args)
        if positional and not read_form:
            raise ValueError("branch creation is not allowed")
    if command == "symbolic-ref":
        if any(arg.startswith("-") and arg not in SYMBOLIC_REF_READ_FLAGS for arg in args):
            raise ValueError("symbolic-ref mutation or unknown option is not allowed")
        if len([arg for arg in args if not arg.startswith("-")]) != 1:
            raise ValueError("symbolic-ref only permits one reference read")
    if command == "remote":
        positional = [arg for arg in args if not arg.startswith("-")]
        if positional and positional[0] not in {"get-url"}:
            raise ValueError("remote mutation or network query is not allowed")
        if positional and positional[0] == "get-url" and len(positional) != 2:
            raise ValueError("remote get-url needs one remote")
    if command == "config":
        reads = False
        for arg in args:
            if arg in {"--global", "--system", "--worktree", "--file", "--blob", "--includes", "--show-origin"}:
                raise ValueError("config scope or include is not allowed")
            if arg in CONFIG_READ:
                reads = True
            elif arg.startswith("-"):
                raise ValueError("config write or unknown option is not allowed")
        if not reads:
            raise ValueError("config writes are not allowed")
    if command == "hash-object" and any(arg in {"-w", "--write", "--literally"} for arg in args):
        raise ValueError("hash-object writes are not allowed")
    if command in {"blame", "diff", "diff-files", "diff-index", "grep", "hash-object", "ls-files"}:
        if any(raw.startswith("/") or raw == ".." or raw.startswith("../") or "/../" in raw for raw in args):
            raise ValueError("path leaves the fixture checkout")
        paths = args[args.index("--") + 1:] if "--" in args else []
        if command == "hash-object":
            paths += [arg for arg in args if not arg.startswith("-")]
        for raw in paths:
            if raw and not raw.startswith(":") and not under(safe_path(raw, scope), project):
                raise ValueError("path leaves the fixture checkout")


def ls_remote_request(args: list[str]) -> tuple[list[str], list[str]]:
    options: list[str] = []
    positional: list[str] = []
    for arg in args:
        if arg in {"--heads", "-h", "--tags", "-t", "--refs", "--quiet", "-q", "--exit-code"}:
            options.append(arg)
        elif arg == "--":
            continue
        elif arg.startswith("-"):
            raise ValueError("unsafe ls-remote option")
        else:
            positional.append(arg)
    remote = positional[0] if positional else "origin"
    if not REMOTE_NAME.fullmatch(remote):
        raise ReadDenied("ls-remote accepts fixture remote names only")
    return options, positional


def ls_remote(parsed: dict[str, object], root: Path, project: Path, env: dict[str, str]) -> int:
    options, positional = ls_remote_request(list(parsed["args"]))
    remote = positional[0] if positional else "origin"
    patterns = positional[1:]
    bare = permitted_bare(root, project)
    if bare and remote == "origin" and (root / "push-permission.json").is_file():
        return subprocess.run(["/usr/bin/git", "ls-remote", *options, str(bare), *patterns],
                              cwd=project, env=env, check=False).returncode
    git_dir = parsed["git_dir"] or project / ".git"
    rows = subprocess.check_output(
        ["/usr/bin/git", f"--git-dir={git_dir}", "for-each-ref", "--format=%(objectname) %(refname)",
         f"refs/remotes/{remote}/", "refs/tags/"], cwd=project, env=env, text=True,
        stderr=subprocess.STDOUT,
    ).splitlines()
    heads = "--heads" in options or "-h" in options
    tags = "--tags" in options or "-t" in options
    matched = 0
    for row in rows:
        sha, ref = row.split(" ", 1)
        if ref.startswith(f"refs/remotes/{remote}/"):
            name = ref.removeprefix(f"refs/remotes/{remote}/")
            out = "refs/heads/" + name
            if not tags or heads:
                if not patterns or any(fnmatch.fnmatch(name, p) or fnmatch.fnmatch(out, p) for p in patterns):
                    print(sha + "\t" + out); matched += 1
        elif ref.startswith("refs/tags/") and not heads:
            name = ref.removeprefix("refs/tags/")
            if not patterns or any(fnmatch.fnmatch(name, p) or fnmatch.fnmatch(ref, p) for p in patterns):
                print(sha + "\t" + ref); matched += 1
    return 0 if matched or "--exit-code" not in options else 2


def run(argv: list[str], root: Path) -> int:
    project = root.parent
    parsed = parse(argv, root, project)
    env = env_without_git(root)
    command, args = str(parsed["command"]), list(parsed["args"])
    if command == "fetch":
        if parsed["scope_denied"]:
            deny_read(root, list(parsed["forwarded"]), "fixture fetch is outside the fixture checkout")
        log(root, list(parsed["forwarded"]), "git-fixture-fetch")
        print("offline fixture: remote refs refreshed from the prepared seed", file=sys.stderr)
        return 0
    if command == "push":
        if (not parsed["scope_denied"] and (root / "push-permission.json").is_file()
                and parsed["git_dir"] in (None, project / ".git") and parsed["work_tree"] in (None, project)):
            helper = root / "simulate-push.py"
            if helper.is_file():
                os.execv(sys.executable, [sys.executable, str(helper), "push", *args])
        deny(root, list(parsed["forwarded"]), "git mutation blocked: push")
    if command == "ls-remote":
        ls_remote_request(args)
        if parsed["scope_denied"]:
            deny_read(root, list(parsed["forwarded"]), "ls-remote is outside the fixture checkout")
        result = ls_remote(parsed, root, project, env)
        log(root, list(parsed["forwarded"]), "git-read")
        return result
    if command not in READ_COMMANDS:
        deny(root, list(parsed["forwarded"]), "git command is not in the read-only allowlist: " + command)
    validate(command, args, root, project, Path(parsed["scope"]))
    if parsed["scope_denied"]:
        deny_read(root, list(parsed["forwarded"]), "Git read is outside the fixture checkout")
    forwarded = list(parsed["forwarded"])
    if command in {"diff", "diff-files", "diff-index", "diff-tree", "log", "show"}:
        command_index = len(forwarded) - len(args) - 1
        forwarded[command_index + 1:command_index + 1] = ["--no-ext-diff", "--no-textconv"]
    log(root, forwarded, "git-read")
    return subprocess.run(["/usr/bin/git", *forwarded], cwd=Path.cwd(), env=env, check=False).returncode


def main(argv: list[str], root: Path) -> int:
    try:
        return run(argv, root)
    except ReadDenied as error:
        deny_read(root, argv, str(error))
    except (OSError, subprocess.CalledProcessError, ValueError) as error:
        deny(root, argv, str(error))
    return BLOCKED
