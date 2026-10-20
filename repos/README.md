# repos/: the repositories this project fixes

[`repos.txt`](repos.txt) lists the repos to fix. Each one is cloned into `repos/<name>/`, and **that clone is where the
code changes happen**, on one branch per workflow. Only `repos.txt` and this README are committed; the clones are
git-ignored, and there are no submodules. Commands are shown for macOS; on Windows use `py -3 -I toolkit\scripts\repos.py`
([translation table](../README.md#windows)).

```text
repos/
├── repos.txt            the list (you edit this)
└── inventory-service/   the clone: branches main, deps/wf-001, deps/wf-002 … (one per workflow)
~/repos/inventory-service/   your own checkout, if you have one: never touched
```

The changes reach the repo's GitHub only as a pull request from `deps/wf-NNN` (`/dep-publish`), never on `main`.
To see a workflow's changes: `git -C repos/<name> diff main...deps/wf-NNN`, or open `repos/<name>/` in VS Code.

## Add a repo

```bash
python3 -I toolkit/scripts/repos.py add https://github.com/my-org/orders-service.git path=api
python3 -I toolkit/scripts/repos.py add ~/repos/orders-service      # a checkout you have: its URL is looked up
```

Or `/dep-run <git-url>` in chat. Either way it's one line in `repos.txt`:

```text
<name>             <git-url>                                           [options]
inventory-service  https://github.com/acme-corp/inventory-service.git  path=backend  smoke=true
orders-service     git@github.com:my-org/orders-service.git            branch=develop
```

| Part | Meaning |
|------|---------|
| `name` | Clone folder `repos/<name>/` and the name you use in commands. If the repo is already in `repos/`, use that folder's exact name |
| `git-url` | What you'd give `git clone`, HTTPS or SSH, whichever already works for you. Private repos need your account to have access |
| `branch=` | The repo's main branch, if it isn't `main`. Workflow branches start from it |
| `path=` | Sub-folder with `pom.xml` / `build.gradle`, if not the repo root |
| `smoke=true` | Spring Boot apps: also start the app during verification, to catch startup-only failures |
| `build=` | Your own build command, e.g. `build="./mvnw -B -Pci verify"` (default: `./mvnw -B clean verify` or `./gradlew clean build`) |

## Clone, and what the messages mean

```bash
python3 -I toolkit/scripts/repos.py clone                  # every repo in the list (or: clone orders-service)
python3 -I toolkit/scripts/repos.py status                 # branch, commit, uncommitted files
```

`/dep-run` clones as its first step, so you rarely run this yourself. Inside a workflow
(`repos.py --workflow <id> clone`) each clone is also put on that workflow's branch.

| Message | Meaning |
|---------|---------|
| `cloned into repos/<name>` / `up to date` | Done (an existing clone on main is fetched and fast-forwarded) |
| `created deps/wf-002 from origin/main @ a1b2c3d` | New workflow: a fresh branch from the **latest** main |
| `switched back to existing deps/wf-001` / `on deps/wf-001` | Resuming a workflow: its earlier work is still there |
| `kept as is - on deps/wf-NNN` / `kept as is - N uncommitted file(s)` | A workflow is using the clone, or it has unpublished changes: left alone |
| `BLOCKED: … unpublished changes of workflow wf-001` | Another workflow's changes aren't published. Nothing was switched: publish or abandon that one first |
| `NO 'main' BRANCH` | Add `branch=<name>` to the repo's line |
| `CLONE FAILED: …` | Wrong URL or no access: try `git clone <url>` yourself |
| `WARNING: path=… does not exist` | The `path=` option is wrong |

**One workflow at a time per repo:** a clone can be on only one branch. Workflows on different repos never collide.
When a workflow is finished, `repos.py --workflow <id> release` puts the clone back on main (the branch is kept).
To stop working on a repo: delete its line, then the `repos/<name>/` folder once nothing in it is needed.

## Monorepos (one git repo, several projects)

List a monorepo **once**: one line, one clone, one branch and one PR per workflow. It works when the **root
`pom.xml` lists the projects as `<module>`s**. Check: `grep -c '<module>' ~/repos/my-monorepo/pom.xml` (Windows:
`(Select-String -Path $HOME\repos\my-monorepo\pom.xml -Pattern '<module>').Count`) prints a number above 0.

```bash
python3 -I toolkit/scripts/repos.py add https://github.com/my-org/my-monorepo.git my-monorepo   # no path=, no smoke=true
python3 -I toolkit/scripts/repos.py clone my-monorepo
```

Then `/dep-run my-monorepo`. Every step covers every project: the scan reads every `pom.xml` (each finding names its
project), the inventory reads every pom and module tree, the impact search covers the whole repo, and verify builds
the whole reactor and counts **every module's** tests. To run that build by hand:
`bash toolkit/scripts/verify-repo.sh repos/my-monorepo /tmp/verify-my-monorepo` (writes `summary.json` and `build.log`).

- **No `smoke=true`:** the app-start check looks for the jar in the root `target/`, but each app's jar is in its module.
- **No root `pom.xml`** (each project builds separately): not supported yet. One line names one build folder, and
  listing the repo several times would clone it several times and clash at publish. Ask for multi-folder
  support (`path=a,b,c`).
