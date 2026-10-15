"""End to end: running the read-only steps of a workflow leaves NOTHING in the clone except its branch -
with the bash scripts and with their PowerShell twins.

Everything the steps produce (Snyk reports, build logs, results) must land in workflows/<id>/ here.
"""
import json
import os
import shlex

from helpers import BashScripts, PowerShellScripts, Sandbox

FAKE_BUILD = """import os
os.makedirs(os.path.join("target", "surefire-reports"), exist_ok=True)
with open(os.path.join("target", "surefire-reports", "TEST-A.xml"), "w") as fh:
    fh.write('<testsuite name="A" tests="1" failures="0" errors="0" skipped="0"><testcase classname="A" name="ok"/></testsuite>')
"""
FAKE_SNYK = """import sys
sys.exit(0 if sys.argv[1:2] in (["config"], ["whoami"]) else (print("[]") or 0))
"""


class CloneStaysCleanTests:
    def test_workflow_steps_write_only_into_the_workflow_folder(self):
        url, _ = self.make_remote("svc", {"pom.xml": "<project/>\n", ".gitignore": "target/\n", "build.py": FAKE_BUILD})
        build = self.python_command("build.py").replace('"build.py"', "build.py")
        self.write("repos/repos.txt", "svc  %s  build=%s\n" % (url, shlex.quote(build)))
        wf_id, folder = self.script("workflows.py", "new", "svc", "--repo", "svc", check=True).stdout.strip().split("\t")
        wf_dir = os.path.join(self.root, folder)
        clone = os.path.join(self.root, "repos", "svc")

        # step 0: clone + workflow branch
        self.script("repos.py", "--workflow", wf_id, "clone", check=True)
        # step 1: Snyk scan with a fake CLI
        cli = self.make_tool(os.path.join(self.tmp, "bin", "snyk"), FAKE_SNYK)
        self.script("snyk-scan.sh", os.path.join(wf_dir, "snyk"), "--workflow", wf_id,
                    env=dict(self.env, SNYK_CLI=cli), check=True)
        # steps 2/5: build + tests, results into the workflow folder
        row = self.script("repos.py", "--workflow", wf_id, "list", check=True).stdout.rstrip("\n").split("\t")
        build_dir, verify_args = row[1], shlex.split(row[2])
        self.script("verify-repo.sh", build_dir, os.path.join(wf_dir, "verification", "baseline", "svc"),
                    *verify_args, check=True)

        # the clone: on its branch, and NOTHING added or changed
        self.assertEqual(self.git(clone, "rev-parse", "--abbrev-ref", "HEAD"), "deps/%s" % wf_id)
        self.assertEqual(self.git(clone, "status", "--porcelain", "--untracked-files=all"), "",
                         "the clone must hold no files from the workflow")
        self.assertEqual(self.git(clone, "log", "--oneline", "main..HEAD"), "", "no commits either")
        # ... and the evidence is in this project
        for rel in ("STATUS.md", "repos.txt", "snyk/svc.json", "snyk/scan-index.tsv",
                    "verification/baseline/svc/summary.json", "verification/baseline/svc/build.log"):
            self.assertTrue(os.path.isfile(os.path.join(wf_dir, rel)), rel)
        with open(os.path.join(wf_dir, "verification", "baseline", "svc", "summary.json"), encoding="utf-8") as fh:
            summary = json.load(fh)
        self.assertEqual((summary["status"], summary["tests"]["tests"], summary["left_in_repo"]), ("green", 1, []))


class CloneStaysCleanBash(BashScripts, CloneStaysCleanTests, Sandbox):
    pass


class CloneStaysCleanPowerShell(PowerShellScripts, CloneStaysCleanTests, Sandbox):
    pass
