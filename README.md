# snyk-update-package

**One place to fix Snyk findings across many Java repos.** You list the repos, it clones them, finds
every vulnerable package, documents what an upgrade will break, applies it on a branch, builds and
tests everything, and opens the pull requests. You decide at each step.

Works with **GitHub Copilot** (VS Code, agent mode) and **Claude Code**: same commands, same results.

```
 repos.txt ──▶ /dep-clone ──▶ /dep-scan ──▶ /dep-inventory ──▶ /dep-analyze ──▶ you approve ──▶ /dep-apply ──▶ /dep-verify ──▶ /dep-publish
 (your list)   clone into     every         current vs         what breaks,     the plan        edit on a      build, test,    commit, push,
               workspace/     flagged       target, what       where, and                       branch         boot, re-scan   open PRs
                              package       moves with it      a plan
```

This repo holds **no application code**. Your repos are cloned into `workspace/` (never committed here).
What this repo keeps is the **workflow** and the **documentation of every upgrade** in `upgrades/`.

---

## Quick start

**1. Get the project and the tools** (once)

```bash
git clone https://github.com/elinasarvari/snyk-update-package.git
cd snyk-update-package
brew tap snyk/tap && brew install snyk-cli && snyk auth     # Snyk CLI (or: npm install -g snyk)
brew install gh && gh auth login                            # only needed to open PRs at the end
```

You also need Java (the version your repos use), Git, and Python 3.9+ (built into macOS).

**2. List the repos you want to fix** in [`repos.txt`](repos.txt):

```text
# <name>        <git-url>                                          [options]
learning-java   https://github.com/elinasarvari/learning-java.git  path=backend  smoke=true
orders-service  git@github.com:my-org/orders-service.git           branch=develop
```

`path` = the folder that has the `pom.xml` (if not the repo root). `smoke=true` also starts the app
during verification. Or let the assistant add it: `/dep-clone <git-url>`.

**3. Open this folder** in VS Code (Copilot Chat → **Agent** mode) or run `claude` in it.

**4. Run the steps.** Each one ends by telling you the **▶ Next step**. In Copilot, the next step is also
a button under the reply.

```text
/dep-clone                       clone / refresh everything in repos.txt
/dep-scan                        Snyk scan → every flagged package (or: /dep-scan path/to/snyk.json)
/dep-inventory <id>              exact versions, what sets them, what moves with them, baseline build
/dep-analyze <id>                breaking changes in YOUR code with file:line, and a step-by-step plan
  → read upgrades/<id>/03-plan.md and reply "approve"
/dep-apply <id>                  apply the plan on branch deps/<id> in each clone (not committed)
/dep-verify <id>                 build + tests + app boot for every repo, compared to before
/dep-publish <id>                commit, push, open one PR per repo
```

`<id>` is the upgrade folder name, e.g. `2026-10-15-spring-boot-4-1`. `/dep-scan` creates it. Lost? Run
**`/dep-upgrade status`**.

**5. Read the results** in `upgrades/<id>/`. Start with `STATUS.md`.

---

## The commands

| Command | What it does | Creates (in `upgrades/<id>/`) | Changes your repos? |
|---------|--------------|-------------------------------|---------------------|
| `/dep-clone [git-url \| name]` | Adds repos to `repos.txt`, clones missing ones, fast-forwards clean ones. Leaves a clone alone if it has local changes or is on another branch | `STATUS.md` repos table | clones / pulls only |
| `/dep-scan [snyk.json]` | Runs Snyk on every clone (or reads your export). Lists **every** flagged package: current version, severity, CVEs, fixed-in version, which dependency brings it in, how to fix it. Groups them into the few changes you actually make | `01-snyk-findings.md`, `snyk/findings.csv` | no |
| `/dep-inventory <id>` | For the packages in scope: the version each repo really uses, what sets it (parent/BOM/property), everything else that changes with it, coupled libraries (e.g. Camel). Builds each repo as a **baseline** | `02-inventory.md`, `facts/`, `verification/baseline/` | no |
| `/dep-analyze <id>` | Subagents read the official migration guides and search your code, config and tests. Each finding cites `file:line` and a source. Writes an ordered plan with exact diffs | `03-impact.md`, `analysis/`, `03-plan.md` | no |
| *you approve* | Reply "approve" (or click the button). Your words and the date are recorded | `STATUS.md` | — |
| `/dep-apply <id>` | Applies the plan on branch `deps/<id>` in each clone and compiles after every step. Refuses clones with uncommitted changes. Never commits | `04-apply-log.md` | **edits files** on a branch |
| `/dep-verify <id>` | Full build, all tests and app boot for every repo, plus a Snyk re-scan. Each failure is marked regression, already-failing or environment | `05-verification.md`, `verification/after/` | no |
| `/dep-publish <id>` | Commits, pushes `deps/<id>`, opens a PR per repo with a description built from the docs | `06-publish.md` | **commits, pushes, opens PRs** |
| `/dep-upgrade [status \| id]` | Shows where every upgrade stands and runs the next step | `STATUS.md` | — |
| `/dep-verify baseline` | Health check of all repos, outside any upgrade | `upgrades/_health/` (git-ignored) | no |

## What you get per upgrade

```text
upgrades/2026-10-15-spring-boot-4-1/
├── STATUS.md               ← start here: phase tracker, ▶ next step, repos, decisions & approvals
├── 01-snyk-findings.md     every flagged package + the changes they boil down to
├── 02-inventory.md         current vs target, what moves with it, coupled libraries, baseline
├── 03-impact.md            what breaks, where (file:line), with sources
├── 03-plan.md              ordered steps with exact diffs + the approval box
├── 04-apply-log.md         what changed per step, deviations from the plan
├── 05-verification.md      build/test/boot results per repo, before vs after, verdict
├── 06-publish.md           commits and PR links
├── snyk/                   raw Snyk JSON per repo, findings.{md,csv,json}
├── facts/<repo>/           resolved dependency tree, declared deps, version properties
├── analysis/<repo>--<artifact>.md   full report from each analyst subagent
└── verification/{baseline,after}/<repo>/summary.json, diagnosis.md
```

## Files in this project

| Path | What it is | Edit it? |
|------|------------|----------|
| `repos.txt` | The repos to clone and fix | **yes**, this is your list |
| `workspace/` | Clones of your repos (git-ignored) | no, managed by `/dep-clone` |
| `upgrades/` | Documentation of each upgrade | generated, review it |
| `workflow/WORKFLOW.md` | Overview the assistants read first: phases, gates, rules | to change behaviour |
| `workflow/phases/0-clone.md … 6-publish.md` | Step-by-step procedure for each command | to change behaviour |
| `workflow/roles/*.md` | The three subagents: `dependency-analyst`, `upgrade-applier`, `repo-verifier` | to change behaviour |
| `workflow/templates/*.md` | Blank templates for each document above | to change doc layout |
| `workflow/scripts/repos.py` | Add / clone / list / status of target repos | — |
| `workflow/scripts/snyk-scan.sh` | Snyk scan of every clone | — |
| `workflow/scripts/parse-snyk.py` | Snyk JSON → findings tables + CSV | — |
| `workflow/scripts/maven-facts.sh` | What a repo's pom really resolves | — |
| `workflow/scripts/verify-repo.sh` | Build → tests → boot → `summary.json` | — |
| `.github/prompts/`, `.github/agents/` | Copilot slash commands and agents (**generated**) | no, edit `workflow/` and regenerate |
| `.github/skills/dep-upgrade/SKILL.md`, `.github/copilot-instructions.md`, `.github/instructions/` | Copilot context and pom-editing rules | rarely |
| `.claude/skills/`, `.claude/agents/`, `CLAUDE.md` | Claude Code commands and subagents (**generated**, except `CLAUDE.md`) | no, regenerate |
| `tools/generate-entrypoints.py` | Regenerates the Copilot and Claude files from one spec | when adding a command |

To change how a step works, edit its file in `workflow/phases/`. Both assistants pick it up immediately.
To add or rename a command, or change a handoff button, edit `tools/generate-entrypoints.py`, then run
`python3 -I tools/generate-entrypoints.py`.

## The scripts work without an assistant too

```bash
python3 -I workflow/scripts/repos.py clone                          # clone/refresh all
python3 -I workflow/scripts/repos.py status                         # branch, dirty, ahead/behind
bash workflow/scripts/snyk-scan.sh /tmp/snyk                        # scan all clones
python3 -I workflow/scripts/parse-snyk.py /tmp/snyk/*.json --md findings.md --csv findings.csv
bash workflow/scripts/verify-repo.sh workspace/learning-java/backend /tmp/verify --smoke
```

## Guard rails

- **Read-only until you approve.** Clone, scan, inventory, analyze and verify never edit your code.
- **Approval is yours.** The plan's approval box is ticked only after you approve in chat.
- **Branches, not main.** Changes go to `deps/<id>` in the clone. Nothing is committed until `/dep-publish`.
  Nothing is pushed to a default branch or force-pushed.
- **Your work is safe.** A clone with uncommitted changes or on an unexpected branch is reported and left alone.
- **Red stays red.** Tests are never skipped or disabled to get a green build.
- **Manual-only steps.** `/dep-apply` and `/dep-publish` only run when you invoke them (Claude: can't be
  auto-triggered; Copilot: handoff buttons you have to send).

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `/dep-*` commands don't appear | Open **this folder** as the workspace root. In Copilot, use **Agent** mode |
| Clone fails for a private repo | Your git credentials/SSH key must have access: test with `git clone <url>` |
| `snyk-scan.sh` exits 127 / 126 | Snyk CLI missing / not logged in (see Quick start), or pass a JSON export to `/dep-scan` |
| Snyk reports a different version than the inventory | Expected when the scan ran on another branch. See *Discrepancies* in `02-inventory.md` |
| `/dep-clone` says "kept as is" | That clone has local changes or is on `deps/<id>` (upgrade in progress). That's intentional |
| `/dep-apply` stops at "dirty repo" | Commit or discard your own changes in `workspace/<repo>` first |
| Build red only when repos build in parallel | Shared `~/.m2` download clash. Re-run that repo: `/dep-verify <id> <repo>` |
| `/dep-publish` stops | `gh auth status` must pass. For Bitbucket/GitLab it pushes and gives you the PR link instead |
