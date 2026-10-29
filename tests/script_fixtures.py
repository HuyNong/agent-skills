"""Isolated command fixtures for unit tests; these never contact GitHub."""

import json
from os import environ, pathsep
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PUBLISH = "github-pr-review-publish"
VERIFY = "github-pr-review-verify-fixes"
RESPOND = "github-pr-review-respond"

GH_FIXTURE = r'''#!/usr/bin/env python3
import json, pathlib, subprocess, sys
from os import environ
args = sys.argv[1:]
if args[:2] == ["auth", "status"]:
    sys.exit(0)
if not args or args[0] != "api":
    sys.exit("unexpected gh command in unit fixture")
endpoint = next(a for a in args if a.startswith(("/", "repos/")))
method = next((args[args.index(flag) + 1] for flag in ["--method", "-X"] if flag in args), "GET")
key = method + " /" + endpoint.lstrip("/")
log = pathlib.Path(environ["TEST_GH_LOG"])
previous = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
number = sum(item["key"] == key for item in previous) + 1
call = {"key": key}
if "--input" in args:
    call["payload"] = json.loads(pathlib.Path(args[args.index("--input") + 1]).read_text())
with log.open("a") as stream:
    stream.write(json.dumps(call) + "\n")
responses = json.loads(pathlib.Path(environ["TEST_GH_RESPONSES"]).read_text())
response = responses.get(key + "#" + str(number), responses.get(key))
if response is None:
    sys.exit("unexpected API call: " + key)
status = response.get("_status", 0) if isinstance(response, dict) else 0
output = response.get("_stdout", json.dumps(response)) if isinstance(response, dict) else json.dumps(response)
if "--jq" in args and not status:
    result = subprocess.run(["jq", "-r", args[args.index("--jq") + 1]], input=output, text=True, capture_output=True)
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    sys.exit(result.returncode)
sys.stdout.write(output)
if status:
    sys.stderr.write("fixture HTTP failure\n")
sys.exit(status)
'''


class ScriptCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="pr-skill-unit-")
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.bin = self.work / "bin"
        self.bin.mkdir()
        gh = self.bin / "gh"
        gh.write_text(GH_FIXTURE)
        gh.chmod(0o755)
        self.log = self.work / "gh-calls.jsonl"
        self.responses = self.work / "responses.json"
        self.responses.write_text("{}")
        self.process_environment = dict(environ, PATH=str(self.bin) + pathsep + environ["PATH"],
                                        TEST_GH_LOG=str(self.log), TEST_GH_RESPONSES=str(self.responses))

    def respond(self, responses):
        self.responses.write_text(json.dumps(responses))

    def run_script(self, skill, name, *args):
        return subprocess.run(["/bin/bash", str(ROOT / "skills" / skill / "scripts" / name),
                               *map(str, args)], cwd=self.work, env=self.process_environment,
                              text=True, capture_output=True, timeout=20)

    def write_json(self, directory, name, value):
        directory.mkdir(exist_ok=True)
        path = directory / name
        path.write_text(json.dumps(value, ensure_ascii=False))
        return path
