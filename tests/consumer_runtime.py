"""Bounded external runtime execution and process cleanup for consumer checks."""
from __future__ import annotations

import os
from pathlib import Path
import signal
import subprocess
import time
from typing import Any
from consumer_grading import jsonl, trace_metadata


def runtime_outcome(trace_path: Path, exit_code: int, timed_out: bool) -> str:
    messages = [str(event.get("message", "")) + str(event.get("error", ""))
                for event in jsonl(trace_path) if event.get("type") in ("error", "turn.failed")]
    text = " ".join(messages).lower()
    if any(marker in text for marker in ("usage limit", "quota", "rate limit", "unauthorized", "authentication")):
        return "runtime-blocked"
    if timed_out:
        return "timeout"
    return "completed" if exit_code == 0 else "runtime-error"

def runtime_version(runtime: str) -> str | None:
    try:
        completed = subprocess.run([runtime, "--version"], text=True, capture_output=True, timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return (completed.stdout or completed.stderr).strip() or None


def command_for(runtime: str, project: Path, answer: Path) -> list[str]:
    if runtime == "codex":
        return [
            "codex", "exec", "--ephemeral", "--json", "--color", "never",
            "--sandbox", "workspace-write", "-c", 'approval_policy="never"',
            "-c", "sandbox_workspace_write.network_access=false", "-C", str(project),
            "--output-last-message", str(answer), "-",
        ]
    return [
        "claude", "-p", "--verbose", "--output-format", "stream-json", "--no-session-persistence",
        "--strict-mcp-config", "--setting-sources", "project,local", "--permission-mode", "dontAsk",
        "--tools", "Bash,Read,Glob,Grep,Edit,Write,Skill",
    ]


def stop_process(process: subprocess.Popen[str]) -> tuple[bool, int]:
    os.killpg(process.pid, signal.SIGTERM)
    try:
        return True, process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        return True, process.wait(timeout=10)


def execute(
    runtime: str,
    prompt: str,
    project: Path,
    output: Path,
    timeout: int,
) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=False)
    answer_path = output / "answer.txt"
    trace_path = output / "trace.jsonl"
    stderr_path = output / "stderr.log"
    command = command_for(runtime, project, answer_path)
    env = os.environ.copy()
    env["PATH"] = str(project / "tools") + os.pathsep + env.get("PATH", "")
    scratch = project / ".consumer-artifacts"
    scratch.mkdir(mode=0o700)
    env["TMPDIR"] = str(scratch)
    start = time.monotonic()
    timed_out = False
    with trace_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
        process = subprocess.Popen(
            command,
            cwd=project,
            env=env,
            stdin=subprocess.PIPE,
            stdout=stdout,
            stderr=stderr,
            text=True,
            start_new_session=True,
        )
        try:
            process.communicate(prompt, timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out, _ = stop_process(process)
    if not answer_path.exists():
        answer_path.write_text("", encoding="utf-8")
    metadata = {
        "command": command,
        "pid": process.pid,
        "exit_code": process.returncode,
        "timed_out": timed_out,
        "evaluation_status": runtime_outcome(trace_path, process.returncode, timed_out),
        "duration_seconds": round(time.monotonic() - start, 3),
        **trace_metadata(trace_path),
    }
    return metadata
