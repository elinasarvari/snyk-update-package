# Phase 5 — Publish: commit, push, open PRs

**Writes to the target repos' remotes.** Run only when the user explicitly asks. They may limit it to some repos.

## Gate

- Phase 4 is ✅ for each repo being published. A repo with regressions isn't published unless the user
  says so explicitly for that repo; record their words in STATUS "Decisions".
- `gh auth status` succeeds (GitHub CLI installed and logged in). If not, stop and tell the user:
  `brew install gh && gh auth login`. For non-GitHub remotes (Bitbucket, GitLab), push the branch and
  give the user the "create PR" URL instead.

## Steps (per repo)

1. In the clone `repos/<name>/` on `deps/<id>`, review `git status`. Stage **only** the files listed in
   `03-apply-log.md`; never `target/`, `build/`, or stray files.
2. **Commit:** `deps: <one-line summary>` (e.g. `deps: Spring Boot 3.3.2 -> 4.1.1, Camel 4.8.5 -> 4.22.1`).
   In the body, list the Snyk issue ids/CVEs fixed and the meta-repo workflow id.
3. **Push:** `git push -u origin deps/<id>`. Never force-push, never push to the default branch.
4. **Open the PR** against the branch the repo was on before `/dep-apply` (STATUS "Repos" start commit):
   `gh pr create --base <start-branch> --head deps/<id> --title "<commit summary>" --body-file <file>`.
   Build the body from the docs, written to `workflows/<id>/publish/<name>-pr.md`:
   - summary of the upgrade, and the Snyk issues fixed (from 01 and the plan's Versions)
   - risk and breaking changes handled (from the plan's Impact)
   - steps applied and deviations (from 03)
   - verification: tests before/after, smoke boot, Snyk before/after (from 04)
   - a "Review focus" list: behavioural changes with no compile error (from the plan's Impact)
   - **"Known remaining issues"**: the Out of scope table from 02-plan (what, why, next step), so reviewers see what
     this PR does not fix
5. **Record** in the STATUS "Repos" table: commit SHA and PR URL (the PR body stays in `publish/<name>-pr.md`).
6. `python3 -I toolkit/scripts/workflows.py phase <id> 5 done`, with each PR URL logged via `log`. ▶ Next step: "review/merge the PRs. Afterwards: `python3 -I toolkit/scripts/repos.py --workflow <id> release`
   puts the clones back on main (the branch is kept)".
   Then `python3 -I toolkit/scripts/workflows.py save <id>` pushes the workflow's records to this project's repository.
