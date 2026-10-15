# Phase 5 — Verify across repos

Build, test and boot every target repo. Also usable on its own as a health check (`baseline`). Changes no source.

## Steps

1. **Repos:** take them from `repos.py list`, using the upgrade manifest if there is one. If the user named
   repos, check only those. A repo that isn't cloned is reported as `missing`.
2. **Health-check mode** (argument `baseline`): run `verify-repo.sh` for each repo on its current branch
   into `upgrades/_health/<date>/<name>/`, then report. No upgrade folder is needed.
3. **Upgrade mode:** check each clone is on `deps/<id>`. If one isn't, ask; don't switch branches for the
   user. Copy `workflow/templates/05-verification.md`. STATUS phase 5 → 🟡.
4. **Delegate each repo to the `repo-verifier` subagent** (role: `workflow/roles/repo-verifier.md`),
   in parallel when possible. Pass:
   - `repo` = `build_dir`
   - `args` = `verify_args`
   - `script` = absolute path of `workflow/scripts/verify-repo.sh`
   - `out_dir` = `upgrades/<id>/verification/after/<name>`
   - `baseline` = `upgrades/<id>/verification/baseline/<name>/summary.json`
   - `impact` = `upgrades/<id>/03-impact.md`
   Parallel Maven builds share `~/.m2`. On a corrupted-artifact error during concurrent downloads,
   re-run that repo alone before calling it red.
5. **Re-scan (if the Snyk CLI is available):** run phase 1 step 3 into `upgrades/<id>/snyk-after/` and parse
   it. Add "Snyk findings before → after" to the report. This proves the targeted issues are gone and
   that nothing new came in.
6. **Assemble `05-verification.md`:** the Result table, a Failures section per red repo (regression /
   pre-existing / environmental / unknown), and the Verdict.
7. STATUS phase 5 → ✅ if every repo is green, or only pre-existing/environmental failures remain
   (say which). Otherwise ⛔.
   - ▶ Next step when green: "review the diff (`git -C workspace/<name> diff`), then `/dep-publish <id>`".
   - ▶ Next step when red: the fix for each regression. Add it as new plan steps (needs
     re-approval), then `/dep-apply` → `/dep-verify` again.
8. Never re-run with tests skipped to manufacture a green result.
