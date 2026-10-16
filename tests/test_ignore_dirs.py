"""Build output and dependency folders (toolkit/ignore-dirs.txt) are never searched, scanned or edited -
by the scripts (bash and PowerShell) or by the assistants' settings."""
import json
import os
import unittest

from helpers import ON_WINDOWS, PROJECT, BashScripts, PowerShellScripts, Sandbox


def ignore_dirs():
    with open(os.path.join(PROJECT, "toolkit", "ignore-dirs.txt"), encoding="utf-8") as fh:
        return [l.strip() for l in fh if l.strip() and not l.lstrip().startswith("#")]


POM = '<project xmlns="http://maven.apache.org/POM/4.0.0"><artifactId>%s</artifactId>' \
      '<dependencies><dependency><groupId>g</groupId><artifactId>%s-dep</artifactId><version>1</version>' \
      '</dependency></dependencies></project>\n'


class IgnoredFolderTests:
    def repo_with_poms_everywhere(self):
        """A repo whose real poms are at ./ and ./api, plus decoy poms in every ignored folder."""
        repo = os.path.join(self.tmp, "svc")
        self.write(os.path.join(repo, "pom.xml"), POM % ("root", "root"))
        self.write(os.path.join(repo, "api", "pom.xml"), POM % ("api", "api"))
        for d in ignore_dirs():
            self.write(os.path.join(repo, d, "nested", "pom.xml"), POM % ("decoy", "decoy-in-" + d))
        # a Maven wrapper that fails at once: these tests don't need Maven
        if ON_WINDOWS:
            self.write(os.path.join(repo, "mvnw.cmd"), "@exit /b 1\r\n")
        else:
            os.chmod(self.write(os.path.join(repo, "mvnw"), "#!/bin/sh\nexit 1\n"), 0o755)
        return repo

    def test_maven_facts_only_reads_real_poms(self):
        repo = self.repo_with_poms_everywhere()
        out = os.path.join(self.tmp, "facts")
        self.script("maven-facts.sh", repo, out)
        declared = self.read(os.path.join(out, "declared.txt"))
        self.assertIn("./pom.xml\tdependency\tg:root-dep:1", declared)
        self.assertIn("./api/pom.xml\tdependency\tg:api-dep:1", declared)
        self.assertNotIn("decoy", declared, "a pom inside target/, node_modules/, .git/ ... was read")

    def test_snyk_scan_excludes_every_ignored_folder_and_merges_yours(self):
        url, _ = self.make_remote("svc")
        self.git(self.tmp, "clone", "-q", url, os.path.join(self.root, "repos", "svc"))
        self.manifest("svc  %s" % url)
        log = os.path.join(self.tmp, "calls.log")
        cli = self.make_tool(os.path.join(self.tmp, "bin", "snyk"),
                             "import sys\nopen(%r, 'a').write(' '.join(sys.argv[1:]) + '\\n')\n"
                             "sys.exit(0) if sys.argv[1:2] in (['config'], ['whoami']) else print('[]')\n" % log)
        env = dict(self.env, SNYK_CLI=cli)
        self.script("snyk-scan.sh", "out", env=env, check=True)
        self.script("snyk-scan.sh", "out2", "--exclude=legacy", "--org=acme", env=env, check=True)
        tests = [l for l in self.read(log).splitlines() if l.startswith("test ")]
        expected = "--exclude=" + ",".join(ignore_dirs())
        self.assertEqual(tests[0], "test --all-projects --json " + expected)
        self.assertEqual(tests[1], "test --all-projects --json --org=acme --exclude=legacy," + ",".join(ignore_dirs()),
                         "your --exclude is merged into the single one Snyk accepts")


class IgnoredFoldersBash(BashScripts, IgnoredFolderTests, Sandbox):
    pass


class IgnoredFoldersPowerShell(PowerShellScripts, IgnoredFolderTests, Sandbox):
    pass


class HelpersAndRepos(Sandbox):
    def test_find_poms_never_descends_into_ignored_folders(self):
        IgnoredFolderTests.repo_with_poms_everywhere(self)
        out = self.run_cmd([__import__("sys").executable, "-I",
                            os.path.join(self.root, "toolkit", "scripts", "script-helpers.py"), "find-poms"],
                           cwd=os.path.join(self.tmp, "svc"), check=True).stdout.split()
        self.assertEqual(out, ["./api/pom.xml", "./pom.xml"])

    def test_changes_inside_ignored_folders_do_not_count_as_uncommitted_work(self):
        url, _ = self.make_remote("svc")
        self.manifest("svc  %s" % url)
        self.script("repos.py", "clone", check=True)
        clone = os.path.join(self.root, "repos", "svc")
        for d in ("node_modules", "out", ".idea", "build"):           # the repo doesn't git-ignore these
            self.write(os.path.join(clone, d, "junk.txt"), "x\n")
        status = self.script("repos.py", "status", check=True).stdout.splitlines()[1].split()
        self.assertEqual(status[3], "0", "build/dependency folders must not block a workflow")
        self.write(os.path.join(clone, "src", "Real.java"), "class Real {}\n")
        self.assertEqual(self.script("repos.py", "status", check=True).stdout.splitlines()[1].split()[3], "1")


class AssistantsAreRestricted(unittest.TestCase):
    def test_copilot_search_skips_every_ignored_folder(self):
        with open(os.path.join(PROJECT, ".vscode", "settings.json"), encoding="utf-8") as fh:
            settings = json.load(fh)
        for d in ignore_dirs():
            self.assertTrue(settings["search.exclude"].get("**/%s" % d), d)
            self.assertTrue(settings["files.watcherExclude"].get("**/%s/**" % d), d)

    def test_claude_cannot_read_or_edit_inside_ignored_folders(self):
        with open(os.path.join(PROJECT, ".claude", "settings.json"), encoding="utf-8") as fh:
            deny = json.load(fh)["permissions"]["deny"]
        for d in ignore_dirs():
            self.assertIn("Read(./repos/**/%s/**)" % d, deny)
            self.assertIn("Edit(./repos/**/%s/**)" % d, deny)

    def test_instructions_send_the_assistants_around_those_folders(self):
        for rel in ("toolkit/WORKFLOW.md", "toolkit/roles/dependency-analyst.md", "toolkit/roles/upgrade-applier.md"):
            with open(os.path.join(PROJECT, rel), encoding="utf-8") as fh:
                text = fh.read()
            self.assertIn("toolkit/ignore-dirs.txt", text, rel)
            self.assertIn("git -C <repo> grep", text, rel)

    def test_the_list_covers_the_usual_suspects(self):
        for d in ("target", "build", "node_modules", ".git", ".idea", ".gradle"):
            self.assertIn(d, ignore_dirs())
