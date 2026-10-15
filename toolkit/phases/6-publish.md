# Phase 6 — Publish: commit, push, open PRs

**Writes to the target repos' remotes.** Run only when the user explicitly asks. They may limit it to some repos.

## Gate

- Phase 5 is ✅ for each repo being published. A repo with regressions isn't published unless the user
  says so explicitly for that repo; record their words in STATUS "Decisions".
- `gh auth status` succeeds (GitHub CLI installed and logged in). If not, stop and tell the user:
  `brew install gh && gh auth login`. For non-GitHub remotes (Bitbucket, GitLab), push the branch and
  give the user the "create PR" URL instead.

## Steps (per repo)

1. In the repo folder (`repo_dir`) on `deps/<id>`, review `git status`. Stage **only** the files listed in
   `04-apply-log.md`; never `target/`, `build/`, or stray files.
2. **Commit:** `deps: <one-line summary>` (e.g. `deps: Spring Boot 3.3.2 -> 4.1.1, Camel 4.8.5 -> 4.22.1`).
   In the body, list the Snyk issue ids/CVEs fixed and the meta-repo workflow id.
3. **Push:** `git push -u origin deps/<id>`. Never force-push, never push to the default branch.
4. **Open the PR** against the branch the repo was on before `/dep-apply` (STATUS "Repos" start commit):
   `gh pr create --base <start-branch> --head deps/<id> --title "<commit summary>" --body-file <file>`.
   Build the body from the docs, written to `workflows/<id>/publish/<name>-pr.md`:
   - summary of the upgrade, and the Snyk issues fixed (from 01/02)
   - risk and breaking changes handled (from 03-impact)
   - steps applied and deviations (from 04)
   - verification: tests before/after, smoke boot, Snyk before/after (from 05)
   - a "Review focus" list: behavioural changes with no compile error (from 03-impact)
5. **Record** in `06-publish.md` and in the STATUS "Repos" PR column: commit SHA, PR URL, state.
6. `python3 -I toolkit/scripts/workflows.py phase <id> 6 done`, with each PR URL logged via `log`. ▶ Next step: "review/merge the PRs. After merge, `/dep-clone` refreshes URL clones;
   for local folders, switch back (`git switch <start-branch> && git pull`) yourself".
   Offer to commit this upgrade's docs in the meta repo too; only do it if the user says yes.
