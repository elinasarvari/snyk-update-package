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
   **Research once:** if several items share the same lever jump and `workflows/_research/` has no file for it yet,
   run the first analyst alone, so it writes the cache file. Then run the rest in parallel: they reuse the file
   instead of fetching the same migration guides again.
4. **Assemble** `03-impact.md`: the Summary table from each report's `SUMMARY |` line, then each report
   under "Per package" (link the analysis file). If two analysts disagree (e.g. on the Camel version),
   settle it from the cited sources, or record it as an open question in STATUS.

## Plan (`03-plan.md`)

5. Copy `toolkit/templates/03-plan.md`. Plan from 03-impact **only**; do no new research.
   - **Strategy:** one jump or stepping stones, **only at versions Snyk names or the user gives** (e.g. Snyk's fix on
     the current major, then the target), each a separately green checkpoint. Never add a "latest" version of your own.
     Explain the choice. Any version not from Snyk goes in *Versions not from Snyk* with its reason
     (`toolkit/WORKFLOW.md`, "Target versions are Snyk's, exactly").
   - **Order** the steps per repo so each compiles: pom/BOM bumps → coupled deps → renamed starters/artifacts
     → code package moves → config keys → test changes.
   - **Remediation order, for every in-scope package and each of its detailed paths** (`01-snyk-findings.md` §3):
     1. **upgrade** the dependency that brings it in, or the parent/BOM that sets that dependency's version;
     2. no upgrade path but a fixed version exists → **override** the vulnerable package to it (`<dependencyManagement>`
        in Maven, `constraints` in Gradle), after checking the introducing library works with that version
        (its release notes, or that its tests still pass at verify);
     3. no fixed version on that path → check whether the **lowest newer version of the introducing library** that
        drops or replaces the package exists (cite its release notes or pom), or whether it can be **excluded** (`<exclusions>`) because nothing in the repo uses it
        (`git grep` for its packages/classes);
     4. only when 1–3 are exhausted does the path go to **Out of scope**, saying what was tried.
   - **Vulnerable modules, itemized (do it by script, not by hand):**
     1. `python3 -I toolkit/scripts/parse-snyk.py "workflows/<id>/snyk/*.json" --into-plan workflows/<id>/03-plan.md`
        puts every module into the plan: facts, issues, paths, and a Decision table where **Fix chosen**, **Target
        version** (Snyk's version, exactly) and **Verified by** are already filled in from Snyk's data. Don't change a
        pre-filled target. A re-run keeps decisions you filled in.
     2. Read `snyk/module-index.md` (one line per module), **not** the full entries. Open a module's full entry only
        if its status is `needs an override`, `partly fixable` or `no fix`, or its fix isn't what the plan does.
     3. Fill in the open fields **for groups of modules at once**:
        `python3 -I toolkit/scripts/script-helpers.py plan-decide workflows/<id>/03-plan.md <which> "<Field>=<value>" ...`
        where `<which>` is `all`, numbers/ranges (`1-12,15`) or `status:<status>`. Fields: `In scope?`, `Fix chosen`,
        `Target version`, `Plan step(s)`, `Compatibility / risk`, `Verified by`. Example:
        `plan-decide … 1-12 "Plan step(s)=Step 1" "Compatibility / risk=see 03-impact.md: Spring Boot 3.5"`.
     4. **`python3 -I toolkit/scripts/script-helpers.py plan-check workflows/<id>/03-plan.md` must say "all N
        modules decided"** before the plan goes to the user. It lists every module that still has a gap.
     Out-of-scope modules: `In scope?=no, see Out of scope #n`, and a row in *Out of scope*.
   - **Path coverage table:** for each in-scope package, list each path and the plan step that fixes it, or "out of
     scope". A package counts as fixed only when all its paths are.
   - Give exact diffs for pom/config edits, and precise descriptions with `path:line` for code edits.
     Paths are relative to the repo folder.
   - Each step's "Verify after" is `compile`, `test` or `smoke`.
6. `python3 -I toolkit/scripts/workflows.py phase <id> 3 waiting --note "plan needs approval"`. ▶ Next step: "review `03-plan.md`; reply *approve* (or ask
   for changes), then `/dep-apply <id>`".
7. **Never tick the approval box yourself.** When the user approves in chat, tick it, quote their words,
   add the date, copy the entry into STATUS "Decisions", and `python3 -I toolkit/scripts/workflows.py log <id> "Plan approved: <user's words>"`.
   Then `python3 -I toolkit/scripts/workflows.py phase <id> 3 done`.
