# snyk-update-package

**One place to fix Snyk findings across many Java repos.** You list the repos, it clones them, finds
every vulnerable package, documents what an upgrade will break, applies it on a branch, builds and
tests everything, and opens the pull requests. You decide at each step.

Works with **GitHub Copilot** (VS Code, agent mode) and **Claude Code**: same commands, same results.

```
 repos/repos.txt ─▶ /dep-clone ─▶ /dep-scan ─▶ /dep-inventory ─▶ /dep-analyze ─▶ you approve ─▶ /dep-apply ─▶ /dep-verify ─▶ /dep-publish
 your list of       check local / every        current vs       what breaks,    the plan       edit on a     build, test,   commit, push,
 repos              clone URLs    flagged      target, what     where, and                     branch        boot, re-scan  open PRs
                                  package      moves with it    a plan
```

This project holds **no application code** and is **not** a container of submodules. It keeps **the list,
the workflow, and the tracking**. The repos you fix are **cloned into `repos/<name>/`**, and **that is where the
code changes happen**, on one branch per workflow (`deps/wf-NNN`, from the latest main). The changes reach each
repo's GitHub as a pull request. Your own checkouts elsewhere (e.g. `~/repos/...`) are never touched.

```text
snyk-update-package/
├── workflows/                    ← TRACKING: one folder per workflow run
│   ├── INDEX.md                  ← every run, current step, next step (auto-generated)
│   └── wf-002-learning-java/     ← Workflow 2: STATUS.md, documents, history
├── repos/
│   ├── repos.txt                 ← the list of repos to fix (git URLs, you edit this)
│   ├── README.md                 ← how to add and clone repos
│   └── learning-java/            ← the CLONE: code changes happen here, on deps/wf-NNN (git-ignored)
└── toolkit/                      ← how each step works (scripts, procedures, templates)
```

---

## Quick start

**1. Get the project and the tools** (once)

You need **Git**, **Java** (the version your repos use) and **Python 3.9+**.

| | macOS (Terminal) | Windows (PowerShell) |
|---|---|---|
| Tools | Python is built in. `brew install git openjdk@21` if missing | Install [Git for Windows](https://git-scm.com/download/win), [Python](https://www.python.org/downloads/windows/) (tick **"Add python.exe to PATH"**; `py -3 --version` should work) and a JDK (e.g. `winget install EclipseAdoptium.Temurin.21.JDK`). PowerShell 5.1 is built in |
| Get the project | `git clone https://github.com/elinasarvari/snyk-update-package.git`<br>`cd snyk-update-package` | the same two commands |
| GitHub CLI (only to open PRs at the end) | `brew install gh && gh auth login` | `winget install GitHub.cli` then `gh auth login` |

On Windows, scripts run with `powershell -ExecutionPolicy Bypass -File <script>.ps1 ...`, which works without
changing any system setting. Each bash script `x.sh` has a PowerShell twin `x.ps1` with the same arguments.

**The Snyk CLI**, which the scan step uses. Pick one:

| You have | macOS | Windows (PowerShell) |
|----------|-------|----------------------|
| **The Snyk VS Code extension** (it already downloaded the CLI; the path is in its settings: Snyk → Advanced → CLI path) | `export SNYK_CLI="<that path>"` (add it to `~/.zshrc`) | `$env:SNYK_CLI = "<that path>"`, or to keep it: `[Environment]::SetEnvironmentVariable("SNYK_CLI", "<that path>", "User")` |
| Nothing yet | `brew tap snyk/tap && brew install snyk-cli` | `npm install -g snyk` (or download `snyk-win.exe` from Snyk's releases) |

Common download locations of the extension's CLI are also found automatically. Then log in **with the same SSO
account as the extension**: `"$SNYK_CLI" auth` on macOS, `& $env:SNYK_CLI auth` on Windows (or just `snyk auth`).
It opens your browser for the SSO sign-in; nothing is read from the extension. Check with `whoami --experimental`.
No CLI allowed where you are? Pass a Snyk JSON export to `/dep-scan` or `/dep-run` instead.

**2. List the repos you want to fix** in [`repos/repos.txt`](repos/repos.txt), one line each (or skip this:
`/dep-run <git-url>` adds the line for you):

```text
# <name>        <git-url>                                          [options]
learning-java   https://github.com/elinasarvari/learning-java.git  path=backend  smoke=true
orders-service  git@github.com:my-org/orders-service.git           branch=develop
```

- `name`: the clone folder `repos/<name>/`, and the name you use in commands
- `git-url`: what you'd give `git clone`. Already checked out? `repos.py add ~/repos/x` looks the URL up for you
- `branch`: the repo's main branch, if it isn't called `main`
- `path`: the sub-folder that has the `pom.xml`, if it isn't at the repo root
- `smoke=true`: also start the app during verification

**3. Clone them** into `repos/` (optional: `/dep-run` does this as its first step):

```bash
python3 -I toolkit/scripts/repos.py clone      # macOS: clones missing repos, updates clean ones on main
python3 -I toolkit/scripts/repos.py status     # branch, commit, uncommitted files per clone
```

```powershell
py -3 -I toolkit\scripts\repos.py clone          # Windows (PowerShell): the same
py -3 -I toolkit\scripts\repos.py status
```

Every option, HTTPS vs SSH, private repos, and what each message means: **[repos/README.md](repos/README.md)**.

**4. Open this folder** in VS Code (Copilot Chat → **Agent** mode) or run `claude` in it.

**5. Run it: the easy way.** Give `/dep-run` one repo (its name, its git URL, or a checkout of it):

```text
/dep-run learning-java                      a repo already in repos/repos.txt
/dep-run ~/repos/orders-service             a checkout you have: its URL is added, then cloned into repos/
/dep-run https://github.com/acme/billing.git     a git URL: added and cloned into repos/
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
/dep-clone                       clone/refresh every repo in repos/repos.txt into repos/<name>/
/dep-scan                        Snyk scan → every flagged package (or: /dep-scan path/to/snyk.json)
/dep-inventory <id>              exact versions, what sets them, what moves with them, baseline build
/dep-analyze <id>                breaking changes in YOUR code with file:line, and a step-by-step plan
  → read workflows/<id>/03-plan.md and reply "approve"
/dep-apply <id>                  apply the plan in each clone, on branch deps/<id> (not committed)
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
| `/dep-clone [git-url \| checkout \| name]` | Adds repos to `repos/repos.txt` (by URL) and clones them into `repos/<name>/`. In a workflow, puts each clone on `deps/<id>` from the latest main; refuses if another workflow's unpublished changes are there | `STATUS.md` repos table | clones; switches the clone's branch |
| `/dep-scan [snyk.json]` | Runs Snyk on every repo in the list (or reads your export). Lists **every** flagged package: current version, severity, CVEs, fixed-in version, which dependency brings it in, how to fix it. Groups them into the few changes you actually make | `01-snyk-findings.md`, `snyk/findings.csv` | no |
| `/dep-inventory <id>` | For the packages in scope: the version each repo really uses, what sets it (parent/BOM/property), everything else that changes with it, coupled libraries (e.g. Camel). Builds each repo as a **baseline** | `02-inventory.md`, `facts/`, `verification/baseline/` | no |
| `/dep-analyze <id>` | Subagents read the official migration guides and search your code, config and tests. Each finding cites `file:line` and a source. Writes an ordered plan with exact diffs | `03-impact.md`, `analysis/`, `03-plan.md` | no |
| *you approve* | Reply "approve" (or click the button). Your words and the date are recorded | `STATUS.md` | — |
| `/dep-apply <id>` | Applies the plan in each clone on `deps/<id>` and compiles after every step. Never commits | `04-apply-log.md` | **edits files** in the clone, on its branch |
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
| `repos/repos.txt` | The list of repos to fix (git URLs) | **yes**, this is your list |
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
| `toolkit/scripts/*.ps1`, `common.ps1` | PowerShell twins of the `.sh` scripts (Windows PowerShell 5.1 and 7), same arguments and outputs | when you change its `.sh` twin |
| `toolkit/scripts/script-helpers.py` | Parsing shared by the bash and PowerShell scripts (JUnit, pom.xml, summary.json) | — |
| `toolkit/scripts/snyk-scan.sh` | Snyk scan of every repo in the list | — |
| `toolkit/scripts/parse-snyk.py` | Snyk JSON → findings tables + CSV | — |
| `toolkit/scripts/maven-facts.sh` | What a repo's pom really resolves | — |
| `toolkit/scripts/verify-repo.sh` | Build → tests → boot → `summary.json` | — |
| `.github/prompts/`, `.github/agents/` | Copilot slash commands and agents (**generated**) | no, edit `toolkit/` and regenerate |
| `.github/skills/dep-upgrade/SKILL.md`, `.github/copilot-instructions.md`, `.github/instructions/` | Copilot context and pom-editing rules | rarely |
| `.claude/skills/`, `.claude/agents/`, `CLAUDE.md` | Claude Code commands and subagents (**generated**, except `CLAUDE.md`) | no, regenerate |
| `tools/generate-entrypoints.py` | Regenerates the Copilot and Claude files from one spec | when adding a command |
| `tests/` | Automated tests for every script and command (`tests/run.sh`, `tests\\run.ps1`), run locally | when changing behaviour |
| `.gitattributes` | Keeps LF line endings on Windows checkouts, so the bash scripts keep working | no |

To change how a step works, edit its file in `toolkit/phases/`. Both assistants pick it up immediately.
To add or rename a command, or change a handoff button, edit `tools/generate-entrypoints.py`, then run
`python3 -I tools/generate-entrypoints.py`.

## The scripts work without an assistant too

macOS / Linux:

```bash
python3 -I toolkit/scripts/repos.py clone                          # clone/refresh every repo into repos/
python3 -I toolkit/scripts/repos.py status                         # branch, dirty, ahead/behind
bash toolkit/scripts/snyk-scan.sh /tmp/snyk                        # scan every repo
python3 -I toolkit/scripts/parse-snyk.py /tmp/snyk/*.json --md findings.md --csv findings.csv
bash toolkit/scripts/verify-repo.sh repos/learning-java/backend /tmp/verify --smoke
```

Windows (PowerShell). Same scripts and arguments, `.ps1` instead of `.sh`, `py -3` instead of `python3`:

```powershell
py -3 -I toolkit\scripts\repos.py clone
py -3 -I toolkit\scripts\repos.py status
powershell -ExecutionPolicy Bypass -File toolkit\scripts\snyk-scan.ps1 $env:TEMP\snyk
py -3 -I toolkit\scripts\parse-snyk.py (Get-ChildItem $env:TEMP\snyk\*.json) --md findings.md --csv findings.csv
powershell -ExecutionPolicy Bypass -File toolkit\scripts\verify-repo.ps1 repos\learning-java\backend $env:TEMP\verify --smoke
```

## Testing: are the commands doing the right job?

The tests run **locally**, on your machine. There's nothing to set up on GitHub.

| | macOS / Linux | Windows (PowerShell) |
|---|---|---|
| Run all tests | `tests/run.sh` | `powershell -ExecutionPolicy Bypass -File tests\run.ps1` |
| Also a real Maven build | `RUN_MAVEN_TESTS=1 tests/run.sh` | `$env:RUN_MAVEN_TESTS = "1"; powershell -ExecutionPolicy Bypass -File tests\run.ps1` |
| Test the `.ps1` scripts with PowerShell 7 instead of 5.1 | (uses `pwsh` if installed) | `$env:SUP_PS = "pwsh"` first |

The tests run in **throwaway sandboxes** with fake git remotes, a fake `HOME` and a fake `snyk` CLI. They never touch
your real repos or GitHub, and never apply an upgrade.

**Every script test runs twice: against the bash version and against its PowerShell twin.** If a fix lands in only
one of them, the other version's test goes red. On Windows the bash runs are skipped. On a Mac, the PowerShell runs
need `pwsh` (`brew install powershell`); without it they're skipped.

| Test file | Proves |
|-----------|--------|
| `test_repos.py` | Repos are cloned into `repos/` and refreshed only when clean. **Each workflow gets `deps/wf-NNN` from the latest main**, workflows don't overwrite each other's unpublished work, `release` returns to main. **Your own checkout is never touched** (branch, commit, files). No submodules; clones are never committed |
| `test_workflows.py` | Workflow 1 = `wf-001`, Workflow 2 = `wf-002`, **ids never reused**. `1` / `wf-001` / folder name all resolve. Step states, next step, History and INDEX update correctly |
| `test_snyk.py` | Every flagged package listed once with all its paths, severity totals, grouping by the dependency you edit, licence/no-fix rows, CSV. **Both scan scripts** handle a missing or not-logged-in CLI, `SNYK_CLI`, the VS Code extension's CLI and SSO logins, and scan each clone (or one workflow's repos) |
| `test_build_scripts.py` | **Both versions** of verify-repo and maven-facts: build results from JUnit files, failing tests named, build tool auto-detected (`mvnw` / `mvnw.cmd`), smoke boot catches "APPLICATION FAILED TO START", nothing left in the repo, Maven facts right |
| `test_clone_hygiene.py` | End to end, with bash and with PowerShell: clone → scan → build leaves the clone with **no changed files and no commits**; all evidence lands in `workflows/<id>/` |
| `test_wiring.py` | Every `/dep-*` command exists for Copilot **and** Claude and points at files that exist. Every `.sh` has a `.ps1` twin with the same options, every `.ps1` parses and avoids PowerShell-7-only syntax. **`/dep-apply`, `/dep-publish` and `/dep-run` can only be started by you**, and the approval gate is in place |

What tests can't check is the AI's judgement inside a step, e.g. how good an impact analysis is. That's why
every document must cite `file:line` or a source URL, and why nothing changes your code without your approval.

## Guard rails

- **Read-only until you approve.** Clone, scan, inventory, analyze and verify never edit your code.
- **Approval is yours.** The plan's approval box is ticked only after you approve in chat.
- **Branches, not main.** Changes go to `deps/<id>` in the clone under `repos/`. Nothing is committed until `/dep-publish`.
  Nothing is pushed to a default branch or force-pushed.
- **Your work is safe.** Your own checkouts are never touched. A clone with another workflow's unpublished changes is never switched or overwritten.
- **Red stays red.** Tests are never skipped or disabled to get a green build.
- **Manual-only steps.** `/dep-apply` and `/dep-publish` only run when you invoke them (Claude: can't be
  auto-triggered; Copilot: handoff buttons you have to send).

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `/dep-*` commands don't appear | Open **this folder** as the workspace root. In Copilot, use **Agent** mode |
| Clone fails for a private repo | Your git credentials/SSH key must have access: test with `git clone <url>` |
| `snyk-scan.sh` exits 127 | No CLI found: set `SNYK_CLI` to the path from the VS Code extension's settings, or install it (see Quick start) |
| `snyk-scan.sh` exits 126 | Not logged in: `"$SNYK_CLI" auth` (browser SSO) or `SNYK_TOKEN` |
| The scan uses a different CLI than expected | It prints `Using Snyk CLI: <path>`. `SNYK_CLI` always wins over `snyk` on your PATH |
| Snyk reports a different version than the inventory | Expected when the scan ran on another branch. See *Discrepancies* in `02-inventory.md` |
| `/dep-clone` says "kept as is" or "expected main" | That repo has local changes or is on another branch. That's intentional: switch or commit yourself if needed |
| `/dep-run` or `/dep-clone` says BLOCKED | Another workflow's changes in that clone aren't published yet. Publish or abandon that workflow, then run again |
| Build red only when repos build in parallel | Shared `~/.m2` download clash. Re-run that repo: `/dep-verify <id> <repo>` |
| `/dep-publish` stops | `gh auth status` must pass. For Bitbucket/GitLab it pushes and gives you the PR link instead |
