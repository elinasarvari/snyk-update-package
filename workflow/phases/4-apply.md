# Phase 4 — Apply

**Edits the repo folders, including your own local checkouts.** Run only when the user explicitly asks for this phase.

## Gate — stop and say why if any of these fails

- `03-plan.md` contains `- [x] Approved by user` with the user's words and a date.
- Each repo folder (`repos.py status`) has 0 uncommitted files, ignoring `target/` and `build/`,
  and is on its start branch or on `deps/<id>`. Otherwise show the status and ask. Never stash,
  reset or discard for the user.
- A baseline exists for each repo (phase 2 step 8). If one is missing, run it first.

## Steps

1. Create `04-apply-log.md` from the template. STATUS phase 4 → 🟡.
2. **Delegate each repo to the `upgrade-applier` subagent** (role: `workflow/roles/upgrade-applier.md`).
   **Local folders (`kind` = local) are the user's own checkout.** Before starting, tell the user which
   folders will be switched to `deps/<id>`, and that `git switch <start-branch>` takes them back.
   Pass `repo` (= `repo_dir`), `build_dir`, `plan`, `log` (all absolute) and
   `branch = deps/<upgrade-id>`. Run them in parallel when possible. If the user named repos, do only those.
3. **Collect** the results into `04-apply-log.md`, one section per repo: steps ✅/⛔, deviations, final
   `git diff --stat`. Repeat every deviation from the plan at the top.
4. STATUS phase 4 → ✅ if all repos finished, else ⛔ with the step where it stopped.
   ▶ Next step: `/dep-verify <id>`, or the decision needed to unblock.
5. Remind the user that the changes are uncommitted on `deps/<id>` in each repo folder (for local
   folders, that is their own checkout, now on that branch), and that only
   `/dep-publish` commits, pushes and opens PRs.
