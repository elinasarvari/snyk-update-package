# Upgrade: {{TITLE}}

| | |
|--|--|
| **Upgrade id** | `{{UPGRADE_ID}}` |
| **Source** | {{SOURCE — e.g. Snyk report path, or "manual request"}} |
| **Started** | {{DATE}} |
| **Repos in scope** | see [repos](#repos) |

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

{{ONE concrete action, e.g. "Review 03-plan.md and reply approve, then run `/dep-apply {{UPGRADE_ID}}`"}}

## Repos

| Repo | Clone (`repos/…`) | Start commit | Baseline (before) | After upgrade | PR |
|------|-----------------------|--------------|-------------------|---------------|----|

## Decisions and open questions

<!-- Append-only. Date each entry. Record every user approval here verbatim. -->
