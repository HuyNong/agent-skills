#!/usr/bin/env python3
"""Run matched original/candidate PR-skill evaluations in isolated repositories."""

from __future__ import annotations

import argparse
import hashlib
from concurrent.futures import CancelledError, ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any

from consumer_fixtures import build_seed, catalog_hash, install_catalog, run_git, tree_hash
from consumer_grading import audit_calls, grade
from consumer_runtime import execute, runtime_version
from consumer_cases import canonical_cases, cases_digest, select_cases


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", required=True, choices=("codex", "claude"))
    parser.add_argument("--cases", required=True, type=Path)
    parser.add_argument("--original", required=True, type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--variants", default="original,candidate", help="comma-separated original,candidate subset")
    parser.add_argument("--case-id", action="append", default=[], help="run only a named case; repeatable")
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--max-workers", type=int, default=2, choices=(1, 2))
    parser.add_argument("--simulate-push", action="store_true", help="Opt in to a logged local bare-remote push fixture; no network or force push")
    return parser.parse_args()


def preservation(project: Path, before: dict[str, str], catalog_before: str) -> dict[str, bool]:
    status = run_git(project, "status", "--porcelain", "--untracked-files=no")
    expected_status = before["tracked_status"]
    return {
        "head": run_git(project, "rev-parse", "HEAD") == before["head"],
        "tracked": status == expected_status,
        "catalog": tree_hash(project / ".agents" / "skills") == catalog_before,
        "fixture": fixture_hash(project) == before["fixture"],
    }


def fixture_hash(project: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted((project / "tools").iterdir()):
        if path.is_file() and path.suffix != ".jsonl" and path.name != "simulated-state.json":
            digest.update(path.name.encode()); digest.update(path.read_bytes())
    return digest.hexdigest()


def run_one(
    runtime: str,
    version: str | None,
    case: dict[str, Any],
    variant: str,
    source: Path,
    seed: Path,
    output_root: Path,
    workspace_root: Path,
    timeout: int,
) -> dict[str, Any]:
    project = workspace_root / f"{case['id']}-{variant}"
    shutil.copytree(seed, project)
    expected_catalog_hash = install_catalog(source, project)
    installed_catalog_hash = tree_hash(project / ".agents" / "skills")
    before = {
        "head": run_git(project, "rev-parse", "HEAD"),
        "tracked_status": run_git(project, "status", "--porcelain", "--untracked-files=no"),
        "fixture": fixture_hash(project),
    }
    output = output_root / case["id"] / variant
    metadata = execute(runtime, case["prompt"], project, output, timeout)
    artifacts = project / ".consumer-artifacts"
    if artifacts.exists():
        shutil.copytree(artifacts, output / "consumer-artifacts")
    preserved = preservation(project, before, installed_catalog_hash)
    audit = audit_calls(project)
    answer = (output / "answer.txt").read_text(encoding="utf-8", errors="replace")
    result = {
        "case": case["id"],
        "intent": case["intent"],
        "prompt": case["prompt"],
        "input_fixture": case.get("fixture", {}),
        "input_fixture_hash": before["fixture"],
        "variant": variant,
        "runtime": runtime,
        "runtime_version": version,
        "effective_model": metadata.pop("effective_model", None),
        "source_catalog_hash": expected_catalog_hash,
        "installed_catalog_hash": installed_catalog_hash,
        "input_head": before["head"],
        "input_tracked_status": before["tracked_status"],
        "preservation": preserved,
        "audit": audit,
        "grade": {**grade(case, answer, audit, preserved),
                  "valid": metadata["evaluation_status"] == "completed"},
        "metadata": metadata,
        "artifacts": {
            "answer": str(output / "answer.txt"),
            "trace": str(output / "trace.jsonl"),
            "stderr": str(output / "stderr.log"),
        },
    }
    return result


def main() -> int:
    args = arguments()
    cases_path = args.cases.resolve()
    original = args.original.resolve()
    candidate = args.candidate.resolve()
    output = args.output.resolve()
    variants = [item.strip() for item in args.variants.split(",") if item.strip()]
    if not variants or any(item not in ("original", "candidate") for item in variants):
        raise SystemExit("--variants must contain original and/or candidate")
    cases_bytes = cases_path.read_bytes()
    payload = json.loads(cases_bytes)
    try:
        cases = select_cases(payload["cases"], args.case_id, args.simulate_push)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    version = runtime_version(args.runtime)
    output.mkdir(parents=True, exist_ok=True)
    (output / "inputs-used.json").write_bytes(canonical_cases(cases, include_expectations=False))
    if args.runtime == "claude":
        pending = {
            "status": "pending",
            "reason": "Claude execution is intentionally pending; authenticate and request it separately.",
            "runtime_version": version,
            "cases": [case["id"] for case in cases],
        }
        (output / "summary.json").write_text(json.dumps(pending, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(pending))
        return 0
    if not version:
        raise SystemExit("codex runtime unavailable")
    sources = {"original": original, "candidate": candidate}
    source_hashes = {variant: catalog_hash(sources[variant]) for variant in variants}
    workspace_root = Path(tempfile.mkdtemp(prefix="pr-skill-consumers-"))
    results: list[dict[str, Any]] = []
    try:
        seeds: dict[str, Path] = {}
        for case in cases:
            seed = workspace_root / f"seed-{case['id']}"
            build_seed(seed, case.get("fixture", {}))
            seeds[case["id"]] = seed
        jobs = [(case, variant) for case in cases for variant in variants]
        with ThreadPoolExecutor(max_workers=args.max_workers) as pool:
            futures = {
                pool.submit(
                    run_one, args.runtime, version, case, variant, sources[variant], seeds[case["id"]],
                    output, workspace_root, args.timeout,
                ): (case["id"], variant)
                for case, variant in jobs
            }
            for future in as_completed(futures):
                try:
                    result = future.result()
                except CancelledError:
                    continue
                results.append(result)
                if result["metadata"]["evaluation_status"] == "runtime-blocked":
                    for pending in futures:
                        pending.cancel()
    finally:
        shutil.rmtree(workspace_root, ignore_errors=True)
    results.sort(key=lambda row: (row["case"], row["variant"]))
    # No consumers remain alive. Archive the rubric and graded metadata now.
    (output / "cases-used.json").write_bytes(canonical_cases(cases))
    for result in results:
        path = output / result["case"] / result["variant"] / "metadata.json"
        path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    summary = {
        "status": "completed" if len(results) == len(jobs) and all(
            row["metadata"]["evaluation_status"] == "completed" for row in results) else "incomplete",
        "runtime": args.runtime,
        "runtime_version": version,
        "effective_models": sorted({row["effective_model"] for row in results}, key=lambda value: value or ""),
        "source_hashes": source_hashes,
        "cases_hash": cases_digest(cases),
        "source_cases_hash": hashlib.sha256(cases_bytes).hexdigest(),
        "pending_cases": [{"case": case["id"], "variant": variant} for case, variant in jobs
                          if not any(row["case"] == case["id"] and row["variant"] == variant for row in results)],
        "expected_answers_in_consumer_workspace": False,
        "expectations_archived_after_execution": True,
        "network_access": False,
        "results": results,
        "passed": sum(row["grade"]["passed"] and row["grade"]["valid"] for row in results),
        "runtime_blocked": sum(row["metadata"]["evaluation_status"] == "runtime-blocked" for row in results),
        "total": len(results),
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ("status", "runtime", "runtime_version", "passed", "total")}))
    return 0 if summary["status"] == "completed" and all(row["grade"]["valid"] and
                    (row["variant"] == "original" or row["grade"]["passed"]) for row in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
