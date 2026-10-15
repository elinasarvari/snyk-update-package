# repos/: the repositories this project works on

`repos/repos.txt` is **the list of repos to fix**. Each line points at the repo in one of two ways:

| You write | What happens | Where the changes go |
|-----------|--------------|----------------------|
| **a local folder** you already have, e.g. `~/repos/learning-java` | Used **in place**. Nothing is cloned or copied | Your own checkout, on a new branch `deps/<upgrade-id>` |
| **a git URL**, e.g. `https://github.com/my-org/orders.git` | Cloned into `repos/<name>/` here (git-ignored) | That clone, on branch `deps/<upgrade-id>` |

**In both cases the repo's code and changes stay in that repo.** This project (`snyk-update-package`)
never stores them, and nothing here is a git submodule. Only `repos.txt` and this README are committed.
The changes reach the repo's own GitHub as a pull request (`/dep-publish`).

```text
snyk-update-package/repos/
├── README.md          ← this guide                                   (committed)
├── repos.txt          ← THE LIST                                     (committed - you edit this)
└── orders-service/    ← only for repos added by URL: a plain clone   (NOT committed)

~/repos/learning-java/ ← a repo added as a local folder: stays exactly where it is
```

**Which one should I use?**
- **The repo is already on your machine:** use the **local folder**. You'll see the upgrade in your normal
  checkout, and there's no second copy to keep in sync.
- **You don't have it checked out, or you want the upgrade fully separate from your own work:** use the **git URL**.

---

## Step 1: Add a repo to the list

Open [`repos.txt`](repos.txt) and add one line per repo:

```text
<name>          <local folder or git URL>                     [options]
learning-java   ~/repos/learning-java                         branch=main  path=backend  smoke=true
orders-service  https://github.com/my-org/orders-service.git  branch=develop
billing         git@bitbucket.org:my-team/billing.git
```

| Part | Required | Meaning | Example |
|------|----------|---------|---------|
| `name` | yes | Short name you use in commands. For URLs, also the clone folder `repos/<name>/` | `orders-service` |
| local folder | one of these | Path to your checkout. Must start with `/`, `~`, `./` or `../` | `~/repos/learning-java` |
| git URL | one of these | The URL you'd give `git clone`: the green **Code** button on GitHub | `https://github.com/my-org/orders-service.git` |
| `branch=` | no | URL: the branch to clone and keep updated. Local folder: the branch you expect it on; you're warned if it isn't, but it's never switched for you | `branch=main` |
| `path=` | no | Sub-folder with `pom.xml` / `build.gradle`, if not at the repo root | `path=backend` |
| `smoke=true` | no | Also start the app during verification, to catch startup-only failures | `smoke=true` |
| `build=` | no | Your own build command, if the default doesn't fit | `build="./mvnw -B -Pci verify"` |

Or add it with a command, or by asking in chat:

```bash
python3 -I workflow/scripts/repos.py add ~/repos/orders-service path=api                  # local folder
python3 -I workflow/scripts/repos.py add https://github.com/my-org/orders-service.git     # git URL
```

In Copilot or Claude chat: `/dep-clone ~/repos/orders-service` or `/dep-clone <git-url>`.

**Sharing this list:** local folders are specific to your machine. If someone else uses your `repos.txt`,
they change the paths to their own, or use the git URL instead.

**For git URLs, HTTPS or SSH?** Use whatever already works for you with plain `git clone`:
- **HTTPS** (`https://github.com/...`) uses your saved GitHub login (macOS Keychain) or a token.
- **SSH** (`git@github.com:...`) uses your SSH key. Test it with `ssh -T git@github.com`.
- **Private repos** need *your* account to have access.

## Step 2: Check (and clone the URL ones)

From the project root (the `snyk-update-package` folder):

```bash
python3 -I workflow/scripts/repos.py clone                   # every repo in the list
python3 -I workflow/scripts/repos.py clone orders-service    # just one
```

Or in chat: `/dep-clone`

What it prints, per repo:

| Message | Type | Meaning |
|---------|------|---------|
| `local, used in place (main @ 5f3f485)` | local | Found your folder. Nothing was changed |
| `… \| on X, expected main - switch it yourself if needed` | local | Your checkout is on another branch. It's left alone; switch it if the upgrade should start from `main` |
| `… \| N uncommitted file(s)` | local | `/dep-apply` will wait until you commit them, so your work is never mixed into the upgrade |
| `… \| N commit(s) behind origin` | local | Run `git pull` in that folder if you want the latest code first |
| `LOCAL FOLDER NOT FOUND or not a git repo` | local | Wrong path in `repos.txt` |
| `cloned` | URL | Cloned into `repos/<name>/` |
| `up to date` | URL | Already cloned; fetched and fast-forwarded |
| `kept as is - …` | URL | The clone has local changes or is on `deps/…`; it won't touch it |
| `CLONE FAILED: …` | URL | Wrong URL or no access. Try `git clone <url>` by hand to see why |
| `WARNING: path=… does not exist` | both | The `path=` option is wrong |

## Step 3: Check the status

```bash
python3 -I workflow/scripts/repos.py status
```

```text
REPO                 TYPE   COMMIT   BRANCH        DIRTY  AHEAD  BEHIND  FOLDER
learning-java        local  5f3f485  main          0      0      0       ~/repos/learning-java
orders-service       clone  9c1e2aa  develop       0      0      0       ~/repos/snyk-update-package/repos/orders-service
```

`FOLDER` is where the code is, and where the upgrade will make its changes.

---

## Everyday tasks

| I want to… | Do this |
|------------|---------|
| Get the latest code | URL repos: `repos.py clone`. Local folders: `git pull` in the folder yourself |
| Work on only some repos in one upgrade | Create `upgrades/<id>/repos.txt` with just those lines (same format) |
| See what an upgrade changed | `git -C <folder> diff`. The changes are on branch `deps/<upgrade-id>` |
| Go back to my own branch after an upgrade (local folder) | `git -C <folder> switch main`. The `deps/<id>` branch stays until you delete it |
| Stop working on a repo | Delete its line. For URL repos, also `rm -rf repos/<name>` once you no longer need the clone |

## What the tools will and won't do to a repo folder

| Step | Local folder (your checkout) | URL clone in `repos/<name>/` |
|------|------------------------------|------------------------------|
| `/dep-clone` | Looks only: fetches remote refs, never pulls, switches or edits | Clones, or fast-forwards if clean |
| `/dep-scan`, `/dep-inventory`, `/dep-analyze`, `/dep-verify` | Read-only. Builds create `target/` / `build/` | same |
| `/dep-apply` | **Switches your checkout to a new branch `deps/<id>`** and edits files there. You're told before it starts. Refuses if you have uncommitted changes | Same, inside the clone |
| `/dep-publish` | Commits on `deps/<id>`, pushes that branch, opens a PR. Never pushes to `main`, never force-pushes | same |
