# Phase 3 — Impact analysis and plan

Requires phase 2 ✅. Read-only. Writes `03-impact.md` and `03-plan.md`.

## Impact (`03-impact.md`)

1. Copy `toolkit/templates/03-impact.md`. `python3 -I toolkit/scripts/workflows.py phase <id> 3 running`.
2. **Work list** from `02-inventory.md`: one item per **(lever, repo)**. Many Snyk rows that move with
   the Spring Boot parent are *one* item. Add one item per coupled dependency that needs its own bump
   (e.g. Camel).
3. **Delegate each item to the `dependency-analyst` subagent** (role: `toolkit/roles/dependency-analyst.md`),
   in parallel when the tool allows. Pass these as absolute paths:
   - `package`, `current`, `target`, `repo` = the item's `build_dir`
   - `facts_dir` = `workflows/<id>/facts/<name>`
   - `report` = `workflows/<id>/analysis/<name>--<artifact>.md`
   - `coupled` = the coupled-dependency rows from 02 for that repo
   - the intermediate version lines to cover (e.g. `3.4, 3.5, 4.0, 4.1`)
4. **Assemble** `03-impact.md`: the Summary table from each report's `SUMMARY |` line, then each report
   under "Per package" (link the analysis file). If two analysts disagree (e.g. on the Camel version),
   settle it from the cited sources, or record it as an open question in STATUS.

## Plan (`03-plan.md`)

5. Copy `toolkit/templates/03-plan.md`. Plan from 03-impact **only**; do no new research.
   - **Strategy:** one jump or stepping stones. For a medium/high-risk major jump, default to (a) the
     latest minor of the current major, then (b) the target, each a separately green checkpoint. Explain the choice.
   - **Order** the steps per repo so each compiles: pom/BOM bumps → coupled deps → renamed starters/artifacts
     → code package moves → config keys → test changes.
   - Give exact diffs for pom/config edits, and precise descriptions with `path:line` for code edits.
     Paths are relative to the repo folder.
   - Each step's "Verify after" is `compile`, `test` or `smoke`.
6. `python3 -I toolkit/scripts/workflows.py phase <id> 3 waiting --note "plan needs approval"`. ▶ Next step: "review `03-plan.md`; reply *approve* (or ask
   for changes), then `/dep-apply <id>`".
7. **Never tick the approval box yourself.** When the user approves in chat, tick it, quote their words,
   add the date, copy the entry into STATUS "Decisions", and `python3 -I toolkit/scripts/workflows.py log <id> "Plan approved: <user's words>"`.
   Then `python3 -I toolkit/scripts/workflows.py phase <id> 3 done`.
