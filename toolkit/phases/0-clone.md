# Phase 0 — Clone the repos and put them on the workflow's branch

Run by `/dep-run` (step 0) and by `/dep-scan` when a repo isn't cloned yet. There's no separate command: by hand it's
`repos.py add` / `repos.py clone` (`repos/README.md`).

Every repo is cloned into `repos/<name>/`. **All code changes happen in that clone**, on the workflow's
own branch `deps/<id>`, created from the latest main. The user's own checkouts elsewhere are never
touched. This phase never discards, resets or stashes anything.

## Input

- one or more git URLs, or local checkouts (only used to find their URL), optionally with `name`, `path=`,
  `branch=`, `smoke=true` → add them, then clone;
- repo names → clone/refresh just those;
- nothing → every repo in the list (or in the workflow's own `repos.txt`).

## Steps

1. **Add new repos:** `python3 -I toolkit/scripts/repos.py add <git-url | local checkout> [name] [path=<subdir>] [smoke=true]`.
   - A local checkout is turned into its `origin` URL. The list only ever holds URLs.
   - If you don't know `path`, clone first (step 2), look for the folder holding `pom.xml`/`build.gradle`, then
     fix the line in `repos/repos.txt`. If there are several build roots, ask whether to add one entry each.
   - If the repo's main branch isn't called `main`, add `branch=<name>`.
2. **Clone, and in a workflow switch to its branch:**
   - Outside a workflow: `python3 -I toolkit/scripts/repos.py clone [names...]`. This clones missing repos and
     fast-forwards clean clones that are on main.
   - In a workflow: `python3 -I toolkit/scripts/repos.py --workflow <id> clone [names...]`. This also puts
     each clone on `deps/<id>`:
     - `created deps/<id> from origin/main` for a new workflow;
     - `switched back to existing deps/<id>` or `on deps/<id>` when resuming;
     - **`BLOCKED`** if the clone holds uncommitted changes of another workflow. Nothing is switched. Tell the
       user which workflow; it has to be published or abandoned first.
     - `NO 'main' BRANCH` → ask the user for the repo's main branch and add `branch=<name>`.
   - A clone failure is usually authentication (private repo: the user's git credentials or SSH key) or a wrong
     URL. Report it and carry on with the rest.
3. **Check:** `python3 -I toolkit/scripts/repos.py --workflow <id> status`. Every repo must say `yes` in the
   `ON deps/<id>?` column. Confirm each `build_dir` from `repos.py list` contains `pom.xml` or `build.gradle*`.
4. **If inside a workflow:** record each repo's clone, branch and start commit in the STATUS "Repos" table, then
   `python3 -I toolkit/scripts/workflows.py phase <id> 0 done`.
5. Report the status table and anything the user must act on, then continue with the scan.
