#!/usr/bin/env bash
# Real CLI installation tests; every mutation stays inside an owned temp project.
set -euo pipefail

source_root="$(cd "$(dirname "$0")/.." && pwd)"
work="$(mktemp -d "${TMPDIR:-/tmp}/pr-skill-install.XXXXXX")"
trap 'rm -rf -- "$work"' EXIT
export DISABLE_TELEMETRY=1
names=(github-pr-create github-pr-review-publish github-pr-review-respond github-pr-review-verify-fixes)

npx --yes skills@1.7.4 --version
for mode in default copy; do
  for selection in "${names[@]}" all; do
    case_root="$work/$mode-$selection"
    snapshot="$case_root/source"
    project="$case_root/project"
    mkdir -p "$snapshot" "$project"
    cp -R "$source_root/skills" "$snapshot/skills"
    git -C "$project" init -q
    skill="$selection"
    [[ "$selection" == all ]] && skill='*'
    options=()
    [[ "$mode" == copy ]] && options=(--copy)
    # Bash 3.2 with nounset needs the guarded expansion for an empty array.
    (cd "$project" && npx --yes skills@1.7.4 add "$snapshot" \
      --skill "$skill" -a codex claude-code -y ${options[@]+"${options[@]}"}) \
      > "$case_root/install.log" 2>&1 || { cat "$case_root/install.log"; exit 1; }
    if [[ "$mode" == copy ]]; then
      mv "$snapshot" "$case_root/source-detached"
    fi
    python3 - "$project" "$selection" "$mode" "$source_root" <<'PY'
import pathlib, subprocess, sys
project, selection, mode, original = sys.argv[1:]
original = pathlib.Path(original)
names = sorted(p.name for p in (original / "skills").iterdir() if p.is_dir())
expected = names if selection == "all" else [selection]
for base in [".agents/skills", ".claude/skills"]:
    installed = pathlib.Path(project, base)
    assert sorted(p.name for p in installed.iterdir()) == expected, installed
    for name in expected:
        folder = installed / name
        assert (folder / "LICENSE").read_bytes() == (original / "LICENSE").read_bytes()
        for source in (original / "skills" / name).rglob("*"):
            if source.is_file() and source.name != ".DS_Store":
                target = folder / source.relative_to(original / "skills" / name)
                assert target.is_file(), target
                assert target.read_bytes() == source.read_bytes(), target
                if mode == "copy":
                    assert target.resolve().is_relative_to(folder.resolve()), target
        for helper in (folder / "scripts").glob("*.sh"):
            assert helper.stat().st_mode & 0o111, helper
            subprocess.run(["/bin/bash", "-n", str(helper)], check=True)
        if name == "github-pr-review-respond":
            result = subprocess.run(["/bin/bash", str(folder / "scripts/parse-review-url.sh"),
                                     "https://github.com/acme/demo/pull/7#discussion_r42"],
                                    cwd=project, text=True, capture_output=True, check=True)
            assert "comment_id=42\n" in result.stdout, result.stdout
PY
    (cd "$project" && npx --yes skills@1.7.4 remove --skill '*' -y) \
      > "$case_root/remove.log" 2>&1 || { cat "$case_root/remove.log"; exit 1; }
    for name in "${names[@]}"; do
      [[ ! -e "$project/.agents/skills/$name" && ! -e "$project/.claude/skills/$name" ]]
    done
    echo "PASS: $mode / $selection / both agents / remove"
  done
done
