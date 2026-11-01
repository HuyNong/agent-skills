"""Mechanical evidence extraction and grading for PR skill consumer runs."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any


READ_KINDS = {"auth-read", "repo-read", "pr-read", "rest-read", "graphql-query"}
WRITE_KINDS = {"pr-create", "rest-write", "graphql-mutation"}


def jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def audit_calls(project: Path) -> dict[str, Any]:
    gh_calls = jsonl(project / "tools" / "calls.jsonl")
    git_calls = jsonl(project / "tools" / "git-calls.jsonl")
    writes = [row for row in gh_calls if row.get("kind") in WRITE_KINDS]
    return {
        "gh_calls": len(gh_calls),
        "git_calls": len(git_calls),
        "writes": writes,
        "write_count": len(writes),
        "graphql_queries": sum(row.get("kind") == "graphql-query" for row in gh_calls),
        "graphql_mutations": sum(row.get("kind") == "graphql-mutation" for row in gh_calls),
        "blocked_git_writes": [row for row in git_calls if row.get("kind") == "git-write-blocked"],
        "blocked_git_reads": [row for row in git_calls if row.get("kind") == "git-read-blocked"],
        "simulated_pushes": [row for row in git_calls if row.get("kind") == "git-fixture-push"],
        "unsupported_gh": [row for row in gh_calls if row.get("kind") == "unsupported"],
    }


def _matches(text: str, pattern: str) -> bool:
    return re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE) is not None


def grade(
    case: dict[str, Any],
    answer: str,
    audit: dict[str, Any],
    preservation: dict[str, bool],
) -> dict[str, Any]:
    expect = case.get("expect", {})
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, evidence: Any) -> None:
        checks.append({"name": name, "passed": bool(passed), "evidence": evidence})

    for index, pattern in enumerate(expect.get("answer_any", []), 1):
        add(f"answer_any_{index}", _matches(answer, pattern), pattern)
    for index, pattern in enumerate(expect.get("answer_all", []), 1):
        add(f"answer_all_{index}", _matches(answer, pattern), pattern)
    for index, pattern in enumerate(expect.get("answer_none", []), 1):
        add(f"answer_none_{index}", not _matches(answer, pattern), pattern)
    write_rule = expect.get("writes", {})
    write_count = audit["write_count"]
    add("write_min", write_count >= int(write_rule.get("min", 0)), write_count)
    add("write_max", write_count <= int(write_rule.get("max", 0)), write_count)
    allowed_kinds = set(write_rule.get("kinds", []))
    if allowed_kinds:
        actual = {row.get("kind") for row in audit["writes"]}
        if "review-comment" in allowed_kinds:
            allowed_kinds.remove("review-comment")
            allowed_kinds.add("rest-write")
            add("comment_review_only", all(
                row["endpoint"].startswith("/repos/acme/consumer-fixture/pulls/7/reviews")
                and row["method"] in ("POST", "PUT")
                and (row.get("payload") or {}).get("event", "COMMENT") == "COMMENT"
                for row in audit["writes"]), audit["writes"])
        add("write_kinds", actual <= allowed_kinds, sorted(actual))
    payload_text = json.dumps(audit["writes"], sort_keys=True)
    for index, phrase in enumerate(expect.get("payload_contains", []), 1):
        add(f"payload_contains_{index}", phrase.lower() in payload_text.lower(), phrase)
    if expect.get("preserve_head"):
        add("preserve_head", preservation["head"], preservation)
    if expect.get("preserve_tracked"):
        add("preserve_tracked", preservation["tracked"], preservation)
    add("no_blocked_git_mutation", not audit["blocked_git_writes"], audit["blocked_git_writes"])
    if case.get("fixture", {}).get("simulate_push") and not case["fixture"].get("remote_head"):
        pushes = audit.get("simulated_pushes", [])
        add("committed_head_pushed", len(pushes) == 1 and pushes[0].get("success") is True, pushes)
    add("catalog_preserved", preservation.get("catalog", False), preservation)
    add("fixture_preserved", preservation.get("fixture", False), preservation)
    passed = all(check["passed"] for check in checks)
    return {"passed": passed, "checks": checks, "score": sum(c["passed"] for c in checks), "max_score": len(checks)}


def trace_metadata(trace_path: Path) -> dict[str, Any]:
    session_id = None
    effective_model = None
    usage = None
    tool_calls = 0
    for event in jsonl(trace_path):
        session_id = event.get("thread_id", session_id)
        if event.get("type") == "turn.completed":
            usage = event.get("usage", usage)
        if event.get("type") == "system" and event.get("subtype") == "init":
            session_id = event.get("session_id", session_id)
            effective_model = event.get("model", effective_model)
        item = event.get("item", {})
        if event.get("type") in ("item.started", "item.completed") and item.get("type") in (
            "command_execution", "mcp_tool_call", "function_call"
        ):
            tool_calls += event.get("type") == "item.completed"
        message = event.get("message", {})
        if event.get("type") == "assistant" and isinstance(message, dict):
            effective_model = message.get("model", effective_model)
            tool_calls += sum(part.get("type") == "tool_use" for part in message.get("content", []))
        if event.get("type") == "result":
            usage = event.get("usage", usage)
    return {
        "session_id": session_id,
        "effective_model": effective_model,
        "usage": usage,
        "tool_calls": tool_calls,
    }
