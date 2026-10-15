"""parse-snyk.py and snyk-scan.sh - with fixture reports and a fake `snyk` CLI (no network, no account)."""
import csv
import json
import os
import stat

from helpers import Sandbox


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


class SnykScan(Sandbox):
    def fake_snyk(self, test_exit=1, authenticated=True, path=None, sso_only=False):
        """A fake CLI. sso_only: logged in via browser/OAuth, so `config get api` finds no token."""
        bin_dir = os.path.join(self.tmp, "bin")
        report = json.dumps([{"projectName": "x", "vulnerabilities": [H2]}]).replace("'", "'\\''")
        path = self.write(path or os.path.join(bin_dir, "snyk"), "\n".join([
            "#!/bin/bash",
            'echo "$0 | $PWD $*" >> "%s/calls.log"' % self.tmp,
            'if [ "$1" = config ]; then exit %d; fi' % (0 if authenticated and not sso_only else 2),
            'if [ "$1" = whoami ]; then exit %d; fi' % (0 if authenticated else 2),
            "echo '%s'" % report,
            "exit %d" % test_exit, ""]))
        os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
        return dict(self.env, PATH=bin_dir + os.pathsep + self.env["PATH"])

    def env_without_snyk(self):
        return dict(self.env, PATH=os.pathsep.join(d for d in self.env["PATH"].split(os.pathsep)
                                                   if not os.path.exists(os.path.join(d, "snyk"))))

    def cloned_repo(self, name):
        url, _ = self.make_remote(name)
        self.git(self.tmp, "clone", "-q", url, os.path.join(self.root, "repos", name))
        return url

    def test_missing_cli_exits_127_with_install_help(self):
        env = dict(self.env, PATH=os.pathsep.join(d for d in self.env["PATH"].split(os.pathsep)
                                                    if not os.path.exists(os.path.join(d, "snyk"))))
        self.manifest()
        proc = self.script("snyk-scan.sh", "out", env=env)
        self.assertEqual(proc.returncode, 127)
        self.assertIn("brew install snyk-cli", proc.stdout)

    def test_unauthenticated_cli_exits_126(self):
        self.manifest()
        self.assertEqual(self.script("snyk-scan.sh", "out", env=self.fake_snyk(authenticated=False)).returncode, 126)

    def test_scans_each_repo_folder_and_records_results(self):
        url = self.cloned_repo("svc-a")
        self.manifest("svc-a  %s" % url, "ghost  https://example.com/ghost.git")
        proc = self.script("snyk-scan.sh", "out", "--org=acme", env=self.fake_snyk(test_exit=1))
        self.assertEqual(proc.returncode, 0, proc.stdout)
        with open(os.path.join(self.root, "out", "svc-a.json")) as fh:
            self.assertEqual(json.load(fh)[0]["vulnerabilities"][0]["id"], "SNYK-H2-3")
        index = self.read("out/scan-index.tsv")
        self.assertIn("svc-a\t%s\t1\tvulnerabilities found" % os.path.join(self.root, "repos", "svc-a"), index)
        self.assertIn("ghost", index)
        self.assertIn("not cloned", index)
        calls = self.read(os.path.join(self.tmp, "calls.log"))
        self.assertIn("| %s test --all-projects --json --org=acme" % os.path.join(self.root, "repos", "svc-a"), calls,
                      "runs inside the repo folder and passes extra args through")

    def test_workflow_option_scans_only_that_workflows_repos(self):
        a, b = self.cloned_repo("svc-a"), self.cloned_repo("svc-b")
        self.manifest("svc-a  %s" % a, "svc-b  %s" % b)
        wf = self.script("workflows.py", "new", "a-only", "--repo", "svc-a", check=True).stdout.split("\t")[0]
        proc = self.script("snyk-scan.sh", "out", "--workflow", wf, env=self.fake_snyk())
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertTrue(os.path.isfile(os.path.join(self.root, "out", "svc-a.json")))
        self.assertFalse(os.path.exists(os.path.join(self.root, "out", "svc-b.json")))

    # --- which CLI, and SSO logins ------------------------------------------------------------
    def test_sso_login_without_a_token_is_accepted(self):
        url = self.cloned_repo("svc-a")
        self.manifest("svc-a  %s" % url)
        proc = self.script("snyk-scan.sh", "out", env=self.fake_snyk(sso_only=True))
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertTrue(os.path.isfile(os.path.join(self.root, "out", "svc-a.json")))

    def test_snyk_cli_setting_points_at_the_extensions_cli(self):
        url = self.cloned_repo("svc-a")
        self.manifest("svc-a  %s" % url)
        cli = os.path.join(self.tmp, "vscode-ext", "snyk-macos-arm64")
        self.fake_snyk(path=cli)
        env = dict(self.env_without_snyk(), SNYK_CLI=cli)
        proc = self.script("snyk-scan.sh", "out", env=env)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("Using Snyk CLI: %s" % cli, proc.stdout)
        self.assertIn("%s | %s test" % (cli, os.path.join(self.root, "repos", "svc-a")),
                      self.read(os.path.join(self.tmp, "calls.log")))

    def test_snyk_cli_setting_wins_over_snyk_on_path(self):
        url = self.cloned_repo("svc-a")
        self.manifest("svc-a  %s" % url)
        env = self.fake_snyk()                                  # one `snyk` on PATH ...
        cli = os.path.join(self.tmp, "other", "snyk-custom")
        self.fake_snyk(path=cli)                                # ... and the one SNYK_CLI names
        proc = self.script("snyk-scan.sh", "out", env=dict(env, SNYK_CLI=cli))
        self.assertIn("Using Snyk CLI: %s" % cli, proc.stdout)

    def test_bad_snyk_cli_setting_is_reported(self):
        self.manifest()
        proc = self.script("snyk-scan.sh", "out", env=dict(self.env_without_snyk(), SNYK_CLI="/nope/snyk"))
        self.assertEqual(proc.returncode, 127)
        self.assertIn("SNYK_CLI is set to '/nope/snyk', but that is not an executable file", proc.stdout)

    def test_cli_downloaded_by_the_vscode_extension_is_found_automatically(self):
        url = self.cloned_repo("svc-a")
        self.manifest("svc-a  %s" % url)
        cli = os.path.join(self.home, "Library", "Application Support", "snyk", "snyk-macos-arm64")
        self.fake_snyk(path=cli)
        proc = self.script("snyk-scan.sh", "out", env=self.env_without_snyk())
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("Using Snyk CLI: %s" % cli, proc.stdout)

    def test_missing_cli_message_explains_the_vscode_option(self):
        self.manifest()
        proc = self.script("snyk-scan.sh", "out", env=self.env_without_snyk())
        self.assertEqual(proc.returncode, 127)
        self.assertIn("export SNYK_CLI=", proc.stdout)
        self.assertIn("same SSO account", proc.stdout)
