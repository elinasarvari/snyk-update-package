# snyk-update-package

**One place to fix Snyk findings across many Java repos.** You list the repos, it clones them, finds
every vulnerable package, documents what an upgrade will break, applies it on a branch, builds and
tests everything, and opens the pull requests. You decide at each step.

Works with **GitHub Copilot** (VS Code, agent mode) and **Claude Code**: same commands, same results.

```
 repos/repos.txt ─▶ /dep-clone ─▶ /dep-scan ─▶ /dep-inventory ─▶ /dep-analyze ─▶ you approve ─▶ /dep-apply ─▶ /dep-verify ─▶ /dep-publish
 your list of       check local / every        current vs       what breaks,    the plan       edit on a     build, test,   commit, push,
 repos              clone URLs    flagged      target, what     where, and                     branch        boot, re-scan  open PRs
                                  package      moves with it    a plan
```

**How it fits together:** see the diagrams in **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**: components, the workflow's
steps and gates, one `/dep-run` in order, where every file lives, and what each step reads and writes.

This project holds **no application code** and is **not** a container of submodules. It keeps **the list,
the workflow, and the tracking**. The repos you fix are **cloned into `repos/<name>/`**, and **that is where the
code changes happen**, on one branch per workflow (`deps/wf-NNN`, from the latest main). The changes reach each
repo's GitHub as a pull request. Your own checkouts elsewhere (e.g. `~/repos/...`) are never touched.

```text
snyk-update-package/
├── workflows/                    ← TRACKING: one folder per workflow run
│   ├── INDEX.md                  ← every run, current step, next step (auto-generated)
│   └── wf-002-inventory-service/ ← Workflow 2: STATUS.md, documents, history
├── repos/
│   ├── repos.txt                 ← the list of repos to fix (git URLs, you edit this)
│   ├── README.md                 ← how to add and clone repos
│   └── inventory-service/        ← the CLONE: code changes happen here, on deps/wf-NNN (git-ignored)
└── toolkit/                      ← how each step works (scripts, procedures, templates)
```

---

## Quick start

**1. Get the project and the tools** (once)

You need **Git**, **Java** (the version your repos use) and **Python 3.9+**.

| | macOS (Terminal) | Windows (PowerShell) |
|---|---|---|
| Tools | Python is built in. `brew install git openjdk@21` if missing | Install [Git for Windows](https://git-scm.com/download/win), [Python](https://www.python.org/downloads/windows/) (tick **"Add python.exe to PATH"**; `py -3 --version` should work) and a JDK (e.g. `winget install EclipseAdoptium.Temurin.21.JDK`). PowerShell 5.1 is built in |
| Get the project | `git clone https://github.com/elinasarvari/snyk-update-package.git`<br>`cd snyk-update-package` | the same two commands |
| GitHub CLI (only to open PRs at the end) | `brew install gh && gh auth login` | `winget install GitHub.cli` then `gh auth login` |

On Windows, scripts run with `powershell -ExecutionPolicy Bypass -File <script>.ps1 ...`, which works without
changing any system setting. Each bash script `x.sh` has a PowerShell twin `x.ps1` with the same arguments.

**The Snyk CLI**, which the scan step uses. Pick one:

| You have | macOS | Windows (PowerShell) |
|----------|-------|----------------------|
| **The Snyk VS Code extension** (it already downloaded the CLI; the path is in its settings: Snyk → Advanced → CLI path) | `export SNYK_CLI="<that path>"` (add it to `~/.zshrc`) | `$env:SNYK_CLI = "<that path>"`, or to keep it: `[Environment]::SetEnvironmentVariable("SNYK_CLI", "<that path>", "User")` |
| Nothing yet | `brew tap snyk/tap && brew install snyk-cli` | `npm install -g snyk` (or download `snyk-win.exe` from Snyk's releases) |

Common download locations of the extension's CLI are also found automatically.

**Log the CLI in (once), with OAuth2 and your company SSO.** No clicking "Authenticate" in the extension; the
toolkit starts the login and **your browser opens by itself**:

| | macOS | Windows (PowerShell) |
|---|---|---|
| Log in (browser, SSO) | `bash toolkit/scripts/snyk-login.sh` | `powershell -ExecutionPolicy Bypass -File toolkit\scripts\snyk-login.ps1` |
| Am I logged in? | `bash toolkit/scripts/snyk-login.sh --status` | `... snyk-login.ps1 --status` |
| Log out | `bash toolkit/scripts/snyk-login.sh --logout` | `... snyk-login.ps1 --logout` |

Step by step, with what you'll see: **[Logging in to Snyk](#logging-in-to-snyk-step-by-step)**.
Or in chat: **`/dep-login`**. You rarely need any of these: if a scan finds the CLI isn't logged in, `/dep-scan`
and `/dep-run` start the login themselves and retry. You only sign in in the browser window that opens.

- **How it works:** it runs the CLI's own OAuth2 login (`snyk auth --auth-type=oauth`; OAuth is the CLI's default
  since 1.1293). The CLI stores a token that renews itself, so you sign in once, not per scan. The extension keeps its
  own login inside VS Code, which is why the CLI needs this one-time sign-in of its own.
- **No browser (automation / build machine):** with a Snyk *service account* (Enterprise plan), set
  `SNYK_CLIENT_ID` and `SNYK_CLIENT_SECRET` (`$env:…` on Windows) and run the same script. It uses the OAuth2
  *client credentials* grant instead, with no browser. The secret is only read from the environment and never
  printed or saved.
- **Snyk in another region (EU / AU) or a private instance:** add `--endpoint <url>` once, e.g.
  `--endpoint https://api.eu.snyk.io`. Get the exact URL from your Snyk admin.
- **No CLI allowed where you are?** Pass a Snyk JSON export to `/dep-scan` or `/dep-run` instead.

**2. List the repos you want to fix** in [`repos/repos.txt`](repos/repos.txt), one line each (or skip this:
`/dep-run <git-url>` adds the line for you):

```text
# <name>           <git-url>                                           [options]
inventory-service  https://github.com/acme-corp/inventory-service.git  path=backend  smoke=true
orders-service     git@github.com:my-org/orders-service.git            branch=develop
```

- `name`: the clone folder `repos/<name>/`, and the name you use in commands
- `git-url`: what you'd give `git clone`. Already checked out? `repos.py add ~/repos/x` looks the URL up for you
- `branch`: the repo's main branch, if it isn't called `main`
- `path`: the sub-folder that has the `pom.xml`, if it isn't at the repo root
- `smoke=true`: also start the app during verification (Spring Boot apps)

**3. Clone them** into `repos/` (optional: `/dep-run` does this as its first step):

```bash
python3 -I toolkit/scripts/repos.py clone      # macOS: clones missing repos, updates clean ones on main
python3 -I toolkit/scripts/repos.py status     # branch, commit, uncommitted files per clone
```

```powershell
py -3 -I toolkit\scripts\repos.py clone          # Windows (PowerShell): the same
py -3 -I toolkit\scripts\repos.py status
```

Every option, HTTPS vs SSH, private repos, and what each message means: **[repos/README.md](repos/README.md)**.

**4. Open this folder** in VS Code with GitHub Copilot (first time: **[Setting up GitHub Copilot](#setting-up-github-copilot-vs-code)**),
or start Claude Code in it (first time: **[Setting up Claude Code](#setting-up-claude-code)**).

**5. Run it: the easy way.** Give `/dep-run` one repo (its name, its git URL, or a checkout of it):

```text
/dep-run inventory-service                      a repo already in repos/repos.txt
/dep-run ~/repos/orders-service             a checkout you have: its URL is added, then cloned into repos/
/dep-run https://github.com/acme/billing.git     a git URL: added and cloned into repos/
/dep-run inventory-service ~/Downloads/snyk.json    use a Snyk export instead of running the CLI
```

It opens **Workflow N (`wf-NNN`)** for that repo, or resumes the unfinished one, and runs **every step by
itself**: clone → Snyk scan → inventory → impact + plan. It **stops only where it needs you**:

| It stops when | You reply / run |
|---------------|-----------------|
| the plan is ready (always) | read `workflows/wf-NNN-…/03-plan.md` ([how](#reviewing-the-plan-vulnerable-modules-step-by-step)), then `/dep-run inventory-service approve`, or the *Approve* button in Copilot. It then applies and verifies |
| verification finished (always) | green: `/dep-publish wf-NNN` to push and open the PR (always your own command). Red: it lists the fixes |
| something blocks it | what it asks for, e.g. install Snyk, pick the starting version, commit your local changes |

Every stop ends with **Done this run / Stopped because / ▶ Next step**, so you always know what to do.
What happens at each step, and every reason it can stop: **[What `/dep-run` does, step by step](#what-dep-run-does-step-by-step)**.

**Or run the steps one by one**, each ending with its own **▶ Next step** (in Copilot, also a button under the reply):

```text
/dep-clone                       clone/refresh every repo in repos/repos.txt into repos/<name>/
/dep-scan                        Snyk scan → every flagged package (or: /dep-scan path/to/snyk.json)
/dep-inventory <id>              exact versions, what sets them, what moves with them, baseline build
/dep-analyze <id>                breaking changes in YOUR code with file:line, and a step-by-step plan
  → read workflows/<id>/03-plan.md and reply "approve"
/dep-apply <id>                  apply the plan in each clone, on branch deps/<id> (not committed)
/dep-verify <id>                 build + tests + app boot for every repo, compared to before
/dep-publish <id>                commit, push, open one PR per repo
```

`<id>` is the **workflow id**. Every run gets the next number: the first is **Workflow 1, `wf-001`**, the
next **Workflow 2, `wf-002`**, and so on (never reused). `/dep-scan` (or `/dep-upgrade`) creates it and tells
you the number. You can then write `1`, `wf-001`, or the folder name, e.g. `/dep-inventory 1`. To see every run
and where it stands, open [`workflows/INDEX.md`](workflows/INDEX.md) or run **`/dep-upgrade status`**.

**6. Read the results** in `workflows/<id>/`. Start with `STATUS.md`.

One git repo with several Java projects inside? See **[Monorepos, step by step](#monorepos-one-git-repo-several-projects-step-by-step)**.

---

## What `/dep-run` does, step by step

`/dep-run <repo>` works through the steps by itself and stops only where it needs you. **Nothing is pushed to your
repo** until you run `/dep-publish` yourself. The example uses `inventory-service`. Any name in `repos/repos.txt`, a
git URL or a checkout of the repo works the same way.

**Start.** It finds the repo in `repos/repos.txt`, adding it first if you gave a URL or a folder. Then it opens the
**next workflow number** (e.g. Workflow 3, `wf-003`), or **resumes** the unfinished run for that repo. It tells you
which workflow it is before doing anything else, and creates `workflows/wf-NNN-inventory-service/STATUS.md`.

| # | Step | What happens | Goes on by itself? |
|---|------|--------------|--------------------|
| 0 | Clone | Updates (or clones) `repos/inventory-service/` and creates branch `deps/wf-NNN` from the latest main. Your own checkout is never touched | ✅ |
| 1 | Snyk scan | Scans every `pom.xml`. Not logged in? Your browser opens for SSO, then it scans again. Lists every flagged package: version, severity, CVEs, fixed-in, dependency paths. Default scope: **every finding with a fix** (change it by replying `scope: ...`) | ✅ (no findings: the run ends, nothing to do) |
| 2 | Inventory | Reads every pom's declared versions and properties and the resolved dependency tree, then runs a **baseline build** of the repo before any change | ✅ |
| 3 | Impact + plan | Finds breaking changes in **your** code with file:line, then writes `03-plan.md`, itemizing every vulnerable module | ⏸ **STOP 1: always** |
| 4 | Apply | Edits poms and code in `repos/inventory-service/` on `deps/wf-NNN`, compiling after each plan step. Nothing is committed | ✅ after you approve |
| 5 | Verify | Build, tests (every module's) and app start (if `smoke=true`), compared with the baseline | ⏸ **STOP 2: always** |
| 6 | Publish | Commits, pushes `deps/wf-NNN`, opens the PR | ❌ never: only your own `/dep-publish` |

**At STOP 1 (the plan is ready):**

1. Open `workflows/wf-NNN-inventory-service/03-plan.md` ([how to read it](#reviewing-the-plan-vulnerable-modules-step-by-step)).
2. Reply `/dep-run inventory-service approve` (Copilot: the *Approve* button), or say what to change, e.g.
   `/dep-run inventory-service scope: high+`.
3. It applies the plan, then verifies.

**At STOP 2 (verification finished):**

| Result | You run |
|--------|---------|
| Green | `/dep-publish wf-NNN`: commits, pushes the branch, opens the PR |
| Red | Read the proposed fixes, then reply `/dep-run inventory-service approve fixes`: they're added to the plan, applied and verified again |

**It also stops when something blocks it**, and says what to do:

| Stops because | What you do |
|---------------|-------------|
| The clone failed, or there's no `main` branch | Check the URL and your access, or add `branch=<name>` to the repo's line |
| BLOCKED: another workflow's changes aren't published | Publish or abandon that workflow first (the message names it) |
| The Snyk CLI is missing, or the login didn't finish | Install the CLI or retry the login ([Logging in to Snyk](#logging-in-to-snyk-step-by-step)), or pass a Snyk export: `/dep-run inventory-service path/to/snyk.json` |
| The **baseline build is red** | Fix the build on main first: an upgrade can't be checked on top of a broken build |
| A target version doesn't exist, or the inventory needs a decision | Reply with your decision, e.g. `/dep-run inventory-service proceed from 3.3.2` |
| A plan step stays red after two fix rounds | Read the apply log and decide |

**Every stop ends with the same reply**, so you always know the next command:

```text
Workflow 3 (wf-003) · inventory-service · workflows/wf-003-inventory-service

Done this run:     0 Clone ✅ · 1 Scan ✅ (12 packages, 3 changes) · 2 Inventory ✅ · 3 Plan ⏸
Stopped because:   the plan is ready for your review

▶ Next step:       read workflows/wf-003-inventory-service/03-plan.md, then reply "approve"
                   /dep-run inventory-service approve
```

**Good to know:**

- **Start a fresh chat after each stop.** It's cheaper, and `/dep-run inventory-service` resumes from `STATUS.md`.
  The run reads the step files, not the chat.
- **At each stop it saves the workflow's records** (`workflows.py save`). While this repo is public, the save is
  refused and the reply says so. The records stay on your machine until you make the repo private and run
  `/dep-save <id>` ([Saving workflow results](#saving-workflow-results-into-the-repository)).
- **Where the changes are:** `git -C repos/inventory-service diff main...deps/wf-NNN`, or open the folder in VS Code.
- **Where it stands:** `STATUS.md` in the workflow folder, [`workflows/INDEX.md`](workflows/INDEX.md), or `/dep-upgrade status`.

---

## Monorepos (one git repo, several projects), step by step

A monorepo is listed **once**: one line in `repos.txt`, one clone, one branch `deps/wf-NNN` and one PR per
workflow, covering every project inside it.

**1. Check how your monorepo builds.** Open the `pom.xml` at the **root** of the repo (your own checkout, or
`repos/<name>/` if it's already cloned) and look for `<module>` lines:

| | macOS | Windows (PowerShell) |
|---|---|---|
| Count the modules | `grep -c '<module>' ~/repos/my-monorepo/pom.xml` | `(Select-String -Path $HOME\repos\my-monorepo\pom.xml -Pattern '<module>').Count` |

| You see | Your case | Supported? |
|---------|-----------|------------|
| A number (e.g. `4`): the root `pom.xml` lists the projects as modules | **A: one multi-module build** | ✅ Yes, continue below |
| `0`, or "no such file": there is no root `pom.xml`, each project builds on its own | **B: separate builds** | ❌ Not yet. One line can name only one build folder (`path=`), and listing the same repo several times would clone it several times and clash at publish. Ask for multi-folder support (`path=a,b,c`) |

**2. Add it to the list** (once), with no `path=` and no `smoke=true`:

```bash
python3 -I toolkit/scripts/repos.py add https://github.com/my-org/my-monorepo.git my-monorepo
```

```powershell
py -3 -I toolkit\scripts\repos.py add https://github.com/my-org/my-monorepo.git my-monorepo
```

This writes one line to [`repos/repos.txt`](repos/repos.txt):

```text
my-monorepo  https://github.com/my-org/my-monorepo.git
```

- Main branch not called `main`? Add `branch=<name>` to the line.
- Already cloned into `repos/`? Use the **exact folder name** as the name, so the clone is reused.
- **Don't add `smoke=true`.** The app-start check looks for the jar in the root `target/`, but in a multi-module
  build each app's jar is inside its own module, so it would report a failure that isn't real.

**3. Clone it and check it:**

```bash
python3 -I toolkit/scripts/repos.py clone my-monorepo
python3 -I toolkit/scripts/repos.py status
```

```powershell
py -3 -I toolkit\scripts\repos.py clone my-monorepo
py -3 -I toolkit\scripts\repos.py status
```

**4. Run the workflow** in chat: **`/dep-run my-monorepo`**. It covers every project in the repo:

| Step | What it reads in the monorepo |
|------|-------------------------------|
| Snyk scan | Every `pom.xml` (`--all-projects`). Each finding names the project and `pom.xml` it came from |
| Inventory | Every `pom.xml`'s declared dependencies and version properties, and every module's dependency tree |
| Impact + plan | Code, config and tests across the whole repo. The plan's *Vulnerable modules* lists each project's findings |
| Apply | Edits on `deps/wf-NNN`, in the root `pom.xml` (shared versions) or a module's `pom.xml`, as the plan says |
| Verify | One build of the whole reactor from the root. Test results are counted from **every** module (each failing test is named, as `<test class>#<test>`) |
| Publish | One branch, one PR for the whole monorepo |

Folders like `target/` and `node_modules/` are skipped everywhere (`toolkit/ignore-dirs.txt`).

**Build and test it by hand (optional)**, the same check the verify step runs, from the monorepo's root:

```bash
bash toolkit/scripts/verify-repo.sh repos/my-monorepo /tmp/verify-my-monorepo
```

```powershell
powershell -ExecutionPolicy Bypass -File toolkit\scripts\verify-repo.ps1 repos\my-monorepo $env:TEMP\verify-my-monorepo
```

It prints the first errors if the build fails, and writes `summary.json` with the test counts of every module
(`"tests": {"tests": …, "failures": …, "failed_tests": [...]}`), plus `build.log`.

---

## Reviewing the plan: vulnerable modules, step by step

When `/dep-run` stops with *"review 03-plan.md, reply approve"*, this is how to read the plan. Its **Vulnerable
modules** section lists every vulnerable module from the Snyk scan, itemized, so you can check each one before
anything changes in your code.

**1. Open the plan:** `workflows/wf-NNN-<repo>/03-plan.md`. Each module has four parts:

```text
### 1. org.yaml:snakeyaml@1.33

Facts      current version · highest severity · status · fixed in · number of dependency paths · introduced via · projects
Issues     one row per Snyk issue: Snyk ID (links to Snyk's page) · title · severity · CVSS · CVE · CWE · exploit · fixed in
Paths      one row per dependency path the module arrives by, with Snyk's fix for that path
Decision   in scope? · fix chosen · target version · plan step(s) · compatibility / risk · how it's verified
```

**2. Check the facts and issues.** These come straight from Snyk, so you're checking they look right, not editing them.

| Column | What it tells you |
|--------|-------------------|
| **Status** | `fixable by upgrade`: upgrading the library that brings it in fixes every path · `needs an override`: at least one path has no upgrade, so the module itself must be forced to the fixed version · `partly fixable`: some path has no fix at all · `no fix`: no fixed version exists |
| **CVSS** | Severity score from 0 to 10 (9+ critical, 7+ high) |
| **Exploit** | Whether attackers have working code for it, e.g. `Mature`, `Proof of Concept`, `No Known Exploit`. Mature or proof-of-concept first |
| **Fixed in** | The first versions without the vulnerability |
| **Paths** | Every route into your build, e.g. `your-app › A@1.0 › B@2.1 › module@1.33`. **A module is only fixed when every path is** |

**3. Check each decision.** The decision table is the assistant's proposal. Look for these, module by module:

| Look at | It's right when |
|---------|-----------------|
| **Fix chosen** | Follows the order: upgrade the library that brings it in → **override** the module to the fixed version → a newer introducing library or excluding the module → only then *out of scope* |
| **Target version** | **Snyk's version, exactly**, pre-filled from the scan. Any other version must be listed under *Strategy* → *Versions not from Snyk*, with its reason |
| **Plan step(s)** | Names the steps that cover **every** path listed. Cross-check with the plan's *Path coverage* table |
| **Compatibility / risk** | Says what could break, with evidence from `03-impact.md`, not just "low risk" |
| **In scope? = no** | Points to a row in *Out of scope* that says why and what happens next |

**4. Check nothing is missing.** The module entries are generated from the scan, so every flagged package and
issue is there by construction, and `plan-check` has confirmed every module has a decision. For a quick overview, open
`snyk/module-index.md`: one line per module, with its status and Snyk's fix.

**5. Reply.**

- Everything looks right: **`approve`** (`/dep-run <repo> approve`, or the *Approve* button in Copilot).
- Something's off: say what, e.g. *"module 3: override to 2.2, not 2.0"* or *"put the medium findings out of scope"*.
  The plan is updated, and you approve the new version.

**6. After verification**, `05-verification.md` has a **Vulnerable modules: before → after** table: one row per
module and issue, marked **✅ fixed**, **➖ out of scope** (as planned), or **⛔ still open, not planned**. A ⛔ means
the plan missed something; the report proposes a fix.

**Regenerating the list** (e.g. after changing the scope). The assistant does this itself; by hand it's below.
It refreshes the facts and **keeps every decision field already filled in**:

```bash
python3 -I toolkit/scripts/parse-snyk.py "workflows/wf-001-<repo>/snyk/*.json" --into-plan workflows/wf-001-<repo>/03-plan.md   # macOS
```

```powershell
py -3 -I toolkit\scripts\parse-snyk.py "workflows\wf-001-<repo>\snyk\*.json" --into-plan workflows\wf-001-<repo>\03-plan.md   # Windows
```

**Is every module decided?** `python3 -I toolkit/scripts/script-helpers.py plan-check workflows/wf-001-<repo>/03-plan.md`
lists any module with an open field. `/dep-run` only asks you to approve once this says *"all N modules decided"*.

## How the plan is built (fast), step by step

The planning step (`/dep-analyze`, or step 3 of `/dep-run`) does most of its work with scripts, so it's quick and
doesn't spend tokens re-typing tables. You don't have to run anything here; the assistant does. The commands are
shown so you can follow along, or adjust decisions yourself.

**1. The scan writes three summaries** in `workflows/wf-NNN-<repo>/snyk/`:

| File | What it is | Who reads it |
|------|------------|--------------|
| `findings.md` | Every flagged package, the changes to make, every dependency path | You; the assistant reads only section 2 |
| `vulnerable-modules.md` | Every vulnerable module, itemized: facts, issues, paths, decision | Goes into the plan (step 2) |
| `module-index.md` | **One line per module**: severity, status, Snyk's fix | The assistant, instead of every full entry |

**2. A script puts the modules into the plan.** Every module from the scan lands in `03-plan.md` → *Vulnerable
modules*, so none can be missed. Snyk's own answer is already filled in: **Fix chosen** (Snyk's fix for each path),
**Target version** (Snyk's version, exactly: never the latest release) and **Verified by** (the re-scan must show
these issues gone).

```bash
python3 -I toolkit/scripts/parse-snyk.py "workflows/wf-001-<repo>/snyk/*.json" --into-plan workflows/wf-001-<repo>/03-plan.md   # macOS
```

```powershell
py -3 -I toolkit\scripts\parse-snyk.py "workflows\wf-001-<repo>\snyk\*.json" --into-plan workflows\wf-001-<repo>\03-plan.md   # Windows
```

It prints `put 30 vulnerable modules into …/03-plan.md (0 filled-in decision fields kept)`. Run it again any time,
e.g. after changing the scope: it refreshes the facts and **keeps every decision field already filled in**.

**3. The assistant reads the index, not every module.** It opens a module's full entry only for the ones that need
thought: status `needs an override`, `partly fixable` or `no fix`.

**4. Decisions are set for groups of modules at once.** Most modules share a decision, e.g. everything fixed by one
upgrade gets the same plan step and risk note:

```bash
python3 -I toolkit/scripts/script-helpers.py plan-decide workflows/wf-001-<repo>/03-plan.md 1-12 "Plan step(s)=Step 1" "Compatibility / risk=see 03-impact.md: Spring Boot 3.5"
python3 -I toolkit/scripts/script-helpers.py plan-decide workflows/wf-001-<repo>/03-plan.md all "In scope?=yes"
python3 -I toolkit/scripts/script-helpers.py plan-decide workflows/wf-001-<repo>/03-plan.md "status:no fix" "In scope?=no, see Out of scope #1"
```

On Windows: `py -3 -I toolkit\scripts\script-helpers.py plan-decide …` with the same arguments.

| Part | Means |
|------|-------|
| `1-12`, `3,5,7`, `all` | which modules, by their number in the plan |
| `"status:needs an override"` | every module with that status: `fixable by upgrade`, `needs an override`, `partly fixable`, `no fix` |
| `"Field=value"` | one or more of `In scope?`, `Fix chosen`, `Target version`, `Plan step(s)`, `Compatibility / risk`, `Verified by` |

It prints `set Plan step(s), Compatibility / risk for 12 module(s): 1, 2, …`.

**5. A check by code that nothing is left open:**

```bash
python3 -I toolkit/scripts/script-helpers.py plan-check workflows/wf-001-<repo>/03-plan.md            # macOS
```

```powershell
py -3 -I toolkit\scripts\script-helpers.py plan-check workflows\wf-001-<repo>\03-plan.md             # Windows
```

| It prints | Meaning |
|-----------|---------|
| `all 30 modules decided` | Every module has a full decision. Only now does `/dep-run` ask you to approve |
| `2 of 30 modules still have open decisions:` and a list like `7. org.foo:bar@1.0: Target version, Plan step(s)` | Those fields are still open; the assistant fills them before asking you |

**6. You review and approve:** see [Reviewing the plan](#reviewing-the-plan-vulnerable-modules-step-by-step).

**Changing a decision yourself:** edit the row in `03-plan.md`, or use `plan-decide` as above, e.g.
`plan-decide … 7 "Target version=2.2"`. Re-running step 2 keeps your edit.

## Saving workflow results into the repository

Every workflow's results (its folder `workflows/wf-NNN-<repo>/`, plus `workflows/INDEX.md` and the research cache)
are **saved into this repository**: committed, then pushed to its online copy so your other machines get them too.
That's how the documentation of every upgrade lives in `snyk-update-package`, not only on one computer.

**What gets saved:** `STATUS.md`, `01-snyk-findings.md` … `06-publish.md`, `findings.md` / `.csv` / `.json`, the
analysis files, and the verification summaries. **What doesn't:** raw Snyk JSON, logs and error files (the
documents summarise them), the repo clones in `repos/`, and your personal settings.

### Step by step

**1. One-time: make this repository private.** The results name your repos and list their open vulnerabilities,
so saving **refuses to push while the repository is public**. On GitHub, open `snyk-update-package` →
**Settings** → **General** → scroll to **Danger Zone** → **Change visibility** → **Make private**. Only people you
invite (Settings → Collaborators) can then see it.

**2. Run your workflow as usual.** `/dep-run <repo>` and every step **save by themselves** when they finish or stop
for you. There's nothing extra to do.

**3. Save by hand when you want to** (for example after editing a document, or for a workflow from before saving existed):

```text
/dep-save 1                                                        in Copilot or Claude chat (1 = Workflow 1, wf-001)
```

```bash
python3 -I toolkit/scripts/workflows.py save 1                     # macOS
```

```powershell
py -3 -I toolkit\scripts\workflows.py save 1                       # Windows
```

**4. Check the result.** A successful save prints:

```text
committed 9 file(s) for wf-001
pushed workflows/wf-001-inventory-service to https://github.com/<you>/snyk-update-package.git
```

**5. Read the documentation.** On GitHub: `workflows/INDEX.md` lists every workflow, and each workflow's `STATUS.md`
links to its documents. On another machine: `git pull` in `snyk-update-package`. New workflows pull first by
themselves, so their numbers never clash with ones saved elsewhere.

### What the messages mean

| You see | Meaning | What to do |
|---------|---------|------------|
| `committed N file(s) for wf-NNN` then `pushed …` | Saved and pushed | Nothing |
| `wf-NNN: nothing new to commit` | No changes since the last save; anything not yet pushed is pushed | Nothing |
| `REFUSED: this repository is PUBLIC, …` | Nothing was committed or pushed | Step 1, then save again. Only if publishing really is intended: add `--allow-public` |
| `Note: couldn't check whether the repository is public …` | Offline, or the repo isn't on GitHub. It saves anyway | Make sure the repository is private |
| `could not sync with origin automatically …` | Someone pushed changes that conflict with yours (not just the index, which is fixed automatically) | Resolve it with `git pull --rebase` in `snyk-update-package`, then save again |
| `push failed: …` | No access to the online repo, or no network. The commit is kept locally | Fix access/network, then save again (it pushes what's waiting) |
| `this project has no git remote 'origin' …` | This copy isn't connected to an online repository | Clone it from GitHub, or save with `--no-push` to only commit |

### Options

| Option | Effect |
|--------|--------|
| `--no-push` | Commit into the repository only. Push later with `git push`, or by saving again without the option |
| `--allow-public` | Push even though the repository is public. Not recommended for real company repos |

**Your other changes are safe:** a save commits only that workflow's records. Anything else you've changed in
`snyk-update-package` stays uncommitted, exactly as it was. And it never force-pushes.

## Setting up GitHub Copilot (VS Code)

The `/dep-*` commands are ordinary files in this project (`.github/prompts`, `.github/agents`, `.github/skills`,
`.github/instructions`, `.github/copilot-instructions.md`). VS Code finds them when this folder is open; there's
nothing to install or configure in Copilot itself.

**1. Install VS Code and GitHub Copilot.** Install [VS Code](https://code.visualstudio.com/) (keep it up to date:
these features are recent), then the **GitHub Copilot** extension from the Extensions view (`Ctrl+Shift+X` /
`⌘⇧X`), which includes Copilot Chat. Sign in with the GitHub account that has your company's Copilot licence.

**2. Open this folder as the workspace.** *File → Open Folder…* and pick **`snyk-update-package` itself**, not the
folder above it, or Copilot won't find the commands. If VS Code asks *"Do you trust the authors of the files in this
folder?"*, choose **Yes, I trust the authors**.

**3. Open the chat** (`Ctrl+Alt+I` on Windows, `⌃⌘I` on macOS, or the chat icon in the title bar), then:

- set the **Session Target** control to **Local**, because the `/dep-*` slash commands only work in Local sessions;
- in the **Agent** dropdown you can also pick a command's agent directly (e.g. `dep-run`).

**4. Check the commands are there.** Type **`/dep`** in the chat box. You should see all eleven:

| Command | What it's for |
|---------|---------------|
| `/dep-run <repo>` | **Start here:** runs every step for one repo, stops for your approval |
| `/dep-login` | Log the Snyk CLI in (browser SSO) |
| `/dep-upgrade status` | Where every workflow stands |
| `/dep-save [id]` | Push a workflow's records to this repo (automatic at every stop) |
| `/dep-clone`, `/dep-scan`, `/dep-inventory`, `/dep-analyze`, `/dep-apply`, `/dep-verify`, `/dep-publish` | The steps one by one |

The three helpers (`dependency-analyst`, `upgrade-applier`, `repo-verifier`) are **meant** to be invisible: `/dep-run`
and the step commands call them by themselves.

**5. First run.**

```text
/dep-login                       sign in to Snyk once (a browser window opens)
/dep-run inventory-service       or your own repo: its name in repos/repos.txt, git URL, or a local checkout
```

- **Copilot asks before it runs a terminal command**, and every step runs the toolkit's scripts. Read the command it
  shows (it should be one of `toolkit/scripts/…`, `git …`, or a build such as `mvnw`), then allow it.
- **Buttons under a reply**, e.g. *Approve the plan and continue* or *Next: verify all repos*: clicking one only
  **fills in** the next prompt. Nothing happens until you press send. Apply and publish never start without you.
- **On Windows**, Copilot's terminal is PowerShell. The project's instructions tell it to use the `.ps1` scripts and
  `py -3`, so the commands look different from the macOS ones in this README. That's expected.

**What Copilot picks up by itself from this folder:**

| File | Effect |
|------|--------|
| `.github/copilot-instructions.md` | Project rules in every chat: changes only in `repos/<name>/` clones, never publish without you, run the tests |
| `.github/instructions/maven-dependencies.instructions.md` | Extra rules whenever Copilot edits a `pom.xml` under `repos/` |
| `.github/skills/dep-upgrade/SKILL.md` | Lets Copilot recognise upgrade requests even without a slash command |
| `.vscode/settings.json` | Copilot's search skips `target/`, `node_modules/`, `.git/` … |

### If something's missing

| Problem | Fix |
|---------|-----|
| `/dep-…` doesn't appear when you type `/` | Check the **Session Target** is **Local**, and that the open folder is `snyk-update-package` (*File → Open Folder*). Then update VS Code and the Copilot extension. If it's still missing, your organisation may have turned off custom prompts or agents: ask your Copilot admin |
| A command appears **twice** | VS Code also reads the Claude Code versions in `.claude/skills/`. Both do exactly the same; use either |
| Copilot only answers in text and never runs anything | You're not in an agent session: pick **Agent** (or a `dep-…` agent) in the dropdown, then check terminal commands aren't blocked in your settings |
| It searches inside `target/` or `node_modules/` | Reload the window (*Developer: Reload Window*) so `.vscode/settings.json` is applied |
| Commands fail on Windows with bash errors | Copilot ignored the Windows rules: tell it *"use the .ps1 scripts and py -3 (see toolkit/WORKFLOW.md)"* |

VS Code's own guides: [prompt files](https://code.visualstudio.com/docs/copilot/customization/prompt-files) ·
[custom agents](https://code.visualstudio.com/docs/copilot/customization/custom-agents) ·
[agent skills](https://code.visualstudio.com/docs/copilot/customization/agent-skills) ·
[custom instructions](https://code.visualstudio.com/docs/copilot/customization/custom-instructions).

## Setting up Claude Code

Claude Code reads this project's `.claude/` folder and `CLAUDE.md` by itself, so the `/dep-*` commands are there as
soon as you start it **in this folder**. Nothing else to configure.

**1. Install Claude Code** (once):

| | macOS | Windows |
|---|---|---|
| Install | `curl -fsSL https://claude.ai/install.sh \| bash` (or `brew install --cask claude-code`) | In PowerShell: `irm https://claude.ai/install.ps1 \| iex` (or `winget install Anthropic.ClaudeCode`). No Administrator needed |
| Check | `claude --version` | `claude --version` |

If `claude` isn't found, open a **new** terminal. On Windows, [Git for Windows](https://git-scm.com/download/win) is
recommended (you need Git for this project anyway).

**2. Start it in the project folder.** This matters: the commands and the folder restrictions are only picked up
when Claude Code starts **inside `snyk-update-package`**.

```bash
cd ~/snyk-update-package        # wherever you cloned it  (Windows: cd $HOME\snyk-update-package)
claude
```

**3. Log in to Claude** the first time: a browser window opens. Use a Claude **Pro, Max, Team or Enterprise**
account, or a **Claude Console** (API) account; the free plan doesn't include Claude Code. Later, `/login` switches
accounts.

**4. Check the commands are there.** Type **`/dep`**: autocomplete shows all eleven, with a hint for what each one
takes (e.g. `/dep-run <repo name | git URL | local checkout> …`). `/skills` lists them too.

| Command | What it's for |
|---------|---------------|
| `/dep-run <repo>` | **Start here:** runs every step for one repo, stops for your approval |
| `/dep-login` | Log the Snyk CLI in (browser SSO) |
| `/dep-upgrade status` | Where every workflow stands |
| `/dep-save [id]` | Push a workflow's records to this repo (automatic at every stop) |
| `/dep-clone`, `/dep-scan`, `/dep-inventory`, `/dep-analyze`, `/dep-apply`, `/dep-verify`, `/dep-publish` | The steps one by one |

The helpers in `.claude/agents/` (`dependency-analyst`, `upgrade-applier`, `repo-verifier`) aren't commands. Claude
starts them by itself during `/dep-analyze`, `/dep-apply`, `/dep-verify` and `/dep-run`.

**5. First run.**

```text
! bash toolkit/scripts/snyk-login.sh                                              Snyk login, macOS
! powershell -ExecutionPolicy Bypass -File toolkit\scripts\snyk-login.ps1         Snyk login, Windows
/dep-run inventory-service                                                        or your own repo
```

- **Why `!` for the Snyk login:** a line starting with `!` runs the command yourself, right in the session, and its
  output goes into the conversation. The browser login waits until you've signed in, which works best as your own
  command. `/dep-login` works too, but Claude may ask you to run exactly this.
- **Claude asks before it runs a command.** Choose *Yes*, *Yes, and don't ask again* (saved in
  `.claude/settings.local.json`, which is git-ignored), or *No*. Every step runs `toolkit/scripts/…`, `git …` or a
  build such as `mvnw`. `/permissions` shows and edits what you've allowed.
- **`/dep-run`, `/dep-apply` and `/dep-publish` only start when you type them.** Claude can't start them on its own,
  and the plan approval is always your reply.

**What Claude Code picks up by itself from this folder:**

| File | Effect |
|------|--------|
| `CLAUDE.md` | Project rules in every session: changes only in `repos/<name>/` clones, never publish without you, run the tests |
| `.claude/skills/dep-*/` | The eleven `/dep-*` commands |
| `.claude/agents/` | The three helpers |
| `.claude/settings.json` | Claude may not read or edit inside `target/`, `node_modules/`, `.git/` … under `repos/` (`/permissions` lists these rules) |

**In VS Code instead of a terminal:** the [Claude Code extension](https://code.claude.com/docs/en/vs-code)
(`anthropic.claude-code`) uses the same project files, but the `!` shortcut isn't available there. Run the Snyk login
in VS Code's terminal instead. For everything the terminal version can do, run `claude` in VS Code's terminal.

### If something's missing

| Problem | Fix |
|---------|-----|
| `claude: command not found` | Open a new terminal. Still missing: run the install command again |
| `/dep-…` doesn't appear | You started Claude Code in another folder. Quit (`/exit`), `cd` into `snyk-update-package`, run `claude` again. `/skills` should list them |
| Login problems, or "Claude Code isn't included" | Your account needs Pro, Max, Team, Enterprise or Console access. `/status` shows which account you're on, `/login` switches |
| Claude reads files inside `target/` | Check `/permissions` lists the deny rules from `.claude/settings.json`. They apply when Claude Code is started in this folder |
| Anything else odd | `/doctor` inside a session, or `claude doctor` in the terminal, checks the install and settings |

Claude Code's own guides: [setup](https://code.claude.com/docs/en/setup) ·
[skills](https://code.claude.com/docs/en/skills) · [subagents](https://code.claude.com/docs/en/sub-agents) ·
[permissions](https://code.claude.com/docs/en/permissions) · [memory / CLAUDE.md](https://code.claude.com/docs/en/memory).

## Logging in to Snyk, step by step

You do this **once per machine**. Windows users: the steps written out for PowerShell are in
**[On Windows, step by step](#on-windows-step-by-step)**. It's the same company SSO login as the VS Code extension's "Authenticate"
button, started from the toolkit, with your browser doing the sign-in. No client ID or secret needed.

**1. Make the Snyk CLI available** (skip this if `snyk --version` already works).

| | macOS | Windows (PowerShell) |
|---|---|---|
| Use the CLI the VS Code extension downloaded (path: VS Code → Settings → Snyk → Advanced → CLI path) | `export SNYK_CLI="<that path>"` | `$env:SNYK_CLI = "<that path>"` |
| …or install it | `brew tap snyk/tap && brew install snyk-cli` | `npm install -g snyk` |

**2. Start the login** from the `snyk-update-package` folder:

```bash
bash toolkit/scripts/snyk-login.sh                                           # macOS
```

```powershell
powershell -ExecutionPolicy Bypass -File toolkit\scripts\snyk-login.ps1      # Windows
```

Or type **`/dep-login`** in Copilot or Claude chat. `/dep-scan` and `/dep-run` also start it by themselves when needed.

**3. The terminal says:**

```text
Using Snyk CLI: /path/to/snyk
Opening your browser for the Snyk login (OAuth2). Sign in with your company SSO, then come back here.
If no browser opens, copy the link the Snyk CLI prints below into your browser.
```

**4. Sign in, in the browser window that opens.** Choose your company's SSO option on the Snyk page (often "Log in
with SSO", where you enter your work email), then sign in as usual: your password, plus MFA if your company uses it.
Your password goes only to your company's sign-in page, never to the toolkit or the terminal.

**5. When the browser says you're signed in, close the tab and go back to the terminal.** It finishes with:

```text
Logged in to Snyk as you@company.com
```

**6. Check it any time:**

```bash
bash toolkit/scripts/snyk-login.sh --status                                          # macOS
```

```powershell
powershell -ExecutionPolicy Bypass -File toolkit\scripts\snyk-login.ps1 --status     # Windows
```

That's it. The CLI keeps a token that renews itself, so scans just work from now on. You only sign in again after
`--logout`, or if your company's SSO policy ends the session.

### On Windows, step by step

The same login, written out for **Windows PowerShell** (built into Windows; PowerShell 7 works the same).
Run everything from the `snyk-update-package` folder.

**1. Open PowerShell in the project folder.** Start menu → *Windows PowerShell* (or Windows Terminal), then:

```powershell
cd $HOME\snyk-update-package          # wherever you cloned it
```

In VS Code, the built-in terminal (`` Ctrl+` ``) is PowerShell by default and opens in the project folder.

**2. Check whether a Snyk CLI is already there:**

```powershell
Get-Command snyk -ErrorAction SilentlyContinue
```

- **It prints a path:** skip to step 4.
- **Nothing printed, but you use the Snyk VS Code extension:** go to step 3a. The extension has already downloaded a CLI.
- **Nothing printed, no extension:** go to step 3b.

**3a. Point the toolkit at the extension's CLI.** In VS Code: *File → Preferences → Settings*, search for
**`snyk cli path`**, and copy the path shown (it ends in `.exe`, e.g. `...\snyk-win.exe`). Then save it for your
user, so every new window has it:

```powershell
[Environment]::SetEnvironmentVariable("SNYK_CLI", "C:\path\from\settings\snyk-win.exe", "User")
$env:SNYK_CLI = [Environment]::GetEnvironmentVariable("SNYK_CLI", "User")   # also use it in this window
Test-Path $env:SNYK_CLI                                                      # must print True
```

Keep the quotes: the path often contains spaces. **Restart VS Code** afterwards so its terminals and Copilot see the
new variable. The usual download folders under `%LOCALAPPDATA%` and `%APPDATA%` are also searched automatically,
so this step is sometimes not needed. The login script prints `Using Snyk CLI: …` either way.

**3b. Or install the CLI** (needs Node.js: `winget install OpenJS.NodeJS.LTS`, then a new PowerShell window):

```powershell
npm install -g snyk
snyk --version
```

**4. Start the login:**

```powershell
powershell -ExecutionPolicy Bypass -File toolkit\scripts\snyk-login.ps1
```

`-ExecutionPolicy Bypass` allows just this script to run, without changing any Windows setting. You'll see:

```text
Using Snyk CLI: C:\...\snyk-win.exe
Opening your browser for the Snyk login (OAuth2). Sign in with your company SSO, then come back here.
If no browser opens, copy the link the Snyk CLI prints below into your browser.
```

**5. Sign in, in the browser that opens** (your default browser, e.g. Edge). Choose your company's SSO option on
the Snyk page and sign in as usual, with MFA if your company uses it. When the page says you're signed in, close the
tab and go back to PowerShell. It finishes with:

```text
Logged in to Snyk as you@company.com
```

**6. Check it any time:**

```powershell
powershell -ExecutionPolicy Bypass -File toolkit\scripts\snyk-login.ps1 --status
```

You're done. Scans (`/dep-scan`, `/dep-run`, or `snyk-scan.ps1`) now use this login, and the CLI renews it by itself.

| Windows problem | Fix |
|-----------------|-----|
| `... cannot be loaded because running scripts is disabled on this system` | You ran `.\toolkit\scripts\snyk-login.ps1` directly. Use the `powershell -ExecutionPolicy Bypass -File ...` form from step 4 |
| `Snyk CLI not found` right after step 3a or 3b | The window was opened before the change. Open a **new** PowerShell window, or restart VS Code |
| `SNYK_CLI is set to '...', but that is not an executable file` | The path is wrong or missing its quotes. Run `Test-Path $env:SNYK_CLI` and redo step 3a |
| `npm : The term 'npm' is not recognized` | Install Node.js (step 3b), then open a new window |
| Windows / your antivirus blocks `snyk-win.exe` | Use the CLI the VS Code extension downloaded (step 3a), or ask IT to allow the Snyk CLI |
| The browser opens but the sign-in page won't load | Your company network may need a proxy. Set it for this window (`$env:HTTPS_PROXY = "http://proxy:port"`, ask IT for the address), then step 4 again |
| `Note: SNYK_TOKEN / SNYK_OAUTH_TOKEN is set in this shell, Snyk rejects it, ...` | `Remove-Item Env:SNYK_TOKEN, Env:SNYK_OAUTH_TOKEN -ErrorAction SilentlyContinue`, and remove it from your user variables too, then step 4 |
| `Snyk login did not complete. ...` | Run step 4 again. If it keeps failing, ask your Snyk admin to check that SSO login is enabled for you |

### What the messages mean

| You see | Meaning | What to do |
|---------|---------|------------|
| `Logged in to Snyk as …` | Snyk accepted the login | Nothing: you're done |
| `Already logged in to Snyk as … - nothing to do` | You were already logged in; no browser opened | Nothing |
| `Not logged in to Snyk - run: …` | (`--status`) No valid login | Run step 2 |
| `Snyk login did not complete. …` | The sign-in was cancelled, timed out, or SSO isn't set up for you | Run step 2 again. If it keeps failing, ask your Snyk admin to check that SSO login is enabled for your account |
| `Note: SNYK_TOKEN / SNYK_OAUTH_TOKEN is set in this shell, Snyk rejects it, …` | An old or wrong token in your environment overrides the login | Remove it (`unset SNYK_TOKEN` on macOS, `Remove-Item Env:SNYK_TOKEN` on Windows), then step 2 |
| `Snyk CLI not found. …` | Step 1 isn't done | Do step 1 |

**How the toolkit knows you're logged in:** it doesn't guess. It runs `snyk whoami`, which sends the stored token to
Snyk. Only if Snyk answers with your username does it count as logged in, so an expired or revoked login is caught
before a scan starts.

### Special cases

| Situation | Do this |
|-----------|---------|
| **No browser opens** (e.g. remote desktop) | Copy the link the CLI prints into any browser and sign in there |
| **Your Snyk is in another region** (EU / AU) or a private instance | Run step 2 with `--endpoint <url>` once, e.g. `--endpoint https://api.eu.snyk.io`. Get the exact URL from your Snyk admin |
| **Automation / build machine** (no person to sign in) | With a Snyk service account (Enterprise plan), set `SNYK_CLIENT_ID` and `SNYK_CLIENT_SECRET`, then run step 2: it logs in without a browser |
| **Log out** | `--logout` on the same command |
| **Sign in again anyway** | `--force` on the same command |

## Saving tokens

The toolkit is set up to keep the assistants' context small, and you can help.

**Already done for you:**

- **Scripts print summaries, not raw output:** Maven's output goes to `build.log`, a build ends in a ~20-line
  summary, Snyk's raw JSON is condensed into `findings.md`, and the tests print a line of dots.
- **The assistants are told not to open the big files:** raw Snyk JSON, whole build logs, the whole dependency tree.
  They use the summaries and the `first-errors` helper instead (*Token budget* in `toolkit/WORKFLOW.md`).
- **Migration research happens once per upgrade jump.** E.g. "Spring Boot 3.3 → 4.1" is saved in
  `workflows/_research/` and reused by every later workflow and repo, instead of fetching the same guides again.
- **Searches skip `target/`, `node_modules/`, `.git/` …**, and the assistants find code with `git grep`.
- **The verify helper runs on a smaller model** (Claude: Haiku). It only runs a script and reads a summary.
- **State lives in files** (`STATUS.md` and the numbered documents), so no step needs the earlier conversation.
- **The plan is built by script:** the modules are inserted and pre-filled from Snyk, the assistant reads a
  one-line-per-module index, sets decisions for groups at once, and `plan-check` confirms nothing is open
  ([how](#how-the-plan-is-built-fast-step-by-step)).

**Habits that help:**

| Do | Why |
|----|-----|
| **Start a fresh chat after each stop** (after the plan, after verification), then `/dep-run <repo>` again | It resumes from `STATUS.md`, so you lose nothing and the new chat starts small. Copilot: *New Chat* (`+`). Claude Code: `/clear` |
| **One repo per `/dep-run`** | Each workflow stays small, and the research cache makes the second repo much cheaper than the first |
| **Ask "where are we?" with `/dep-upgrade status`**, or open `workflows/INDEX.md` | Cheaper than asking the assistant to re-read documents |
| **Don't ask it to paste logs or whole files** into the chat | Open the linked file yourself, or ask for the part you need |
| **Claude Code: `/context`** shows what fills the context, **`/compact`** shrinks a long session | Useful in a long `/dep-run` |

## The commands

| Command | What it does | Creates (in `workflows/<id>/`) | Changes your repos? |
|---------|--------------|-------------------------------|---------------------|
| `/dep-clone [git-url \| checkout \| name]` | Adds repos to `repos/repos.txt` (by URL) and clones them into `repos/<name>/`. In a workflow, puts each clone on `deps/<id>` from the latest main; refuses if another workflow's unpublished changes are there | `STATUS.md` repos table | clones; switches the clone's branch |
| `/dep-scan [snyk.json]` | Runs Snyk on every repo in the list (or reads your export). Lists **every** flagged package: current version, severity, CVEs, fixed-in version, which dependency brings it in, how to fix it. Groups them into the few changes you actually make | `01-snyk-findings.md`, `snyk/findings.csv` | no |
| `/dep-inventory <id>` | For the packages in scope: the version each repo really uses, what sets it (parent/BOM/property), everything else that changes with it, coupled libraries (e.g. Camel). Builds each repo as a **baseline** | `02-inventory.md`, `facts/`, `verification/baseline/` | no |
| `/dep-analyze <id>` | Subagents read the official migration guides and search your code, config and tests. Each finding cites `file:line` and a source. Writes an ordered plan with exact diffs | `03-impact.md`, `analysis/`, `03-plan.md` | no |
| *you approve* | Reply "approve" (or click the button). Your words and the date are recorded | `STATUS.md` | — |
| `/dep-apply <id>` | Applies the plan in each clone on `deps/<id>` and compiles after every step. Never commits | `04-apply-log.md` | **edits files** in the clone, on its branch |
| `/dep-verify <id>` | Full build, all tests and app boot for every repo, plus a Snyk re-scan. Each failure is marked regression, already-failing or environment | `05-verification.md`, `verification/after/` | no |
| `/dep-publish <id>` | Commits, pushes `deps/<id>`, opens a PR per repo with a description built from the docs | `06-publish.md` | **commits, pushes, opens PRs** |
| `/dep-run <repo> [id] [reply]` | **Autopilot:** every step for one repo, stopping only for your approval, blockers, and before publish | everything up to `05-verification.md` | only after you approve the plan |
| `/dep-save [id]` | Commits and pushes a workflow's records to this repo (automatic at every stop) | — | no (pushes **this** repo) |
| `/dep-upgrade [status \| id]` | Shows where every workflow stands, or runs one next step | `STATUS.md` | — |
| `/dep-verify baseline` | Health check of all repos, outside any upgrade | `workflows/_health/` (git-ignored) | no |

## What you get per workflow run

Each run has its own folder, named after its id. Two runs never share files:

```text
workflows/
├── INDEX.md                ← every run: id, title, current step, ▶ next step (auto-generated)
├── wf-001-spring-boot-4-1/ ← Workflow 1
└── wf-002-jackson-fix/     ← Workflow 2 (example)
```

Inside one run's folder:

```text
workflows/wf-001-spring-boot-4-1/
├── STATUS.md               ← start here: step tracker, ▶ next step, repos, decisions, timestamped History
├── 01-snyk-findings.md     every flagged package, the changes (upgrade / override), every dependency path
├── 02-inventory.md         current vs target, what moves with it, coupled libraries, baseline
├── 03-impact.md            what breaks, where (file:line), with sources
├── 03-plan.md              every vulnerable module itemized + decision, ordered steps, path coverage, out of scope, approval
├── 04-apply-log.md         what changed per step, deviations from the plan
├── 05-verification.md      build/test/boot results per repo, before vs after, verdict
├── 06-publish.md           commits and PR links
├── snyk/                   raw Snyk JSON per repo, findings.{md,csv,json}, vulnerable-modules.md, module-index.md
├── facts/<repo>/           resolved dependency tree, declared deps, version properties
├── analysis/<repo>--<artifact>.md   full report from each analyst subagent
└── verification/{baseline,after}/<repo>/summary.json, diagnosis.md
```

## Files in this project

| Path | What it is | Edit it? |
|------|------------|----------|
| `repos/repos.txt` | The list of repos to fix (git URLs). Ships with commented-out examples only | **yes**, this is your list (see the note below) |
| `repos/README.md` | How to add repos (local vs URL), check, clone, refresh and remove them | — |
| `repos/<name>/` | Clones of repos listed by URL (git-ignored, never committed here) | no, managed by `/dep-clone` |
| `workflows/wf-NNN-<slug>/` | One folder per workflow run (Workflow 1 = `wf-001`, …). **Pushed to this repo** by `/dep-save` (automatic at every stop), raw Snyk JSON and logs excluded | generated, review it |
| `workflows/INDEX.md` | All runs with their current step and next step. Pushed with the records | no, rebuilt automatically |
| `workflows/README.md` | How workflow ids and folders work | — |
| `toolkit/WORKFLOW.md` | Overview the assistants read first: phases, gates, rules | to change behaviour |
| `toolkit/RUN.md` | What `/dep-run` does: step order, when it continues, when it stops, its final reply | to change behaviour |
| `toolkit/phases/0-clone.md … 6-publish.md` | Step-by-step procedure for each command | to change behaviour |
| `toolkit/roles/*.md` | The three subagents: `dependency-analyst`, `upgrade-applier`, `repo-verifier` | to change behaviour |
| `toolkit/templates/*.md` | Blank templates for each document above | to change doc layout |
| `toolkit/scripts/repos.py` | Add / check+clone / list / status of target repos | — |
| `toolkit/scripts/workflows.py` | Workflow ids: new run, resolve `1`→folder, step states, history, index | — |
| `toolkit/scripts/*.ps1`, `common.ps1` | PowerShell twins of the `.sh` scripts (Windows PowerShell 5.1 and 7), same arguments and outputs | when you change its `.sh` twin |
| `toolkit/scripts/script-helpers.py` | Parsing shared by the bash and PowerShell scripts (JUnit, pom.xml, summary.json) | — |
| `toolkit/scripts/snyk-login.sh` / `.ps1`, `snyk-common.sh` / `.ps1` | OAuth2 login for the Snyk CLI (browser SSO or service account), and the CLI lookup shared with the scan | — |
| `toolkit/LOGIN.md` | What `/dep-login` does (and what `/dep-scan` / `/dep-run` do when the CLI isn't logged in) | to change behaviour |
| `toolkit/ignore-dirs.txt` | Folders never searched, scanned or edited in a repo: `target/`, `build/`, `node_modules/`, `.git/`, IDE folders … | to add a folder (then re-run the generator) |
| `.vscode/settings.json`, `.claude/settings.json` | Keep Copilot's search and Claude's reads/edits out of those folders (**generated** from `ignore-dirs.txt`) | no, regenerate |
| `toolkit/scripts/snyk-scan.sh` | Snyk scan of every repo in the list | — |
| `toolkit/scripts/parse-snyk.py` | Snyk JSON → findings tables + CSV | — |
| `toolkit/scripts/maven-facts.sh` | What a repo's pom really resolves | — |
| `toolkit/scripts/verify-repo.sh` / `.ps1` | Build → tests → boot → `summary.json` (bash / Windows PowerShell, same arguments and output) | — |
| `.github/prompts/`, `.github/agents/` | Copilot slash commands and agents (**generated**) | no, edit `toolkit/` and regenerate |
| `.github/skills/dep-upgrade/SKILL.md`, `.github/copilot-instructions.md`, `.github/instructions/` | Copilot context and pom-editing rules | rarely |
| `.claude/skills/`, `.claude/agents/`, `CLAUDE.md` | Claude Code commands and subagents (**generated**, except `CLAUDE.md`) | no, regenerate |
| `tools/generate-entrypoints.py` | Regenerates the Copilot and Claude files from one spec | when adding a command |
| `docs/ARCHITECTURE.md` | Architecture diagrams (Mermaid, rendered by GitHub) | when the design changes |
| `tests/` | Automated tests for every script and command (`tests/run.sh`, `tests\\run.ps1`), run locally | when changing behaviour |
| `.gitattributes` | Keeps LF line endings on Windows checkouts, so the bash scripts keep working | no |

**What goes to GitHub:** the toolkit, and your **workflow records** (`workflows/`), pushed by `/dep-save` so the
documentation is in this repo, not only on one machine. Never pushed: the clones (`repos/<name>/`), raw Snyk JSON,
logs, and your personal settings. `repos/repos.txt` is tracked so the project ships an example. Once you add your own
repos to it, don't commit it (`git status` shows it as modified), or keep it uncommitted with
`git update-index --skip-worktree repos/repos.txt`.

To change how a step works, edit its file in `toolkit/phases/`. Both assistants pick it up immediately.
To add or rename a command, or change a handoff button, edit `tools/generate-entrypoints.py`, then run
`python3 -I tools/generate-entrypoints.py`.

## The scripts work without an assistant too

macOS / Linux:

```bash
python3 -I toolkit/scripts/repos.py clone                          # clone/refresh every repo into repos/
python3 -I toolkit/scripts/repos.py status                         # branch, dirty, ahead/behind
bash toolkit/scripts/snyk-scan.sh /tmp/snyk                        # scan every repo
python3 -I toolkit/scripts/parse-snyk.py /tmp/snyk/*.json --md findings.md --csv findings.csv
bash toolkit/scripts/verify-repo.sh repos/inventory-service/backend /tmp/verify --smoke
```

Windows (PowerShell). Same scripts and arguments, `.ps1` instead of `.sh`, `py -3` instead of `python3`:

```powershell
py -3 -I toolkit\scripts\repos.py clone
py -3 -I toolkit\scripts\repos.py status
powershell -ExecutionPolicy Bypass -File toolkit\scripts\snyk-scan.ps1 $env:TEMP\snyk
py -3 -I toolkit\scripts\parse-snyk.py (Get-ChildItem $env:TEMP\snyk\*.json) --md findings.md --csv findings.csv
powershell -ExecutionPolicy Bypass -File toolkit\scripts\verify-repo.ps1 repos\inventory-service\backend $env:TEMP\verify --smoke
```

## Testing: are the commands doing the right job?

The tests run **locally**, on your machine. There's nothing to set up on GitHub.

| | macOS / Linux | Windows (PowerShell) |
|---|---|---|
| Run all tests | `tests/run.sh` | `powershell -ExecutionPolicy Bypass -File tests\run.ps1` |
| Also a real Maven build | `RUN_MAVEN_TESTS=1 tests/run.sh` | `$env:RUN_MAVEN_TESTS = "1"; powershell -ExecutionPolicy Bypass -File tests\run.ps1` |
| Test the `.ps1` scripts with PowerShell 7 instead of 5.1 | (uses `pwsh` if installed) | `$env:SUP_PS = "pwsh"` first |

The tests run in **throwaway sandboxes** with fake git remotes, a fake `HOME` and a fake `snyk` CLI. They never touch
your real repos or GitHub, and never apply an upgrade.

**Every script test runs twice: against the bash version and against its PowerShell twin.** If a fix lands in only
one of them, the other version's test goes red. On Windows the bash runs are skipped. On a Mac, the PowerShell runs
need `pwsh` (`brew install powershell`); without it they're skipped.

### Running the tests on Windows, step by step

**1. Check the tools.** Open **Windows PowerShell** (Start menu → "Windows PowerShell", or Windows Terminal) and run:

```powershell
git --version        # any recent Git for Windows
py -3 --version      # Python 3.9 or newer
java -version        # Java 17+ (the version your repos use)
javac -version       # optional: a full JDK runs 3 extra app-boot tests
```

If one says *"is not recognized"*, install it (see [Quick start](#quick-start), step 1), then **open a new PowerShell
window** so it picks up the new PATH.

**2. Get the latest project.**

```powershell
git clone https://github.com/elinasarvari/snyk-update-package.git    # first time
cd snyk-update-package
git pull                                                              # every time after that
```

**3. Run the tests** from the `snyk-update-package` folder. It takes 1–3 minutes:

```powershell
powershell -ExecutionPolicy Bypass -File tests\run.ps1
```

`-ExecutionPolicy Bypass` lets this one run use the scripts without changing any Windows setting.

**4. Read the result**, on the last lines:

| You see | Meaning |
|---------|---------|
| `Ran … tests in …s` then **`OK (skipped=…)`** | **Everything works.** On Windows the skipped ones are the bash versions of the script tests (bash isn't used on Windows) and the real-Maven test (step 5). The exact numbers grow as tests are added |
| `OK`, with 3 more skipped than usual | Also fine: `javac` wasn't found, so the 3 app-boot tests were skipped. Install a JDK to run them |
| `FAILED (failures=…, errors=…)` | Something doesn't work on this machine. Each problem is listed above as a line starting with **`FAIL:`** or **`ERROR:`**, followed by the details |

**5. Optional extra runs:**

```powershell
$env:RUN_MAVEN_TESTS = "1"; powershell -ExecutionPolicy Bypass -File tests\run.ps1   # + a real Maven build (needs mvn and internet the first time)
$env:SUP_PS = "pwsh";       powershell -ExecutionPolicy Bypass -File tests\run.ps1   # test the .ps1 scripts with PowerShell 7 instead of 5.1
Remove-Item Env:RUN_MAVEN_TESTS, Env:SUP_PS -ErrorAction SilentlyContinue           # back to normal
```

**6. Something failed? Save the output to share it:**

```powershell
powershell -ExecutionPolicy Bypass -File tests\run.ps1 2>&1 | Tee-Object -FilePath test-results.txt
```

You still see the output on screen, and `test-results.txt` holds a copy (it isn't committed). Send the
`FAIL:` / `ERROR:` blocks, or the whole file.

| Problem | Fix |
|---------|-----|
| `py : The term 'py' is not recognized` | Reinstall Python from python.org with **"py launcher"** and **"Add python.exe to PATH"** ticked, then open a new window |
| `… cannot be loaded because running scripts is disabled on this system` | You ran `.\tests\run.ps1` directly. Use the `powershell -ExecutionPolicy Bypass -File …` form above |
| `git : The term 'git' is not recognized` | Install Git for Windows, then open a new window |
| Many `ERROR:` lines mentioning `bash` | Should not happen on Windows (bash tests are skipped). Send the output |
| Very slow, or files "in use" | Antivirus scanning the temporary test folders. Run it again, or ask IT to exclude `%TEMP%\sup-test-*` |

### What the tests check

| Test file | Proves |
|-----------|--------|
| `test_repos.py` | Repos are cloned into `repos/` and refreshed only when clean. **Each workflow gets `deps/wf-NNN` from the latest main**, workflows don't overwrite each other's unpublished work, `release` returns to main. **Your own checkout is never touched** (branch, commit, files). No submodules; clones are never committed |
| `test_workflows.py` | Workflow 1 = `wf-001`, Workflow 2 = `wf-002`, **ids never reused**. `1` / `wf-001` / folder name all resolve. Step states, next step, History and INDEX update correctly |
| `test_snyk.py` | Every flagged package listed once with **every dependency path and the fix for each path** (upgrade / override / none, Snyk's remediation section), severity totals, grouping by the dependency you edit, licence/no-fix rows, CSV. **Both scan scripts** handle a missing or not-logged-in CLI, `SNYK_CLI`, the VS Code extension's CLI and SSO logins, and scan each clone (or one workflow's repos) |
| `test_build_scripts.py` | **Both versions** of verify-repo and maven-facts: build results from JUnit files, failing tests named, build tool auto-detected (`mvnw` / `mvnw.cmd`), smoke boot catches "APPLICATION FAILED TO START", nothing left in the repo, Maven facts right |
| `test_clone_hygiene.py` | End to end, with bash and with PowerShell: clone → scan → build leaves the clone with **no changed files and no commits**; all evidence lands in `workflows/<id>/` |
| `test_ignore_dirs.py` | `target/`, `node_modules/`, `.git/` … are skipped by both shells' Snyk scan and pom discovery, don't count as uncommitted work, and are excluded in the Copilot and Claude settings |
| `test_snyk_login.py` | **Both login scripts:** browser OAuth2 when logged out, nothing when already logged in, service-account client credentials **without ever printing or saving the secret**, `--status`, `--logout`, `--endpoint`, failed logins, and that a scan without a login points to it |
| `test_wiring.py` | Every `/dep-*` command exists for Copilot **and** Claude and points at files that exist. Every `.sh` has a `.ps1` twin with the same options, every `.ps1` parses and avoids PowerShell-7-only syntax. **`/dep-apply`, `/dep-publish` and `/dep-run` can only be started by you**, and the approval gate is in place |

What tests can't check is the AI's judgement inside a step, e.g. how good an impact analysis is. That's why
every document must cite `file:line` or a source URL, and why nothing changes your code without your approval.

## Guard rails

- **Never into build output or dependencies.** `target/`, `build/`, `node_modules/`, `.git/`, IDE folders and the rest of
  [`toolkit/ignore-dirs.txt`](toolkit/ignore-dirs.txt) are skipped by the Snyk scan (`--exclude`), by pom discovery, by
  Copilot's search and by Claude's read/edit permissions, and the assistants search with `git grep` (tracked files only).
- **Read-only until you approve.** Clone, scan, inventory, analyze and verify never edit your code.
- **Approval is yours.** The plan's approval box is ticked only after you approve in chat.
- **Branches, not main.** Changes go to `deps/<id>` in the clone under `repos/`. Nothing is committed until `/dep-publish`.
  Nothing is pushed to a default branch or force-pushed.
- **Your work is safe.** Your own checkouts are never touched. A clone with another workflow's unpublished changes is never switched or overwritten.
- **Red stays red.** Tests are never skipped or disabled to get a green build.
- **Manual-only steps.** `/dep-apply` and `/dep-publish` only run when you invoke them (Claude: can't be
  auto-triggered; Copilot: handoff buttons you have to send).

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `/dep-*` commands don't appear | Open **this folder** as the workspace root. Copilot: Session Target **Local**, see [Setting up GitHub Copilot](#setting-up-github-copilot-vs-code). Claude Code: start `claude` inside this folder, see [Setting up Claude Code](#setting-up-claude-code) |
| Clone fails for a private repo | Your git credentials/SSH key must have access: test with `git clone <url>` |
| `snyk-scan.sh` exits 127 | No CLI found: set `SNYK_CLI` to the path from the VS Code extension's settings, or install it (see Quick start) |
| `snyk-scan.sh` exits 126 | Not logged in: run `snyk-login.sh` / `snyk-login.ps1` (or `/dep-login`); a browser opens for your SSO sign-in |
| The login says "did not complete" | Sign-in was cancelled or SSO isn't enabled for you: run it again, or ask your Snyk admin |
| The scan uses a different CLI than expected | It prints `Using Snyk CLI: <path>`. `SNYK_CLI` always wins over `snyk` on your PATH |
| Snyk reports a different version than the inventory | Expected when the scan ran on another branch. See *Discrepancies* in `02-inventory.md` |
| `/dep-clone` says "kept as is" or "expected main" | That repo has local changes or is on another branch. That's intentional: switch or commit yourself if needed |
| `save` says `REFUSED: this repository is PUBLIC` (see [Saving workflow results](#saving-workflow-results-into-the-repository)) | Make the repo private on GitHub (*Settings → General → Danger Zone → Change visibility*), then `/dep-save <id>` again |
| `/dep-run` or `/dep-clone` says BLOCKED | Another workflow's changes in that clone aren't published yet. Publish or abandon that workflow, then run again |
| Build red only when repos build in parallel | Shared `~/.m2` download clash. Re-run that repo: `/dep-verify <id> <repo>` |
| `/dep-publish` stops | `gh auth status` must pass. For Bitbucket/GitLab it pushes and gives you the PR link instead |
