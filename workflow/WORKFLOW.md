# Snyk package-update workflow — overview for agents

This project is a **meta repository**. It holds no application code. It works on the target repos
listed in `repos/repos.txt` (your own local folders, or git URLs it clones into `repos/`), then scans, documents, upgrades, verifies and publishes
them. Every tool entry point (`.github/` for Copilot, `.claude/` for Claude Code) reads this file
and the phase file it's running. **This folder is the single source of truth.**

```
/dep-clone ─▶ /dep-scan ─▶ /dep-inventory ─▶ /dep-analyze ─▶ ⏸ approve ─▶ /dep-apply ─▶ /dep-verify ─▶ /dep-publish
 repos/    01-snyk-      02-inventory     03-impact       03-plan      04-apply-log   05-verification  06-publish
 repo folders  findings                       03-plan                      (deps/<id>)                     (commit+PR)
```

| # | Command | Procedure | Subagent (role) | Writes to target repos? |
|---|---------|-----------|-----------------|-------------------------|
| 0 | `/dep-clone` | [phases/0-clone.md](phases/0-clone.md) | — | URLs: clone / fast-forward. Local folders: check only |
| 1 | `/dep-scan` | [phases/1-scan.md](phases/1-scan.md) | — | no |
| 2 | `/dep-inventory` | [phases/2-inventory.md](phases/2-inventory.md) | — | no (build output only) |
| 3 | `/dep-analyze` | [phases/3-analyze.md](phases/3-analyze.md) | `dependency-analyst` × (lever, repo) | no |
| 4 | `/dep-apply` | [phases/4-apply.md](phases/4-apply.md) | `upgrade-applier` × repo | **yes**: edits on `deps/<id>`, uncommitted |
| 5 | `/dep-verify` | [phases/5-verify.md](phases/5-verify.md) | `repo-verifier` × repo | no (build output only) |
| 6 | `/dep-publish` | [phases/6-publish.md](phases/6-publish.md) | — | **yes**: commit, push, open PR |
| — | `/dep-upgrade` | this file, "Orchestrating" | any of the above | — |

## Layout (paths relative to the project root)

| Path | What |
|------|------|
| `repos/repos.txt` | Target repos, each a local folder or a git URL: `<name> <git-url> [branch=] [path=] [smoke=true] [build="..."]` |
| repo folder (`repo_dir`) | Where a repo's code is: the **local folder** from the list (used in place), or `repos/<name>/` for a git URL (git-ignored). Build dir = `<repo_dir>/<path>` |
| `upgrades/<YYYY-MM-DD>-<slug>/` | One folder per upgrade: `STATUS.md` + the numbered docs + raw data |
| `upgrades/<id>/repos.txt` | Optional: limit this upgrade to some repos (same format) |
| `workflow/phases/`, `roles/`, `templates/`, `scripts/` | Procedures, subagent definitions, doc templates, tools |

Scripts (run from the project root, Python with `python3 -I`):

| Script | Purpose |
|--------|---------|
| `workflow/scripts/repos.py add\|clone\|list\|status` | Manage target repos. `list` gives `name, build_dir, verify_args, url, branch, repo_dir, kind` as TSV |
| `workflow/scripts/snyk-scan.sh <out> [--manifest f] [snyk args]` | `snyk test --all-projects --json` for every repo folder |
| `workflow/scripts/parse-snyk.py <json…> --md --csv --json` | Every flagged package + changes grouped by the dependency you edit |
| `workflow/scripts/maven-facts.sh <build_dir> <out> [filters]` | Parent, declared deps, version properties, resolved tree |
| `workflow/scripts/verify-repo.sh <build_dir> <out> [--smoke] [--build-cmd]` | Build → JUnit counts → smoke boot → `summary.json` |

The manifest for an upgrade is `upgrades/<id>/repos.txt` if it exists, else `repos/repos.txt`. Pass it with
`--manifest` to `repos.py` and `snyk-scan.sh`.

## Orchestrating (`/dep-upgrade`)

1. **Which upgrade?**
   - `status` or an existing upgrade id → resume it.
   - a git URL or a local folder → run phase 0 to add it, then continue as a new upgrade.
   - a Snyk JSON path, pasted Snyk output, or "scan" → new upgrade starting at phase 1.
   - `group:artifact X->Y` pairs → new upgrade starting at phase 2 (phase 1 = "skipped — manual").
   - no argument → list `upgrades/*/STATUS.md` phase rows and `repos.py status`, then ask which.
2. **New upgrade folder:** `upgrades/<YYYY-MM-DD>-<slug>/` with a copy of `templates/STATUS.md`. Make sure
   phase 0 is done (every repo folder in the manifest exists) before phases 1–5.
3. **Resume:** read `STATUS.md`, run the first phase not ✅. **Gates:** phase 4 needs `03-plan.md`
   to contain `- [x] Approved by user`, ticked only after the user approves in chat. Phases 4 and
   6 run only when the user asks for them explicitly.
4. **One phase per run** by default; continue only if the user asks, and never past a gate.
5. **End every run** by updating STATUS (state, date, ▶ Next step) and replying with what was
   produced (links), the headline findings, and **▶ Next step**: one concrete command or decision.

## Principles

- **The repo folder is the source of truth, not the report.** Reconcile every version against
  `dependency:tree`. Report-vs-repo mismatches go under *Discrepancies* for the user to decide.
- **Upgrade the lever, not the leaf.** Starters, Spring Framework, Jackson, Hibernate, Tomcat and Netty are
  managed by the Boot parent/BOM. Bump the parent; never pin one managed artifact across a major line.
- **Majors are stepped.** Read every intermediate line's migration guide (3.3 → 3.4 → 3.5 → 4.0 → 4.1).
- **Documentation is the product.** Each claim cites `repos/<repo>/path:line` or a URL.
  "Checked, not affected" lists are required.
- **Never hide red.** No skipping tests, `@Disabled`, or `-DskipTests` to get green.
- **Never touch the user's work.** A repo folder with uncommitted changes or on an unexpected branch is
  reported, never reset, stashed, pulled or switched. Local folders are the user's own checkout: say so
  whenever a phase is about to create or switch to a `deps/<id>` branch there.
- **Nothing leaves the machine without the user asking.** Commits, pushes and PRs in target repos
  happen only in `/dep-publish`. This meta repo's own docs are committed only when the user asks.
