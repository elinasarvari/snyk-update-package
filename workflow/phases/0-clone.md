# Phase 0 — Clone target repos

Get every target repo into `workspace/<name>/` and current. Only clones or fast-forwards. It never
discards, resets or switches branches.

## Input

- one or more git URLs (optionally with `name`, `path=`, `branch=`, `smoke=true`) → add them, then clone;
- repo names → clone/refresh just those;
- nothing → clone/refresh everything in the manifest.

## Steps

1. **Add new repos:** for each URL, run
   `python3 -I workflow/scripts/repos.py add <git-url> [name] [path=<subdir>] [smoke=true]`.
   If you don't know `path`, clone first (step 2), find the folder holding `pom.xml`/`build.gradle`,
   and fix the line in `repos.txt`. If there are several build roots, ask whether to add one entry each.
2. **Clone / refresh:** `python3 -I workflow/scripts/repos.py clone [names...]`. Per repo it:
   - clones it if missing;
   - fast-forwards it if clean and on its default (or configured) branch;
   - **keeps it as is** if it has uncommitted changes or is on another branch, e.g. `deps/<id>` from
     an upgrade in progress. Report these to the user; don't "fix" them.
   A clone failure is usually authentication (private repo: the user's git credentials/SSH key) or
   a wrong URL. Report it and carry on with the rest.
3. **Check:** `python3 -I workflow/scripts/repos.py status`. Then, for each repo, check that
   `build_dir` from `repos.py list` contains `pom.xml` or `build.gradle*`.
4. **If inside an upgrade:** record each repo's start commit in the STATUS "Repos" table and set phase 0 → ✅.
5. Reply with the status table and **▶ Next step** (usually `/dep-scan`).
