# repos/: the repositories this project works on

This folder holds **the list of repos to fix** and **the clones of those repos**.

```text
repos/
├── README.md          ← this guide                      (committed)
├── repos.txt          ← THE LIST: which repos to clone  (committed - you edit this)
├── learning-java/     ← a clone of a repo from the list (NOT committed - git-ignored)
└── orders-service/    ← another clone                    (NOT committed)
```

- **`repos.txt` is the only file you edit.** Every command reads it.
- **Each clone is a normal git repo** in `repos/<name>/`. You can `cd` into it, open it in VS Code,
  and use git as usual. This project never commits the clones; only the list and this README are tracked.

---

## Step 1: Add a repo to the list

Open [`repos.txt`](repos.txt) and add one line per repo:

```text
<name>          <git-url>                                          [options]
learning-java   https://github.com/elinasarvari/learning-java.git  path=backend  smoke=true
orders-service  git@github.com:my-org/orders-service.git           branch=develop
billing         https://bitbucket.org/my-team/billing.git
```

| Part | Required | Meaning | Example |
|------|----------|---------|---------|
| `name` | yes | Folder name: the clone goes to `repos/<name>/`. You also use it in commands | `orders-service` |
| `git-url` | yes | The URL you'd give `git clone`: the green **Code** button on GitHub | `https://github.com/my-org/orders-service.git` |
| `branch=` | no | Branch to clone and keep updated. Default: the repo's default branch | `branch=develop` |
| `path=` | no | Sub-folder with `pom.xml` / `build.gradle`, if not at the root | `path=backend` |
| `smoke=true` | no | Also start the app during verification, to catch startup-only failures | `smoke=true` |
| `build=` | no | Your own build command, if the default doesn't fit | `build="./mvnw -B -Pci verify"` |

You can also add a repo without editing the file:

```bash
python3 -I workflow/scripts/repos.py add https://github.com/my-org/orders-service.git orders-service path=api
```

Or in Copilot / Claude chat: `/dep-clone https://github.com/my-org/orders-service.git`

**Which URL, HTTPS or SSH?** Use whatever already works for you with plain `git clone`:
- **HTTPS** (`https://github.com/...`) uses your saved GitHub login (macOS Keychain) or a token.
- **SSH** (`git@github.com:...`) uses your SSH key. Test it with `ssh -T git@github.com`.
- **Private repos** clone only if *your* account has access. This project uses your normal git credentials.

## Step 2: Clone

From the project root (the `snyk-update-package` folder):

```bash
python3 -I workflow/scripts/repos.py clone                   # clone/refresh every repo in the list
python3 -I workflow/scripts/repos.py clone orders-service    # just one
```

Or in chat: `/dep-clone`

What it prints, per repo:

| Message | Meaning |
|---------|---------|
| `cloned` | It wasn't there; now it is, in `repos/<name>/` |
| `up to date` | Already cloned; fetched and fast-forwarded to the latest commit |
| `kept as is - N uncommitted file(s)` | You have local changes there; it won't touch them |
| `kept as is - on branch deps/…` | An upgrade is in progress on that clone; it won't switch branches |
| `CLONE FAILED: …` | Wrong URL or no access. Try the same `git clone <url>` by hand to see why |
| `WARNING: path=… does not exist` | The `path=` option is wrong; fix the line in `repos.txt` |

## Step 3: Check

```bash
python3 -I workflow/scripts/repos.py status
```

```text
REPO                     COMMIT   BRANCH                       DIRTY     AHEAD  BEHIND
learning-java            5f3f485  main                         0         0      0
orders-service           not cloned - run: repos.py clone orders-service
```

- `DIRTY` = files you changed.
- `AHEAD` / `BEHIND` = commits compared with the remote branch.

`python3 -I workflow/scripts/repos.py list` shows the folder each repo builds in.

---

## Everyday tasks

| I want to… | Do this |
|------------|---------|
| Get the latest code for all repos | `python3 -I workflow/scripts/repos.py clone` (safe to re-run any time) |
| Work on only some repos in one upgrade | Create `upgrades/<id>/repos.txt` with just those lines (same format) |
| Stop working on a repo | Delete its line from `repos.txt`, then `rm -rf repos/<name>` once you no longer need the clone |
| Start a clone from scratch | Make sure nothing in it is needed, `rm -rf repos/<name>`, then `repos.py clone <name>` |
| See what an upgrade changed in a clone | `git -C repos/<name> diff` (changes sit on branch `deps/<upgrade-id>`) |

## What the tools will and won't do to a clone

| Step | Effect on `repos/<name>/` |
|------|---------------------------|
| `/dep-clone` | Clones it, or fast-forwards it if it's clean. Never resets, stashes or switches branches |
| `/dep-scan`, `/dep-inventory`, `/dep-analyze`, `/dep-verify` | Read-only (builds create `target/` / `build/`, which the clone's own `.gitignore` should ignore) |
| `/dep-apply` | Creates branch `deps/<upgrade-id>` and edits files there. Nothing is committed |
| `/dep-publish` | Commits on `deps/<upgrade-id>`, pushes that branch, opens a PR. Never pushes to `main`, never force-pushes |
