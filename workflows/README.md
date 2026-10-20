# workflows/: one folder per workflow run

Each run gets the next **unique id** and its own folder. Ids are never reused (`workflows/.last-id` remembers the
highest), and you can refer to a run as `1`, `wf-001` or its folder name. [`INDEX.md`](INDEX.md) lists every run
with its current step and ▶ next step; it's rebuilt automatically.

| Run | Id | Folder | Branch in each repo |
|-----|----|--------|---------------------|
| Workflow 1 | `wf-001` | `workflows/wf-001-<slug>/` | `deps/wf-001` |

The records are pushed to this repository at every stop (`/dep-save`; raw Snyk JSON, logs and error files are left
out), and saving refuses while the repository is public.

## Inside a run's folder

| File | Written by | Contains |
|------|------------|----------|
| `STATUS.md` | every step | **Start here.** Step tracker, ▶ next step, repos, decisions, timestamped History |
| `01-snyk-findings.md` | scan | Every flagged package, the changes to make, links to the full tables in `snyk/` |
| `02-inventory.md` | inventory | Current vs target, what sets each version, what moves with it, coupled libraries, baseline |
| `03-impact.md` | analyze | What breaks and where (`file:line`), with sources |
| `03-plan.md` | analyze | Every vulnerable module with its decision, the ordered steps, path coverage, out of scope, your approval |
| `04-apply-log.md` | apply | What changed per step, and any deviation |
| `05-verification.md` | verify | Build, tests, boot and Snyk before vs after; every module ✅ / ➖ / ⛔; the verdict |
| `06-publish.md` | publish | Commits and PR links |
| `snyk/` | scan | `findings.{md,csv,json}`, `vulnerable-modules.md`, `module-index.md` (raw JSON stays local) |
| `facts/<repo>/`, `analysis/`, `verification/{baseline,after}/<repo>/` | inventory, analyze, verify | The evidence behind the documents |

Migration research is cached in `workflows/_research/` and reused by later runs.

```bash
python3 -I toolkit/scripts/workflows.py list         # every run and its step
python3 -I toolkit/scripts/workflows.py resolve 1    # the folder of Workflow 1
```
