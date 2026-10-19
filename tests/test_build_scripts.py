"""verify-repo and maven-facts - every test runs against the bash (*.sh) AND the PowerShell (*.ps1) version,
with fake builds and tiny jars, so no real repo is built."""
import json
import os
import shutil
import unittest

from helpers import ON_WINDOWS, BashScripts, PowerShellScripts, Sandbox

HAVE_JDK = shutil.which("javac") is not None and shutil.which("jar") is not None

FAKE_BUILD = '''import os, sys
os.makedirs(os.path.join("target", "surefire-reports"), exist_ok=True)
failure = '<testcase classname="com.example.Broken" name="fails"><failure message="boom"/></testcase>' if {failures} else ""
with open(os.path.join("target", "surefire-reports", "TEST-AppTest.xml"), "w") as fh:
    fh.write('<?xml version="1.0"?>\\n<testsuite name="AppTest" tests="{tests}" failures="{failures}" errors="0" '
             'skipped="{skipped}"><testcase classname="com.example.AppTest" name="works"/>%s</testsuite>\\n' % failure)
print("[INFO] fake build")
{extra}
if {exit_code}:
    print("[ERROR] Tests failed")
sys.exit({exit_code})
'''


class VerifyRepoTests:
    def repo(self):
        path = os.path.join(self.tmp, "svc")
        os.makedirs(path)
        self.write(os.path.join(path, "pom.xml"), "<project/>\n")
        self.write(os.path.join(path, ".gitignore"), "target/\n")       # like any real Maven repo
        self.git(path, "init", "-q", "-b", "main")
        self.git(path, "add", "-A")
        self.git(path, "commit", "-q", "-m", "initial")
        return path

    def fake_build(self, tests=3, failures=0, skipped=0, exit_code=0, extra=""):
        script = self.write(os.path.join(self.tmp, "build.py"), FAKE_BUILD.format(
            tests=tests, failures=failures, skipped=skipped, exit_code=exit_code, extra=extra))
        return self.python_command(script)

    def verify(self, repo, *args):
        out = os.path.join(self.tmp, "verify")
        proc = self.script("verify-repo.sh", repo, out, *args)
        summary = os.path.join(out, "summary.json")
        if not os.path.isfile(summary):
            return proc, None
        with open(summary, encoding="utf-8") as fh:
            return proc, json.load(fh)

    def test_green_build_counts_tests_from_junit_xml(self):
        proc, summary = self.verify(self.repo(), "--build-cmd", self.fake_build(tests=3, skipped=1))
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertEqual(summary["status"], "green")
        self.assertEqual(summary["tests"]["tests"], 3)
        self.assertEqual(summary["tests"]["skipped"], 1)
        self.assertEqual(summary["smoke"], "skipped")
        self.assertEqual(summary["branch"], "main")
        self.assertEqual(summary["build_cmd"], self.fake_build(tests=3, skipped=1), "quotes survive")
        self.assertIn("version", summary["java"])

    def test_failing_tests_make_it_red_and_name_the_failed_test(self):
        proc, summary = self.verify(self.repo(), "--build-cmd", self.fake_build(tests=2, failures=1, exit_code=1))
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(summary["status"], "build-failed")
        self.assertEqual(summary["tests"]["failures"], 1)
        self.assertEqual(summary["tests"]["failed_tests"], ["com.example.Broken#fails"])
        self.assertIn("[ERROR] Tests failed", proc.stdout, "prints the first errors from the log")

    def test_multi_module_build_counts_every_modules_tests(self):
        repo = self.repo()
        build = self.write(os.path.join(self.tmp, "multi.py"), "\n".join([
            "import os",
            "def suite(mod, folder, tests, failing=None):",
            "    d = os.path.join(mod, *folder.split('/')); os.makedirs(d, exist_ok=True)",
            "    bad = '<testcase classname=\"%s.Broken\" name=\"fails\"><failure/></testcase>' % mod if failing else ''",
            "    open(os.path.join(d, 'TEST-%s.xml' % mod), 'w').write('<testsuite name=\"%s\" tests=\"%d\" failures=\"%d\" errors=\"0\" skipped=\"0\">%s</testsuite>' % (mod, tests, 1 if failing else 0, bad))",
            "suite('service-a', 'target/surefire-reports', 3)",
            "suite('service-b', 'target/surefire-reports', 2, failing=True)",
            "suite('service-c', 'target/failsafe-reports', 1)",
            "suite('node_modules/some-lib', 'target/surefire-reports', 99)",   # must be ignored
            "raise SystemExit(1)", ""]))
        proc, summary = self.verify(repo, "--build-cmd", self.python_command(build))
        self.assertEqual(summary["tests"]["tests"], 6, "3 + 2 + 1 across modules; node_modules ignored")
        self.assertEqual(summary["tests"]["failures"], 1)
        self.assertEqual(summary["tests"]["failed_tests"], ["service-b.Broken#fails"])
        self.assertEqual(summary["status"], "build-failed")

    def test_a_clean_build_leaves_nothing_in_the_repo(self):
        repo = self.repo()
        proc, summary = self.verify(repo, "--build-cmd", self.fake_build())
        self.assertEqual(summary["left_in_repo"], [], proc.stdout)
        self.assertEqual(self.git(repo, "status", "--porcelain", "--untracked-files=all"), "")
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, "verify", "build.log")), "logs go to the out dir")
        self.assertEqual(sorted(os.listdir(os.path.join(self.tmp, "verify"))), ["build.log", "summary.json"],
                         "no temporary files left behind")

    def test_files_a_build_leaves_outside_target_are_reported_not_deleted(self):
        repo = self.repo()
        build = self.fake_build(extra='open("generated-report.txt", "w").write("x")')
        proc, summary = self.verify(repo, "--build-cmd", build)
        self.assertEqual(proc.returncode, 0, "a warning, not a failure")
        self.assertEqual(summary["left_in_repo"], ["generated-report.txt"])
        self.assertIn("WARNING: the build left files in the repo", proc.stdout)
        self.assertTrue(os.path.exists(os.path.join(repo, "generated-report.txt")), "never deletes anything")

    def test_folder_without_build_file_is_unsupported(self):
        empty = os.path.join(self.tmp, "empty")
        os.makedirs(empty)
        proc, summary = self.verify(empty)
        self.assertEqual(proc.returncode, 3)
        self.assertEqual(summary["status"], "unsupported")

    def test_unknown_argument_is_rejected(self):
        proc, _ = self.verify(self.repo(), "--colour")
        self.assertEqual(proc.returncode, 64)

    def test_missing_arguments_exit_1_with_the_same_message(self):
        proc = self.script("verify-repo.sh")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("repo dir required", proc.stdout)
        proc = self.script("verify-repo.sh", self.repo())
        self.assertEqual(proc.returncode, 1)
        self.assertIn("out dir required", proc.stdout)

    def test_maven_wrapper_is_auto_detected(self):
        repo = self.repo()
        if ON_WINDOWS:
            self.write(os.path.join(repo, "mvnw.cmd"), "@echo wrapper called: %*\r\n")
            expected = "mvnw.cmd -B clean verify"
        else:
            wrapper = self.write(os.path.join(repo, "mvnw"), "#!/bin/sh\necho \"wrapper called: $*\"\n")
            os.chmod(wrapper, 0o755)
            expected = "./mvnw -B clean verify"
        proc, summary = self.verify(repo)
        self.assertEqual(summary["build_cmd"], expected)
        self.assertIn("wrapper called: -B clean verify", self.read(os.path.join(self.tmp, "verify", "build.log")))

    # --- smoke boot ----------------------------------------------------------------------------
    def jar(self, repo, main_body):
        src = self.write(os.path.join(self.tmp, "src", "App.java"),
                         "public class App { public static void main(String[] a) throws Exception { %s } }" % main_body)
        self.run_cmd(["javac", "-d", os.path.join(self.tmp, "classes"), src], check=True)
        self.write(os.path.join(self.tmp, "manifest.txt"), "Main-Class: App\n")
        os.makedirs(os.path.join(repo, "target"), exist_ok=True)
        self.run_cmd(["jar", "cfm", os.path.join(repo, "target", "app-1.0.jar"), os.path.join(self.tmp, "manifest.txt"),
                      "-C", os.path.join(self.tmp, "classes"), "."], check=True)

    @unittest.skipUnless(HAVE_JDK, "needs javac and jar")
    def test_smoke_boot_detects_a_started_app_and_stops_it(self):
        repo = self.repo()
        self.jar(repo, 'System.out.println("Started App in 0.5 seconds (process running)"); Thread.sleep(60000);')
        proc, summary = self.verify(repo, "--smoke", "--build-cmd", self.fake_build())
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertEqual(summary["smoke"], "started")
        self.assertIn("Started App in", self.read(os.path.join(self.tmp, "verify", "smoke.log")))

    @unittest.skipUnless(HAVE_JDK, "needs javac and jar")
    def test_files_the_app_writes_while_booting_land_in_the_out_dir_not_the_repo(self):
        repo = self.repo()
        self.jar(repo, 'java.nio.file.Files.write(java.nio.file.Paths.get("app.log"), "hello".getBytes()); '
                       'System.out.println("Started App in 0.5 seconds"); Thread.sleep(60000);')
        proc, summary = self.verify(repo, "--smoke", "--build-cmd", self.fake_build())
        self.assertEqual(summary["smoke"], "started", proc.stdout)
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, "verify", "app.log")))
        self.assertFalse(os.path.exists(os.path.join(repo, "app.log")))
        self.assertEqual(summary["left_in_repo"], [])

    @unittest.skipUnless(HAVE_JDK, "needs javac and jar")
    def test_smoke_boot_failure_is_red_even_when_tests_pass(self):
        repo = self.repo()
        self.jar(repo, 'System.out.println("APPLICATION FAILED TO START"); System.exit(1);')
        proc, summary = self.verify(repo, "--smoke", "--build-cmd", self.fake_build())
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(summary["status"], "smoke-failed")
        self.assertEqual(summary["smoke"], "failed")


class MavenFactsTests:
    def test_non_maven_folder_is_reported_unsupported(self):
        folder = os.path.join(self.tmp, "gradle-only")
        os.makedirs(folder)
        self.write(os.path.join(folder, "build.gradle"), "")
        proc = self.script("maven-facts.sh", folder, os.path.join(self.tmp, "facts"))
        self.assertEqual(proc.returncode, 3)
        self.assertIn("BUILD_TOOL=unsupported", self.read(os.path.join(self.tmp, "facts", "facts.env")))

    @unittest.skipUnless(os.environ.get("RUN_MAVEN_TESTS") == "1" and shutil.which("mvn"),
                         "set RUN_MAVEN_TESTS=1 (needs mvn and network or a warm ~/.m2)")
    def test_real_maven_project_parent_declared_deps_properties_and_tree(self):
        repo = os.path.join(self.tmp, "mvn-app")
        self.write(os.path.join(repo, "pom.xml"), """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId><artifactId>mvn-app</artifactId><version>1.0</version>
  <properties><java.version>17</java.version><pool.version>2.12.0</pool.version></properties>
  <dependencies>
    <dependency><groupId>org.apache.commons</groupId><artifactId>commons-pool2</artifactId><version>${pool.version}</version></dependency>
  </dependencies>
</project>
""")
        real_home = os.path.expanduser("~")
        env = dict(self.env, HOME=real_home, USERPROFILE=real_home)    # reuse the real ~/.m2 cache
        out = os.path.join(self.tmp, "facts")
        proc = self.script("maven-facts.sh", repo, out, "commons-pool2", env=env)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        facts = self.read(os.path.join(out, "facts.env"))
        self.assertIn("BUILD_TOOL=maven (mvn)", facts)
        self.assertIn("PROJECT_JAVA=17", facts)
        self.assertIn("dependency\torg.apache.commons:commons-pool2:${pool.version}", self.read(os.path.join(out, "declared.txt")))
        self.assertIn("./pom.xml: <pool.version>2.12.0</pool.version>", self.read(os.path.join(out, "version-props.txt")))
        self.assertIn("org.apache.commons:commons-pool2:jar:2.12.0:compile", self.read(os.path.join(out, "filtered-tree.txt")))


class VerifyRepoBash(BashScripts, VerifyRepoTests, Sandbox):
    pass


class VerifyRepoPowerShell(PowerShellScripts, VerifyRepoTests, Sandbox):
    pass


class MavenFactsBash(BashScripts, MavenFactsTests, Sandbox):
    pass


class MavenFactsPowerShell(PowerShellScripts, MavenFactsTests, Sandbox):
    pass
