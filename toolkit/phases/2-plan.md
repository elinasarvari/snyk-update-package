# Phase 2 — Plan: versions, impact, steps

Turn the in-scope findings into one document, `02-plan.md`: the verified versions and a baseline build (A), the impact
on the code (B), and the steps for the user to approve (C). Read-only: it never edits a repo.

## Input

- a workflow id whose `01-snyk-findings.md` has a **Scope decision** → use the rows in scope; or
- a manual list `group:artifact current->target, ...` → create the workflow folder as in phase 1 step 1. Then
  `python3 -I toolkit/scripts/workflows.py phase <id> 1 skipped --note "manual request"`.

Start: copy `toolkit/templates/02-plan.md` → `workflows/<id>/02-plan.md`, then
`python3 -I toolkit/scripts/workflows.py phase <id> 2 running`.

## A. Versions (section "Versions")

1. **One row per in-scope change**, with the Snyk issue ids it fixes. Confirm each target **exists** on Maven Central
   (`https://repo1.maven.org/maven2/<group/as/path>/<artifact>/maven-metadata.xml`).
   - The target is **exactly Snyk's version** (`snyk/findings.md` §2 *Target*, or the override's version), never a
     newer one you look up. Several Snyk versions for the same dependency → the highest of Snyk's.
   - The lever is a parent/BOM: its target is the release that manages **exactly** Snyk's version (e.g. Snyk:
     `spring-boot-starter-web` → 3.5.17 means `spring-boot-starter-parent` 3.5.17), not the newest release.
   - No target from Snyk and none from the user, or a target that doesn't exist → a blocker: ask, don't guess.
2. **Repos:** from the manifest (`repos.py list`). Snyk projects that aren't in the manifest go under Discrepancies.
3. **Facts per repo** (in parallel for several repos):
   `bash toolkit/scripts/maven-facts.sh <build_dir> workflows/<id>/facts/<name> <artifact substrings...>`
   Gradle: `./gradlew dependencies --configuration runtimeClasspath > workflows/<id>/facts/<name>/dependency-tree.txt`.
4. **Reconcile** with `declared.txt`, `version-props.txt` and `dependency-tree.txt`: the version that actually
   resolves now, and the **lever** that sets it (parent, BOM, property, explicit, or the direct dependency that pulls a
   transitive in). A mismatch with the report (e.g. Snyk says 3.5.16, the repo resolves 3.3.2) goes under
   **Discrepancies**, with the likely reason (other branch, stale scan).
5. **Moves with it:** if the lever is a platform parent/BOM, fetch the target's managed versions from that BOM's POM on
   Maven Central (e.g. `spring-boot-dependencies-<target>.pom`) and list every dependency whose version changes.
6. **Coupled libraries:** every third-party BOM/starter the lever does *not* manage (Camel, springdoc, Testcontainers,
   Lombok, MapStruct, cloud SDKs...): version now, whether it supports the target, and the **lowest** version that does,
   with evidence (the library's compatibility matrix, or its own parent POM: e.g. `<spring-boot-version>` in
   `org.apache.camel:camel-parent:<v>`).
7. **Baseline:** for each repo, on its current branch, in parallel:
   `bash toolkit/scripts/verify-repo.sh <build_dir> workflows/<id>/verification/baseline/<name> <verify_args>`
   (Windows: `powershell -ExecutionPolicy Bypass -File toolkit\scripts\verify-repo.ps1` with the same arguments).
   Record it in the plan's Baseline table and the STATUS "Repos" table.
8. **Stop** (`phase <id> 2 blocked --note "<decision needed>"`) if a discrepancy needs a decision, a target is missing,
   or the **baseline is red**: an upgrade can't be verified on top of a broken build.

## B. Impact (section "Impact")

9. **Work list:** one item per **(lever, repo)**. Many Snyk rows that move with one parent are *one* item. Add one item
   per coupled library that needs its own bump.
10. **Delegate each item to the `dependency-analyst` subagent** (role: `toolkit/roles/dependency-analyst.md`), in
    parallel when the tool allows. Pass, as absolute paths: `package`, `current`, `target`, `repo` = the item's
    `build_dir`, `facts_dir` = `workflows/<id>/facts/<name>`, `report` = `workflows/<id>/analysis/<name>--<artifact>.md`,
    `coupled` = the coupled-library rows for that repo, and the intermediate version lines to cover (e.g. `3.4, 3.5`).
    **Research once:** if several items share a lever jump and `workflows/_research/` has no file for it yet, run the
    first analyst alone so it writes the cache file; the rest then reuse it.
11. **Assemble the Impact section:** the table from each report's `SUMMARY |` line, then a short entry per lever
    linking its report. If two analysts disagree, settle it from the cited sources, or record an open question in STATUS.

## C. Steps (sections "Strategy" to "Out of scope")

12. Plan from the Versions and Impact sections **only**; do no new research.
    - **Strategy:** one jump or stepping stones, **only at versions Snyk names or the user gives** (e.g. Snyk's fix on
      the current major, then the target), each a separately green checkpoint. Never add a "latest" version of your own.
      Explain the choice. Any version not from Snyk goes in *Versions not from Snyk* with its reason
      (`toolkit/WORKFLOW.md`, "Target versions are Snyk's, exactly").
    - **Order** the steps per repo so each compiles: pom/BOM bumps → coupled libraries → renamed starters/artifacts
      → code package moves → config keys → test changes.
    - **Remediation order, for every in-scope package and each of its detailed paths** (`01-snyk-findings.md` §3):
      1. **upgrade** the dependency that brings it in, or the parent/BOM that sets that dependency's version, to Snyk's
         version (the finding's upgrade path, or the report's *remediation* section when the finding has none);
      2. no upgrade path but a fixed version exists → **override** the vulnerable package to it (`<dependencyManagement>`
         in Maven, `constraints` in Gradle), after checking the introducing library works with that version
         (its release notes, or that its tests still pass at verify);
      3. no fixed version on that path → check whether the **lowest newer version of the introducing library** that
         drops or replaces the package exists (cite its release notes or pom), or whether it can be **excluded**
         (`<exclusions>`) because nothing in the repo uses it (`git grep` for its packages/classes);
      4. only when 1–3 are exhausted does the path go to **Out of scope**, saying what was tried.
    - **Vulnerable modules, itemized (do it by script, not by hand):**
      1. `python3 -I toolkit/scripts/parse-snyk.py "workflows/<id>/snyk/*.json" --into-plan workflows/<id>/02-plan.md`
         puts every module into the plan: facts, issues, paths, and a Decision table where **Fix chosen**, **Target
         version** (Snyk's version, exactly) and **Verified by** are already filled in from Snyk's data. Don't change a
         pre-filled target. A re-run keeps decisions you filled in.
      2. Read `snyk/module-index.md` (one line per module), **not** the full entries. Open a module's full entry only
         if its status is `needs an override`, `partly fixable` or `no fix`, or its fix isn't what the plan does.
      3. Fill in the open fields **for groups of modules at once**:
         `python3 -I toolkit/scripts/script-helpers.py plan-decide workflows/<id>/02-plan.md <which> "<Field>=<value>" ...`
         where `<which>` is `all`, numbers/ranges (`1-12,15`) or `status:<status>`. Fields: `In scope?`, `Fix chosen`,
         `Target version`, `Plan step(s)`, `Compatibility / risk`, `Verified by`. Example:
         `plan-decide … 1-12 "Plan step(s)=Step 1" "Compatibility / risk=see Impact: Spring Boot 3.5"`.
      4. **`python3 -I toolkit/scripts/script-helpers.py plan-check workflows/<id>/02-plan.md` must say "all N
         modules decided"** before the plan goes to the user. It lists every module that still has a gap.
      Out-of-scope modules: `In scope?=no, see Out of scope #n`, and a row in *Out of scope*.
    - **Path coverage table:** for each in-scope package, list each path and the plan step that fixes it, or "out of
      scope". A package counts as fixed only when all its paths are.
    - Give exact diffs for pom/config edits, and precise descriptions with `path:line` for code edits.
      Paths are relative to the repo folder. Each step's "Verify after" is `compile`, `test` or `smoke`.
13. `python3 -I toolkit/scripts/workflows.py phase <id> 2 waiting --note "plan needs approval"`. ▶ Next step: "review
    `02-plan.md`; reply *approve* (or ask for changes), then `/dep-apply <id>`".
14. **Never tick the approval box yourself.** When the user approves in chat, tick it, quote their words, add the date,
    copy the entry into STATUS "Decisions", and `python3 -I toolkit/scripts/workflows.py log <id> "Plan approved: <user's words>"`.
    Then `python3 -I toolkit/scripts/workflows.py phase <id> 2 done`.
