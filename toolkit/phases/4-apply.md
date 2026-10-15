# Phase 4 — Apply

**Edits the clones under `repos/`, on the workflow's branch.** Run only when the user explicitly asks for this phase.

## Gate — stop and say why if any of these fails

- `03-plan.md` contains `- [x] Approved by user` with the user's words and a date.
- Each clone (`repos.py --workflow <id> status`) has 0 uncommitted files, ignoring `target/` and `build/`,
  and is on its start branch or on `deps/<id>`. Otherwise show the status and ask. Never stash,
  reset or discard for the user.
- A baseline exists for each repo (phase 2 step 8). If one is missing, run it first.

## Steps

1. Create `04-apply-log.md` from the template. `python3 -I toolkit/scripts/workflows.py phase <id> 4 running`.
2. **Delegate each repo to the `upgrade-applier` subagent** (role: `toolkit/roles/upgrade-applier.md`).
   First run `python3 -I toolkit/scripts/repos.py --workflow <id> clone`: every clone must report it's on `deps/<id>` (not BLOCKED).
   Pass `repo` (= `repo_dir`, the clone), `build_dir`, `plan`, `log` (all absolute) and
   `branch = deps/<workflow-id>`. Run them in parallel when possible. If the user named repos, do only those.
3. **Collect** the results into `04-apply-log.md`, one section per repo: steps ✅/⛔, deviations, final
   `git diff --stat`. Repeat every deviation from the plan at the top.
4. `python3 -I toolkit/scripts/workflows.py phase <id> 4 done` if all repos finished, else `blocked --note "<repo, step>"`.
   ▶ Next step: `/dep-verify <id>`, or the decision needed to unblock.
5. Remind the user that the changes are uncommitted on `deps/<id>` in each clone under `repos/`, and that only
   `/dep-publish` commits, pushes and opens PRs.
