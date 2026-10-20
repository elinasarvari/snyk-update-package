"""parse-snyk.py and snyk-scan.sh - with fixture reports and a fake `snyk` CLI (no network, no account)."""
import csv
import json
import os
import sys
import re
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
        nofix = next(p for p in data["packages"] if p["package"] == "org.foo:bar")
        text = " ".join(nofix["remediation"])
        self.assertIn("no Snyk fix on this path (checked: upgrade path, remediation section, pin, fixed-in)", text)
        self.assertIn("plan: a newer `org.foo:bar` that fixes it", text, "says what the plan checks next")
        self.assertEqual(nofix["status"], "no fix")

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
        self.assertEqual(set(rows[0]), {"package", "current_version", "type", "max_severity", "status", "paths", "issues",
                                        "cves", "fixed_in", "introduced_via", "remediation", "projects"})


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


class RemediationAndPaths(Sandbox):
    """A package can arrive by several paths; each path has its own fix (or none). Snyk's remediation section counts."""

    def report(self, vulns, remediation=None):
        project = {"projectName": "com.example:app", "displayTargetFile": "pom.xml", "vulnerabilities": vulns}
        if remediation is not None:
            project["remediation"] = remediation
        return self.write("in/r.json", json.dumps(project))

    def parse(self, path):
        out = os.path.join(self.root, "out")
        proc = self.script("parse-snyk.py", path, "--json", out + ".json", "--md", out + ".md", check=True)
        with open(out + ".json", encoding="utf-8") as fh:
            return json.load(fh), self.read(out + ".md")

    def snakeyaml(self, via, upgrade_to=None, fixed=("2.0",), vid="SNYK-YAML-1"):
        return vuln(vid, "org.yaml:snakeyaml", "1.33", "high", [APP] + via + ["org.yaml:snakeyaml@1.33"],
                    [False, upgrade_to] if upgrade_to else [], list(fixed), ["CVE-2022-1471"],
                    upgradable=bool(upgrade_to))

    def test_every_path_is_listed_with_its_own_fix(self):
        data, md = self.parse(self.report([
            self.snakeyaml(["org.springframework.boot:spring-boot-starter@3.0.0"],
                           upgrade_to="org.springframework.boot:spring-boot-starter@3.2.0"),
            self.snakeyaml(["com.acme:legacy-config@1.0"]),                          # no upgrade path, but a fix exists
        ]))
        pkg = data["packages"][0]
        self.assertEqual(len(pkg["paths"]), 2)
        fixes = {tuple(p["path"]): p["fix"] for p in pkg["paths"]}
        self.assertEqual(fixes[("org.springframework.boot:spring-boot-starter@3.0.0", "org.yaml:snakeyaml@1.33")], "upgrade")
        self.assertEqual(fixes[("com.acme:legacy-config@1.0", "org.yaml:snakeyaml@1.33")], "override")
        self.assertEqual(pkg["status"], "needs an override", "upgrading the starter alone leaves the legacy path open")
        kinds = {(c["fix"], c["direct_dependency"], c["target_version"]) for c in data["changes"]}
        self.assertIn(("upgrade", "org.springframework.boot:spring-boot-starter", "3.2.0"), kinds)
        self.assertIn(("override", "org.yaml:snakeyaml", "2.0"), kinds, "the override is planned, not dropped")
        self.assertIn("## 3. Detailed paths", md)
        self.assertIn("`com.acme:legacy-config@1.0` › `org.yaml:snakeyaml@1.33`", md)
        self.assertIn("override `org.yaml:snakeyaml` to 2.0", md)

    def test_snyk_pin_suggestion_is_used(self):
        data, _ = self.parse(self.report(
            [self.snakeyaml(["com.acme:legacy-config@1.0"], fixed=("2.0", "1.34"))],
            remediation={"pin": {"org.yaml:snakeyaml@1.33": {"upgradeTo": "org.yaml:snakeyaml@2.2", "vulns": ["SNYK-YAML-1"]}}}))
        path = data["packages"][0]["paths"][0]
        self.assertEqual(path["fix"], "override")
        self.assertIn("to 2.2 (Snyk pin", path["remediation"])

    def test_no_upgrade_path_uses_the_remediation_sections_upgrade_for_that_paths_dependency(self):
        # The finding says "no fix", but Snyk's remediation section upgrades its direct dependency to 3.2.5 (and lists
        # the issue): that path is an upgrade to Snyk's version, not an override or "none". Entries for another
        # dependency, or that don't list this issue, don't count.
        data, md = self.parse(self.report(
            [self.snakeyaml(["org.springframework.boot:spring-boot-starter@3.0.0"], fixed=()),
             self.snakeyaml(["com.acme:other@1.0"], fixed=())],
            remediation={"upgrade": {
                "org.springframework.boot:spring-boot-starter@3.0.0": {
                    "upgradeTo": "org.springframework.boot:spring-boot-starter@3.2.5", "upgrades": ["org.yaml:snakeyaml@1.33"],
                    "vulns": ["SNYK-YAML-1"]},
                "com.acme:unrelated@1.0": {"upgradeTo": "com.acme:unrelated@9.0", "vulns": ["SNYK-YAML-1"]},
                "com.acme:other@1.0": {"upgradeTo": "com.acme:other@2.0", "vulns": ["SNYK-OTHER-9"]}}}))
        fixes = {p["path"][0]: (p["fix"], p["remediation"]) for p in data["packages"][0]["paths"]}
        self.assertEqual(fixes["org.springframework.boot:spring-boot-starter@3.0.0"],
                         ("upgrade", "upgrade `org.springframework.boot:spring-boot-starter` 3.0.0 -> 3.2.5 (Snyk remediation)"))
        self.assertEqual(fixes["com.acme:other@1.0"][0], "none", "only an upgrade that lists THIS issue counts")
        kinds = {(c["fix"], c["direct_dependency"], c["target_version"]) for c in data["changes"]}
        self.assertIn(("upgrade", "org.springframework.boot:spring-boot-starter", "3.2.5"), kinds)
        self.assertEqual(data["packages"][0]["status"], "partly fixable")

    def test_a_path_without_any_remediation_makes_the_package_partly_fixable(self):
        unfixable = vuln("SNYK-YAML-1", "org.yaml:snakeyaml", "1.33", "high",
                         [APP, "com.acme:old-thing@0.9", "org.yaml:snakeyaml@1.33"], [], [], upgradable=False)
        data, md = self.parse(self.report(
            [self.snakeyaml(["org.springframework.boot:spring-boot-starter@3.0.0"],
                            upgrade_to="org.springframework.boot:spring-boot-starter@3.2.0"), unfixable],
            remediation={"unresolved": [{"id": "SNYK-YAML-1"}]}))
        pkg = data["packages"][0]
        self.assertEqual(pkg["status"], "partly fixable")
        none = [p["remediation"] for p in pkg["paths"] if p["fix"] == "none"]
        self.assertEqual(len(none), 1)
        self.assertIn("no Snyk fix on this path (Snyk: unresolved)", none[0])
        self.assertIn("the lowest newer `com.acme:old-thing` that drops or fixes it, or exclude it", none[0],
                      "names the library that brings it in on that path")

    def test_override_takes_the_lowest_fixed_version_above_yours_in_version_order(self):
        # Text order would pick "1.10.0" (and "2.4.1" below); version order on your line picks 1.9.5 and 2.6.
        lib = vuln("SNYK-LIB-1", "org.example:lib", "1.9.0", "high", [APP, "com.acme:x@1.0", "org.example:lib@1.9.0"],
                   [], ["2.0", "1.10.0", "1.9.5"], upgradable=False)
        old = vuln("SNYK-OLD-2", "org.example:old", "2.5", "high", [APP, "com.acme:y@1.0", "org.example:old@2.5"],
                   [], ["3.0", "2.4.1", "2.6"], upgradable=False)
        data, _ = self.parse(self.report([lib, old]))
        fixes = {p["package"]: p["paths"][0]["remediation"] for p in data["packages"]}
        self.assertIn("to 1.9.5 ", fixes["org.example:lib"])
        self.assertIn("to 2.6 ", fixes["org.example:old"], "fixed versions below yours don't count")

    def test_long_path_lists_are_capped_in_markdown_but_complete_in_json(self):
        vulns = [self.snakeyaml(["com.acme:lib-%02d@1.0" % n]) for n in range(25)]
        data, md = self.parse(self.report(vulns))
        self.assertEqual(len(data["packages"][0]["paths"]), 25)
        self.assertIn("… 5 more paths in findings.json", md)


class VulnerableModules(Sandbox):
    """--modules: the itemized "Vulnerable modules" section of the plan, generated so nothing can be missed."""

    def test_every_module_issue_and_path_is_itemized_with_decision_fields(self):
        yaml1 = vuln("SNYK-YAML-1", "org.yaml:snakeyaml", "1.33", "high",
                     [APP, "org.springframework.boot:spring-boot-starter@3.0.0", "org.yaml:snakeyaml@1.33"],
                     [False, "org.springframework.boot:spring-boot-starter@3.2.0"], ["2.0"], ["CVE-2022-1471"])
        yaml1.update({"cvssScore": 8.3, "exploit": "Proof of Concept", "identifiers": {"CVE": ["CVE-2022-1471"], "CWE": ["CWE-502"]}})
        yaml2 = vuln("SNYK-YAML-2", "org.yaml:snakeyaml", "1.33", "medium",
                     [APP, "com.acme:legacy-config@1.0", "org.yaml:snakeyaml@1.33"], [], ["1.34"], ["CVE-2022-38749"],
                     upgradable=False)
        report = self.write("in/r.json", json.dumps({"projectName": "com.example:app", "vulnerabilities": [yaml1, yaml2, H2, NOFIX]}))
        out = os.path.join(self.root, "modules.md")
        self.script("parse-snyk.py", report, "--modules", out, check=True)
        md = self.read(out)
        self.assertEqual(md.count("\n### "), 3, "one entry per vulnerable module")
        for issue in ("SNYK-YAML-1", "SNYK-YAML-2", "SNYK-H2-3", "SNYK-NOFIX-4"):
            self.assertIn("[%s](https://security.snyk.io/vuln/%s)" % (issue, issue), md, "every issue, linked")
        self.assertIn("| 8.3 | CVE-2022-1471 | CWE-502 | Proof of Concept | 2.0 |", md)
        self.assertIn("| Dependency paths | 2 (listed below) |", md)
        self.assertIn("`com.acme:legacy-config@1.0` › `org.yaml:snakeyaml@1.33`", md)
        self.assertIn("| Fixed in | no fixed version |", md)
        self.assertEqual(md.count("| Plan step(s) | {{"), 3, "a decision table to fill in for every module")
        self.assertIn("| Fix chosen | {{no Snyk fix:", md, "no Snyk fix: left open")

    def test_target_is_snyks_version_and_the_highest_of_snyks_when_it_names_several(self):
        # Two issues in one package, Snyk names 2.9 and 2.10 for the same starter: 2.10 fixes both (version order).
        a = vuln("SNYK-A-1", "org.example:core", "1.0", "high", [APP, "org.example:starter@2.0", "org.example:core@1.0"],
                 [False, "org.example:starter@2.9"], ["1.1"])
        b = vuln("SNYK-B-2", "org.example:core", "1.0", "high", [APP, "org.example:starter@2.0", "org.example:core@1.0"],
                 [False, "org.example:starter@2.10"], ["1.2"])
        report = self.write("in/r.json", json.dumps({"projectName": "com.example:app", "vulnerabilities": [a, b]}))
        out = os.path.join(self.root, "modules.md")
        self.script("parse-snyk.py", report, "--modules", out, check=True)
        self.assertIn("| Target version | `org.example:starter` 2.10 _(Snyk's version, exactly)_ |", self.read(out))


class ModulesIntoPlan(Sandbox):
    """--into-plan: the script puts the itemized modules into 02-plan.md, so nobody re-types them (token budget)."""

    def setUp(self):
        super().setUp()
        self.report = self.write("in/r.json", json.dumps({"projectName": "com.example:app", "vulnerabilities": [H2, NOFIX]}))
        self.plan = self.write("plan.md", self.read("toolkit/templates/02-plan.md"))

    def test_modules_replace_the_placeholder_section_and_leave_the_rest_alone(self):
        before = self.read(self.plan)
        self.script("parse-snyk.py", self.report, "--into-plan", self.plan, check=True)
        after = self.read(self.plan)
        self.assertIn("### 1. `com.h2database:h2@2.2.224`", after)
        self.assertIn("### 2. `org.foo:bar@1.0`", after)
        self.assertNotIn("{{group:artifact@version}}", after.split("## Path coverage")[0], "placeholder module replaced")
        for keep in ("## Approval", "## Strategy", "## Steps", "## Path coverage", "## Rollback", "## Out of scope"):
            self.assertIn(keep, after)
        self.assertEqual(before.split("## Path coverage")[1], after.split("## Path coverage")[1], "the rest is untouched")

    def test_running_it_again_keeps_every_filled_in_field_even_partly_decided_modules(self):
        helpers = os.path.join(self.root, "toolkit", "scripts", "script-helpers.py")
        self.script("parse-snyk.py", self.report, "--into-plan", self.plan, check=True)
        decide = lambda *a: self.run_cmd([sys.executable, "-I", helpers, "plan-decide", self.plan] + list(a), check=True)
        decide("1", "In scope?=yes", "Target version=2.3.232", "Plan step(s)=Step 1", "Compatibility / risk=low, patch line",
               "Fix chosen=upgrade `com.h2database:h2` to 2.3.232")
        decide("2", "Plan step(s)=Step 4")                     # module 2 only partly decided
        proc = self.script("parse-snyk.py", self.report, "--into-plan", self.plan, check=True)
        self.assertIn("filled-in decision fields kept", proc.stdout)
        again = self.read(self.plan)
        mod1, mod2 = again.split("### 2.")[0], again.split("### 2.")[1]
        self.assertIn("| Fix chosen | upgrade `com.h2database:h2` to 2.3.232 |", mod1, "your decision wins over Snyk's")
        self.assertIn("| Compatibility / risk | low, patch line |", mod1)
        self.assertIn("| Plan step(s) | Step 4 |", mod2, "a partly decided module keeps what was decided")
        self.assertIn("| In scope? | {{", mod2, "... and the rest stays open")

    def test_a_plan_without_the_section_is_an_error(self):
        self.write(self.plan, "# plan\n\n## Steps\n")
        self.assertNotEqual(self.script("parse-snyk.py", self.report, "--into-plan", self.plan).returncode, 0)


class EfficientPlanning(Sandbox):
    """The plan step reads a one-line index and sets decisions in bulk; plan-check proves nothing was left open."""

    def setUp(self):
        super().setUp()
        up = vuln("SNYK-UP-1", "org.example:up", "1.0", "high", [APP, "org.example:intro@1.0", "org.example:up@1.0"],
                  [False, "org.example:intro@2.0"], ["1.1"], ["CVE-2026-0101"])
        pin = vuln("SNYK-PIN-2", "org.example:pin", "3.0", "medium", [APP, "org.example:legacy@0.1", "org.example:pin@3.0"],
                   [], ["3.1"], ["CVE-2026-0102"], upgradable=False)
        self.write("wf/snyk/app.json", json.dumps({"projectName": "com.example:app", "vulnerabilities": [up, pin, NOFIX]}))
        self.write("wf/snyk/findings.json", "{}")                               # our own output, must be ignored
        self.plan = self.write("wf/02-plan.md", self.read("toolkit/templates/02-plan.md"))
        self.helpers = os.path.join(self.root, "toolkit", "scripts", "script-helpers.py")

    def helper(self, *args, **kw):
        return self.run_cmd([sys.executable, "-I", self.helpers] + list(args), **kw)

    def test_wildcards_are_expanded_by_the_script_itself_and_own_outputs_skipped(self):
        proc = self.script("parse-snyk.py", os.path.join(self.root, "wf", "snyk", "*.json"),    # unexpanded, like PowerShell
                           "--index", os.path.join(self.root, "wf", "index.md"), check=True)
        self.assertIn("across 1 projects", proc.stdout)
        self.assertNotIn("findings.json is not", proc.stdout, "our own findings.json is skipped quietly")

    def test_index_is_one_terse_line_per_module(self):
        self.script("parse-snyk.py", os.path.join(self.root, "wf", "snyk", "*.json"), "--index",
                    os.path.join(self.root, "wf", "index.md"), check=True)
        index = self.read("wf/index.md")
        rows = [l for l in index.splitlines() if re.match(r"^\| \d+ \|", l)]
        self.assertEqual(len(rows), 3)
        self.assertIn("| `org.example:up@1.0` | high | fixable by upgrade | 1 | 1 | upgrade intro→2.0 |", index)
        self.assertIn("override→3.1", index)
        self.assertIn("no fix", index)

    def test_snyk_decisions_are_prefilled_and_the_rest_left_open(self):
        self.script("parse-snyk.py", os.path.join(self.root, "wf", "snyk", "*.json"), "--into-plan", self.plan, check=True)
        plan = self.read(self.plan)
        self.assertIn("| Fix chosen | upgrade `org.example:intro` 1.0 -> 2.0 _(Snyk's fix for every path)_ |", plan)
        self.assertIn("| Verified by | Snyk re-scan shows SNYK-UP-1 gone · build and tests green |", plan)
        self.assertIn("| Fix chosen | {{no Snyk fix:", plan, "no fix: left for a decision")
        self.assertIn("| Target version | `org.example:intro` 2.0 _(Snyk's version, exactly)_ |", plan)
        self.assertIn("| Target version | `org.example:pin` 3.1 _(Snyk's version, exactly)_ |", plan)
        self.assertIn("| Target version | {{no Snyk version: the LOWEST version", plan, "no Snyk version: never guessed")

    def test_bulk_decisions_then_plan_check_proves_completeness(self):
        self.script("parse-snyk.py", os.path.join(self.root, "wf", "snyk", "*.json"), "--into-plan", self.plan, check=True)
        check = self.helper("plan-check", self.plan)
        self.assertEqual(check.returncode, 1)
        self.assertIn("3 of 3 modules still have open decisions", check.stdout)
        self.helper("plan-decide", self.plan, "all", "In scope?=yes", "Compatibility / risk=see Impact | low", check=True)
        self.helper("plan-decide", self.plan, "1-2", "Plan step(s)=Step 1", check=True)
        self.helper("plan-decide", self.plan, "status:fixable by upgrade", "Target version=1.1", check=True)
        self.helper("plan-decide", self.plan, "2", "Target version=3.1", check=True)
        still = self.helper("plan-check", self.plan)
        self.assertIn("1 of 3 modules still have open decisions", still.stdout)
        self.assertIn("3. org.foo:bar@1.0: Fix chosen, Target version, Plan step(s)", still.stdout)
        self.helper("plan-decide", self.plan, "3", "In scope?=no, see Out of scope #1", "Fix chosen=out of scope",
                    "Target version=-", "Plan step(s)=-", check=True)
        done = self.helper("plan-check", self.plan)
        self.assertEqual(done.returncode, 0, done.stdout)
        self.assertIn("all 3 modules decided", done.stdout)
        self.assertIn("| Compatibility / risk | see Impact / low |", self.read(self.plan), "| in a value can't break the table")

    def test_plan_decide_rejects_unknown_fields_and_empty_selections(self):
        self.script("parse-snyk.py", os.path.join(self.root, "wf", "snyk", "*.json"), "--into-plan", self.plan, check=True)
        self.assertNotEqual(self.helper("plan-decide", self.plan, "1", "Colour=blue").returncode, 0)
        self.assertNotEqual(self.helper("plan-decide", self.plan, "status:does not exist", "In scope?=yes").returncode, 0)


class ReuseHelper(Sandbox):
    """script-helpers.py reuse: facts, baseline and analyst reports are redone only when the repo's commit (or, for an
    analysis, the version jump) changed - so re-planning doesn't re-analyse everything."""

    def setUp(self):
        super().setUp()
        self.repo = os.path.join(self.tmp, "svc")
        os.makedirs(self.repo)
        self.git(self.repo, "init", "-q", "-b", "main")
        self.git(self.repo, "commit", "-q", "--allow-empty", "-m", "one")
        self.commit = self.git(self.repo, "rev-parse", "--short", "HEAD").strip()
        self.helpers = os.path.join(self.root, "toolkit", "scripts", "script-helpers.py")

    def reuse(self, *args):
        return self.run_cmd([sys.executable, "-I", self.helpers, "reuse"] + list(args))

    def test_results_made_at_the_current_commit_are_reused(self):
        facts = self.write("facts.env", "BUILD_TOOL=maven\nGIT_COMMIT=%s\n" % self.commit)
        base = self.write("summary.json", json.dumps({"commit": self.commit, "status": "green"}))
        report = self.write("analysis.md", "SUMMARY | g:a | 1.0 → 2.0 | major | high | 3 | 1 | M\nBASED ON | %s | 1.0 → 2.0\n" % self.commit)
        for args in (("facts", facts, self.repo), ("baseline", base, self.repo), ("analysis", report, self.repo, "1.0", "2.0")):
            proc = self.reuse(*args)
            self.assertEqual(proc.returncode, 0, proc.stdout)
            self.assertIn("reuse ", proc.stdout)

    def test_anything_else_is_redone_with_the_reason(self):
        report = self.write("analysis.md", "SUMMARY | g:a | 1.0 → 2.0\nBASED ON | %s | 1.0 → 2.0\n" % self.commit)
        other_jump = self.reuse("analysis", report, self.repo, "1.0", "3.0")
        self.assertEqual(other_jump.returncode, 1)
        self.assertIn("made for 1.0 → 2.0, now 1.0 → 3.0", other_jump.stdout)
        self.assertIn("not there yet", self.reuse("facts", os.path.join(self.tmp, "nope.env"), self.repo).stdout)
        old = self.write("no-based-on.md", "SUMMARY | g:a | 1.0 → 2.0\n")
        self.assertIn("no 'BASED ON", self.reuse("analysis", old, self.repo, "1.0", "2.0").stdout)
        facts = self.write("facts.env", "GIT_COMMIT=%s\n" % self.commit)
        self.git(self.repo, "commit", "-q", "--allow-empty", "-m", "two")
        moved = self.reuse("facts", facts, self.repo)
        self.assertEqual(moved.returncode, 1)
        self.assertIn("made at %s, the repo is now at" % self.commit, moved.stdout)


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

    def test_reuse_scans_each_repo_once_per_commit(self):
        self.manifest("svc-a  %s" % self.cloned_repo("svc-a"), "svc-b  %s" % self.cloned_repo("svc-b"))
        env, _ = self.fake_snyk()
        scans = lambda: self.calls().count("test --all-projects")
        self.script("snyk-scan.sh", "out", "--reuse", env=env, check=True)          # nothing to reuse yet
        self.assertEqual(scans(), 2)
        index = self.read("out/scan-index.tsv")
        commit_a = self.git(self.clone_dir("svc-a"), "rev-parse", "--short", "HEAD").strip()
        self.assertIn("\t1\tvulnerabilities found\t%s" % commit_a, index, "the commit scanned is recorded")

        proc = self.script("snyk-scan.sh", "out", "--reuse", env=env, check=True)   # same commits: no new scans
        self.assertEqual(scans(), 2, proc.stdout)
        self.assertIn("REUSE svc-a: already scanned at %s" % commit_a, proc.stdout)
        self.assertIn("vulnerabilities found (reused)\t%s" % commit_a, self.read("out/scan-index.tsv"))

        self.git(self.clone_dir("svc-a"), "commit", "-q", "--allow-empty", "-m", "new code")
        proc = self.script("snyk-scan.sh", "out", "--reuse", env=env, check=True)   # svc-a changed: only it is rescanned
        self.assertEqual(scans(), 3, proc.stdout)
        self.assertIn("SCAN svc-a", proc.stdout)
        self.assertIn("REUSE svc-b", proc.stdout)
        self.assertNotIn("(reused) (reused)", self.read("out/scan-index.tsv"))

        self.script("snyk-scan.sh", "out", env=env, check=True)                     # without --reuse: a fresh scan
        self.assertEqual(scans(), 5)

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
