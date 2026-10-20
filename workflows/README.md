# workflows/: one folder per workflow run

Each run gets the next **unique id** and its own folder. Ids are never reused (`workflows/.last-id` remembers the
highest), and you can refer to a run as `1`, `wf-001` or its folder name. [`INDEX.md`](INDEX.md) lists every run
with its current step and ▶ next step; it's rebuilt automatically.

| Run | Id | Folder | Branch in each repo |
|-----|----|--------|---------------------|
| Workflow 1 | `wf-001` | `workflows/wf-001-<slug>/` | `deps/wf-001` |

The records are pushed to this repository at every stop (`workflows.py save`; raw Snyk JSON, logs and error files are left
out), and saving refuses while the repository is public.

## Inside a run's folder

| File | Written by | Contains |
|------|------------|----------|
| `STATUS.md` | every step | **Start here.** Step tracker, ▶ next step, repos (with each commit and PR link), decisions, timestamped History |
| `01-snyk-findings.md` | scan | Every flagged package, the changes to make, links to the full tables in `snyk/` |
| `02-plan.md` | plan | **Versions** (current vs Snyk's target, what sets each, what moves with it, coupled libraries, baseline), **Impact** (what breaks and where, `file:line`, with sources), the ordered **steps**, every vulnerable module with its decision, path coverage, out of scope, your approval |
| `03-apply-log.md` | apply | What changed per step, and any deviation |
| `04-verification.md` | verify | Build, tests, boot and Snyk before vs after; every module ✅ / ➖ / ⛔; each failure diagnosed; the verdict |
| `snyk/` | scan | `findings.{md,csv,json}`, `vulnerable-modules.md`, `module-index.md` (raw JSON stays local) |
| `facts/<repo>/`, `analysis/`, `verification/{baseline,after}/<repo>/`, `publish/` | plan, verify, publish | The evidence behind the documents, and each PR's description |

Migration research is cached in `workflows/_research/` and reused by later runs.

```bash
python3 -I toolkit/scripts/workflows.py list         # every run and its step
python3 -I toolkit/scripts/workflows.py resolve 1    # the folder of Workflow 1
```
