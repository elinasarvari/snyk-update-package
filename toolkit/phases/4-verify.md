# Phase 4 — Verify

Build, test and boot every repo of the workflow, compare with the baseline, re-scan with Snyk, and diagnose every
failure. Changes no source.

## Steps

1. **Repos:** from `repos.py list` (the workflow's manifest if there is one); if the user named repos, only those. Each
   clone must be on `deps/<id>`; if one isn't, ask, don't switch branches for the user. Copy
   `toolkit/templates/04-verification.md`. `python3 -I toolkit/scripts/workflows.py phase <id> 4 running`.
2. **Build, test and boot each repo** (in parallel when the tool allows; timeout ≥ 10 min each):
   `bash toolkit/scripts/verify-repo.sh <build_dir> workflows/<id>/verification/after/<name> <verify_args>`
   (Windows: `powershell -ExecutionPolicy Bypass -File toolkit\scripts\verify-repo.ps1` with the same arguments).
   Exit codes: 0 green · 1 build/tests failed · 2 smoke failed · 3 unsupported repo. Parallel Maven builds share
   `~/.m2`: on a corrupted-artifact error during concurrent downloads, re-run that repo alone before calling it red.
3. **Diagnose each red repo** from its `summary.json`, never from whole logs: get the **first** errors with
   `python3 -I toolkit/scripts/script-helpers.py first-errors <out_dir>/build.log 40` (same for `smoke.log`), the first
   cause, not the cascade. Classify each failure against `verification/baseline/<name>/summary.json`:
   - **regression**: new since the baseline (or no baseline and clearly tied to the upgrade, e.g. `ClassNotFoundException`
     for a relocated package). Match it to an item in the plan's Impact section when possible;
   - **pre-existing**: also failing in the baseline;
   - **environmental**: network, missing Docker/Redis, port in use, JDK mismatch;
   - **unknown**: no baseline and ambiguous. Don't guess.
   Write `<out_dir>/diagnosis.md` per red repo: symptom, cause, class, proposed fix.
4. **Re-scan (if the Snyk CLI is available):** run phase 1 step 3 into `workflows/<id>/snyk-after/` **without
   `--reuse`** (the changes aren't committed, so the commit hasn't moved; this scan must see them), and parse it.
   Add "Snyk findings before → after" to the report. **Every finding still open must be in `02-plan.md` → Out of
   scope.** Any other one (a path the plan meant to fix, or a new finding) is a regression: list it under Failures.
   Fill in the *Vulnerable modules: before → after* table, one row per module and issue from the plan.
5. **Clone hygiene:** a non-empty `left_in_repo` in any `summary.json` goes under Failures as `environmental` (the build
   writes outside `target/`). Those files are never committed: publish stages only the plan's files.
6. **Assemble `04-verification.md`:** the Result table, a Failures section per red repo, and the Verdict.
7. `python3 -I toolkit/scripts/workflows.py phase <id> 4 done` if every repo is green, or only pre-existing/environmental
   failures remain (say which). Otherwise ⛔.
   - ▶ Next step when green: "review the diff (`git -C repos/<name> diff main...deps/<id>`), then `/dep-publish <id>`".
   - ▶ Next step when red: the fix for each regression. Add it as new plan steps (needs re-approval), then
     `/dep-apply` → `/dep-verify` again.
8. Never re-run with tests skipped to manufacture a green result.
