# Snyk package-update workflow — overview for agents

This project is a **meta repository**. It holds no application code. It works on the target repos
listed in `repos/repos.txt`, cloned into `repos/<name>/`, then scans, documents, upgrades, verifies and publishes
them. Every tool entry point (`.github/` for Copilot, `.claude/` for Claude Code) reads this file
and the phase file it's running. **This folder is the single source of truth.**

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

Each of these appends a timestamped line to the run's **History** and rebuilds `workflows/INDEX.md`.

## Principles

- **The repo folder is the source of truth, not the report.** Reconcile every version against
  `dependency:tree`. Report-vs-repo mismatches go under *Discrepancies* for the user to decide.
- **Upgrade the lever, not the leaf.** Starters, Spring Framework, Jackson, Hibernate, Tomcat and Netty are
  managed by the Boot parent/BOM. Bump the parent; never pin one managed artifact across a major line.
- **Majors are stepped.** Read every intermediate line's migration guide (3.3 → 3.4 → 3.5 → 4.0 → 4.1).
- **Documentation is the product.** Each claim cites `repos/<repo>/path:line` or a URL.
  "Checked, not affected" lists are required.
- **Never hide red.** No skipping tests, `@Disabled`, or `-DskipTests` to get green.
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
  happen only in `/dep-publish`. Workflow records (`workflows/wf-*`, `INDEX.md`) are git-ignored and stay on the
  user's machine; never commit them or `repos/repos.txt` entries for the user.
