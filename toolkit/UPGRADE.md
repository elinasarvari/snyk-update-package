# /dep-upgrade: show where workflows stand, or run one next step

Read `toolkit/WORKFLOW.md` first (rules, tracking, token budget). This file is only needed by `/dep-upgrade`.

## Steps

1. **Which upgrade?**
   - `status` or an existing workflow id → resume it.
   - a git URL, or a local checkout (used only to find its URL) → run phase 0 to add it, then continue as a new upgrade.
   - a Snyk JSON path, pasted Snyk output, or "scan" → new upgrade starting at phase 1.
   - `group:artifact X->Y` pairs → new upgrade starting at phase 2 (phase 1 = "skipped — manual").
   - no argument → show `workflows.py list` and `repos.py status`, then ask which.
2. **New workflow:** `python3 -I toolkit/scripts/workflows.py new <slug> --title "<title>" --source "<source>"`. It allocates the next
   unique id (`wf-001`, `wf-002`, ... never reused) and creates `workflows/<id>-<slug>/STATUS.md`. Make sure
   phase 0 is done (every repo folder in the manifest exists) before phases 1–5.
3. **Resume:** read `STATUS.md`, run the first phase not ✅. **Gates:** phase 4 needs `03-plan.md`
   to contain `- [x] Approved by user`, ticked only after the user approves in chat. Phases 4 and
   6 run only when the user asks for them explicitly.
4. **One phase per run** by default; continue only if the user asks, and never past a gate.
5. **End every run** by updating STATUS (state, date, ▶ Next step) and replying with what was
   produced (links), the headline findings, and **▶ Next step**: one concrete command or decision.

