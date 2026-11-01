#!/usr/bin/env python3
"""Offline gh fixture: serve reads, simulate writes, and log exact operations."""

from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parent
ARGS = sys.argv[1:]


def option_value(*names: str) -> str | None:
    for name in names:
        if name in ARGS and ARGS.index(name) + 1 < len(ARGS):
            return ARGS[ARGS.index(name) + 1]
    return None


def input_payload() -> object | None:
    input_name = option_value("--input")
    if not input_name:
        fields = {}
        for index, arg in enumerate(ARGS[:-1]):
            if arg in ("-f", "-F", "--field", "--raw-field") and "=" in ARGS[index + 1]:
                key, value = ARGS[index + 1].split("=", 1)
                fields[key] = Path(value[1:]).read_text() if value.startswith("@") else value
        return fields or None
    try:
        text = sys.stdin.read() if input_name == "-" else Path(input_name).read_text(encoding="utf-8")
        return json.loads(text)
    except (OSError, ValueError):
        return {"unparsed": True}


def graphql_text() -> str:
    for index, arg in enumerate(ARGS):
        if arg in ("-f", "-F", "--field", "--raw-field") and index + 1 < len(ARGS):
            value = ARGS[index + 1]
            if value.startswith("query="):
                return value.split("=", 1)[1]
    return ""


def classify_api() -> tuple[str, str, str]:
    endpoint = next((arg for arg in ARGS[1:] if arg == "graphql" or arg.startswith(("/repos/", "repos/", "/user"))), "")
    endpoint = endpoint if endpoint == "graphql" else "/" + endpoint.split("?", 1)[0].strip("/")
    query = graphql_text()
    if endpoint == "graphql" and re.match(r"^\s*(query\b|\{)", query) and not re.search(r"\bmutation\b", query):
        return endpoint, "POST", "graphql-query"
    explicit = option_value("-X", "--method")
    implied_post = any(arg in ARGS for arg in ("-f", "-F", "--field", "--raw-field", "--input"))
    method = (explicit or ("POST" if implied_post else "GET")).upper()
    kind = "graphql-mutation" if endpoint == "graphql" else ("rest-read" if method == "GET" else "rest-write")
    return endpoint, method, kind


def record(kind: str, endpoint: str = "", method: str = "", payload: object | None = None) -> None:
    row = {"args": ARGS, "kind": kind, "endpoint": endpoint, "method": method, "payload": payload}
    with (ROOT / "calls.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, sort_keys=True) + "\n")


def emit(value: object) -> None:
    query = option_value("--jq", "-q")
    pages = value.get("_pages") if isinstance(value, dict) else None
    selected = pages if pages and "--paginate" in ARGS else ([pages[0]] if pages else [value])
    if "--slurp" in ARGS:
        selected = [selected]
    for page in selected:
        if query:
            completed = subprocess.run(
                ["jq", "-r", query], input=json.dumps(page), text=True, capture_output=True, check=False
            )
            sys.stdout.write(completed.stdout)
            sys.stderr.write(completed.stderr)
            if completed.returncode:
                raise SystemExit(completed.returncode)
        else:
            print(json.dumps(page))


def main() -> int:
    data = json.loads((ROOT / "responses.json").read_text(encoding="utf-8"))
    state_path = ROOT / "simulated-state.json"
    if state_path.exists():
        data.update(json.loads(state_path.read_text(encoding="utf-8")))
    if ARGS[:2] == ["auth", "status"]:
        record("auth-read")
        print("github.com\n  Logged in to github.com as fixture-user")
        return 0
    if ARGS[:2] == ["repo", "view"]:
        record("repo-read")
        emit(data["repo"])
        return 0
    if ARGS[:2] == ["pr", "view"]:
        record("pr-read", "/repos/acme/consumer-fixture/pulls/7", "GET")
        if not data.get("current_pr_exists", True) and "7" not in ARGS[2:]:
            print("no pull requests found for branch negative-amount-guard", file=sys.stderr)
            return 1
        emit(data["/repos/acme/consumer-fixture/pulls/7"])
        return 0
    if ARGS[:2] == ["pr", "diff"]:
        record("pr-read", "/repos/acme/consumer-fixture/pulls/7/files", "GET")
        print(data["diff"])
        return 0
    if ARGS[:2] == ["pr", "checks"]:
        record("pr-read", "/repos/acme/consumer-fixture/pulls/7/checks", "GET")
        print("checks unavailable in offline fixture", file=sys.stderr)
        return 1
    if ARGS[:2] == ["pr", "create"]:
        record("pr-create", "/repos/acme/consumer-fixture/pulls", "POST", {"args": ARGS[2:]})
        print("https://github.com/acme/consumer-fixture/pull/7")
        return 0
    if ARGS and ARGS[0] == "api":
        endpoint, method, kind = classify_api()
        payload = input_payload()
        record(kind, endpoint, method, payload)
        if kind == "graphql-query":
            emit({"data": {"repository": {"pullRequest": {"mergeable": "UNKNOWN", "reviewDecision": None}}}})
            return 0
        if kind in ("rest-write", "graphql-mutation"):
            if endpoint.endswith("/reviews") and method == "POST":
                review = {**(payload or {}), "id": 700, "user": {"login": "fixture-user"},
                    "state": "COMMENTED", "html_url": "https://github.com/acme/consumer-fixture/pull/7#pullrequestreview-700"}
                data[endpoint] = [*data.get(endpoint, []), review]
                data[endpoint + "/700"] = review
                comments = []
                for index, comment in enumerate((payload or {}).get("comments", []), 701):
                    comments.append({**comment, "id": index, "pull_request_review_id": 700,
                        "commit_id": review.get("commit_id"), "user": {"login": "fixture-user"},
                        "html_url": f"https://github.com/acme/consumer-fixture/pull/7#discussion_r{index}"})
                data[endpoint + "/700/comments"] = comments
                wide = endpoint.removesuffix("/reviews") + "/comments"
                data[wide] = [*data.get(wide, []), *comments]
                state_path.write_text(json.dumps(data), encoding="utf-8")
                emit(review)
            elif method == "PUT" and re.search(r"/reviews/\d+$", endpoint):
                review = {**data.get(endpoint, {}), **(payload or {})}
                data[endpoint] = review
                parent = endpoint.rsplit("/", 1)[0]
                data[parent] = [review if item["id"] == review["id"] else item for item in data[parent]]
                state_path.write_text(json.dumps(data), encoding="utf-8")
                emit(review)
            elif endpoint.endswith("/replies") or endpoint.endswith("/comments"):
                emit({"id": 701, "html_url": "https://github.com/acme/consumer-fixture/pull/7#discussion_r701"})
            else:
                emit({"ok": True})
            return 0
        if endpoint not in data:
            print(f"offline fixture: unsupported read endpoint {endpoint}", file=sys.stderr)
            return 2
        emit(data[endpoint])
        return 0
    record("unsupported")
    print("offline fixture: unsupported gh command", file=sys.stderr)
    return 2


raise SystemExit(main())
