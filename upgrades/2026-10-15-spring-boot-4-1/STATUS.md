# Upgrade: Spring Boot → 4.1.1 (spring-boot-starter-web)

| | |
|--|--|
| **Upgrade id** | `2026-10-15-spring-boot-4-1` |
| **Source** | manual request: `spring-boot-starter-web` 3.5.16 → 4.1.1 (from Snyk; report not attached yet) |
| **Started** | 2026-10-15 (moved here from `learning-java/docs/upgrades/`) |
| **Repos in scope** | all of `repos/repos.txt` — see [repos](#repos) |

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

Run the full Snyk scan so the upgrade covers **every** flagged package, not just `spring-boot-starter-web`:
`/dep-scan 2026-10-15-spring-boot-4-1` (needs `brew tap snyk/tap && brew install snyk-cli && snyk auth`),
or `/dep-scan 2026-10-15-spring-boot-4-1 <snyk.json>` with an export. Then choose the scope and re-run
`/dep-inventory 2026-10-15-spring-boot-4-1`. That also settles where 3.5.16 came from.

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
