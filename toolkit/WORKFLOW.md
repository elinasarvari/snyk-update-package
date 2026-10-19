# Snyk package-update workflow — overview for agents

This project is a **meta repository**. It holds no application code. It works on the target repos
listed in `repos/repos.txt`, cloned into `repos/<name>/`, then scans, documents, upgrades, verifies and publishes
them. Every tool entry point (`.github/` for Copilot, `.claude/` for Claude Code) reads this file
and the phase file it's running. **This folder is the single source of truth.**

**Nothing here is specific to one library.** The packages and versions to upgrade always come from the **Snyk
findings** (or a list the user gives): whatever Snyk reports, in any Maven or Gradle repo. Spring Boot, Camel,
Jackson etc. in these files are only **examples** of the patterns to look for (a platform parent/BOM, a coupled
library), never a target to assume.

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
| — | `/dep-upgrade` | this file, "Orchestrating" | any of the above | — |

## Layout (paths relative to the project root)

| Path | What |
|------|------|
| `repos/repos.txt` | Target repos, by git URL: `<name> <git-url> [branch=] [path=] [smoke=true] [build="..."]` |
| `repos/<name>/` (`repo_dir`) | The repo's clone (git-ignored). **All code changes happen here**, on the workflow's branch `deps/<id>`. Build dir = `<repo_dir>/<path>`. The user's own checkouts elsewhere are never touched |
| `workflows/wf-<NNN>-<slug>/` | One folder per upgrade: `STATUS.md` + the numbered docs + raw data |
| `workflows/<id>/repos.txt` | Optional: limit this upgrade to some repos (same format) |
| `toolkit/phases/`, `roles/`, `templates/`, `scripts/` | Procedures, subagent definitions, doc templates, tools |

Scripts (run from the project root, Python with `python3 -I`):

| Script | Purpose |
|--------|---------|
| `toolkit/scripts/repos.py add\|ensure\|clone\|list\|status\|release` | Manage target repos. `--workflow <id> clone` puts each clone on `deps/<id>`. `list` gives `name, build_dir, verify_args, url, base_branch, repo_dir` as TSV |
| `toolkit/scripts/snyk-scan.sh <out> [--manifest f] [snyk args]` | `snyk test --all-projects --json` for every repo folder |
| `toolkit/scripts/parse-snyk.py <json…> --md --csv --json` | Every flagged package + changes grouped by the dependency you edit |
| `toolkit/scripts/maven-facts.sh <build_dir> <out> [filters]` | Parent, declared deps, version properties, resolved tree |
| `toolkit/scripts/verify-repo.sh <build_dir> <out> [--smoke] [--build-cmd]` | Build → JUnit counts → smoke boot → `summary.json` |

The manifest for an upgrade is `workflows/<id>/repos.txt` if it exists, else `repos/repos.txt`. Pass it with
`--manifest` to `repos.py` and `snyk-scan.sh`.

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

## Orchestrating (`/dep-upgrade`)

1. **Which upgrade?**
   - `status` or an existing workflow id → resume it.
   - a git URL, or a local checkout (used only to find its URL) → run phase 0 to add it, then continue as a new upgrade.
   - a Snyk JSON path, pasted Snyk output, or "scan" → new upgrade starting at phase 1.
   - `group:artifact X->Y` pairs → new upgrade starting at phase 2 (phase 1 = "skipped — manual").
   - no argument → show `workflows.py list` and `repos.py status`, then ask which.
2. **New workflow:** `python3 -I toolkit/scripts/workflows.py new <slug> --title "<title>" --source "<source>"`. It allocates the next
   unique id (`wf-001`, `wf-002`, ... never reused) and creates `workflows/<id>-<slug>/STATUS.md`. Make sure
   phase 0 is done (every repo folder in the manifest exists) before phases 1–5.
3. **Resume:** read `STATUS.md`, run the first phase not ✅. **Gates:** phase 4 needs `03-plan.md`
   to contain `- [x] Approved by user`, ticked only after the user approves in chat. Phases 4 and
   6 run only when the user asks for them explicitly.
4. **One phase per run** by default; continue only if the user asks, and never past a gate.
5. **End every run** by updating STATUS (state, date, ▶ Next step) and replying with what was
   produced (links), the headline findings, and **▶ Next step**: one concrete command or decision.

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
