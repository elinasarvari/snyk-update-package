# Phase 5 — Verify across repos

Build, test and boot every target repo. Also usable on its own as a health check (`baseline`). Changes no source.

## Steps

1. **Repos:** take them from `repos.py list`, using the upgrade manifest if there is one. If the user named
   repos, check only those. A repo whose folder doesn't exist (not cloned, or wrong local path) is reported as `missing`.
2. **Health-check mode** (argument `baseline`): run `verify-repo.sh` for each repo on its current branch
   into `workflows/_health/<date>/<name>/`, then report. No workflow folder is needed.
3. **Upgrade mode:** check each repo folder is on `deps/<id>`. If one isn't, ask; don't switch branches for the
   user. Copy `toolkit/templates/05-verification.md`. `python3 -I toolkit/scripts/workflows.py phase <id> 5 running`.
4. **Delegate each repo to the `repo-verifier` subagent** (role: `toolkit/roles/repo-verifier.md`),
   in parallel when possible. Pass:
   - `repo` = `build_dir`
   - `args` = `verify_args`
   - `script` = absolute path of `toolkit/scripts/verify-repo.sh`
   - `out_dir` = `workflows/<id>/verification/after/<name>`
   - `baseline` = `workflows/<id>/verification/baseline/<name>/summary.json`
   - `impact` = `workflows/<id>/03-impact.md`
   Parallel Maven builds share `~/.m2`. On a corrupted-artifact error during concurrent downloads,
   re-run that repo alone before calling it red.
5. **Re-scan (if the Snyk CLI is available):** run phase 1 step 3 into `workflows/<id>/snyk-after/` and parse
   it. Add "Snyk findings before → after" to the report. This proves the targeted issues are gone and
   that nothing new came in. **Every finding still open must be in `03-plan.md` → Out of scope.** Any other one (a
   path the plan meant to fix, or a new finding) is a regression: list it under Failures. Fill in the report's
   *Vulnerable modules: before → after* table, one row per module and issue from 03-plan.
6. **Clone hygiene:** if any `summary.json` has a non-empty `left_in_repo`, list those files under Failures as
   `environmental` (the build writes outside `target/`). They are never committed: publish stages only the plan's files.
7. **Assemble `05-verification.md`:** the Result table, a Failures section per red repo (regression /
   pre-existing / environmental / unknown), and the Verdict.
8. `python3 -I toolkit/scripts/workflows.py phase <id> 5 done` if every repo is green, or only pre-existing/environmental failures remain
   (say which). Otherwise ⛔.
   - ▶ Next step when green: "review the diff (`git -C repos/<name> diff main...deps/<id>`), then `/dep-publish <id>`".
   - ▶ Next step when red: the fix for each regression. Add it as new plan steps (needs
     re-approval), then `/dep-apply` → `/dep-verify` again.
9. Never re-run with tests skipped to manufacture a green result.
