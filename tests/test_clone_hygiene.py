"""End to end: running the read-only steps of a workflow leaves NOTHING in the clone except its branch.

Everything the steps produce (Snyk reports, build logs, results) must land in workflows/<id>/ here.
"""
import json
import os
import stat

from helpers import Sandbox

FAKE_BUILD = """mkdir -p target/surefire-reports
cat > target/surefire-reports/TEST-A.xml <<'XML'
<testsuite name="A" tests="1" failures="0" errors="0" skipped="0"><testcase classname="A" name="ok"/></testsuite>
XML
"""


class CloneStaysClean(Sandbox):
    def test_workflow_steps_write_only_into_the_workflow_folder(self):
        url, _ = self.make_remote("svc", {"pom.xml": "<project/>\n", ".gitignore": "target/\n",
                                          "build.sh": FAKE_BUILD})
        self.manifest('svc  %s  build="bash build.sh"' % url)
        wf_id, folder = self.script("workflows.py", "new", "svc", "--repo", "svc", check=True).stdout.strip().split("\t")
        wf_dir = os.path.join(self.root, folder)
        clone = os.path.join(self.root, "repos", "svc")

        # step 0: clone + workflow branch
        self.script("repos.py", "--workflow", wf_id, "clone", check=True)
        # step 1: Snyk scan with a fake CLI
        bin_dir = os.path.join(self.tmp, "bin")
        snyk = self.write(os.path.join(bin_dir, "snyk"), "#!/bin/bash\n[ \"$1\" = config ] && exit 0\necho '[]'\nexit 0\n")
        os.chmod(snyk, os.stat(snyk).st_mode | stat.S_IEXEC)
        env = dict(self.env, PATH=bin_dir + os.pathsep + self.env["PATH"])
        self.script("snyk-scan.sh", os.path.join(wf_dir, "snyk"), "--workflow", wf_id, env=env, check=True)
        # step 2/5: build + tests, results into the workflow folder
        row = self.script("repos.py", "--workflow", wf_id, "list", check=True).stdout.split("\t")
        build_dir, verify_args = row[1], row[2]
        self.script("verify-repo.sh", build_dir, os.path.join(wf_dir, "verification", "baseline", "svc"),
                    *__import__("shlex").split(verify_args), check=True)

        # the clone: on its branch, and NOTHING added or changed
        self.assertEqual(self.git(clone, "rev-parse", "--abbrev-ref", "HEAD"), "deps/%s" % wf_id)
        self.assertEqual(self.git(clone, "status", "--porcelain", "--untracked-files=all"), "",
                         "the clone must hold no files from the workflow")
        self.assertEqual(self.git(clone, "log", "--oneline", "main..HEAD"), "", "no commits either")
        # ... and the evidence is in this project
        for rel in ("STATUS.md", "repos.txt", "snyk/svc.json", "snyk/scan-index.tsv",
                    "verification/baseline/svc/summary.json", "verification/baseline/svc/build.log"):
            self.assertTrue(os.path.isfile(os.path.join(wf_dir, rel)), rel)
        summary = json.load(open(os.path.join(wf_dir, "verification", "baseline", "svc", "summary.json")))
        self.assertEqual((summary["status"], summary["left_in_repo"]), ("green", []))
