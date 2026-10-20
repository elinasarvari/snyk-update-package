# Workflow {{NUMBER}}: {{TITLE}}

| | |
|--|--|
| **Workflow id** | `{{WORKFLOW_ID}}` (Workflow {{NUMBER}}). Use it in commands, e.g. `/dep-plan {{WORKFLOW_ID}}`, or just `{{NUMBER}}` |
| **Source** | {{SOURCE}} |
| **Started** | {{DATE}} |
| **Repos in scope** | see [repos](#repos) |
| **Branch in each repo** | `deps/{{WORKFLOW_ID}}` (created from the latest main when the workflow starts) |

## Phase tracker

| # | Phase | Command | State | Output | Updated |
|---|-------|---------|-------|--------|---------|
| 0 | Clone target repos | `/dep-run` (or `repos.py clone`) | ⬜ not started | [repos](#repos) | |
| 1 | Snyk scan | `/dep-scan` | ⬜ not started | [01-snyk-findings.md](01-snyk-findings.md) | |
| 2 | Plan (approval) | `/dep-plan` | ⬜ not started | [02-plan.md](02-plan.md) | |
| 3 | Apply | `/dep-apply` | ⬜ not started | [03-apply-log.md](03-apply-log.md) | |
| 4 | Verify | `/dep-verify` | ⬜ not started | [04-verification.md](04-verification.md) | |
| 5 | Publish (commit, push, PR) | `/dep-publish` | ⬜ not started | [repos](#repos): commit and PR | |

States: ⬜ not started · 🟡 in progress · ✅ done · ⛔ blocked · ⏸ awaiting approval

## ▶ Next step

Run `/dep-scan {{WORKFLOW_ID}}` to list every package Snyk flags (or `/dep-plan {{WORKFLOW_ID}}` with a manual package list).

## Repos

| Repo | Clone (where changes happen) | Branch | Created from | Baseline (before) | After upgrade | Commit | PR |
|------|------------------------------|--------|--------------|-------------------|---------------|--------|----|

## Decisions and open questions

<!-- Append-only. Date each entry. Record every user approval here verbatim. -->

## History

<!-- Append-only, written by `toolkit/scripts/workflows.py log`. One line per step started/finished. -->

| When | Event |
|------|-------|
