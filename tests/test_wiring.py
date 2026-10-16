"""The /dep-* commands themselves: generated files are current, every reference resolves, and the
safety rules (manual-only apply/publish, approval gate, no hidden subagent calls) hold.

The assistants' reasoning can't be unit-tested, but everything they are told to read or run can be.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

from helpers import ON_WINDOWS, POWERSHELL, PROJECT

PHASES = ["dep-clone", "dep-scan", "dep-inventory", "dep-analyze", "dep-apply", "dep-verify", "dep-publish"]
COMMANDS = ["dep-upgrade", "dep-run", "dep-login"] + PHASES
SUBAGENTS = ["dependency-analyst", "upgrade-applier", "repo-verifier"]
MANUAL_ONLY = ["dep-apply", "dep-publish", "dep-run"]   # can change code or push: user-started only


def read(rel):
    with open(os.path.join(PROJECT, rel), encoding="utf-8") as fh:
        return fh.read()


def frontmatter(rel):
    """Parse the simple YAML used here: `key: value`, `key: [..]` and the `handoffs:` list."""
    text = read(rel)
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        raise AssertionError("%s: no frontmatter" % rel)
    data, handoffs, current = {}, [], None
    for line in m.group(1).splitlines():
        if not line.strip():
            continue
        item = re.match(r"^\s+- (\w[\w-]*): (.*)$", line)
        cont = re.match(r"^\s{4}(\w[\w-]*): (.*)$", line)
        top = re.match(r"^([\w-]+):\s*(.*)$", line)
        if item:
            current = {item.group(1): _value(item.group(2), rel)}
            handoffs.append(current)
        elif cont and current is not None:
            current[cont.group(1)] = _value(cont.group(2), rel)
        elif top:
            current = None
            if top.group(1) != "handoffs":
                data[top.group(1)] = _value(top.group(2), rel)
        else:
            raise AssertionError("%s: unparseable frontmatter line %r" % (rel, line))
    data["handoffs"] = handoffs
    return data, text[m.end():]


def _value(raw, rel):
    raw = raw.strip()
    if raw.startswith(("[", '"')):
        try:
            return json.loads(raw)
        except ValueError:
            raise AssertionError("%s: value is not valid (JSON-compatible) YAML: %s" % (rel, raw))
    if raw.startswith("'"):
        raise AssertionError("%s: single-quoted YAML values are fragile here: %s" % (rel, raw))
    return raw


class GeneratedFilesAreCurrent(unittest.TestCase):
    def test_generator_output_matches_committed_files(self):
        tmp = tempfile.mkdtemp(prefix="sup-gen-")
        try:
            os.makedirs(os.path.join(tmp, "tools"))
            shutil.copy(os.path.join(PROJECT, "tools", "generate-entrypoints.py"), os.path.join(tmp, "tools"))
            os.makedirs(os.path.join(tmp, "toolkit"))                       # the generator reads the ignore list
            shutil.copy(os.path.join(PROJECT, "toolkit", "ignore-dirs.txt"), os.path.join(tmp, "toolkit"))
            subprocess.run([sys.executable, "-I", os.path.join(tmp, "tools", "generate-entrypoints.py")],
                           check=True, stdout=subprocess.DEVNULL)
            stale = []
            for base, _dirs, files in os.walk(tmp):
                for name in files:
                    rel = os.path.relpath(os.path.join(base, name), tmp)
                    if rel.startswith(("tools", "toolkit")):
                        continue
                    committed = os.path.join(PROJECT, rel)
                    with open(os.path.join(base, name), encoding="utf-8") as fh:
                        generated = fh.read()
                    if not os.path.isfile(committed) or read(rel) != generated:
                        stale.append(rel)
            self.assertEqual(stale, [], "run: python3 -I tools/generate-entrypoints.py")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class CommandsExistEverywhere(unittest.TestCase):
    def test_every_command_has_a_copilot_agent_prompt_and_claude_skill(self):
        for name in COMMANDS:
            for rel in (".github/agents/%s.agent.md" % name, ".github/prompts/%s.prompt.md" % name,
                        ".claude/skills/%s/SKILL.md" % name):
                self.assertTrue(os.path.isfile(os.path.join(PROJECT, rel)), rel)
        for name in SUBAGENTS:
            for rel in (".github/agents/%s.agent.md" % name, ".claude/agents/%s.md" % name,
                        "toolkit/roles/%s.md" % name):
                self.assertTrue(os.path.isfile(os.path.join(PROJECT, rel)), rel)

    def test_each_phase_command_runs_its_own_phase_file(self):
        for n, name in enumerate(PHASES):
            phase_files = [f for f in os.listdir(os.path.join(PROJECT, "toolkit", "phases")) if f.startswith("%d-" % n)]
            self.assertEqual(len(phase_files), 1, "exactly one toolkit/phases/%d-*.md" % n)
            for rel in (".github/agents/%s.agent.md" % name, ".claude/skills/%s/SKILL.md" % name):
                self.assertIn("toolkit/phases/%s" % phase_files[0], read(rel), rel)

    def test_status_template_tracks_exactly_the_seven_steps(self):
        rows = re.findall(r"^\|\s*(\d)\s*\|[^|]*\|\s*`/(dep-[a-z]+)`", read("toolkit/templates/STATUS.md"), re.M)
        self.assertEqual([int(n) for n, _ in rows], list(range(7)))
        self.assertEqual([cmd for _, cmd in rows], PHASES)
        for placeholder in ("{{WORKFLOW_ID}}", "{{NUMBER}}", "{{TITLE}}", "{{DATE}}", "{{SOURCE}}"):
            self.assertIn(placeholder, read("toolkit/templates/STATUS.md"))


class FrontmatterAndLinks(unittest.TestCase):
    def agent_files(self):
        return sorted(f for f in os.listdir(os.path.join(PROJECT, ".github", "agents")) if f.endswith(".agent.md"))

    def test_all_frontmatter_parses_with_required_keys(self):
        for f in self.agent_files():
            data, _ = frontmatter(".github/agents/" + f)
            self.assertEqual(data["name"], f[:-len(".agent.md")], f)
            self.assertTrue(data["description"], f)
            self.assertIsInstance(data["tools"], list, f)
        for f in os.listdir(os.path.join(PROJECT, ".github", "prompts")):
            data, _ = frontmatter(".github/prompts/" + f)
            self.assertTrue(os.path.isfile(os.path.join(PROJECT, ".github", "agents", data["agent"] + ".agent.md")), f)
        for name in os.listdir(os.path.join(PROJECT, ".claude", "skills")):
            data, _ = frontmatter(".claude/skills/%s/SKILL.md" % name)
            self.assertEqual(data["name"], name)
        for f in os.listdir(os.path.join(PROJECT, ".claude", "agents")):
            data, _ = frontmatter(".claude/agents/" + f)
            self.assertEqual(data["name"], f[:-3])
        frontmatter(".github/skills/dep-upgrade/SKILL.md")
        frontmatter(".github/instructions/maven-dependencies.instructions.md")

    def test_handoffs_and_subagent_lists_point_at_real_agents(self):
        agents = {f[:-len(".agent.md")] for f in self.agent_files()}
        for f in self.agent_files():
            data, _ = frontmatter(".github/agents/" + f)
            for target in data.get("agents", []):
                self.assertIn(target, agents, "%s: agents: %s" % (f, target))
                self.assertIn("agent", data["tools"], "%s lists subagents but lacks the 'agent' tool" % f)
            for h in data["handoffs"]:
                self.assertIn(h["agent"], agents, "%s: handoff to %s" % (f, h["agent"]))
                self.assertTrue(h.get("label") and h.get("prompt"), f)

    def test_every_referenced_project_path_exists(self):
        sources = ["toolkit/WORKFLOW.md", "README.md", "repos/README.md", "CLAUDE.md", ".github/copilot-instructions.md"]
        for base in ("toolkit/phases", "toolkit/roles"):
            sources += [os.path.join(base, f) for f in os.listdir(os.path.join(PROJECT, base))]
        sources += [".github/agents/" + f for f in self.agent_files()]
        sources += [".claude/skills/%s/SKILL.md" % d for d in os.listdir(os.path.join(PROJECT, ".claude", "skills"))]
        missing = []
        for rel in sources:
            for ref in re.findall(r"`((?:toolkit|tools|repos|workflows|\.github|\.claude)/[^`\s]*)", read(rel)):
                ref = ref.rstrip("/.,):")
                if any(ch in ref for ch in "<>{}*…") or ref.startswith(("workflows/wf-", "workflows/_health", "workflows/INDEX.md", "repos/inventory-service",
                                                                         ".claude/settings.local.json")):
                    continue                                   # placeholders / generated-at-runtime paths
                if not os.path.exists(os.path.join(PROJECT, ref)):
                    missing.append("%s -> %s" % (rel, ref))
        self.assertEqual(missing, [])


class SafetyRules(unittest.TestCase):
    def test_apply_and_publish_are_manual_only(self):
        for name in MANUAL_ONLY:
            data, _ = frontmatter(".claude/skills/%s/SKILL.md" % name)
            self.assertEqual(data.get("disable-model-invocation"), "true", "Claude must not auto-run " + name)
        for f in os.listdir(os.path.join(PROJECT, ".github", "agents")):
            data, _ = frontmatter(".github/agents/" + f)
            for name in MANUAL_ONLY:
                self.assertNotIn(name, data.get("agents", []), "%s may not call %s as a subagent" % (f, name))
            for h in data["handoffs"]:
                if h["agent"] in MANUAL_ONLY:
                    self.assertEqual(h.get("send"), "false", "%s: handoff to %s must wait for the user" % (f, h["agent"]))

    def test_autopilot_stops_for_approval_and_never_publishes(self):
        run = read("toolkit/RUN.md")
        self.assertIn("**always stop after writing `03-plan.md`**", run)
        self.assertIn("**never run it from here**", run)
        self.assertIn("Never** tick the approval box without the user's explicit words", run)
        for n in range(6):
            self.assertIn("phases/%d-" % n, run, "RUN.md must route step %d to its phase file" % n)
        data, body = frontmatter(".github/agents/dep-run.agent.md")
        self.assertNotIn("dep-publish", data["agents"], "autopilot may not call publish")
        self.assertIn("Never publish", body)

    def test_subagents_are_hidden_from_the_user_picker(self):
        for name in SUBAGENTS:
            data, _ = frontmatter(".github/agents/%s.agent.md" % name)
            self.assertEqual(data.get("user-invocable"), "false", name)

    def test_read_only_roles_say_so_and_apply_requires_approval(self):
        self.assertIn("never modify", read("toolkit/roles/dependency-analyst.md"))
        self.assertIn("You do not fix anything", read("toolkit/roles/repo-verifier.md"))
        self.assertIn("- [x] Approved by user", read("toolkit/phases/4-apply.md"))
        self.assertIn("- [x] Approved by user", read("toolkit/roles/upgrade-applier.md"))
        self.assertIn("Never tick the approval box yourself", read("toolkit/phases/3-analyze.md"))
        for rel in ("toolkit/roles/upgrade-applier.md", "toolkit/phases/5-verify.md", "toolkit/WORKFLOW.md"):
            self.assertRegex(read(rel), r"(?i)never (re-run with tests skipped|hide red|delete or skip tests)|skip", rel)


class BranchNamesAreConsistent(unittest.TestCase):
    """Workflow wf-NNN always works on branch deps/wf-NNN - never deps/wf-NNN-<slug> or anything else."""
    ALLOWED = re.compile(r"^deps/(<id>|<workflow-id>|wf-NNN|wf-\d{3,}|\{\{WORKFLOW_ID\}\}|\*|…)$")

    def test_every_documented_workflow_branch_has_the_one_true_form(self):
        bad = []
        for base, dirs, files in os.walk(PROJECT):
            dirs[:] = [d for d in dirs if d not in (".git", "repos", "tests", "__pycache__")]
            for name in files:
                if not name.endswith((".md", ".py", ".sh", ".yml")):
                    continue
                rel = os.path.relpath(os.path.join(base, name), PROJECT)
                for m in re.finditer(r"deps/[^\s`'\")\],|]*", read(rel)):
                    branch = m.group(0).rstrip(".:;")
                    if branch in ("deps/", "deps") or self.ALLOWED.match(branch):
                        continue
                    if branch.startswith(("deps/<id>", "deps/<workflow-id>")):   # e.g. deps/<id>.
                        continue
                    bad.append("%s: %s" % (rel, branch))
        self.assertEqual(bad, [], "workflow branches must be deps/wf-NNN")

    def test_the_code_builds_the_branch_name_from_the_workflow_id_only(self):
        self.assertIn('return "deps/" + wf_id', read("toolkit/scripts/repos.py"))
        self.assertIn("`deps/{{WORKFLOW_ID}}`", read("toolkit/templates/STATUS.md"))


class ScriptsAreSound(unittest.TestCase):
    SCRIPTS = os.path.join(PROJECT, "toolkit", "scripts")

    @unittest.skipIf(ON_WINDOWS, "bash and file modes are not checked on Windows")
    def test_shell_scripts_parse_and_are_executable(self):
        for f in os.listdir(self.SCRIPTS):
            path = os.path.join(self.SCRIPTS, f)
            if f.endswith(".sh"):
                subprocess.run(["bash", "-n", path], check=True)
            if f.endswith((".sh", ".py")):
                self.assertTrue(os.access(path, os.X_OK), "%s is not executable" % f)

    def test_every_bash_script_has_a_powershell_twin_with_the_same_arguments(self):
        pairs = [("toolkit/scripts/" + f, "toolkit/scripts/" + f[:-3] + ".ps1")
                 for f in os.listdir(self.SCRIPTS) if f.endswith(".sh")] + [("tests/run.sh", "tests/run.ps1")]
        for sh, ps1 in pairs:
            self.assertTrue(os.path.isfile(os.path.join(PROJECT, ps1)), "missing PowerShell twin: " + ps1)
            flags_sh = set(re.findall(r"(?<![\w-])--[a-z][a-z-]+", read(sh))) - {"--all-projects", "--json"}
            flags_ps = set(re.findall(r"(?<![\w-])--[a-z][a-z-]+", read(ps1))) - {"--all-projects", "--json"}
            self.assertEqual(sorted(flags_sh - flags_ps), [], "%s documents options %s doesn't" % (sh, ps1))

    @unittest.skipUnless(POWERSHELL, "PowerShell not found")
    def test_powershell_scripts_parse(self):
        files = [os.path.join(self.SCRIPTS, f) for f in os.listdir(self.SCRIPTS) if f.endswith(".ps1")]
        files.append(os.path.join(PROJECT, "tests", "run.ps1"))
        checker = os.path.join(tempfile.mkdtemp(prefix="sup-ps-"), "check.ps1")
        with open(checker, "w", encoding="utf-8") as fh:
            fh.write("$bad = 0\nforeach ($f in $args) {\n  $e = $null\n"
                     "  [void][System.Management.Automation.Language.Parser]::ParseFile($f, [ref]$null, [ref]$e)\n"
                     "  foreach ($x in @($e)) { if ($x) { Write-Output ($f + ': ' + $x.ToString()); $bad++ } }\n}\nexit $bad\n")
        proc = subprocess.run([POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", checker]
                              + files, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
        shutil.rmtree(os.path.dirname(checker), ignore_errors=True)
        self.assertEqual(proc.returncode, 0, proc.stdout)

    def test_powershell_scripts_never_assign_arrays_from_if_expressions(self):
        """`$x = if (...) { @('a') }` hands back the bare 'a', not an array - a bug we hit twice."""
        for rel in [os.path.join("toolkit/scripts", f) for f in os.listdir(self.SCRIPTS) if f.endswith(".ps1")] + ["tests/run.ps1"]:
            for n, line in enumerate(read(rel).splitlines(), 1):
                if not line.lstrip().startswith("#"):
                    self.assertNotRegex(line, r"=\s*if\s*\(.*\{\s*@\(", "%s:%d assigns an array from an if-expression" % (rel, n))

    def test_powershell_scripts_avoid_powershell_7_only_syntax(self):
        """Windows ships PowerShell 5.1: no ?? / ?. / ternary, no -Encoding utf8NoBOM, no $IsWindows."""
        files = [os.path.join("toolkit/scripts", f) for f in os.listdir(self.SCRIPTS) if f.endswith(".ps1")] + ["tests/run.ps1"]
        for rel in files:
            text = "\n".join(l for l in read(rel).splitlines() if not l.lstrip().startswith("#"))
            for pattern, why in ((r"\?\?", "?? operator"), (r"\?\.", "?. operator"), (r"utf8NoBOM", "utf8NoBOM encoding"),
                                 (r"\$IsWindows|\$IsMacOS|\$IsLinux", "$IsWindows"), (r"\)\s*\?\s*[^:]+\s:\s", "ternary")):
                self.assertNotRegex(text, pattern, "%s uses %s (PowerShell 7 only)" % (rel, why))

    def test_python_scripts_compile_for_3_9(self):
        for f in os.listdir(os.path.join(PROJECT, "toolkit", "scripts")):
            if f.endswith(".py"):
                src = read("toolkit/scripts/" + f)
                compile(src, f, "exec")
                self.assertNotRegex(src, r"^\s*match .*:$", "%s: match statements need 3.10" % f)
