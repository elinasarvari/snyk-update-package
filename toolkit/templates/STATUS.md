# Workflow {{NUMBER}}: {{TITLE}}

| | |
|--|--|
| **Workflow id** | `{{WORKFLOW_ID}}` (Workflow {{NUMBER}}). Use it in commands, e.g. `/dep-inventory {{WORKFLOW_ID}}`, or just `{{NUMBER}}` |
| **Source** | {{SOURCE}} |
| **Started** | {{DATE}} |
| **Repos in scope** | see [repos](#repos) |
| **Branch in each repo** | `deps/{{WORKFLOW_ID}}` (created by `/dep-apply`) |

## Phase tracker

| # | Phase | Command | State | Output | Updated |
|---|-------|---------|-------|--------|---------|
| 0 | Clone target repos | `/dep-clone` | ⬜ not started | [repos](#repos) | |
| 1 | Snyk scan | `/dep-scan` | ⬜ not started | [01-snyk-findings.md](01-snyk-findings.md) | |
| 2 | Inventory | `/dep-inventory` | ⬜ not started | [02-inventory.md](02-inventory.md) | |
| 3 | Impact + plan (approval) | `/dep-analyze` | ⬜ not started | [03-impact.md](03-impact.md), [03-plan.md](03-plan.md) | |
| 4 | Apply | `/dep-apply` | ⬜ not started | [04-apply-log.md](04-apply-log.md) | |
| 5 | Verify | `/dep-verify` | ⬜ not started | [05-verification.md](05-verification.md) | |
| 6 | Publish (commit, push, PR) | `/dep-publish` | ⬜ not started | [06-publish.md](06-publish.md) | |

States: ⬜ not started · 🟡 in progress · ✅ done · ⛔ blocked · ⏸ awaiting approval

## ▶ Next step

Run `/dep-scan {{WORKFLOW_ID}}` to list every package Snyk flags (or `/dep-inventory {{WORKFLOW_ID}}` for a manual package list).

## Repos

| Repo | Type | Folder | Start commit | Baseline (before) | After upgrade | PR |
|------|------|--------|--------------|-------------------|---------------|----|

## Decisions and open questions

<!-- Append-only. Date each entry. Record every user approval here verbatim. -->

## History

<!-- Append-only, written by `toolkit/scripts/workflows.py log`. One line per step started/finished. -->

| When | Event |
|------|-------|
