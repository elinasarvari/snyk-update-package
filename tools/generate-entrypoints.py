#!/usr/bin/env python3
"""Generate the thin Copilot (.github) and Claude Code (.claude) entry points from one spec.

The real instructions live in toolkit/. Re-run after changing a phase list, description or
handoff:  python3 -I tools/generate-entrypoints.py
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
q = json.dumps  # JSON strings are valid YAML double-quoted strings - no quoting surprises

RO = ["read", "search", "web/fetch", "execute/runInTerminal", "execute/getTerminalOutput", "edit/editFiles", "todo"]

PHASES = [
    # name, phase file, description, argument hint, subagents, manual-only, handoffs [(label, agent, prompt)]
    # phase file: a name in toolkit/phases/ or a path starting with toolkit/.
    ("dep-run", "toolkit/RUN.md",
     "Autopilot for ONE repo (name, git URL, or a local checkout to take the URL from): opens or resumes its workflow (wf-NNN), works in its clone under repos/ on branch deps/wf-NNN, and runs every step - clone, Snyk scan, plan - then stops for your approval; after you approve, applies and verifies, then stops before publish. Always ends with what to do next. '/dep-run status' shows where every workflow stands.",
     "<repo name | git URL | local checkout | status> [workflow id] [snyk.json] [your reply: approve | scope: ... | decision]",
     ["dependency-analyst", "upgrade-applier"], True,
     [("Approve the plan and continue", "dep-run", "I have reviewed 02-plan.md for this workflow and approve it as written. Continue: apply and verify."),
      ("Publish the PRs", "dep-publish", "Verification is green. Commit, push and open PRs for this workflow."),
      ("Where does it stand?", "dep-run", "status")]),
    ("dep-scan", "1-scan.md",
     "Step 1 - run Snyk over every repo in the list (or parse supplied Snyk JSON / pasted output; logs the CLI in with your SSO if needed) and document EVERY flagged package: current version, severity, CVEs, fixed-in, how it is introduced, remediation - in 01-snyk-findings.md plus CSV. Read-only.",
     "[workflow-id] [snyk.json ... | pasted output | (empty = scan all repos)]", [], False,
     [("Next: plan (scope: all)", "dep-plan", "Plan the in-scope findings from 01-snyk-findings.md for this workflow. Scope: all")]),
    ("dep-plan", "2-plan.md",
     "Step 2 - one plan document (02-plan.md): verified versions and a baseline build, dependency-analyst subagents' impact on pom, code, config and tests with citations, and the ordered steps with every vulnerable module decided - for your approval. Read-only.",
     "<workflow-id | group:artifact current->target, ...>", ["dependency-analyst"], False,
     [("I approve the plan - apply it", "dep-apply", "I have reviewed 02-plan.md for this workflow and approve it as written. Record my approval and apply it.")]),
    ("dep-apply", "3-apply.md",
     "Step 3 - applies the USER-APPROVED 02-plan.md to each repo's clone under repos/ on branch deps/<workflow-id> via upgrade-applier subagents, compiling per step, logging to 03-apply-log.md. Edits the clones; never commits.",
     "<workflow-id> [repo-name ...]", ["upgrade-applier"], True,
     [("Next: verify all repos", "dep-verify", "Verify all repos for this workflow against the baseline.")]),
    ("dep-verify", "4-verify.md",
     "Step 4 - build, test and smoke-boot every repo with verify-repo, diagnose each failure against the baseline, compare Snyk before/after, and write 04-verification.md with a go/no-go verdict. Changes no source.",
     "<workflow-id> [repo-name ...]", [], False,
     [("Green: publish PRs", "dep-publish", "Verification is green. Commit, push and open PRs for this workflow."),
      ("Red: re-plan the fixes", "dep-plan", "Add plan steps that fix the regressions in 04-verification.md for this workflow (needs my re-approval).")]),
    ("dep-publish", "5-publish.md",
     "Step 5 - commits the verified changes in each clone, pushes deps/<workflow-id> and opens a pull request per target repo with a description built from the workflow docs; records commits and PR links in STATUS.md. Only when the user asks.",
     "<workflow-id> [repo-name ...]", [], True, []),
]

WORKERS = [
    ("dependency-analyst",
     "Read-only impact analysis of ONE dependency upgrade in ONE repo: how the version is set, what moves with it, affected code/config/tests with path:line, coupled library requirements, cited from official migration docs.",
     ["read", "search", "search/usages", "web/fetch", "execute/runInTerminal", "execute/getTerminalOutput", "edit/editFiles"],
     "Read, Grep, Glob, Bash, WebFetch, WebSearch, Write"),
    ("upgrade-applier",
     "Executes the approved 02-plan.md steps for ONE repo on branch deps/<id>, compiling after each step and logging every change; never commits, never skips tests.",
     ["read", "search", "edit/editFiles", "execute/runInTerminal", "execute/getTerminalOutput", "read/problems"],
     "Read, Edit, Write, Bash, Grep, Glob"),
]
# Claude model per subagent (none set: the analyst and applier need careful reasoning, so they inherit the session's).
CLAUDE_MODEL = {}

HEADER = "<!-- Generated by tools/generate-entrypoints.py - edit toolkit/ instead, then re-run it. -->\n"

# The project rules every session loads: written once here, generated as CLAUDE.md and .github/copilot-instructions.md.
PROJECT_RULES = """# snyk-update-package

This is a **meta repository** for Snyk-driven dependency upgrades. It has no application code of its own.

- Target repos are listed in `repos/repos.txt` (by git URL) and cloned into `repos/<name>/` (git-ignored).
  **All code changes happen in those clones**, on the workflow's branch `deps/wf-NNN` (created from the latest
  main by `repos.py --workflow <id> clone`). The user's own checkouts elsewhere are never touched, and this
  project never stores the repos' code. The tracking of each workflow lives in `workflows/`.
- Snyk fixes, CVE fixes or library upgrades, and "what's the next step?": use the workflow. `/dep-run <repo>` runs it
  (`toolkit/RUN.md`), `/dep-run status` shows where every run stands. Commands: `/dep-run`, `/dep-scan`, `/dep-plan`,
  `/dep-apply`, `/dep-verify`, `/dep-publish`.
- The workflow is defined in `toolkit/`: `WORKFLOW.md` (overview), `phases/`, `roles/`, `templates/`,
  `scripts/`. The `.github/` and `.claude/` entry points and this file are generated by `tools/generate-entrypoints.py`.
  Edit `toolkit/` (or the generator), not the generated files.
- Each workflow run has a unique id (Workflow 1 = `wf-001`, never reused) and its own folder
  `workflows/wf-<NNN>-<slug>/`, starting from `STATUS.md`. Create runs, change step states and log events only
  through `toolkit/scripts/workflows.py`; `workflows/INDEX.md` lists them all. **Save every step's result with
  `workflows.py save <id>`** (commits only that workflow's records and pushes; refuses while this repo is public).
- Target versions are exactly the ones Snyk names, never the latest release (`toolkit/WORKFLOW.md`).
- Windows: use the `.ps1` twin of every `.sh` script and `py -3` for Python (table in `toolkit/WORKFLOW.md`,
  "Running the commands on Windows").
- Tests run locally: `tests/run.sh` (macOS/Linux) or `tests\\run.ps1` (Windows). Run them after changing anything in
  `toolkit/` or `tools/`. A change to a `.sh` script must be made in its `.ps1` twin too: the tests run both.
- Never commit, push or open PRs in a target repo outside `/dep-publish`. Never reset, stash or switch
  branches in a clone with the user's changes. Never skip or disable tests.
"""


def write(rel, text):
    path = os.path.join(ROOT, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def body(name, phase, subagents, manual, tool):
    steps = ["1. Read `toolkit/WORKFLOW.md` (layout, gates, principles).",
             "2. Follow `%s`" % (phase if phase.startswith("toolkit/") else "toolkit/phases/" + phase)
             + " step by step. "
             + ("The user's message" if tool == "copilot" else "`$ARGUMENTS`") + " is the input.",
             "3. Templates are in `toolkit/templates/`, scripts in `toolkit/scripts/`. Run commands from the project root."]
    n = 4
    if subagents:
        how = ("Delegate with the agent tool" if tool == "copilot"
               else "Launch the agents in one message so they run in parallel")
        steps.append("%d. Subagents: %s - one `%s` per item." % (n, how, "` / `".join(subagents)))
        n += 1
    if manual and name == "dep-run":
        steps.append("%d. Run the steps back to back; stop only at the stop points in `toolkit/RUN.md`. Never publish." % n)
    elif manual:
        steps.append("%d. Check the gate in the phase file first; if it fails, stop and explain." % n)
        n += 1
    return ("\n# %s\n\n" % name) + "\n".join(steps) + (
        "\n\nTrack the run with `toolkit/scripts/workflows.py` (`phase`, `next`, `log`; see \"Tracking every run\" in "
        "`toolkit/WORKFLOW.md`) and finish with `workflows.py save <id>`, which pushes the records. Never hand-edit the "
        "phase tracker or the index. Reply with the workflow id "
        "(\"Workflow N, `wf-NNN`\"), what was produced (links), the headline findings, and **▶ Next step**.\n")


def ignore_dirs():
    with open(os.path.join(ROOT, "toolkit", "ignore-dirs.txt"), encoding="utf-8") as fh:
        return [l.strip() for l in fh if l.strip() and not l.lstrip().startswith("#")]


def write_settings():
    """Keep the assistants out of build output / dependency folders (toolkit/ignore-dirs.txt)."""
    dirs = ignore_dirs()
    vscode = {
        "//": "Generated by tools/generate-entrypoints.py from toolkit/ignore-dirs.txt - Copilot's search tools skip these.",
        "search.exclude": dict(("**/%s" % d, True) for d in dirs),
        "files.watcherExclude": dict(("**/%s/**" % d, True) for d in dirs),
    }
    write(".vscode/settings.json", json.dumps(vscode, indent=2) + "\n")
    deny = []
    for d in dirs:
        deny += ["Read(./repos/**/%s/**)" % d, "Edit(./repos/**/%s/**)" % d]
    claude = {"permissions": {"deny": deny}}
    write(".claude/settings.json", json.dumps(claude, indent=2) + "\n")


def main():
    write_settings()
    for rel in ("CLAUDE.md", ".github/copilot-instructions.md"):
        write(rel, HEADER + "\n" + PROJECT_RULES)
    for name, phase, desc, hint, subagents, manual, handoffs in PHASES:
        fm = ["---", "name: " + q(name), "description: " + q(desc), "argument-hint: " + q(hint),
              "tools: [%s]" % ", ".join(q(t) for t in RO + (["agent"] if subagents else []))]
        if subagents:
            fm.append("agents: [%s]" % ", ".join(q(a) for a in subagents))
        if handoffs:
            fm.append("handoffs:")
            for label, agent, prompt in handoffs:
                fm += ["  - label: " + q(label), "    agent: " + q(agent), "    prompt: " + q(prompt), "    send: false"]
        write(".github/agents/%s.agent.md" % name, "\n".join(fm + ["---", HEADER]) + body(name, phase, subagents, manual, "copilot"))
        write(".github/prompts/%s.prompt.md" % name,
              "---\nagent: %s\ndescription: %s\n---\n" % (q(name), q(desc.split(" - ", 1)[-1])))
        cfm = ["---", "name: " + name, "description: " + q(desc), "argument-hint: " + q(hint)]
        if manual:
            cfm.append("disable-model-invocation: true")
        write(".claude/skills/%s/SKILL.md" % name, "\n".join(cfm + ["---", HEADER]) + body(name, phase, subagents, manual, "claude"))

    for name, desc, copilot_tools, claude_tools in WORKERS:
        text = ("Read and follow `toolkit/roles/%s.md` exactly. It defines your inputs, method, output format "
                "and limits. The caller supplies the inputs as absolute paths; return the output block that file specifies.\n" % name)
        write(".github/agents/%s.agent.md" % name, "\n".join([
            "---", "name: " + q(name), "description: " + q(desc + " Invoked as a subagent."),
            "tools: [%s]" % ", ".join(q(t) for t in copilot_tools), "user-invocable: false", "---", HEADER]) + "\n" + text)
        model = ["model: " + CLAUDE_MODEL[name]] if name in CLAUDE_MODEL else []
        write(".claude/agents/%s.md" % name, "\n".join([
            "---", "name: " + name, "description: " + q(desc + " Used by the dep-* skills."),
            "tools: " + claude_tools] + model + ["---", HEADER]) + "\n" + text)
    print("generated %d phase entry points and %d subagents for Copilot and Claude" % (len(PHASES), len(WORKERS)))


if __name__ == "__main__":
    main()
