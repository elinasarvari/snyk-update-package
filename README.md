# snyk-update-package

**One place to fix Snyk findings across many Java repos.** You list the repos (your local folders, or git URLs), it finds
every vulnerable package, documents what an upgrade will break, applies it on a branch, builds and
tests everything, and opens the pull requests. You decide at each step.

Works with **GitHub Copilot** (VS Code, agent mode) and **Claude Code**: same commands, same results.

```
 repos/repos.txt ─▶ /dep-clone ─▶ /dep-scan ─▶ /dep-inventory ─▶ /dep-analyze ─▶ you approve ─▶ /dep-apply ─▶ /dep-verify ─▶ /dep-publish
 your list of       check local / every        current vs       what breaks,    the plan       edit on a     build, test,   commit, push,
 repos              clone URLs    flagged      target, what     where, and                     branch        boot, re-scan  open PRs
                                  package      moves with it    a plan
```

This project holds **no application code** and is **not** a container of submodules. The repos you fix
stay separate git repos. Each line of the list points at one of them:

- **a local folder you already have**, e.g. `~/repos/learning-java`: the upgrade happens **in that folder**,
  on a new branch `deps/<workflow-id>`;
- **a git URL**: cloned into `repos/<name>/` here (git-ignored), and the upgrade happens in that clone.

Either way the changes stay in that repo and reach its GitHub as a pull request. This project keeps only
the list, the workflow and the documentation:

```text
snyk-update-package/
├── repos/
│   ├── repos.txt        ← the list: local folders and/or git URLs (you edit this)
│   ├── README.md        ← how to add repos, local vs URL, what happens to each
│   └── <name>/          ← only for repos listed by URL: plain clones (git-ignored)
├── workflows/            ← documentation of every upgrade
└── toolkit/            ← how each step works (scripts, procedures, templates)
```

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

**2. List the repos you want to fix** in [`repos/repos.txt`](repos/repos.txt), one line each:

```text
# <name>        <local folder or git URL>                     [options]
learning-java   ~/repos/learning-java                         branch=main  path=backend  smoke=true
orders-service  https://github.com/my-org/orders-service.git  branch=develop
```

- `name`: a short name you use in commands
- a **local folder** (starts with `/`, `~`, `./` or `../`) is used in place. Use this for repos you already have checked out
- a **git URL** is cloned into `repos/<name>/`. Use this for repos you don't have locally
- `path`: the sub-folder that has the `pom.xml`, if it isn't at the repo root
- `smoke=true`: also start the app during verification

**3. Check them** (and clone the URL ones):

```bash
python3 -I toolkit/scripts/repos.py clone      # local: checks only. URL: clones or updates
python3 -I toolkit/scripts/repos.py status     # type, folder, branch, commit, local changes
```

Or run `/dep-clone` in chat (step 5). Local vs URL, every option, private repos, and what each message
means are in **[repos/README.md](repos/README.md)**.

**4. Open this folder** in VS Code (Copilot Chat → **Agent** mode) or run `claude` in it.

**5. Run it: the easy way.** Give `/dep-run` one repo (its name, a local folder, or a git URL):

```text
/dep-run learning-java                      a repo already in repos/repos.txt
/dep-run ~/repos/orders-service             a local folder (added to the list for you)
/dep-run https://github.com/acme/billing.git     a git URL (added and cloned for you)
/dep-run learning-java ~/Downloads/snyk.json    use a Snyk export instead of running the CLI
```

It opens **Workflow N (`wf-NNN`)** for that repo, or resumes the unfinished one, and runs **every step by
itself**: clone → Snyk scan → inventory → impact + plan. It **stops only where it needs you**:

| It stops when | You reply / run |
|---------------|-----------------|
| the plan is ready (always) | read `workflows/wf-NNN-…/03-plan.md`, then `/dep-run learning-java approve`, or the *Approve* button in Copilot. It then applies and verifies |
| verification finished (always) | green: `/dep-publish wf-NNN` to push and open the PR (always your own command). Red: it lists the fixes |
| something blocks it | what it asks for, e.g. install Snyk, pick the starting version, commit your local changes |

Every stop ends with **Done this run / Stopped because / ▶ Next step**, so you always know what to do.

**Or run the steps one by one**, each ending with its own **▶ Next step** (in Copilot, also a button under the reply):

```text
/dep-clone                       check local folders, clone/refresh URL repos from repos/repos.txt
/dep-scan                        Snyk scan → every flagged package (or: /dep-scan path/to/snyk.json)
/dep-inventory <id>              exact versions, what sets them, what moves with them, baseline build
/dep-analyze <id>                breaking changes in YOUR code with file:line, and a step-by-step plan
  → read workflows/<id>/03-plan.md and reply "approve"
/dep-apply <id>                  apply the plan on branch deps/<id> in each repo folder (not committed)
/dep-verify <id>                 build + tests + app boot for every repo, compared to before
/dep-publish <id>                commit, push, open one PR per repo
```

`<id>` is the **workflow id**. Every run gets the next number: the first is **Workflow 1, `wf-001`**, the
next **Workflow 2, `wf-002`**, and so on (never reused). `/dep-scan` (or `/dep-upgrade`) creates it and tells
you the number. You can then write `1`, `wf-001`, or the folder name, e.g. `/dep-inventory 1`. To see every run
and where it stands, open [`workflows/INDEX.md`](workflows/INDEX.md) or run **`/dep-upgrade status`**.

**6. Read the results** in `workflows/<id>/`. Start with `STATUS.md`.

---

## The commands

| Command | What it does | Creates (in `workflows/<id>/`) | Changes your repos? |
|---------|--------------|-------------------------------|---------------------|
| `/dep-clone [folder \| git-url \| name]` | Adds repos to `repos/repos.txt`. Local folders: checks them (branch, local changes, behind origin) without changing anything. URLs: clones missing ones, fast-forwards clean ones | `STATUS.md` repos table | URL clones only |
| `/dep-scan [snyk.json]` | Runs Snyk on every repo in the list (or reads your export). Lists **every** flagged package: current version, severity, CVEs, fixed-in version, which dependency brings it in, how to fix it. Groups them into the few changes you actually make | `01-snyk-findings.md`, `snyk/findings.csv` | no |
| `/dep-inventory <id>` | For the packages in scope: the version each repo really uses, what sets it (parent/BOM/property), everything else that changes with it, coupled libraries (e.g. Camel). Builds each repo as a **baseline** | `02-inventory.md`, `facts/`, `verification/baseline/` | no |
| `/dep-analyze <id>` | Subagents read the official migration guides and search your code, config and tests. Each finding cites `file:line` and a source. Writes an ordered plan with exact diffs | `03-impact.md`, `analysis/`, `03-plan.md` | no |
| *you approve* | Reply "approve" (or click the button). Your words and the date are recorded | `STATUS.md` | — |
| `/dep-apply <id>` | Applies the plan on branch `deps/<id>` in each repo folder (for a local folder, your own checkout switches to that branch; you're told first) and compiles after every step. Refuses folders with uncommitted changes. Never commits | `04-apply-log.md` | **edits files** on a branch |
| `/dep-verify <id>` | Full build, all tests and app boot for every repo, plus a Snyk re-scan. Each failure is marked regression, already-failing or environment | `05-verification.md`, `verification/after/` | no |
| `/dep-publish <id>` | Commits, pushes `deps/<id>`, opens a PR per repo with a description built from the docs | `06-publish.md` | **commits, pushes, opens PRs** |
| `/dep-run <repo> [id] [reply]` | **Autopilot:** every step for one repo, stopping only for your approval, blockers, and before publish | everything up to `05-verification.md` | only after you approve the plan |
| `/dep-upgrade [status \| id]` | Shows where every workflow stands, or runs one next step | `STATUS.md` | — |
| `/dep-verify baseline` | Health check of all repos, outside any upgrade | `workflows/_health/` (git-ignored) | no |

## What you get per workflow run

Each run has its own folder, named after its id. Two runs never share files:

```text
workflows/
├── INDEX.md                ← every run: id, title, current step, ▶ next step (auto-generated)
├── wf-001-spring-boot-4-1/ ← Workflow 1
└── wf-002-jackson-fix/     ← Workflow 2 (example)
```

Inside one run's folder:

```text
workflows/wf-001-spring-boot-4-1/
├── STATUS.md               ← start here: step tracker, ▶ next step, repos, decisions, timestamped History
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
| `repos/repos.txt` | The list of repos to fix: local folders and/or git URLs | **yes**, this is your list |
| `repos/README.md` | How to add repos (local vs URL), check, clone, refresh and remove them | — |
| `repos/<name>/` | Clones of repos listed by URL (git-ignored, never committed here) | no, managed by `/dep-clone` |
| `workflows/wf-NNN-<slug>/` | One folder per workflow run (Workflow 1 = `wf-001`, …) | generated, review it |
| `workflows/INDEX.md` | All runs with their current step and next step | no, rebuilt automatically |
| `workflows/README.md` | How workflow ids and folders work | — |
| `toolkit/WORKFLOW.md` | Overview the assistants read first: phases, gates, rules | to change behaviour |
| `toolkit/RUN.md` | What `/dep-run` does: step order, when it continues, when it stops, its final reply | to change behaviour |
| `toolkit/phases/0-clone.md … 6-publish.md` | Step-by-step procedure for each command | to change behaviour |
| `toolkit/roles/*.md` | The three subagents: `dependency-analyst`, `upgrade-applier`, `repo-verifier` | to change behaviour |
| `toolkit/templates/*.md` | Blank templates for each document above | to change doc layout |
| `toolkit/scripts/repos.py` | Add / check+clone / list / status of target repos | — |
| `toolkit/scripts/workflows.py` | Workflow ids: new run, resolve `1`→folder, step states, history, index | — |
| `toolkit/scripts/snyk-scan.sh` | Snyk scan of every repo in the list | — |
| `toolkit/scripts/parse-snyk.py` | Snyk JSON → findings tables + CSV | — |
| `toolkit/scripts/maven-facts.sh` | What a repo's pom really resolves | — |
| `toolkit/scripts/verify-repo.sh` | Build → tests → boot → `summary.json` | — |
| `.github/prompts/`, `.github/agents/` | Copilot slash commands and agents (**generated**) | no, edit `toolkit/` and regenerate |
| `.github/skills/dep-upgrade/SKILL.md`, `.github/copilot-instructions.md`, `.github/instructions/` | Copilot context and pom-editing rules | rarely |
| `.claude/skills/`, `.claude/agents/`, `CLAUDE.md` | Claude Code commands and subagents (**generated**, except `CLAUDE.md`) | no, regenerate |
| `tools/generate-entrypoints.py` | Regenerates the Copilot and Claude files from one spec | when adding a command |
| `tests/` | Automated tests for every script and command (`tests/run.sh`) | when changing behaviour |
| `.github/workflows/tests.yml` | Runs the tests on GitHub after every push (Linux + macOS) | rarely |

To change how a step works, edit its file in `toolkit/phases/`. Both assistants pick it up immediately.
To add or rename a command, or change a handoff button, edit `tools/generate-entrypoints.py`, then run
`python3 -I tools/generate-entrypoints.py`.

## The scripts work without an assistant too

```bash
python3 -I toolkit/scripts/repos.py clone                          # check local folders, clone/refresh URLs
python3 -I toolkit/scripts/repos.py status                         # branch, dirty, ahead/behind
bash toolkit/scripts/snyk-scan.sh /tmp/snyk                        # scan every repo
python3 -I toolkit/scripts/parse-snyk.py /tmp/snyk/*.json --md findings.md --csv findings.csv
bash toolkit/scripts/verify-repo.sh ~/repos/learning-java/backend /tmp/verify --smoke
```

## Testing: are the commands doing the right job?

```bash
tests/run.sh                       # about 40 seconds, safe to run any time
RUN_MAVEN_TESTS=1 tests/run.sh     # also does a real Maven build of a tiny sample project
```

The tests run in **throwaway sandboxes** with fake git remotes, a fake `HOME` and a fake `snyk` CLI. They never touch
your real repos or GitHub, and never apply an upgrade. They also run on GitHub after every push
([Actions tab](https://github.com/elinasarvari/snyk-update-package/actions)).

| Test file | Proves |
|-----------|--------|
| `test_repos.py` | URLs are cloned into `repos/` and refreshed only when clean. **Local folders are never pulled, switched or copied.** Local changes and `deps/*` branches are left alone. No submodules; clones are never committed |
| `test_workflows.py` | Workflow 1 = `wf-001`, Workflow 2 = `wf-002`, **ids never reused**. `1` / `wf-001` / folder name all resolve. Step states, next step, History and INDEX update correctly |
| `test_snyk.py` | Every flagged package listed once with all its paths, severity totals, grouping by the dependency you edit, licence/no-fix rows, CSV. The scan script handles a missing or unauthenticated CLI and scans each repo folder |
| `test_build_scripts.py` | Build results come from JUnit files, failing tests are named, the build tool is auto-detected, the smoke boot catches "APPLICATION FAILED TO START", and the Maven facts are right |
| `test_wiring.py` | Every `/dep-*` command (including `/dep-run`) exists for Copilot **and** Claude and points at files that exist. Handoffs and subagents resolve. Generated files are current. **`/dep-apply` and `/dep-publish` can only be started by you**, and the approval gate is in place |

What tests can't check is the AI's judgement inside a step, e.g. how good an impact analysis is. That's why
every document must cite `file:line` or a source URL, and why nothing changes your code without your approval.

## Guard rails

- **Read-only until you approve.** Clone, scan, inventory, analyze and verify never edit your code.
- **Approval is yours.** The plan's approval box is ticked only after you approve in chat.
- **Branches, not main.** Changes go to `deps/<id>` in the repo folder. Nothing is committed until `/dep-publish`.
  Nothing is pushed to a default branch or force-pushed.
- **Your work is safe.** A repo folder with uncommitted changes or on an unexpected branch is reported and left alone. Local folders are never pulled or switched, except by `/dep-apply` creating `deps/<id>`, and you're told before it does.
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
| `/dep-clone` says "kept as is" or "expected main" | That repo has local changes or is on another branch. That's intentional: switch or commit yourself if needed |
| `/dep-apply` stops at "dirty repo" | Commit or discard your own changes in that repo folder first (`repos.py status` shows which) |
| Build red only when repos build in parallel | Shared `~/.m2` download clash. Re-run that repo: `/dep-verify <id> <repo>` |
| `/dep-publish` stops | `gh auth status` must pass. For Bitbucket/GitLab it pushes and gives you the PR link instead |
