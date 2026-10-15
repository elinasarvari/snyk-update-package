# Workflow 2: Snyk fixes: learning-java

| | |
|--|--|
| **Workflow id** | `wf-002` (Workflow 2). Use it in commands, e.g. `/dep-inventory wf-002`, or just `2` |
| **Source** | /dep-run learning-java |
| **Started** | 2026-10-15 |
| **Repos in scope** | see [repos](#repos) |
| **Branch in each repo** | `deps/wf-002` (created by `/dep-apply`) |

## Phase tracker

| # | Phase | Command | State | Output | Updated |
|---|-------|---------|-------|--------|---------|
| 0 | Clone target repos | `/dep-clone` | ✅ done | [repos](#repos) | 2026-10-15 |
| 1 | Snyk scan | `/dep-scan` | ⛔ blocked (no Snyk CLI on this machine) | [01-snyk-findings.md](01-snyk-findings.md) | 2026-10-15 |
| 2 | Inventory | `/dep-inventory` | ⬜ not started | [02-inventory.md](02-inventory.md) | |
| 3 | Impact + plan (approval) | `/dep-analyze` | ⬜ not started | [03-impact.md](03-impact.md), [03-plan.md](03-plan.md) | |
| 4 | Apply | `/dep-apply` | ⬜ not started | [04-apply-log.md](04-apply-log.md) | |
| 5 | Verify | `/dep-verify` | ⬜ not started | [05-verification.md](05-verification.md) | |
| 6 | Publish (commit, push, PR) | `/dep-publish` | ⬜ not started | [06-publish.md](06-publish.md) | |

States: ⬜ not started · 🟡 in progress · ✅ done · ⛔ blocked · ⏸ awaiting approval

## ▶ Next step

Choose how to get the findings: (a) install + log in to the Snyk CLI, then reply "continue"; (b) give a Snyk JSON export path; or (c) reply "manual: spring-boot-starter-web 4.1.1" to skip the scan. Then /dep-run learning-java continues.

## Repos

| Repo | Clone (where changes happen) | Branch | Created from | Baseline (before) | After upgrade | PR |
|------|------------------------------|--------|--------------|-------------------|---------------|----|
| learning-java | `repos/learning-java` (`path=backend`) | `deps/wf-002` | `origin/main` @ `5f3f485` | | | |

## Decisions and open questions

<!-- Append-only. Date each entry. Record every user approval here verbatim. -->

## History

<!-- Append-only, written by `toolkit/scripts/workflows.py log`. One line per step started/finished. -->

| When | Event |
|------|-------|
| 2026-10-15 16:41 | Workflow 2 created (wf-002) for learning-java |
| 2026-10-15 16:41 | Started by /dep-run learning-java (driven from a Claude Code session) |
| 2026-10-15 16:41 | Step 0 Clone target repos → 🟡 in progress |
| 2026-10-15 16:41 | Step 0 Clone target repos → ✅ done |
| 2026-10-15 16:41 | Step 1 Snyk scan → 🟡 in progress |
| 2026-10-15 16:41 | Step 1 Snyk scan → ⛔ blocked: no Snyk CLI on this machine |
| 2026-10-15 16:41 | Next step: Choose how to get the findings: (a) install + log in to the Snyk CLI, then reply "continue"; (b) give a Snyk JSON export path; or (c) reply "manual: spring-boot-starter-web 4.1.1" to skip the scan. Then /dep-run learning-java continues. |
