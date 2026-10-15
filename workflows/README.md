# workflows/: one folder per workflow run

Every time you start the `/dep-*` workflow, the run gets the next **unique id** and its own folder:

| Run | Id | Folder | Branch it creates in each repo |
|-----|----|--------|--------------------------------|
| Workflow 1 | `wf-001` | `workflows/wf-001-<slug>/` | `deps/wf-001` |
| Workflow 2 | `wf-002` | `workflows/wf-002-<slug>/` | `deps/wf-002` |

- **Ids are never reused.** Even if you delete a folder, the next run gets a new number
  (`workflows/.last-id` remembers the highest one).
- **Refer to a run however you like:** `1`, `wf-1`, `wf-001`, or the folder name, e.g. `/dep-inventory 1`.
- **[INDEX.md](INDEX.md) lists every run** with its current step and ▶ next step. It's rebuilt
  automatically; don't edit it.

## Inside each run's folder

| File | Written by | Contains |
|------|------------|----------|
| `STATUS.md` | every step | **Start here.** Step tracker, ▶ next step, repos, decisions, and a timestamped **History** of everything that happened |
| `01-snyk-findings.md` | `/dep-scan` | Every package Snyk flags |
| `02-inventory.md` | `/dep-inventory` | Current vs target versions, what moves with them, baseline build |
| `03-impact.md`, `03-plan.md` | `/dep-analyze` | What breaks and where; the step-by-step plan you approve |
| `04-apply-log.md` | `/dep-apply` | What changed |
| `05-verification.md` | `/dep-verify` | Build, tests and boot, before vs after |
| `06-publish.md` | `/dep-publish` | Commits and PR links |
| `snyk/`, `facts/`, `analysis/`, `verification/` | the steps above | The raw evidence behind each document |

## From the terminal

```bash
python3 -I toolkit/scripts/workflows.py list            # all runs, current step
python3 -I toolkit/scripts/workflows.py resolve 1       # folder of Workflow 1
python3 -I toolkit/scripts/workflows.py new my-slug --title "..."   # start a run by hand
```
