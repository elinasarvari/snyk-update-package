"""parse-snyk.py and snyk-scan.sh - with fixture reports and a fake `snyk` CLI (no network, no account)."""
import csv
import json
import os
import stat

from helpers import ON_WINDOWS, BashScripts, PowerShellScripts, Sandbox


def vuln(vid, pkg, version, severity, path, upgrade, fixed, cves=(), kind=None, upgradable=True):
    v = {"id": vid, "title": vid + " title", "severity": severity, "packageName": pkg, "version": version,
         "from": path, "upgradePath": upgrade, "fixedIn": fixed, "isUpgradable": upgradable,
         "identifiers": {"CVE": list(cves)}}
    if kind:
        v["type"] = kind
    return v


APP = "com.example:app@1.0"
WEB = "org.springframework.boot:spring-boot-starter-web@3.5.16"
WS = "org.springframework.boot:spring-boot-starter-websocket@3.5.16"
TOMCAT = vuln("SNYK-TOMCAT-1", "org.apache.tomcat.embed:tomcat-embed-core", "10.1.26", "high",
              [APP, WEB, "org.springframework.boot:spring-boot-starter-tomcat@3.5.16",
               "org.apache.tomcat.embed:tomcat-embed-core@10.1.26"],
              [False, "org.springframework.boot:spring-boot-starter-web@4.1.1"], ["11.0.5"], ["CVE-2026-0001"])
WEBMVC = vuln("SNYK-WEBMVC-2", "org.springframework:spring-webmvc", "6.2.0", "critical",
              [APP, WEB, "org.springframework:spring-webmvc@6.2.0"],
              [False, "org.springframework.boot:spring-boot-starter-web@4.1.1"], ["7.0.1"], ["CVE-2026-0002"])
H2 = vuln("SNYK-H2-3", "com.h2database:h2", "2.2.224", "medium", [APP, "com.h2database:h2@2.2.224"],
          [False, "com.h2database:h2@2.3.232"], ["2.3.232"])
NOFIX = vuln("SNYK-NOFIX-4", "org.foo:bar", "1.0", "low", [APP, "org.foo:bar@1.0"], [], [], upgradable=False)


class ParseSnyk(Sandbox):
    def reports(self):
        app = [{"projectName": "com.example:app", "displayTargetFile": "backend/pom.xml", "dependencyCount": 120,
                "vulnerabilities": [TOMCAT, WEBMVC, H2, NOFIX]}]          # --all-projects shape: a list
        tomcat_again = dict(TOMCAT, **{"from": [APP, WS, "org.apache.tomcat.embed:tomcat-embed-core@10.1.26"],
                                       "upgradePath": [False, "org.springframework.boot:spring-boot-starter-websocket@4.1.1"]})
        lic = vuln("snyk:lic:gpl", "org.foo:gpl", "2.0", "high", [APP, "org.foo:gpl@2.0"], [], [], kind="license",
                   upgradable=False)
        orders = {"projectName": "com.example:orders", "displayTargetFile": "pom.xml",   # single-object shape
                  "vulnerabilities": [TOMCAT, tomcat_again, lic]}
        return (self.write("in/app.json", json.dumps(app)), self.write("in/orders.json", json.dumps(orders)),
                self.write("in/not-snyk.json", json.dumps({"packages": []})))

    def parse(self, *files):
        out = os.path.join(self.root, "out")
        proc = self.script("parse-snyk.py", *files, "--json", out + ".json", "--csv", out + ".csv",
                           "--md", out + ".md", check=True)
        with open(out + ".json") as fh:
            return json.load(fh), proc.stdout, out

    def test_every_flagged_package_is_listed_once_with_all_its_paths(self):
        data, _, _ = self.parse(*self.reports())
        names = [p["package"] for p in data["packages"]]
        # tomcat, webmvc, h2, bar (app) + gpl licence (orders); tomcat appears in both but is one row
        self.assertEqual(len(names), 5)
        self.assertEqual(len(set(names)), 5, "one row per package@version")
        tomcat = next(p for p in data["packages"] if p["package"].endswith("tomcat-embed-core"))
        self.assertEqual(sorted(tomcat["introduced_via"]), sorted([WEB, WS]))
        self.assertEqual(tomcat["fixed_in"], ["11.0.5"])
        self.assertEqual(len(tomcat["projects"]), 2)

    def test_sorted_by_severity_and_totals_count_each_issue_once_per_project(self):
        data, _, _ = self.parse(*self.reports())
        self.assertEqual(data["packages"][0]["max_severity"], "critical")
        # app: critical 1, high 1 (tomcat), medium 1, low 1; orders: high tomcat (once, 2 paths) + licence high
        self.assertEqual(data["totals"], {"critical": 1, "high": 3, "medium": 1, "low": 1})

    def test_changes_are_grouped_by_the_direct_dependency_to_edit(self):
        data, _, _ = self.parse(*self.reports())
        web = next(c for c in data["changes"] if c["direct_dependency"].endswith("starter-web"))
        self.assertEqual((web["current_version"], web["target_version"]), ("3.5.16", "4.1.1"))
        self.assertEqual(len(web["fixes_packages"]), 2, "one bump fixes tomcat + webmvc")
        nofix = next(c for c in data["changes"] if c["direct_dependency"] == "org.foo:bar")
        self.assertIsNone(nofix["target_version"])

    def test_license_and_no_fix_rows_are_marked(self):
        data, md, _ = self.parse(*self.reports())
        lic = next(p for p in data["packages"] if p["package"] == "org.foo:gpl")
        self.assertEqual(lic["type"], "license")
        self.assertIn("`org.foo:gpl` (license)", md)
        self.assertIn("no fix available", next(p for p in data["packages"] if p["package"] == "org.foo:bar")["remediation"])

    def test_non_snyk_files_are_skipped_with_a_warning(self):
        _, stdout, _ = self.parse(*self.reports())
        self.assertIn("not-snyk.json is not a snyk test --json report, skipped", stdout)
        self.assertIn("across 2 projects", stdout)

    def test_csv_has_a_row_per_flagged_package(self):
        _, _, out = self.parse(*self.reports())
        with open(out + ".csv", newline="") as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[0]["package"], "org.springframework:spring-webmvc")
        self.assertEqual(set(rows[0]), {"package", "current_version", "type", "max_severity", "issues", "cves",
                                        "fixed_in", "introduced_via", "remediation", "projects"})


FAKE_SNYK = """import json, os, sys
args = sys.argv[1:]
with open(%(log)r, "a", encoding="utf-8") as fh:
    fh.write("%%s | %%s %%s\\n" %% (%(ident)r, os.path.realpath(os.getcwd()), " ".join(args)))
if args[:1] == ["config"]:
    sys.exit(%(config_exit)d)
if args[:1] == ["whoami"]:
    sys.exit(%(whoami_exit)d)
print(json.dumps(json.loads(%(report)r)))
sys.exit(%(test_exit)d)
"""


class SnykScanTests:
    """snyk-scan.sh / snyk-scan.ps1 with a fake `snyk` CLI (a small Python program)."""

    def fake_snyk(self, test_exit=1, authenticated=True, path=None, sso_only=False):
        """Install a fake CLI at `path` (default: a bin dir put first on PATH). Returns (env, launcher).
        sso_only: logged in via browser/OAuth, so `config get api` finds no token but `whoami` works."""
        on_path = path is None
        base = path or os.path.join(self.tmp, "bin", "snyk")
        report = json.dumps([{"projectName": "x", "vulnerabilities": [H2]}])
        launcher = self.make_tool(base, FAKE_SNYK % {
            "log": os.path.join(self.tmp, "calls.log"), "ident": base, "report": report, "test_exit": test_exit,
            "config_exit": 0 if authenticated and not sso_only else 2, "whoami_exit": 0 if authenticated else 2})
        env = dict(self.env)
        if on_path:
            env["PATH"] = os.path.dirname(base) + os.pathsep + env["PATH"]
        return env, launcher

    def env_without_snyk(self):
        names = ("snyk", "snyk.exe", "snyk.cmd")
        keep = [d for d in self.env["PATH"].split(os.pathsep) if not any(os.path.exists(os.path.join(d, n)) for n in names)]
        return dict(self.env, PATH=os.pathsep.join(keep))

    def calls(self):
        path = os.path.join(self.tmp, "calls.log")
        return self.read(path) if os.path.exists(path) else ""

    def cloned_repo(self, name):
        url, _ = self.make_remote(name)
        self.git(self.tmp, "clone", "-q", url, os.path.join(self.root, "repos", name))
        return url

    def clone_dir(self, name):
        return os.path.realpath(os.path.join(self.root, "repos", name))

    def test_missing_cli_exits_127_with_install_help(self):
        self.manifest()
        proc = self.script("snyk-scan.sh", "out", env=self.env_without_snyk())
        self.assertEqual(proc.returncode, 127)
        self.assertIn("install", proc.stdout.lower())
        self.assertIn("SNYK_CLI", proc.stdout)
        self.assertIn("same SSO account", proc.stdout)

    def test_unauthenticated_cli_exits_126(self):
        self.manifest()
        env, _ = self.fake_snyk(authenticated=False)
        self.assertEqual(self.script("snyk-scan.sh", "out", env=env).returncode, 126)

    def test_sso_login_without_a_token_is_accepted(self):
        self.manifest("svc-a  %s" % self.cloned_repo("svc-a"))
        env, _ = self.fake_snyk(sso_only=True)
        proc = self.script("snyk-scan.sh", "out", env=env)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertTrue(os.path.isfile(os.path.join(self.root, "out", "svc-a.json")))

    def test_scans_each_clone_and_records_results(self):
        self.manifest("svc-a  %s" % self.cloned_repo("svc-a"), "ghost  https://example.com/ghost.git")
        env, _ = self.fake_snyk(test_exit=1)
        proc = self.script("snyk-scan.sh", "out", "--org=acme", env=env)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        with open(os.path.join(self.root, "out", "svc-a.json"), encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)[0]["vulnerabilities"][0]["id"], "SNYK-H2-3")
        index = self.read("out/scan-index.tsv")
        self.assertIn("svc-a\t%s\t1\tvulnerabilities found" % os.path.join(self.root, "repos", "svc-a"), index)
        self.assertIn("ghost", index)
        self.assertIn("not cloned", index)
        self.assertIn("| %s test --all-projects --json --org=acme" % self.clone_dir("svc-a"), self.calls(),
                      "runs inside the clone and passes extra args through")

    def test_workflow_option_scans_only_that_workflows_repos(self):
        self.manifest("svc-a  %s" % self.cloned_repo("svc-a"), "svc-b  %s" % self.cloned_repo("svc-b"))
        wf = self.script("workflows.py", "new", "a-only", "--repo", "svc-a", check=True).stdout.split("\t")[0]
        env, _ = self.fake_snyk()
        proc = self.script("snyk-scan.sh", "out", "--workflow", wf, env=env)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertTrue(os.path.isfile(os.path.join(self.root, "out", "svc-a.json")))
        self.assertFalse(os.path.exists(os.path.join(self.root, "out", "svc-b.json")))

    def test_snyk_cli_setting_points_at_the_extensions_cli(self):
        self.manifest("svc-a  %s" % self.cloned_repo("svc-a"))
        base = os.path.join(self.tmp, "vscode-ext", "snyk-cli")
        _, launcher = self.fake_snyk(path=base)
        proc = self.script("snyk-scan.sh", "out", env=dict(self.env_without_snyk(), SNYK_CLI=launcher))
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("Using Snyk CLI: %s" % launcher, proc.stdout)
        self.assertIn("%s | %s test" % (base, self.clone_dir("svc-a")), self.calls())

    def test_snyk_cli_setting_wins_over_snyk_on_path(self):
        self.manifest("svc-a  %s" % self.cloned_repo("svc-a"))
        env, _ = self.fake_snyk()                                   # one `snyk` on PATH ...
        _, launcher = self.fake_snyk(path=os.path.join(self.tmp, "other", "snyk-custom"))   # ... and SNYK_CLI's
        proc = self.script("snyk-scan.sh", "out", env=dict(env, SNYK_CLI=launcher))
        self.assertIn("Using Snyk CLI: %s" % launcher, proc.stdout)

    def test_bad_snyk_cli_setting_is_reported(self):
        self.manifest()
        missing = os.path.join(self.tmp, "nope", "snyk")
        proc = self.script("snyk-scan.sh", "out", env=dict(self.env_without_snyk(), SNYK_CLI=missing))
        self.assertEqual(proc.returncode, 127)
        self.assertIn("SNYK_CLI is set to '%s', but that is not an executable file" % missing, proc.stdout)

    def test_cli_downloaded_by_the_vscode_extension_is_found_automatically(self):
        self.manifest("svc-a  %s" % self.cloned_repo("svc-a"))
        if ON_WINDOWS:
            base = os.path.join(self.env["LOCALAPPDATA"], "snyk", "snyk-win")
        else:
            base = os.path.join(self.home, "Library", "Application Support", "snyk", "snyk-macos-arm64")
        _, launcher = self.fake_snyk(path=base)
        proc = self.script("snyk-scan.sh", "out", env=self.env_without_snyk())
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("Using Snyk CLI: %s" % launcher, proc.stdout)


class SnykScanBash(BashScripts, SnykScanTests, Sandbox):
    pass


class SnykScanPowerShell(PowerShellScripts, SnykScanTests, Sandbox):
    pass
