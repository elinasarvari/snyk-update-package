# /dep-run: run the whole workflow for one repo, stop only where the user is needed

Input: **one repo**, as its name in `repos/repos.txt`, its git URL, or a local checkout of it (only used to
find the URL; the work always happens in the clone under `repos/`). Optionally also a
workflow id to resume, and/or the user's reply to the last stop (e.g. "approve", "scope: high+",
"proceed from 3.3.2").

**`/dep-run status`** (or no argument): show where every workflow stands and stop. Run
`python3 -I toolkit/scripts/workflows.py list` and `python3 -I toolkit/scripts/repos.py status`, then for each open run
its ▶ next step (`workflows.py show <id>`). Change nothing.

Run the steps below **in order without asking**, following each step's own file in `toolkit/phases/`.
Stop **only** at the stop points listed. Each step is tracked with `workflows.py` as described in
`toolkit/WORKFLOW.md` ("Tracking every run"). `W` below means `python3 -I toolkit/scripts/workflows.py`;
`R` means `python3 -I toolkit/scripts/repos.py`. On Windows: `py -3 -I toolkit\scripts\workflows.py` / `repos.py`, and
`.ps1` instead of `.sh` scripts (see "Running the commands on Windows" in `toolkit/WORKFLOW.md`).

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
   - approval → tick `02-plan.md` and quote it;
   - a decision → add it to STATUS "Decisions".
   Then mark the blocked step done and carry on.

## B. Steps, and when to stop

| Step | Do | Continue automatically when | **STOP** (set ▶ Next step, then end the run) when |
|------|----|-----------------------------|---------------------------------------------------|
| 0 Clone | `phases/0-clone.md`: `R --workflow <id> clone` | the clone is on `deps/<id>` | the clone failed, there's no main branch, or the clone is BLOCKED by another workflow's unpublished changes (say which workflow) |
| 1 Scan | `phases/1-scan.md` (not logged in → `LOGIN.md`, then scan again) | findings are summarised. **Default scope = every finding with a fix**; record it as "autopilot default, change it by replying `scope: ...`" | the Snyk CLI is missing, or the login (`LOGIN.md`) didn't complete, and no report was given: tell the user how to get the CLI / retry the login, or to pass a Snyk JSON (`/dep-run <repo> <file>`). **Zero findings:** close the run as nothing to do (steps 2–5 `skipped --note "no findings"`) |
| 2 Plan | `phases/2-plan.md` | — | a discrepancy needs a decision, a target version doesn't exist, or the **baseline build is red** (an upgrade can't be verified on top of a broken build). Otherwise **always stop after writing `02-plan.md`** (and only once `plan-check` says every module is decided): `W phase <id> 2 waiting`. Ask the user to review it and reply **"approve"**, or to say what to change |
| 3 Apply | `phases/3-apply.md` | approval is recorded (from the user's words, never inferred) | the gate fails, or a step goes red after two fix rounds |
| 4 Verify | `phases/4-verify.md` | — | **always stop afterwards.** Green → the next step is `/dep-publish <id>`. Red → the proposed fixes; replying "approve fixes" adds them as plan steps and the run continues with apply → verify |
| 5 Publish | **never run it from here** (`phases/5-publish.md` belongs to `/dep-publish`) | — | `/dep-publish <id>` is the user's own command: it pushes and opens PRs |

Rules while running:
- **Never** tick the approval box without the user's explicit words in *this* conversation.
- **The clone gets code changes only**: every document, log and report goes to `workflows/<id>/`.
- **Never** publish, push, commit, force anything, or touch other repos. Scope is the run's own `repos.txt`.
- **All changes happen in the clone `repos/<name>/` on `deps/<id>`**, never in the user's own checkout. Say where
  in the stop message at step 2 ("Approving will change `repos/<name>/` on branch `deps/wf-NNN`.")
- A failing script is a stop, not something to work around. Show its output and the fix.

## C. Every run ends with this reply

```text
Workflow N (wf-NNN) · <repo> · <folder>

Done this run:     0 Clone ✅ · 1 Scan ✅ (12 packages, 3 changes) · 2 Plan ⏸
Stopped because:   <the stop reason, one line>

▶ Next step:       <exactly what the user does, e.g. read workflows/wf-NNN-x/02-plan.md, then reply "approve">
                   <and the command to continue, e.g. /dep-run <repo>>
```

Before replying, run `W next <id> "<the same next step>"` so `STATUS.md` and `workflows/INDEX.md` show the same thing,
then `W save <id>` so the records are pushed (`toolkit/SAVE.md`; if it refuses because the repo is public, say so).
Link the documents produced in this run, and keep the headline findings to a few bullets.
