# /dep-run: run the whole workflow for one repo, stop only where the user is needed

Input: **one repo**, as its name in `repos/repos.txt`, a local folder, or a git URL. Optionally also a
workflow id to resume, and/or the user's reply to the last stop (e.g. "approve", "scope: high+",
"proceed from 3.3.2").

Run the steps below **in order without asking**, following each step's own file in `toolkit/phases/`.
Stop **only** at the stop points listed. Each step is tracked with `workflows.py` as described in
`toolkit/WORKFLOW.md` ("Tracking every run"). `W` below means `python3 -I toolkit/scripts/workflows.py`;
`R` means `python3 -I toolkit/scripts/repos.py`.

## A. Pick the repo and the run

1. **Repo:** `R ensure "<input>"` prints the repo's list name. It adds the repo first if it's new
   (folder or URL). It fails if a bare name isn't in the list: then ask for a folder or URL and stop.
2. **Run:**
   - the user gave a workflow id → `W resolve <id>` and resume it;
   - else `W find-open --repo <name>` → resume that run if it prints one;
   - else start one: `W new <name> --repo <name> --title "Snyk fixes: <name>" --source "/dep-run <input>"`.
   Tell the user **"Workflow N (`wf-NNN`)", new or resumed**, before doing anything else.
3. **Show where it stands:** `W show <id>`. Continue from the first step that isn't done or skipped.
4. **The user's reply to a previous stop** (if any) is applied first: record it with `W log <id> "<their words>"`.
   - scope → write it into `01-snyk-findings.md` "Scope decision";
   - approval → tick `03-plan.md` and quote it;
   - a decision → add it to STATUS "Decisions".
   Then mark the blocked step done and carry on.

## B. Steps, and when to stop

| Step | Do | Continue automatically when | **STOP** (set ▶ Next step, then end the run) when |
|------|----|-----------------------------|---------------------------------------------------|
| 0 Clone | `phases/0-clone.md` | the repo folder exists | the folder is missing, the clone failed, or the repo has uncommitted files (they'd block apply later; ask the user to commit them) |
| 1 Scan | `phases/1-scan.md` | findings are summarised. **Default scope = every finding with a fix**; record it as "autopilot default, change it by replying `scope: ...`" | the Snyk CLI is missing or not logged in, and no report was given: tell the user the install/login commands, or to pass a Snyk JSON (`/dep-run <repo> <file>`). **Zero findings:** close the run as nothing to do (steps 2–6 `skipped --note "no findings"`) |
| 2 Inventory | `phases/2-inventory.md` | no discrepancy; baseline taken | a discrepancy needs a decision, a target version doesn't exist, or the **baseline build is red** (an upgrade can't be verified on top of a broken build) |
| 3 Analyze + plan | `phases/3-analyze.md` | — | **always stop after writing `03-plan.md`**: `W phase <id> 3 waiting`. Ask the user to review it and reply **"approve"**, or to say what to change |
| 4 Apply | `phases/4-apply.md` | approval is recorded (from the user's words, never inferred) | the gate fails, or a step goes red after two fix rounds |
| 5 Verify | `phases/5-verify.md` | — | **always stop afterwards.** Green → the next step is `/dep-publish <id>`. Red → the proposed fixes; replying "approve fixes" adds them as plan steps and the run continues with apply → verify |
| 6 Publish | **never run it from here** | — | `/dep-publish <id>` is the user's own command: it pushes and opens PRs |

Rules while running:
- **Never** tick the approval box without the user's explicit words in *this* conversation.
- **Never** publish, push, commit, force anything, or touch other repos. Scope is the run's own `repos.txt`.
- **Local folders are the user's checkout:** before step 4 switches it to `deps/<id>`, say so in the stop
  message at step 3. ("Approving will switch `~/repos/x` to branch `deps/wf-NNN`.")
- A failing script is a stop, not something to work around. Show its output and the fix.

## C. Every run ends with this reply

```text
Workflow N (wf-NNN) · <repo> · <folder>

Done this run:     0 Clone ✅ · 1 Scan ✅ (12 packages, 3 changes) · 2 Inventory ✅ · 3 Plan ⏸
Stopped because:   <the stop reason, one line>

▶ Next step:       <exactly what the user does, e.g. read workflows/wf-NNN-x/03-plan.md, then reply "approve">
                   <and the command to continue, e.g. /dep-run <repo>>
```

Before replying, run `W next <id> "<the same next step>"` so `STATUS.md` and `workflows/INDEX.md` show the same thing.
Link the documents produced in this run, and keep the headline findings to a few bullets.
