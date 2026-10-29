# GitHub PR skills

Four portable [Agent Skills](https://agentskills.io) for GitHub pull-request workflows. Each skill includes its own instructions, resources and MIT license and can be installed independently.

| Skill | Use it to |
|---|---|
| `github-pr-create` | Create a PR from committed branch changes, with a structured description and an authorized push when needed. |
| `github-pr-review-publish` | Publish existing review findings as one summary and anchored inline comments. |
| `github-pr-review-respond` | Verify incoming reviewer feedback, draft a reply, and apply/commit a fix when authorized. |
| `github-pr-review-verify-fixes` | Check new commits against prior findings and publish an authorized follow-up with per-finding verdicts. |

Use your normal code-review workflow to produce new findings. Publishing findings, responding to a reviewer and checking later fixes are separate intents.

## Install

Use the [skills CLI](https://github.com/vercel-labs/skills) from the project where you want the skills:

```bash
# Discover this collection
npx skills add HuyNong/agent-skills --list

# Install one skill for both agents
npx skills add HuyNong/agent-skills \
  --skill github-pr-create -a codex claude-code

# Install the collection
npx skills add HuyNong/agent-skills \
  --skill '*' -a codex claude-code
```

Add `-g` to install across projects. The CLI manages the shared `.agents/skills/` location and agent-specific links. Use `--copy` when independent copies are preferred. Repository source stays in `skills/`; no custom installer or npm package is required.

```bash
npx skills list
npx skills update github-pr-create -p
npx skills remove github-pr-create
```

Omitting agent filters when removing a named skill cleans its shared installation and all agent links. Filtering removal to selected agents can leave the shared `.agents/skills/` copy available to other universal agents.

## Requirements

- Node.js/npm for the installer; validation uses Node.js 24 and skills CLI 1.7.4.
- `git` and authenticated [GitHub CLI](https://cli.github.com/); run `gh auth login` yourself if needed.
- Bash 3.2+ on macOS or Linux. Publishing reviews and verifying fixes also require `jq` and standard Unix tools.
- Network access for GitHub operations. GitButler's `but` is optional for create/respond workflows.

Skills use the active `gh` identity. Check that it is the intended account before posting. Do not place credentials or machine-specific configuration inside skill directories. Windows execution is not covered by this collection's Bash verification matrix.

## Examples

- **Create:** “Open a PR for this branch against develop. Push the committed branch if needed.”
- **Publish:** “Post these verified findings on PR #12 as a COMMENT review.”
- **Respond:** “Is this reviewer right? Check the claim and draft a reply. Do not change code yet.”
- **Authorized fix:** “Apply the agreed fix, run the relevant tests, commit it and reply with the real commit link.”
- **Verify fixes:** “The author pushed new commits to PR #12. Check whether the findings from my prior review are fixed.”

Authorization applies to the requested actions. An evaluation request alone does not authorize edits or GitHub posts. Skills reuse authorization already given in the session; merge, thread resolution and unsolicited approval are outside their workflows. Fix verification always submits COMMENT, never APPROVE or REQUEST_CHANGES.

## Resource handling

Agents resolve bundled helpers relative to the loaded skill's directory and keep their working directory in the consuming repository. Skills do not depend on Claude-specific global paths or another installed skill. Temporary review artifacts belong to the current invocation; failed operations retain artifacts and report partial results instead of retrying blindly.

## Development and validation

Source layout:

```text
skills/<skill-name>/
  SKILL.md
  LICENSE
  scripts/       # when the workflow needs helpers
  references/    # rubrics, examples and API notes
```

Run the focused script regression suite and actual installer matrix:

```bash
python3 tests/test-pr-skill-scripts.py
bash tests/test-skill-installation.sh
```

The Python suite uses isolated GitHub response fixtures for parser/error contracts and does not contact GitHub. The installer suite invokes the real CLI in disposable Git projects, tests each skill and the collection in default/copy modes, checks licenses/resources and removes the disposable installs. It leaves existing global skills untouched.

CI in [validate-skills.yml](.github/workflows/validate-skills.yml) runs on macOS and Linux, validates metadata with the official `skills-ref` reference tool, checks shell syntax, runs regressions and exercises installation. Development validation tools are not runtime dependencies of installed skills.

Actual-agent and live-PR checks are separate from fixture/installation tests. Use a dedicated sandbox repository; record the tested commit, CI run and actual GitHub receipts before tagging a release. Plans, journals and local verification artifacts are kept outside the distributed package and ignored by Git.

## Name migration

| Previous directory | Current skill |
|---|---|
| `huynong-create-pr` | `github-pr-create` |
| `huynong-post-pr-review-comment` | `github-pr-review-publish` |
| `huynong-pr-review-evaluator` | `github-pr-review-respond` |
| `huynong-pr-review-followup` | `github-pr-review-verify-fixes` |

Existing global copies are not renamed automatically. Install the desired new skill and remove an obsolete personal copy separately when ready.

## License

[MIT](LICENSE). The complete license is also included in each installed skill directory.
