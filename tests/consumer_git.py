"""Git fixture primitives with deterministic commit metadata."""
import os
import subprocess
from pathlib import Path

def run_git(repo: Path, *args: str) -> str:
    environment = dict(os.environ)
    for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR", "GIT_OBJECT_DIRECTORY",
                "GIT_ALTERNATE_OBJECT_DIRECTORIES"):
        environment.pop(key, None)
    for key in list(environment):
        if key.startswith("GIT_CONFIG"):
            environment.pop(key)
    environment.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    environment.update(GIT_AUTHOR_NAME="Consumer Fixture", GIT_AUTHOR_EMAIL="fixture@example.invalid",
                       GIT_COMMITTER_NAME="Consumer Fixture", GIT_COMMITTER_EMAIL="fixture@example.invalid",
                       GIT_AUTHOR_DATE="2026-01-01T00:00:00Z", GIT_COMMITTER_DATE="2026-01-01T00:00:00Z")
    return subprocess.check_output(
        ["/usr/bin/git", *args], cwd=repo, text=True, stderr=subprocess.STDOUT,
        env=environment
    ).strip()
