# repos/: the repositories this project fixes

`repos/repos.txt` is **the list of repos to fix**. Each one is cloned into `repos/<name>/`, and **that clone is
where the code changes happen**, on one branch per workflow. The tracking (steps, documents, history) lives
in `workflows/`, not in the repo.

```text
snyk-update-package/
├── workflows/
│   └── wf-002-learning-java/      ← tracking for Workflow 2: STATUS.md, docs, history
└── repos/
    ├── README.md                  ← this guide                       (committed)
    ├── repos.txt                  ← THE LIST: git URLs               (committed - you edit this)
    └── learning-java/             ← the clone: code changes go here  (NOT committed - git-ignored)
        branches: main, deps/wf-001, deps/wf-002   ← one branch per workflow, each from the latest main

~/repos/learning-java/             ← your own checkout, if you have one: never touched
```

- **Your own checkouts are never touched.** The workflow never switches their branch, never edits them, and
  never creates branches in them.
- **The clone is a normal git repo.** You can open `repos/learning-java/` in VS Code to look at a workflow's
  changes, e.g. `git -C repos/learning-java diff main...deps/wf-002`.
- **The changes reach the repo's GitHub as a pull request** from branch `deps/wf-NNN` (`/dep-publish`). Nothing
  is ever pushed to `main`.
- **No submodules.** This project never records the repos inside itself; only `repos.txt` and this README are
  committed.

---

## Step 1: Add a repo to the list

Add one line per repo to [`repos.txt`](repos.txt):

```text
<name>          <git-url>                                          [options]
learning-java   https://github.com/elinasarvari/learning-java.git  path=backend  smoke=true
orders-service  git@github.com:my-org/orders-service.git           branch=develop
```

| Part | Required | Meaning | Example |
|------|----------|---------|---------|
| `name` | yes | Clone folder `repos/<name>/`, and the name you use in commands | `orders-service` |
| `git-url` | yes | The URL you'd give `git clone`: the green **Code** button on GitHub | `https://github.com/my-org/orders-service.git` |
| `branch=` | no | The repo's main branch, if it isn't called `main`. Workflow branches start from it | `branch=develop` |
| `path=` | no | Sub-folder with `pom.xml` / `build.gradle`, if not at the repo root | `path=backend` |
| `smoke=true` | no | Also start the app during verification, to catch startup-only failures | `smoke=true` |
| `build=` | no | Your own build command, if the default doesn't fit | `build="./mvnw -B -Pci verify"` |

Or let the tools write the line:

```bash
python3 -I toolkit/scripts/repos.py add https://github.com/my-org/orders-service.git path=api
python3 -I toolkit/scripts/repos.py add ~/repos/orders-service     # already checked out? its URL is looked up for you
```

In chat, `/dep-run <git-url>` (or `/dep-run ~/repos/orders-service`) adds it for you as well.

**HTTPS or SSH?** Use whatever already works for you with `git clone`:
- HTTPS uses your saved GitHub login (macOS Keychain) or a token;
- SSH uses your key (`ssh -T git@github.com` to test);
- private repos need *your* account to have access.

## Step 2: Clone

```bash
python3 -I toolkit/scripts/repos.py clone                  # every repo in the list
python3 -I toolkit/scripts/repos.py clone orders-service   # just one
```

Or `/dep-clone` in chat. You rarely need to do this yourself: `/dep-run` clones as its first step.

| Message | Meaning |
|---------|---------|
| `cloned into repos/<name>` | Done |
| `up to date` | Already cloned; fetched and fast-forwarded on main |
| `kept as is - on deps/wf-NNN` | A workflow is using the clone; it was fetched but not switched |
| `kept as is - N uncommitted file(s)` | Unpublished changes in the clone; left alone |
| `CLONE FAILED: …` | Wrong URL or no access. Try `git clone <url>` by hand to see why |
| `WARNING: path=… does not exist` | The `path=` option is wrong |

## Step 3 (done for you by every workflow): the workflow's branch

When a workflow starts (`/dep-run`, or `repos.py --workflow <id> clone`), each clone is put on that workflow's
branch:

| Message | Meaning |
|---------|---------|
| `created deps/wf-002 from origin/main @ 5f3f485` | New workflow: a fresh branch from the **latest** main |
| `switched back to existing deps/wf-001` / `on deps/wf-001` | Resuming a workflow: its earlier work is still there |
| `BLOCKED: … unpublished changes of workflow wf-001` | Another workflow's changes aren't published yet. Nothing was switched. Publish or abandon that one first |
| `NO 'main' BRANCH` | The repo's main branch has another name: add `branch=<name>` to its line |

```bash
python3 -I toolkit/scripts/repos.py --workflow 2 status    # is every clone on deps/wf-002?
python3 -I toolkit/scripts/repos.py --workflow 2 release   # finished: back to main (the branch is kept)
```

**One workflow at a time per repo.** Each workflow has its own branch, but a clone can only be on one branch
at a time. Workflows on *different* repos never get in each other's way.

---

## Everyday tasks

| I want to… | Do this |
|------------|---------|
| See what a workflow changed | `git -C repos/<name> diff main...deps/wf-NNN`, or open `repos/<name>/` in VS Code |
| Get the latest code | `repos.py clone` (clones on main are fast-forwarded; new workflows always start from the latest main anyway) |
| Work on only some repos in one workflow | `/dep-run <repo>` scopes the workflow to that repo (`workflows/<id>/repos.txt`) |
| Stop working on a repo | Delete its line, then `rm -rf repos/<name>` once nothing in it is needed |

## What each command does to a clone

| Command | Effect on `repos/<name>/` |
|---------|---------------------------|
| `/dep-clone`, first step of `/dep-run` | Clones it; in a workflow, puts it on `deps/<id>` from the latest main |
| `/dep-scan`, `/dep-inventory`, `/dep-analyze`, `/dep-verify` | Read-only (builds create `target/` / `build/`) |
| `/dep-apply` | Edits files on `deps/<id>`, only after you approved the plan. Nothing is committed |
| `/dep-publish` | Commits on `deps/<id>`, pushes that branch, opens a PR. Never pushes to `main`, never force-pushes |
