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
    # phase file: a name in toolkit/phases/, a path starting with toolkit/, or None for the orchestrator.
    ("dep-run", "toolkit/RUN.md",
     "Autopilot for ONE repo (name, local folder or git URL): opens or resumes its workflow (wf-NNN) and runs every step - clone, Snyk scan, inventory, impact + plan - then stops for your approval; after you approve, applies and verifies, then stops before publish. Always ends with what to do next.",
     "<repo name | local folder | git URL> [workflow id] [snyk.json] [your reply: approve | scope: ... | decision]",
     ["dependency-analyst", "upgrade-applier", "repo-verifier"], True,
     [("Approve the plan and continue", "dep-run", "I have reviewed 03-plan.md for this workflow and approve it as written. Continue: apply and verify."),
      ("Publish the PRs", "dep-publish", "Verification is green. Commit, push and open PRs for this workflow."),
      ("Where does it stand?", "dep-upgrade", "status")]),
    ("dep-upgrade", None,
     "Show where every workflow stands (status), or run ONE next step of a workflow across the repos in repos/repos.txt, and always state the next step. For hands-off runs on one repo use /dep-run. Offers apply/publish as handoffs only.",
     "[status | workflow id (1, wf-001) | folder or git-url | snyk.json | group:artifact current->target]",
     ["dependency-analyst", "repo-verifier"], False,
     [("Apply the approved plan", "dep-apply", "I have reviewed 03-plan.md for this upgrade and approve it as written. Record my approval and apply it."),
      ("Verify all repos", "dep-verify", "Verify all repos for this upgrade.")]),
    ("dep-clone", "0-clone.md",
     "Phase 0 - add target repos to repos/repos.txt as a local folder (used in place) or a git URL (cloned into repos/), then check/refresh them. Never resets, pulls local folders, or switches branches.",
     "[local-folder | git-url [name] [path=<subdir>] [smoke=true] | repo-name ... | (empty = all)]", [], False,
     [("Next: Snyk scan", "dep-scan", "Run the Snyk scan over all repos in the list.")]),
    ("dep-scan", "1-scan.md",
     "Phase 1 - run Snyk over every repo in the list (or parse supplied Snyk JSON / pasted output) and document EVERY flagged package: current version, severity, CVEs, fixed-in, how it is introduced, remediation - in 01-snyk-findings.md plus CSV. Read-only.",
     "[workflow-id] [snyk.json ... | pasted output | (empty = scan all repos)]", [], False,
     [("Next: inventory (scope: all)", "dep-inventory", "Inventory the in-scope findings from 01-snyk-findings.md for this upgrade. Scope: all")]),
    ("dep-inventory", "2-inventory.md",
     "Phase 2 - verified inventory of package, current vs target version, the pom lever that sets it, what moves with it, coupled libraries, plus a baseline build of every repo - in 02-inventory.md. Read-only.",
     "<workflow-id | group:artifact current->target, ...>", [], False,
     [("Next: analyse impact and plan", "dep-analyze", "Analyse impact and write the plan for this upgrade.")]),
    ("dep-analyze", "3-analyze.md",
     "Phase 3 - dependency-analyst subagents document pom, code, config and test impact of each version jump with citations (03-impact.md), then a step-by-step 03-plan.md for approval. Read-only.",
     "<workflow-id>", ["dependency-analyst"], False,
     [("I approve the plan - apply it", "dep-apply", "I have reviewed 03-plan.md for this upgrade and approve it as written. Record my approval and apply it.")]),
    ("dep-apply", "4-apply.md",
     "Phase 4 - applies the USER-APPROVED 03-plan.md to each repo folder on branch deps/<workflow-id> via upgrade-applier subagents, compiling per step, logging to 04-apply-log.md. Edits the repo folders; never commits.",
     "<workflow-id> [repo-name ...]", ["upgrade-applier"], True,
     [("Next: verify all repos", "dep-verify", "Verify all repos for this upgrade against the baseline.")]),
    ("dep-verify", "5-verify.md",
     "Phase 5 (or health check with 'baseline') - build, test and smoke-boot every repo via repo-verifier subagents, compare to the baseline and Snyk before/after, write 05-verification.md with a go/no-go verdict.",
     "<workflow-id | baseline> [repo-name ...]", ["repo-verifier"], False,
     [("Green: publish PRs", "dep-publish", "Verification is green. Commit, push and open PRs for this upgrade."),
      ("Red: re-plan the fixes", "dep-analyze", "Add plan steps that fix the regressions in 05-verification.md for this upgrade (needs my re-approval).")]),
    ("dep-publish", "6-publish.md",
     "Phase 6 - commits the verified changes in each repo folder, pushes deps/<workflow-id> and opens a pull request per target repo with a description built from the upgrade docs; records PR links in 06-publish.md. Only when the user asks.",
     "<workflow-id> [repo-name ...]", [], True, []),
]

WORKERS = [
    ("dependency-analyst",
     "Read-only impact analysis of ONE dependency upgrade in ONE repo: how the version is set, what moves with it, affected code/config/tests with path:line, coupled library requirements, cited from official migration docs.",
     ["read", "search", "search/usages", "web/fetch", "execute/runInTerminal", "execute/getTerminalOutput", "edit/editFiles"],
     "Read, Grep, Glob, Bash, WebFetch, WebSearch, Write"),
    ("upgrade-applier",
     "Executes the approved 03-plan.md steps for ONE repo on branch deps/<id>, compiling after each step and logging every change; never commits, never skips tests.",
     ["read", "search", "edit/editFiles", "execute/runInTerminal", "execute/getTerminalOutput", "read/problems"],
     "Read, Edit, Write, Bash, Grep, Glob"),
    ("repo-verifier",
     "Builds, tests and smoke-boots ONE repo with verify-repo.sh and classifies failures (regression / pre-existing / environmental) against the baseline and 03-impact.md. Reports only.",
     ["read", "search", "execute/runInTerminal", "execute/getTerminalOutput", "edit/editFiles"],
     "Bash, Read, Grep, Glob, Write"),
]

HEADER = "<!-- Generated by tools/generate-entrypoints.py - edit toolkit/ instead, then re-run it. -->\n"


def write(rel, text):
    path = os.path.join(ROOT, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def body(name, phase, subagents, manual, tool):
    steps = ["1. Read `toolkit/WORKFLOW.md` (layout, gates, principles).",
             "2. Follow " + ("`toolkit/WORKFLOW.md` section \"Orchestrating\", then the chosen phase file in `toolkit/phases/`"
                             if phase is None else "`%s`" % (phase if phase.startswith("toolkit/") else "toolkit/phases/" + phase))
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
    if phase is None:
        steps.append("%d. Never run `/dep-apply` or `/dep-publish` yourself; offer them once their gates are met." % n)
    return ("\n# %s\n\n" % name) + "\n".join(steps) + (
        "\n\nTrack the run with `toolkit/scripts/workflows.py` (`phase`, `next`, `log`; see \"Tracking every run\" in "
        "`toolkit/WORKFLOW.md`). Never hand-edit the phase tracker or the index. Reply with the workflow id "
        "(\"Workflow N, `wf-NNN`\"), what was produced (links), the headline findings, and **▶ Next step**.\n")


def main():
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
        write(".claude/agents/%s.md" % name, "\n".join([
            "---", "name: " + name, "description: " + q(desc + " Used by the dep-* skills."),
            "tools: " + claude_tools, "---", HEADER]) + "\n" + text)
    print("generated %d phase entry points and %d subagents for Copilot and Claude" % (len(PHASES), len(WORKERS)))


if __name__ == "__main__":
    main()
