# Phase 0 — Add and check target repos

Make sure every repo in the list has a usable **repo folder**:
- a **local folder**, which is the user's own checkout and is used in place; or
- a **git URL**, which is cloned into `repos/<name>/`.

This phase never discards, resets, pulls into a local folder, or switches branches.

## Input

- one or more local folders or git URLs (optionally with `name`, `path=`, `branch=`, `smoke=true`) → add them, then check;
- repo names → check/refresh just those;
- nothing → check/refresh everything in the list.

## Steps

1. **Add new repos:** `python3 -I workflow/scripts/repos.py add <local-folder | git-url> [name] [path=<subdir>] [smoke=true]`.
   - A local folder must start with `/`, `~`, `./` or `../` and contain `.git`. It's stored as `~/...` when under the home folder.
   - If the user has the repo checked out already, **prefer the local folder**. Only use a URL for repos they don't have.
   - If you don't know `path`, look for the folder holding `pom.xml`/`build.gradle` and fix the line in
     `repos/repos.txt`. If there are several build roots, ask whether to add one entry each.
2. **Check / refresh:** `python3 -I workflow/scripts/repos.py clone [names...]`.
   - **Local folders:** only checked. It fetches remote refs (files untouched) and reports the branch, uncommitted
     files, commits behind `origin`, and whether it's on the expected `branch=`. It never pulls or switches.
     Pass these notes on to the user. Pulling or switching is their decision.
   - **URLs:**
     - cloned if missing;
     - fast-forwarded if clean and on the default (or configured) branch;
     - **kept as is** if dirty or on another branch, e.g. `deps/<id>`.
   - Failures: a wrong local path, a wrong URL, or no access (private repo: the user's git credentials or SSH key).
     Report each and carry on with the rest.
3. **Check:** `python3 -I workflow/scripts/repos.py status`. The `TYPE` column is `local` or `clone`, and `FOLDER`
   is where the code is. Confirm each `build_dir` from `repos.py list` contains `pom.xml` or `build.gradle*`.
4. **If inside an upgrade:** record each repo's type, folder, branch and start commit in the STATUS "Repos" table,
   then set phase 0 → ✅.
5. Reply with the status table, any notes the user must act on (wrong branch, behind origin, uncommitted
   files), and **▶ Next step** (usually `/dep-scan`).
