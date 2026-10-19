# Phase 1 — Snyk scan: every flagged package

Produce a complete list of **everything** Snyk flags across the target repos, so nothing gets
upgraded in isolation. Read-only.

## Input

- nothing → run the Snyk CLI over every repo folder in the list (step 3);
- one or more Snyk JSON files (`snyk test --all-projects --json`, e.g. from CI) → skip to step 4;
- pasted Snyk output (CLI text, IDE plugin, web-UI issue list) → step 4, by hand.

## Steps

1. **Workflow:** resolve the given id (`python3 -I toolkit/scripts/workflows.py resolve <ref>`), or start a new run with
   `python3 -I toolkit/scripts/workflows.py new <slug> --title "<title>" --source "<Snyk report / manual>"`. The slug comes from the
   main package, or `snyk-sweep`. Tell the user the new id ("This is Workflow N: `wf-NNN`"). Then
   `python3 -I toolkit/scripts/workflows.py phase <id> 1 running`.
2. **Repo folders:** if any repo in the list has no folder yet (URL not cloned, or wrong local path), run phase 0 first.
3. **Scan** (only when no report was supplied):
   `bash toolkit/scripts/snyk-scan.sh workflows/<id>/snyk [--manifest workflows/<id>/repos.txt] [--org=<org>]`
   - The script prints `Using Snyk CLI: <path>`. It takes `$SNYK_CLI` (e.g. the CLI the Snyk VS Code extension
     downloaded), then `snyk` on PATH, then the extension's usual download folders.
   - Exit 127 = no CLI found (suggest `export SNYK_CLI=<path from the extension's settings>`, or installing it);
     126 = not logged in → run the login (`toolkit/LOGIN.md`: browser OAuth2 with the user's SSO, or client credentials),
     then re-run the scan once. If the login doesn't complete, stop. Exit 127: stop and give the user the commands
     the script printed. Don't install anything for them.
   - Per-repo results are in `snyk/scan-index.tsv`: 0 clean, 1 findings, 2 failed, 3 no supported
     project. A failed repo is reported, never silently dropped.
4. **Summarise all findings:**
   `python3 -I toolkit/scripts/parse-snyk.py workflows/<id>/snyk/*.json --md workflows/<id>/snyk/findings.md --json workflows/<id>/snyk/findings.json --csv workflows/<id>/snyk/findings.csv --modules workflows/<id>/snyk/vulnerable-modules.md`
   (`vulnerable-modules.md` is the itemized list of every vulnerable module that the plan in step 3 fills in.)
   For pasted output, build the same tables by hand using the columns in `templates/01-snyk-findings.md`.
   A supplied JSON file is first copied into `workflows/<id>/snyk/`.
5. **Write `01-snyk-findings.md`** from the template, using `snyk/findings.md`: the scan summary, table 1 (every
   flagged package with its **status**), table 2 (the changes, each with its **fix** type), and the **detailed
   paths** (section 3: every path each package arrives by, with the fix for that path). Then triage table 2:
   - **upgrade, platform:** the dependency is managed by a parent/BOM already in the pom. Many rows collapse into
     **one** lever bump; name the lever.
   - **upgrade, direct:** a version declared in the pom; bump it.
   - **override:** Snyk has no upgrade path, but a fixed version exists (or Snyk suggests a pin). The vulnerable package
     itself gets forced to that version (`<dependencyManagement>` / Gradle constraints). Compatibility is checked in step 3.
   - **none:** no remediation on that path. It's examined in step 3 (newer introducing library, exclusion) before
     anything is declared out of scope.
   A package whose status is **needs an override** or **partly fixable** has paths that the obvious upgrade does
   **not** fix: call those out, since they're the ones that get missed.
6. **Close out:** `python3 -I toolkit/scripts/workflows.py phase <id> 1 done`, then `python3 -I toolkit/scripts/workflows.py next <id> "..."`. ▶ Next step: "pick the scope (`all`, a severity floor such as
   `high+`, or specific rows), then `/dep-inventory <id>`". Reply with the severity totals, the
   triaged table 2, and the next step.
