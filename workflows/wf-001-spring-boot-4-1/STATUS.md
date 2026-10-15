# Workflow 1: Spring Boot → 4.1.1 (spring-boot-starter-web)

| | |
|--|--|
| **Workflow id** | `wf-001` (Workflow 1). Use it in commands, e.g. `/dep-inventory wf-001`, or just `1` |
| **Source** | manual request: `spring-boot-starter-web` 3.5.16 → 4.1.1 (from Snyk; report not attached yet) |
| **Started** | 2026-10-15 |
| **Repos in scope** | all of `repos/repos.txt`, see [repos](#repos) |
| **Branch in each repo** | `deps/wf-001` (created by `/dep-apply`) |

## Phase tracker

| # | Phase | Command | State | Output | Updated |
|---|-------|---------|-------|--------|---------|
| 0 | Clone target repos | `/dep-clone` | ✅ done | [repos](#repos) | 2026-10-15 |
| 1 | Snyk scan | `/dep-scan` | ⬜ not started (needs Snyk CLI or a JSON export) | [01-snyk-findings.md](01-snyk-findings.md) | |
| 2 | Inventory | `/dep-inventory` | ⛔ needs decision (discrepancy) | [02-inventory.md](02-inventory.md) | 2026-10-15 |
| 3 | Impact + plan (approval) | `/dep-analyze` | ⬜ not started | [03-impact.md](03-impact.md), [03-plan.md](03-plan.md) | |
| 4 | Apply | `/dep-apply` | ⬜ not started | [04-apply-log.md](04-apply-log.md) | |
| 5 | Verify | `/dep-verify` | ⬜ not started | [05-verification.md](05-verification.md) | |
| 6 | Publish (commit, push, PR) | `/dep-publish` | ⬜ not started | [06-publish.md](06-publish.md) | |

States: ⬜ not started · 🟡 in progress · ✅ done · ⛔ blocked · ⏸ awaiting approval

## ▶ Next step

Paused by the user: no upgrade will be applied. To resume later, run `/dep-upgrade wf-001`.

## Repos

| Repo | Type | Folder | Start commit | Baseline (before) | After upgrade | PR |
|------|------|--------|--------------|-------------------|---------------|----|
| learning-java | local | `~/repos/learning-java` (`path=backend`) | `dep-upgrade-copilot-snyk` @ `b4bacd1` | ✅ green — 39/0/0/0, boots ([summary](verification/baseline/learning-java/summary.json)) | | |

## Decisions and open questions

- 2026-10-15 — `learning-java` switched from a separate clone to the local folder `~/repos/learning-java`
  (user chose "local path or URL"). Baseline re-run there. **Open:** that checkout is on
  `dep-upgrade-copilot-snyk`, not `main` (it's 1 commit behind `origin/main`, the PR merge, with identical files).
  Switch it with `git -C ~/repos/learning-java switch main && git pull` before `/dep-apply`, so the upgrade
  branch starts from `main`.

- 2026-10-15 — **Open:** reported current 3.5.16 ≠ resolved 3.3.2 (see 02-inventory Discrepancies).
- 2026-10-15 — **Open:** Camel target 4.22.1 vs 4.23.0 (both built on Boot 4.1.1); prefer the LTS line — phase 3 to confirm.
- 2026-10-15: **User decision:** no upgrade is to be applied for now ("I don't want to do any upgrades").
  This workflow stays at inventory as a record; nothing past step 2 will run unless the user asks.

## History

<!-- Append-only, written by `toolkit/scripts/workflows.py log`. One line per step started/finished. -->

| When | Event |
|------|-------|
| 2026-10-15 13:50 | Workflow 1 created in learning-java/docs/upgrades (manual request) |
| 2026-10-15 13:58 | Step 2 Inventory → ⛔ blocked (discrepancy: Snyk 3.5.16 vs repo 3.3.2) |
| 2026-10-15 15:40 | Moved to snyk-update-package; step 0 → ✅ done |
| 2026-10-15 16:30 | learning-java switched to local folder ~/repos/learning-java; baseline re-run: green, 39 tests |
| 2026-10-15 15:18 | Renamed to wf-001 (unique workflow ids introduced) |
| 2026-10-15 15:18 | Next step: Paused by the user: no upgrade will be applied. To resume later, run `/dep-upgrade wf-001`. |
| 2026-10-15 16:21 | Design change: repos are always cloned into repos/<name>/; workflows work there on deps/wf-NNN (from the latest main). learning-java is now listed by URL; ~/repos/learning-java is no longer used. |
