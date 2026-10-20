# snyk-update-package

**One place to fix Snyk findings across your Java repos.** You list the repos; it clones them, finds every
vulnerable package, documents what the upgrade breaks, applies it on a branch, builds and tests everything, and
opens the pull requests. You approve the plan and you start the publish.

Works the same in **GitHub Copilot** (VS Code, agent mode) and **Claude Code**.

```
repos/repos.txt → clone → Snyk scan → plan (versions, impact, steps) → ⏸ you approve → apply → verify → ⏸ you publish
```

This project holds no application code. The repos you fix are **cloned into `repos/<name>/`** and changed there, on
one branch per workflow (`deps/wf-NNN`, from the latest main); your own checkouts elsewhere are never touched. Every
run is documented in `workflows/`. Diagrams: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

```text
snyk-update-package/
├── repos/repos.txt     the repos to fix (you edit this)      → repos/README.md
├── repos/<name>/       the clones: code changes happen here (git-ignored)
├── workflows/          one folder per run: STATUS.md + documents → workflows/README.md
└── toolkit/            how each step works: procedures, scripts, templates
```

**Windows:** every command below is shown for macOS. Translate it with [this table](#windows).

---

## 1. Set up (once per machine)

**Tools:** Git, Java (the version your repos use) and Python 3.9+.

| | macOS | Windows |
|---|---|---|
| Install | Python is built in. `brew install git openjdk@21` | [Git for Windows](https://git-scm.com/download/win), [Python](https://www.python.org/downloads/windows/) (tick **Add python.exe to PATH**), `winget install EclipseAdoptium.Temurin.21.JDK` |
| Get the project | `git clone https://github.com/elinasarvari/snyk-update-package.git` then `cd snyk-update-package` | the same |
| GitHub CLI (to open PRs) | `brew install gh && gh auth login` | `winget install GitHub.cli` then `gh auth login` |

**The Snyk CLI.** If you use the Snyk VS Code extension, point the toolkit at the CLI it downloaded (VS Code →
Settings → search `snyk cli path`): `export SNYK_CLI="<that path>"` (add it to `~/.zshrc`). Otherwise
`brew tap snyk/tap && brew install snyk-cli` (Windows: `npm install -g snyk`). The extension's usual download folders
are also found automatically.

**Log the CLI in, with your company SSO** (once; no client id or secret needed):

```bash
bash toolkit/scripts/snyk-login.sh            # your browser opens: sign in with SSO, then come back
bash toolkit/scripts/snyk-login.sh --status   # "Logged in to Snyk as you@company.com"
```

Scans start the login themselves when needed. The token renews itself, so you sign in again
only after `--logout`. Other options: `--logout`, `--force` (sign in again), `--endpoint https://api.eu.snyk.io`
(EU/AU or private Snyk; ask your admin for the URL). With a Snyk service account, set `SNYK_CLIENT_ID` and
`SNYK_CLIENT_SECRET` and it logs in without a browser. It counts as logged in only when `snyk whoami` returns
your user.

**Make this repository private** (GitHub → Settings → General → Danger Zone → Change visibility). The workflow
records name your repos and their vulnerabilities, so saving them [refuses while it's public](#5-results-and-saving).

**Your assistant.** Nothing to install in the project: the commands are files in `.github/` (Copilot) and
`.claude/` (Claude Code).

| | GitHub Copilot (VS Code) | Claude Code |
|---|---|---|
| Install | VS Code + the **GitHub Copilot** extension, signed in with your Copilot licence | `curl -fsSL https://claude.ai/install.sh \| bash` (Windows: `irm https://claude.ai/install.ps1 \| iex`); a Pro, Max, Team, Enterprise or Console account |
| Open | *File → Open Folder* → **`snyk-update-package` itself**, trust the folder. In the chat, set the session target to **Local** and pick **Agent** | `cd snyk-update-package` then `claude` (it must start **in this folder**) |
| Check | Type `/dep`: six commands appear | Type `/dep` (or `/skills`): six commands appear |
| Good to know | It asks before each terminal command; buttons under a reply only **fill in** the next prompt | It asks before each command (`/permissions` to review). For the Snyk login, type `! bash toolkit/scripts/snyk-login.sh` so it runs as your own command |

`/dep-run`, `/dep-apply` and `/dep-publish` only start when you type them. The helpers `dependency-analyst`
and `upgrade-applier` aren't commands: the plan and apply steps call them.

## 2. Add your repos

```bash
python3 -I toolkit/scripts/repos.py add https://github.com/acme-corp/inventory-service.git   # or a local checkout path
python3 -I toolkit/scripts/repos.py clone                                                    # into repos/<name>/
python3 -I toolkit/scripts/repos.py status
```

That writes one line per repo to [`repos/repos.txt`](repos/repos.txt), e.g.
`inventory-service  https://github.com/acme-corp/inventory-service.git  path=backend  smoke=true`. You can skip this:
`/dep-run <git-url>` adds and clones the repo itself. Options (`branch=`, `path=`, `smoke=true`, `build=`), what
each clone message means, workflow branches, and **monorepos**: [repos/README.md](repos/README.md).

## 3. Run: `/dep-run <repo>`

Give it the repo's name in `repos.txt`, its git URL, or a local checkout. It opens the next **Workflow N**
(`wf-NNN`), or resumes the open one for that repo, and runs the steps by itself:

| # | Step | What happens | Goes on by itself? |
|---|------|--------------|--------------------|
| 0 | Clone | Updates the clone and creates `deps/wf-NNN` from the latest main | ✅ |
| 1 | Snyk scan | Every `pom.xml` in the repo (logs the CLI in first if needed). Lists every flagged package: version, severity, CVEs, fixed-in, dependency paths. Default scope: every finding with a fix (`scope: high+` to change it) | ✅ (no findings: the run ends) |
| 2 | Plan | One document, `02-plan.md`: the **versions** (what each really resolves to, what sets it, what moves with it, a **baseline build**), the **impact** on your code with `file:line` and sources, and the **steps**, with every vulnerable module decided | ⏸ **always stops** |
| 3 | Apply | Edits in `repos/<name>/` on `deps/wf-NNN`, compiling after each step. Nothing is committed | ✅ after you approve |
| 4 | Verify | Build, every module's tests, app start (`smoke=true`), Snyk re-scan; compared with the baseline, every failure diagnosed | ⏸ **always stops** |
| 5 | Publish | Commit, push `deps/wf-NNN`, open the PR; the links go into `STATUS.md` | only by your own `/dep-publish wf-NNN` |

**Snyk's suggested fixes** are read from the scan once, by script, and kept in the workflow folder:
`snyk/findings.md` section 2 *Changes to make* (each edit, current → Snyk's target, what it fixes; per path: Snyk's
upgrade path, its *remediation* section, its pin or the fixed-in version), section 3 (every dependency path with its
fix), and `snyk/module-index.md` (one line per package). When Snyk has no fix for a path (`none`), the row says what
was checked and names the library that brings it in, and the plan checks that library's newer versions and an
exclusion, path by path, before anything is *Out of scope*.

**Nothing is done twice.** Each repo is scanned once per commit (`snyk-scan --reuse`; changed code is rescanned), and a
repeated plan reuses the facts, the baseline build and each analyst report while the repo's commit and the version jump
are unchanged. Asking for a change in the plan only redoes what that change touches. Add `fresh` to force everything
again (`/dep-scan <id> fresh`, `/dep-plan <id> fresh`). The only planned second scan is verify's, which must see the changes.

**What the impact analysis (inside step 2) does.** Once the versions are verified, it lists the **levers**: the dependencies you actually
edit, per repo. Many Snyk rows that one parent/BOM manages are a single lever. For each lever, a `dependency-analyst`
helper runs, all in parallel, and:

- reads the official migration guides and release notes for **every version line crossed** (e.g. 3.3 → 3.4 → 3.5),
  once per jump: the notes are cached in `workflows/_research/`, and later runs and repos reuse them;
- searches your code, config, tests and poms (`git grep`, never `target/` or `node_modules/`) for each breaking change
  and records it with `file:line`. Changes with no hit go on a required *checked, not affected* list;
- checks coupled libraries the lever doesn't manage (e.g. Camel with Spring Boot) and the lowest version that works;
- writes `analysis/<repo>--<artifact>.md`, never touching the repo.

The reports are summarised in the plan's **Impact** section (per lever: jump type, risk, code sites, config keys,
effort, with sources). The steps are then built from the Versions and Impact sections only: ordered steps that each compile (pom → coupled libraries →
renamed artifacts → code → config → tests), exact diffs, and every vulnerable module inserted by script.

**At the plan:** read `workflows/wf-NNN-<repo>/02-plan.md` ([what to check](#4-review-the-plan)), then reply
`/dep-run <repo> approve` (Copilot: the *Approve* button), or say what to change.
**At verify:** green → `/dep-publish wf-NNN`. Red → it lists fixes; reply `/dep-run <repo> approve fixes`.

**It also stops when blocked**, and says what to do: the clone failed or another workflow's unpublished changes are
in it; no Snyk CLI or login (or pass an export: `/dep-run <repo> path/to/snyk.json`); the **baseline build is red**;
a target version doesn't exist or needs your decision; a step stays red after two fix rounds.

Every stop ends with the same reply:

```text
Workflow 3 (wf-003) · inventory-service · workflows/wf-003-inventory-service
Done this run:     0 Clone ✅ · 1 Scan ✅ (12 packages, 3 changes) · 2 Plan ⏸
Stopped because:   the plan is ready for your review
▶ Next step:       read workflows/wf-003-inventory-service/02-plan.md, then: /dep-run inventory-service approve
```

**Start a fresh chat after each stop** (Copilot: *New Chat*; Claude Code: `/clear`): `/dep-run <repo>` resumes from
`STATUS.md`, so nothing is lost and it costs fewer tokens. One repo per `/dep-run`.

## 4. Review the plan

Each vulnerable module in `02-plan.md` has **Facts** (version, severity, status, fixed in, introduced via),
**Issues** (one row per Snyk issue, linked, with CVSS, CVE, exploit), **Paths** (every route into your build, with
Snyk's fix for each) and a **Decision**. The modules are generated from the scan, so none can be missing, and
`plan-check` has confirmed every decision is filled in before you're asked.

| Check | It's right when |
|-------|-----------------|
| **Status** | `fixable by upgrade` · `needs an override` (a path has no upgrade, so the module is forced to the fixed version) · `partly fixable` (a path has no fix) · `no fix` |
| **Fix chosen** | Follows the order: upgrade the library that brings it in (Snyk's upgrade path, or its *remediation* section: `(Snyk remediation)`) → override the module → the lowest newer introducing library or an exclusion → only then *Out of scope* |
| **Target version** | **Snyk's version, exactly** (pre-filled). Any other version is listed under *Strategy → Versions not from Snyk* with its reason |
| **Plan step(s)** | Covers **every** path. A module is fixed only when every path is (see *Path coverage*) |
| **Compatibility / risk** | Says what could break, with evidence from the plan's Impact section |
| **In scope? = no** | Points to a row in *Out of scope* saying why and what happens next. For a finding Snyk can't fix (`none`), *Remediation tried* lists every check, path by path: Snyk's upgrade path, remediation section, pin and fixed-in, the newer versions of the library that brings it in, and whether it can be excluded |

To change something, say so (*"module 3: override to 2.2"*), or edit the row yourself:
`python3 -I toolkit/scripts/script-helpers.py plan-decide <plan> 7 "Target version=2.2"`, then `plan-check <plan>`.
After verification, `04-verification.md` marks every module and issue ✅ fixed, ➖ out of scope, or ⛔ still open.

## 5. Results and saving

Everything about a run is in `workflows/wf-NNN-<repo>/`, starting with `STATUS.md` (steps, ▶ next step, history);
[`workflows/INDEX.md`](workflows/INDEX.md) lists every run. What each file holds: [workflows/README.md](workflows/README.md).

The records are **saved into this repository** at every stop (committed and pushed; raw Snyk JSON and logs left
out), so they're on GitHub and on your other machines after `git pull`. Save by hand with
`python3 -I toolkit/scripts/workflows.py save <id>`. A save commits only that workflow's files and never force-pushes.

| You see | Do |
|---------|----|
| `committed N file(s)` · `pushed …` · `nothing new to commit` | Nothing |
| `REFUSED: this repository is PUBLIC` | Make it private, then save again (`--allow-public` only if publishing is really intended) |
| `could not sync with origin automatically` | `git pull --rebase` in this project, then save again |
| `push failed` / `no git remote 'origin'` | Fix access or network and save again, or use `--no-push` to only commit |

## Commands

| Command | What it does | Changes your repo? |
|---------|--------------|--------------------|
| `/dep-run <repo> [reply]` | **Start here.** Every step for one repo, stopping for your approval, blockers and before publish | only after you approve |
| `/dep-run status` | Where every workflow stands | no |
| `/dep-scan [snyk.json]` | Step 1 on its own (an export instead of running the CLI) | no |
| `/dep-plan <id>` | Step 2: versions, impact and the steps, for your approval | no |
| `/dep-apply <id>` | Step 3: apply the approved plan on `deps/<id>` | **edits files**, uncommitted |
| `/dep-verify <id>` | Step 4: build, tests, boot, Snyk re-scan | no |
| `/dep-publish <id>` | Step 5: commit, push, open the PRs | **commits, pushes, opens PRs** |

Cloning, the Snyk login and saving have no command of their own: they happen inside the steps, and by hand they're
`repos.py clone`, `snyk-login.sh` and `workflows.py save <id>`. `<id>` can be `3`, `wf-003` or the folder name. The scripts work without an assistant too; they're listed in
[toolkit/REFERENCE.md](toolkit/REFERENCE.md).

## Windows

Same scripts, same arguments, same output. Run them in PowerShell from the project folder:

| macOS | Windows (PowerShell) |
|-------|----------------------|
| `python3 -I toolkit/scripts/<x>.py …` | `py -3 -I toolkit\scripts\<x>.py …` |
| `bash toolkit/scripts/<x>.sh …` | `powershell -ExecutionPolicy Bypass -File toolkit\scripts\<x>.ps1 …` |
| `tests/run.sh` | `powershell -ExecutionPolicy Bypass -File tests\run.ps1` |
| `export SNYK_CLI="<path>"` | `[Environment]::SetEnvironmentVariable("SNYK_CLI", "<path>", "User")`, then a new window |
| `/tmp/…` | `$env:TEMP\…` |

`-ExecutionPolicy Bypass` lets just that script run, without changing a Windows setting. The assistants know this
table (`toolkit/WORKFLOW.md`), so on Windows their commands look different from the ones here. That's expected.

## Guard rails

- **Read-only until you approve.** Clone, scan, plan and verify never edit your code; the approval box
  is ticked only after you approve in chat.
- **Branches, not main.** Changes go to `deps/<id>` in the clone. Nothing is committed until `/dep-publish`, nothing is
  pushed to a default branch, nothing is force-pushed.
- **Your work is safe.** Your own checkouts are never touched; a clone with another workflow's unpublished changes is
  never switched.
- **Snyk's versions only.** Targets are the versions Snyk names, never "the latest".
- **Never into build output.** `target/`, `build/`, `node_modules/`, `.git/` … ([`toolkit/ignore-dirs.txt`](toolkit/ignore-dirs.txt))
  are skipped by the scan, the searches and the assistants' permissions.
- **Red stays red.** Tests are never skipped or disabled to get a green build.

## Tests

```bash
tests/run.sh                     # all tests, in throwaway sandboxes (fake git remotes, fake snyk), 1-3 minutes
RUN_MAVEN_TESTS=1 tests/run.sh   # + a real Maven build
```

Every script test runs against **both** the bash and the PowerShell version (on a Mac the PowerShell runs need
`brew install powershell`; on Windows the bash runs are skipped). `OK (skipped=…)` means everything works; a failure
is listed as `FAIL:` / `ERROR:` above the summary. Save the output to share it: `… 2>&1 | tee test-results.txt`
(Windows: `| Tee-Object -FilePath test-results.txt`). Run the tests after changing anything in `toolkit/` or `tools/`.

## Changing the toolkit

| To change | Edit | Then |
|-----------|------|------|
| How a step works | `toolkit/phases/<n>-*.md`, `toolkit/RUN.md`, `toolkit/roles/*.md` | nothing: both assistants read them |
| Document layout | `toolkit/templates/*.md` | — |
| A command, a handoff button, the project rules (`CLAUDE.md`, `.github/copilot-instructions.md`), or `toolkit/ignore-dirs.txt` | `tools/generate-entrypoints.py` (or the ignore list) | `python3 -I tools/generate-entrypoints.py` |
| A `.sh` script | it **and** its `.ps1` twin | `tests/run.sh` |

`repos/repos.txt` ships with examples only. Once it lists your repos, don't commit it
(`git update-index --skip-worktree repos/repos.txt`).

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `/dep-…` doesn't appear | Open **this folder** itself. Copilot: session target **Local**, then update VS Code and the extension (still missing: your org may block custom agents). Claude Code: quit and run `claude` inside this folder |
| A command appears twice in Copilot | VS Code also reads the Claude versions. Both are the same |
| Copilot only answers in text | Pick **Agent** (or a `dep-…` agent) in the chat dropdown |
| `Snyk CLI not found` (exit 127) | Set `SNYK_CLI` or install the CLI (step 1). Windows: open a **new** window after setting it |
| Not logged in (exit 126), or `did not complete` | Run the login again; if it keeps failing, ask your Snyk admin to enable SSO for you |
| `SNYK_TOKEN … is set in this shell` | `unset SNYK_TOKEN SNYK_OAUTH_TOKEN` (Windows: `Remove-Item Env:SNYK_TOKEN, Env:SNYK_OAUTH_TOKEN`), then log in again |
| Windows: `running scripts is disabled` | Use the `powershell -ExecutionPolicy Bypass -File …` form |
| Windows: sign-in page won't load | Company proxy: `$env:HTTPS_PROXY = "http://proxy:port"` (ask IT), then log in again |
| Clone fails | Test `git clone <url>` yourself: your git login or SSH key needs access |
| `BLOCKED: … unpublished changes of workflow wf-…` | Publish or abandon that workflow first |
| Snyk's version differs from the inventory | The scan ran on another branch: see *Discrepancies* in `02-plan.md` |
| Red only when repos build in parallel | Shared `~/.m2` download clash: `/dep-verify <id> <repo>` again |
| `/dep-publish` stops | `gh auth status` must pass. Bitbucket/GitLab: it pushes and gives you the PR link |
