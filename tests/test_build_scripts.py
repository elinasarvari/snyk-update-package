"""verify-repo.sh and maven-facts.sh - with fake builds and tiny jars, so no real repo is built."""
import json
import os
import shutil
import unittest

from helpers import Sandbox

SUREFIRE = """<?xml version="1.0"?>
<testsuite name="{name}" tests="{tests}" failures="{failures}" errors="0" skipped="{skipped}">
  <testcase classname="com.example.{name}" name="works"/>
  {failure}
</testsuite>
"""
HAVE_JDK = shutil.which("javac") is not None and shutil.which("jar") is not None


class VerifyRepo(Sandbox):
    def repo(self):
        path = os.path.join(self.tmp, "svc")
        os.makedirs(path)
        self.write(os.path.join(path, "pom.xml"), "<project/>\n")
        self.git(path, "init", "-q", "-b", "main")
        self.git(path, "add", "-A")
        self.git(path, "commit", "-q", "-m", "initial")
        return path

    def fake_build(self, tests=3, failures=0, skipped=0, exit_code=0):
        failure = '<testcase classname="com.example.Broken" name="fails"><failure message="boom"/></testcase>' if failures else ""
        xml = SUREFIRE.format(name="AppTest", tests=tests, failures=failures, skipped=skipped, failure=failure)
        script = self.write(os.path.join(self.tmp, "build.sh"), "\n".join([
            "mkdir -p target/surefire-reports",
            "cat > target/surefire-reports/TEST-AppTest.xml <<'XML'", xml, "XML",
            "echo '[INFO] fake build'", "%s" % ("echo '[ERROR] Tests failed' && exit %d" % exit_code if exit_code else "exit 0"), ""]))
        return "bash " + script

    def verify(self, repo, *args):
        out = os.path.join(self.tmp, "verify")
        proc = self.script("verify-repo.sh", repo, out, *args)
        summary = os.path.join(out, "summary.json")
        return proc, (json.load(open(summary)) if os.path.isfile(summary) else None)

    def test_green_build_counts_tests_from_junit_xml(self):
        proc, summary = self.verify(self.repo(), "--build-cmd", self.fake_build(tests=3, skipped=1))
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertEqual(summary["status"], "green")
        self.assertEqual(summary["tests"]["tests"], 3)
        self.assertEqual(summary["tests"]["skipped"], 1)
        self.assertEqual(summary["smoke"], "skipped")
        self.assertEqual(summary["branch"], "main")

    def test_failing_tests_make_it_red_and_name_the_failed_test(self):
        proc, summary = self.verify(self.repo(), "--build-cmd", self.fake_build(tests=2, failures=1, exit_code=1))
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(summary["status"], "build-failed")
        self.assertEqual(summary["tests"]["failures"], 1)
        self.assertEqual(summary["tests"]["failed_tests"], ["com.example.Broken#fails"])
        self.assertIn("[ERROR] Tests failed", proc.stdout, "prints the first errors from the log")

    def test_folder_without_build_file_is_unsupported(self):
        empty = os.path.join(self.tmp, "empty")
        os.makedirs(empty)
        proc, summary = self.verify(empty)
        self.assertEqual(proc.returncode, 3)
        self.assertEqual(summary["status"], "unsupported")

    def test_build_command_is_auto_detected(self):
        repo = self.repo()
        wrapper = self.write(os.path.join(repo, "mvnw"), "#!/bin/bash\necho \"wrapper called: $*\"\n")
        os.chmod(wrapper, 0o755)
        proc, summary = self.verify(repo)
        self.assertEqual(summary["build_cmd"], "./mvnw -B clean verify")
        self.assertIn("wrapper called: -B clean verify", open(os.path.join(self.tmp, "verify", "build.log")).read())

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
        self.assertIn("Started App in", open(os.path.join(self.tmp, "verify", "smoke.log")).read())

    @unittest.skipUnless(HAVE_JDK, "needs javac and jar")
    def test_smoke_boot_failure_is_red_even_when_tests_pass(self):
        repo = self.repo()
        self.jar(repo, 'System.out.println("APPLICATION FAILED TO START"); System.exit(1);')
        proc, summary = self.verify(repo, "--smoke", "--build-cmd", self.fake_build())
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(summary["status"], "smoke-failed")
        self.assertEqual(summary["smoke"], "failed")


class MavenFacts(Sandbox):
    def test_non_maven_folder_is_reported_unsupported(self):
        empty = os.path.join(self.tmp, "gradle-only")
        os.makedirs(empty)
        self.write(os.path.join(empty, "build.gradle"), "")
        proc = self.script("maven-facts.sh", empty, os.path.join(self.tmp, "facts"))
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
        env = dict(self.env, HOME=os.path.expanduser("~"))          # reuse the real ~/.m2 cache
        out = os.path.join(self.tmp, "facts")
        proc = self.script("maven-facts.sh", repo, out, "commons-pool2", env=env)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        facts = self.read(os.path.join(out, "facts.env"))
        self.assertIn("BUILD_TOOL=maven (mvn)", facts)
        self.assertIn("PROJECT_JAVA=17", facts)
        self.assertIn("dependency\torg.apache.commons:commons-pool2:${pool.version}", self.read(os.path.join(out, "declared.txt")))
        self.assertIn("<pool.version>2.12.0</pool.version>", self.read(os.path.join(out, "version-props.txt")))
        self.assertIn("org.apache.commons:commons-pool2:jar:2.12.0:compile", self.read(os.path.join(out, "filtered-tree.txt")))
