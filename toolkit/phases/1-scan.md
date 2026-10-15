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
   - Exit 127/126 means the CLI is missing or not logged in. Stop and give the user the commands
     the script printed. Don't install or log in for them.
   - Per-repo results are in `snyk/scan-index.tsv`: 0 clean, 1 findings, 2 failed, 3 no supported
     project. A failed repo is reported, never silently dropped.
4. **Summarise all findings:**
   `python3 -I toolkit/scripts/parse-snyk.py workflows/<id>/snyk/*.json --md workflows/<id>/snyk/findings.md --json workflows/<id>/snyk/findings.json --csv workflows/<id>/snyk/findings.csv`
   For pasted output, build the same tables by hand using the columns in `templates/01-snyk-findings.md`.
   A supplied JSON file is first copied into `workflows/<id>/snyk/`.
5. **Write `01-snyk-findings.md`** from the template: scan summary, table 1 (every flagged package,
   one row per `package@version`), table 2 (changes grouped by the direct dependency to edit). Then
   triage each table-2 row into a bucket:
   - **platform:** managed by a parent/BOM already in the pom (Spring Boot, Spring Cloud, Camel BOM,
     Jackson BOM...). Many rows collapse into **one** lever bump; name the lever.
   - **direct:** a version declared in the pom; bump it.
   - **transitive-pin:** no upgrade path through its parent. Needs a `<dependencyManagement>`
     override, which is risky; call it out.
   - **no-fix / license:** nothing to upgrade to; needs a decision (accept, replace, or ignore with a reason).
6. **Close out:** `python3 -I toolkit/scripts/workflows.py phase <id> 1 done`, then `python3 -I toolkit/scripts/workflows.py next <id> "..."`. ▶ Next step: "pick the scope (`all`, a severity floor such as
   `high+`, or specific rows), then `/dep-inventory <id>`". Reply with the severity totals, the
   triaged table 2, and the next step.
