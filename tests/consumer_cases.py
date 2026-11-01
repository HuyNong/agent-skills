"""Select effective cases and keep the rubric out of live runtime artifacts."""
import hashlib
import json


def select_cases(cases, ids, simulate_push=False):
    if ids:
        selected = set(ids)
        chosen = [case for case in cases if case["id"] in selected]
        missing = selected - {case["id"] for case in chosen}
        if missing:
            raise ValueError("unknown case ids: " + ", ".join(sorted(missing)))
    else:
        chosen = cases
    if not chosen:
        raise ValueError("no cases selected")
    if simulate_push:
        if len(chosen) != 1 or len(ids) != 1 or not chosen[0].get("fixture", {}).get("push_authorized"):
            raise ValueError("--simulate-push requires exactly one explicit --case-id marked fixture.push_authorized=true")
        chosen = [{**chosen[0], "fixture": {**chosen[0]["fixture"], "simulate_push": True}}]
    elif any(case.get("fixture", {}).get("simulate_push") for case in chosen):
        raise ValueError("push simulation also requires the explicit CLI opt-in")
    return chosen


def canonical_cases(cases, include_expectations=True):
    effective = cases if include_expectations else [
        {key: case[key] for key in ("id", "intent", "fixture", "prompt") if key in case} for case in cases]
    return (json.dumps({"version": 1, "cases": effective}, sort_keys=True, ensure_ascii=False, indent=2) + "\n").encode()


def cases_digest(cases):
    return hashlib.sha256(canonical_cases(cases)).hexdigest()
