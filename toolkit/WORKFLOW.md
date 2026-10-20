# Snyk package-update workflow — overview for agents

This project is a **meta repository**. It holds no application code. It works on the target repos
listed in `repos/repos.txt`, cloned into `repos/<name>/`, then scans, documents, upgrades, verifies and publishes
them. Every tool entry point (`.github/` for Copilot, `.claude/` for Claude Code) reads this file
and the phase file it's running. **This folder is the single source of truth.**

**Nothing here is specific to one library.** The packages and versions to upgrade always come from the **Snyk
findings** (or a list the user gives): whatever Snyk reports, in any Maven or Gradle repo. Spring Boot, Camel,
Jackson etc. in these files are only **examples** of the patterns to look for (a platform parent/BOM, a coupled
library), never a target to assume.

**Target versions are Snyk's, exactly.** Every version the plan moves to is the one Snyk names: the upgrade path's
version for the dependency to edit (the finding's own, or else the report's *remediation* section's upgrade), Snyk's
pin, or for an override the lowest *fixed in* version above the current
one. When Snyk names several versions for the same dependency (one per issue or path), use the highest **of those**,
so every issue is fixed. Never look up or choose the latest/newest release yourself. A version Snyk didn't name
(a coupled library needs it, or Snyk has no fix for a path) is allowed only as the **lowest** version that works, with
evidence, listed in the plan's *Versions not from Snyk* for the user to approve. No version from Snyk and none from
the user means stop and ask.

```
/dep-clone ─▶ /dep-scan ─▶ /dep-inventory ─▶ /dep-analyze ─▶ ⏸ approve ─▶ /dep-apply ─▶ /dep-verify ─▶ /dep-publish
 repos/    01-snyk-      02-inventory     03-impact       03-plan      04-apply-log   05-verification  06-publish
 repo folders  findings                       03-plan                      (deps/<id>)                     (commit+PR)
```

| # | Command | Procedure | Subagent (role) | Writes to target repos? |
|---|---------|-----------|-----------------|-------------------------|
| 0 | `/dep-clone` | [phases/0-clone.md](phases/0-clone.md) | — | clones into `repos/<name>/`; in a workflow, puts the clone on `deps/<id>` from the latest main |
| 1 | `/dep-scan` | [phases/1-scan.md](phases/1-scan.md) | — | no |
| 2 | `/dep-inventory` | [phases/2-inventory.md](phases/2-inventory.md) | — | no (build output only) |
| 3 | `/dep-analyze` | [phases/3-analyze.md](phases/3-analyze.md) | `dependency-analyst` × (lever, repo) | no |
| 4 | `/dep-apply` | [phases/4-apply.md](phases/4-apply.md) | `upgrade-applier` × repo | **yes**: edits on `deps/<id>`, uncommitted |
| 5 | `/dep-verify` | [phases/5-verify.md](phases/5-verify.md) | `repo-verifier` × repo | no (build output only) |
| 6 | `/dep-publish` | [phases/6-publish.md](phases/6-publish.md) | — | **yes**: commit, push, open PR |
| — | `/dep-run <repo>` | [RUN.md](RUN.md): **autopilot**, every step for one repo; stops at approval, blockers, and before publish | all three | only after the user approves (via step 4) |
| — | `/dep-upgrade` | [UPGRADE.md](UPGRADE.md) | any of the above | — |

## Where things are

Target repos: `repos/repos.txt` → clones in `repos/<name>/`. Each run: `workflows/wf-NNN-<slug>/`. Procedures:
`toolkit/phases/`, `toolkit/roles/`, `toolkit/RUN.md`, `toolkit/UPGRADE.md`. Every script, its arguments and the folder
layout: `toolkit/REFERENCE.md` (read it only when a phase file doesn't already give the exact command).

## Token budget (read this, it saves a lot)

Every file you open and every line you print costs context. Keep it small:

| Instead of | Use |
|------------|-----|
| raw Snyk reports `snyk/*.json` (can be megabytes) | `snyk/findings.md` (table 2 "changes to make" first), or `findings.json` / `.csv` with a filter |
| a whole `build.log` / `smoke.log` | `summary.json`, then `python3 -I toolkit/scripts/script-helpers.py first-errors <log> 40` |
| the whole `dependency-tree.txt` | `filtered-tree.txt`, or `grep <artifact> dependency-tree.txt` |
| reading files to find code | `git -C <repo> grep -n -l <pattern>` for the file list, then read only the lines around each hit |
| re-researching a version jump | the research cache `workflows/_research/` (see `roles/dependency-analyst.md`) |
| all phase files up front | only the phase file you're running now |
| re-typing generated tables into a document | link them, or let a script insert them (`parse-snyk.py --into-plan`) |
| reading `snyk/findings.md` in full | section 2 ("changes to make") for planning; `grep` for a package |
| reading every module of a long `vulnerable-modules.md` / plan | `snyk/module-index.md` (one line per module); a full entry only for exceptions |
| editing each module's Decision table one by one | `script-helpers.py plan-decide <plan> <which> "Field=value"` for groups, then `plan-check` |

- **Replies stay short:** what was produced (links), the headline findings (a few bullets), the next step. Never paste
  file contents, logs or long tables into the chat: link the file.
- **State lives in files, not in the chat.** Each step writes its document and updates `STATUS.md`, so the next
  step (or a fresh chat) needs only those files. Don't re-read earlier documents unless the step needs them.
- **Script output:** the toolkit scripts print summaries. Don't add `-v`, `-X` or debug flags unless diagnosing.

## Running the commands on Windows (PowerShell)

The procedures show macOS/Linux commands. **On Windows, translate every command like this** before running it
(Copilot's terminal on Windows is PowerShell):

| macOS / Linux | Windows (PowerShell) |
|---------------|----------------------|
| `python3 -I toolkit/scripts/<x>.py ...` | `py -3 -I toolkit\scripts\<x>.py ...` |
| `bash toolkit/scripts/<x>.sh ...` | `powershell -ExecutionPolicy Bypass -File toolkit\scripts\<x>.ps1 ...` (same arguments) |
| `tests/run.sh` | `powershell -ExecutionPolicy Bypass -File tests\run.ps1` |
| `export NAME=value` | `$env:NAME = "value"` |
| `rm -rf <dir>` | `Remove-Item -Recurse -Force <dir>` |
| `git -C <dir> ...` | the same |

- Every `.sh` script has a `.ps1` twin with **the same arguments, outputs and exit codes**. Both work in Windows
  PowerShell 5.1 and PowerShell 7. The shared parsing is in `toolkit/scripts/script-helpers.py`.
- Builds use `mvnw.cmd` / `gradlew.bat` on Windows. The Snyk CLI is `snyk-win.exe` (or `snyk` from npm).
- Paths may use `\` or `/`. The scripts print project paths with `/` on every OS.

## Tracking every run (unique ids, steps, history)

Each run of the workflow is **Workflow N** with id `wf-NNN`, folder `workflows/wf-NNN-<slug>/`, and
branch `deps/wf-NNN` in each repo. Users may refer to it as `1`, `wf-1`, `wf-001` or the folder name.
**Always go through the script; never hand-edit the phase tracker, History, or `workflows/INDEX.md`:**

| When | Run |
|------|-----|
| Starting a new run | `python3 -I toolkit/scripts/workflows.py new <slug> --title "..." --source "..."` |
| Turning a user's reference into the folder | `python3 -I toolkit/scripts/workflows.py resolve <ref>` |
| A step starts | `python3 -I toolkit/scripts/workflows.py phase <id> <N> running` |
| A step ends | `python3 -I toolkit/scripts/workflows.py phase <id> <N> done` (or `blocked` / `waiting` / `skipped`, with `--note "<why>"`) |
| Setting ▶ Next step | `python3 -I toolkit/scripts/workflows.py next <id> "<one concrete action>"` |
| Anything worth recording (approval, decision, deviation) | `python3 -I toolkit/scripts/workflows.py log <id> "<event>"` |
| Showing all runs | `python3 -I toolkit/scripts/workflows.py list`, or read `workflows/INDEX.md` |
| **Finishing any step or stop (last thing before replying)** | `python3 -I toolkit/scripts/workflows.py save <id>` (commit + push the workflow's records; see `toolkit/SAVE.md`) |

Each of these appends a timestamped line to the run's **History** and rebuilds `workflows/INDEX.md`.

## Principles

- **The repo folder is the source of truth, not the report.** Reconcile every version against
  `dependency:tree`. Report-vs-repo mismatches go under *Discrepancies* for the user to decide.
- **Upgrade the lever, not the leaf.** Many flagged packages get their version from a parent POM or an imported BOM
  (e.g. Spring Boot's parent manages Spring Framework, Jackson, Tomcat …; a Jackson or Netty BOM manages its
  modules). Bump that parent/BOM; never pin one managed artifact to a different major line.
- **Majors are stepped.** Read every intermediate line's migration guide (3.3 → 3.4 → 3.5 → 4.0 → 4.1).
- **Documentation is the product.** Each claim cites `repos/<repo>/path:line` or a URL.
  "Checked, not affected" lists are required.
- **Never hide red.** No skipping tests, `@Disabled`, or `-DskipTests` to get green.
- **Stay out of build output and dependency folders.** Never search, scan, read for analysis, or edit inside the
  folders listed in `toolkit/ignore-dirs.txt` (`target/`, `build/`, `out/`, `node_modules/`, `.git/`, IDE folders
  ...). Use `git -C <repo> grep` / `git ls-files`, which only see tracked files. The scripts already apply the list
  (Snyk `--exclude`, pom discovery), as do `.vscode/settings.json` and `.claude/settings.json`. The one exception:
  `verify-repo` reads the build's own results (test reports, the packaged jar).
- **The clone holds code changes only. Everything else lives in this project.** In `repos/<name>/` the
  workflow may only change what the approved plan says (code, `pom.xml`/build files, config, tests). It
  never writes documentation, reports, logs, notes, Snyk policy files (`.snyk`), helper scripts or anything
  else there. All of that goes to `workflows/<id>/`. Builds may create the repo's normal build output
  (`target/`, `build/`); `verify-repo.sh` reports anything else a build leaves behind (`left_in_repo`).
- **Never touch the user's work.** All changes happen in the clones under `repos/`, never in the user's own
  checkouts. A clone with uncommitted changes (e.g. another workflow's unpublished work) is reported, never
  reset, stashed or switched.
- **One branch per workflow, one workflow at a time per clone.** Workflow `wf-NNN` works on `deps/wf-NNN`, created
  from the latest main by `repos.py --workflow <id> clone`. Never create or name the branch any other way.
- **Nothing leaves the machine without the user asking.** Commits, pushes and PRs in target repos
  happen only in `/dep-publish`. Workflow records (`workflows/wf-*`, `INDEX.md`, `_research/`) are committed and
  pushed to this project's own repository **only** through `workflows.py save` (it refuses while the repo is public).
  Never commit `repos/repos.txt` entries or the clones for the user.
