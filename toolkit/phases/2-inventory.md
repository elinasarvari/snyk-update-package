# Phase 2 — Inventory

Turn the chosen upgrades into a verified list: package, current version, target version, how each
version is set in the pom, and what else moves with it. Then take a **baseline** build. Read-only.

## Input

- an workflow id whose `01-snyk-findings.md` has a **Scope decision** → use the rows in scope; or
- a manual list `group:artifact current->target, ...` → create the workflow folder as in phase 1
  step 1. Then `python3 -I toolkit/scripts/workflows.py phase <id> 1 skipped --note "manual request"`.

## Steps

1. Copy `toolkit/templates/02-inventory.md` → `workflows/<id>/02-inventory.md`. `python3 -I toolkit/scripts/workflows.py phase <id> 2 running`.
2. **Requested changes:** one row per in-scope change, with the Snyk issue ids/CVEs it fixes.
   Confirm each target **exists** on Maven Central
   (`https://repo1.maven.org/maven2/<group/as/path>/<artifact>/maven-metadata.xml`).
   - No target given → look up the latest patch of the fixed line and mark it `proposed`.
   - A target version that doesn't exist is a blocker.
3. **Repos:** take them from the manifest (`repos.py list`). Snyk projects that aren't in the manifest go
   under Discrepancies, with the suggestion to `/dep-clone` them.
4. **Facts per repo** (run in parallel for several repos):
   `bash toolkit/scripts/maven-facts.sh <build_dir> workflows/<id>/facts/<name> <artifact substrings...>`
   Gradle: `./gradlew dependencies --configuration runtimeClasspath > workflows/<id>/facts/<name>/dependency-tree.txt`.
5. **Reconcile** using `declared.txt`, `version-props.txt` and `dependency-tree.txt`:
   - the version that actually resolves now;
   - the **lever** that sets it: parent, BOM, property, explicit, or the direct dependency that pulls a
     transitive in.
   Any mismatch with the report (e.g. Snyk says 3.5.16, the repo resolves 3.3.2) goes under
   **Discrepancies**, with the likely reason (other branch, stale scan).
6. **What moves with it:** if the lever is a platform parent/BOM, fetch the target's managed versions
   (e.g. `spring-boot-dependencies-<target>.pom` on Maven Central). List every dependency in the
   tree whose version changes (now → after), with its jump type.
7. **Coupled dependencies:** list every third-party BOM/starter the lever does *not* manage (Camel,
   springdoc, Testcontainers, Lombok, MapStruct, cloud SDKs...). For each: version now, whether it
   supports the target, and the minimum version that does, with evidence. Camel tip: the
   `<spring-boot-version>` property in `org.apache.camel:camel-parent:<v>` on Maven Central tells you
   which Boot version that Camel release is built against.
8. **Baseline:** for each repo, on its current branch, in parallel, run
   `bash toolkit/scripts/verify-repo.sh <build_dir> workflows/<id>/verification/baseline/<name> <verify_args>`.
   Record the results in 02-inventory "Baseline" and the STATUS "Repos" table.
9. **Close out:** `python3 -I toolkit/scripts/workflows.py phase <id> 2 done`, or `blocked --note "<decision needed>"` if a
   discrepancy/blocker needs a user decision.
   ▶ Next step: "resolve discrepancy X" or "`/dep-analyze <id>`".
