"""workflows.py: unique workflow ids, folders, step states, history and the index."""
import os
import re
import sys

from helpers import Sandbox


class WorkflowIds(Sandbox):
    def new(self, slug, *extra):
        out = self.script("workflows.py", "new", slug, *extra, check=True).stdout.strip()
        wf_id, folder = out.split("\t")
        return wf_id, folder

    def test_first_and_second_workflows_get_sequential_ids_and_own_folders(self):
        one = self.new("spring-boot", "--title", "Spring Boot 4", "--source", "manual")
        two = self.new("jackson-fix")
        self.assertEqual(one, ("wf-001", "workflows/wf-001-spring-boot"))
        self.assertEqual(two, ("wf-002", "workflows/wf-002-jackson-fix"))
        status = self.read(os.path.join(one[1], "STATUS.md"))
        self.assertTrue(status.startswith("# Workflow 1: Spring Boot 4"))
        self.assertIn("`wf-001`", status)
        self.assertIn("`deps/wf-001`", status)
        self.assertIn("| **Source** | manual |", status)
        self.assertNotIn("{{", status, "all template placeholders must be filled")
        self.assertIn("Workflow 1 created (wf-001)", status)
        self.assertIn("Workflow 2 created (wf-002)", self.read(os.path.join(two[1], "STATUS.md")))

    def test_ids_are_never_reused_after_a_folder_is_deleted(self):
        self.new("a")
        _, folder = self.new("b")
        import shutil
        shutil.rmtree(os.path.join(self.root, folder))
        self.assertEqual(self.new("c")[0], "wf-003")

    def test_slug_is_normalised(self):
        self.assertEqual(self.new("Spring Boot 4.1!")[1], "workflows/wf-001-spring-boot-4-1")

    def test_resolve_accepts_every_way_of_referring_to_a_workflow(self):
        self.new("spring-boot")
        self.new("jackson-fix")
        for ref in ("2", "002", "wf-2", "wf-002", "WF-002", "wf-002-jackson-fix", "jackson-fix",
                    "workflows/wf-002-jackson-fix/"):
            out = self.script("workflows.py", "resolve", ref).stdout.strip()
            self.assertEqual(out, "workflows/wf-002-jackson-fix", "ref %r" % ref)
        proc = self.script("workflows.py", "resolve", "9")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("known: wf-001, wf-002", proc.stdout)


class StepsHistoryIndex(Sandbox):
    def setUp(self):
        super().setUp()
        self.script("workflows.py", "new", "spring-boot", "--title", "Spring Boot 4", check=True)
        self.status = "workflows/wf-001-spring-boot/STATUS.md"

    def row(self, n):
        for line in self.read(self.status).splitlines():
            if re.match(r"^\|\s*%d\s*\|" % n, line):
                return [c.strip() for c in line.strip().strip("|").split("|")]
        self.fail("no row %d" % n)

    def test_phase_updates_state_date_history_and_index(self):
        self.script("workflows.py", "phase", "1", "1", "running", check=True)
        self.assertTrue(self.row(1)[3].startswith("🟡"))
        self.assertRegex(self.row(1)[5], r"\d{4}-\d{2}-\d{2}")
        self.script("workflows.py", "phase", "wf-001", "1", "done", check=True)
        self.script("workflows.py", "phase", "1", "2", "blocked", "--note", "version mismatch", check=True)
        self.assertEqual(self.row(2)[3], "⛔ blocked (version mismatch)")
        text = self.read(self.status)
        self.assertIn("Step 1 Snyk scan → 🟡 in progress", text)
        self.assertIn("Step 2 Inventory → ⛔ blocked: version mismatch", text)
        index = self.read("workflows/INDEX.md")
        self.assertIn("[`wf-001`](wf-001-spring-boot/STATUS.md)", index)
        self.assertIn("0 Clone target repos: ⬜ not started", index, "current step = first step not done")

    def test_skipped_and_done_steps_are_passed_over_in_the_index(self):
        for n in range(0, 7):
            self.script("workflows.py", "phase", "1", str(n), "skipped" if n == 1 else "done", check=True)
        self.assertIn("all steps done ✅", self.read("workflows/INDEX.md"))

    def test_invalid_step_or_state_is_rejected(self):
        self.assertNotEqual(self.script("workflows.py", "phase", "1", "7", "done").returncode, 0)
        self.assertNotEqual(self.script("workflows.py", "phase", "1", "1", "finished").returncode, 0)

    def test_next_replaces_the_next_step_section(self):
        self.script("workflows.py", "next", "1", "Run `/dep-scan wf-001`", check=True)
        self.script("workflows.py", "next", "1", "Review 03-plan.md", check=True)
        text = self.read(self.status)
        section = text.split("## ▶ Next step", 1)[1].split("## ", 1)[0]
        self.assertEqual(section.strip(), "Review 03-plan.md")
        self.assertIn("Review 03-plan.md", self.read("workflows/INDEX.md"))

    def test_log_appends_history_in_order(self):
        self.script("workflows.py", "log", "1", "Plan approved: \"approve\"", check=True)
        self.script("workflows.py", "log", "1", "PR opened | https://example/pr/1", check=True)
        history = self.read(self.status).split("## History", 1)[1]
        first, second = history.index("Plan approved"), history.index("PR opened")
        self.assertLess(first, second)
        self.assertIn("PR opened \\| https://example/pr/1", history, "pipes are escaped so the table stays intact")

    def test_list_shows_every_workflow(self):
        self.script("workflows.py", "new", "jackson", check=True)
        out = self.script("workflows.py", "list", check=True).stdout
        self.assertIn("wf-001", out)
        self.assertIn("wf-002", out)


class OneRepoRuns(Sandbox):
    """What /dep-run relies on: runs scoped to one repo, resuming the open one, and `show`."""

    def setUp(self):
        super().setUp()
        self.manifest("svc  https://example.com/svc.git  path=api", "orders  https://example.com/orders.git")

    def new(self, *args):
        return self.script("workflows.py", "new", *args, check=True).stdout.strip().split("\t")

    def test_new_with_repo_writes_the_runs_own_scope(self):
        wf_id, folder = self.new("svc", "--repo", "svc")
        scope = self.read(os.path.join(folder, "repos.txt"))
        self.assertIn("svc  https://example.com/svc.git  path=api", scope)
        self.assertNotIn("orders", scope)
        self.assertIn("Workflow 1 created (wf-001) for svc", self.read(os.path.join(folder, "STATUS.md")))
        # the scope file is a valid manifest for the other scripts
        names = self.script("repos.py", "--manifest", os.path.join(self.root, folder, "repos.txt"), "list",
                            check=True).stdout.split("\t")[0]
        self.assertEqual(names, "svc")

    def test_new_with_unknown_repo_fails_and_creates_nothing(self):
        proc = self.script("workflows.py", "new", "x", "--repo", "billing")
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual([d for d in os.listdir(os.path.join(self.root, "workflows")) if d.startswith("wf-")], [])

    def test_find_open_returns_the_unfinished_run_for_that_repo_only(self):
        self.assertEqual(self.script("workflows.py", "find-open", "--repo", "svc").returncode, 1, "none yet")
        self.new("all-repos")                                   # wf-001: whole list, not scoped
        self.new("orders", "--repo", "orders")                  # wf-002
        self.new("svc", "--repo", "svc")                        # wf-003
        out = self.script("workflows.py", "find-open", "--repo", "svc", check=True).stdout.strip()
        self.assertEqual(out.split("\t")[0], "wf-003")
        for n in range(7):                                      # finish wf-003
            self.script("workflows.py", "phase", "3", str(n), "done", check=True)
        self.assertEqual(self.script("workflows.py", "find-open", "--repo", "svc").returncode, 1,
                         "a finished run is not resumed; /dep-run starts wf-004")

    def test_show_prints_steps_scope_branch_and_next(self):
        self.new("svc", "--repo", "svc", "--title", "Snyk fixes: svc")
        self.script("workflows.py", "phase", "1", "0", "done", check=True)
        self.script("workflows.py", "next", "1", "Run /dep-run svc", check=True)
        out = self.script("workflows.py", "show", "wf-001", check=True).stdout
        self.assertIn("Workflow 1 (wf-001): Snyk fixes: svc", out)
        self.assertIn("Repos:   svc", out)
        self.assertIn("Branch:  deps/wf-001", out)
        self.assertIn("Current: 1 Snyk scan", out)
        self.assertIn("Next:    Run /dep-run svc", out)


class SavingRecords(Sandbox):
    """workflows.py save: commit only the workflow's records, never raw data, and push - privately."""

    def setUp(self):
        super().setUp()
        self.env["SUP_REPO_VISIBILITY"] = "private"
        self.origin = os.path.join(self.tmp, "origin.git")
        self.git(self.tmp, "init", "-q", "--bare", "-b", "main", self.origin)
        self.write("README.md", "# project\n")
        self.git(self.root, "init", "-q", "-b", "main")
        self.git(self.root, "add", "-A")
        self.git(self.root, "commit", "-q", "-m", "initial")
        self.git(self.root, "remote", "add", "origin", self.origin)
        self.git(self.root, "push", "-q", "-u", "origin", "main")

    def new_with_data(self, slug="svc"):
        wf_id, folder = self.script("workflows.py", "new", slug, check=True).stdout.strip().split("\t")
        self.write(os.path.join(folder, "01-snyk-findings.md"), "# findings\n")
        self.write(os.path.join(folder, "snyk", "findings.json"), "{}\n")
        self.write(os.path.join(folder, "snyk", "svc.json"), '{"raw": "megabytes"}\n')
        self.write(os.path.join(folder, "snyk", "svc.err"), "stderr\n")
        self.write(os.path.join(folder, "verification", "baseline", "svc", "build.log"), "lots of maven output\n")
        self.write(os.path.join(folder, "verification", "baseline", "svc", "summary.json"), "{}\n")
        return wf_id, folder

    def pushed_files(self):
        return self.git(self.root, "ls-tree", "-r", "--name-only", "origin/main").splitlines()

    def test_save_pushes_the_records_but_not_raw_data(self):
        wf_id, folder = self.new_with_data()
        proc = self.script("workflows.py", "save", "1")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.git(self.root, "fetch", "-q")
        files = self.pushed_files()
        for kept in ("STATUS.md", "01-snyk-findings.md", "snyk/findings.json", "verification/baseline/svc/summary.json"):
            self.assertIn("%s/%s" % (folder, kept), files)
        self.assertIn("workflows/INDEX.md", files)
        for dropped in ("snyk/svc.json", "snyk/svc.err", "verification/baseline/svc/build.log"):
            self.assertNotIn("%s/%s" % (folder, dropped), files, "raw data must stay out of git")
        self.assertIn("workflow wf-001", self.git(self.root, "log", "-1", "--format=%s", "origin/main"))

    def test_save_commits_only_the_workflow_never_your_other_changes(self):
        self.new_with_data()
        self.write("README.md", "# my unrelated edit\n")
        self.write("notes.txt", "scratch\n")
        self.script("workflows.py", "save", "1", check=True)
        changed = self.git(self.root, "show", "--name-only", "--format=", "HEAD").splitlines()
        self.assertTrue(all(f.startswith("workflows/") for f in changed), changed)
        self.assertEqual(self.read("README.md"), "# my unrelated edit\n", "your edit is untouched")
        status = self.git(self.root, "status", "--porcelain")
        self.assertIn("README.md", status)
        self.assertIn("notes.txt", status)

    def test_a_public_repository_is_refused_unless_explicitly_allowed(self):
        self.new_with_data()
        env = dict(self.env, SUP_REPO_VISIBILITY="public")
        proc = self.script("workflows.py", "save", "1", env=env)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("REFUSED: this repository is PUBLIC", proc.stdout)
        self.assertEqual(self.git(self.root, "rev-list", "--count", "HEAD"), "1", "nothing committed")
        self.script("workflows.py", "save", "1", "--allow-public", env=env, check=True)
        self.git(self.root, "fetch", "-q")
        self.assertTrue(any(f.startswith("workflows/wf-001") for f in self.pushed_files()))

    def test_save_rebases_onto_records_pushed_from_another_machine(self):
        other = os.path.join(self.tmp, "other-machine")
        self.git(self.tmp, "clone", "-q", self.origin, other)
        self.assertTrue(os.path.isdir(os.path.join(other, "toolkit")), "the clone brings the toolkit")
        os.makedirs(os.path.join(other, "workflows"), exist_ok=True)
        self.run_cmd([sys.executable, "-I", os.path.join(other, "toolkit", "scripts", "workflows.py"), "new", "billing"],
                     cwd=other, check=True)
        self.run_cmd([sys.executable, "-I", os.path.join(other, "toolkit", "scripts", "workflows.py"), "save", "1"],
                     cwd=other, check=True)                                  # wf-001-billing pushed from elsewhere
        wf_id, _ = self.script("workflows.py", "new", "svc", check=True).stdout.strip().split("\t")
        self.assertEqual(wf_id, "wf-002", "new pulled first, so the id doesn't clash with the other machine's")
        self.script("workflows.py", "save", "2", check=True)
        self.git(self.root, "fetch", "-q")
        files = self.pushed_files()
        self.assertTrue(any(f.startswith("workflows/wf-001-billing/") for f in files))
        self.assertTrue(any(f.startswith("workflows/wf-002-svc/") for f in files))
        self.assertIn("wf-001", self.read("workflows/INDEX.md"))
        self.assertIn("wf-002", self.read("workflows/INDEX.md"))

    def test_saving_twice_without_changes_is_harmless(self):
        self.new_with_data()
        self.script("workflows.py", "save", "1", check=True)
        commits = self.git(self.root, "rev-list", "--count", "HEAD")
        proc = self.script("workflows.py", "save", "1", check=True)
        self.assertIn("nothing new to commit", proc.stdout)
        self.assertEqual(self.git(self.root, "rev-list", "--count", "HEAD"), commits)

    def test_no_push_only_commits(self):
        self.new_with_data()
        self.script("workflows.py", "save", "1", "--no-push", check=True)
        self.git(self.root, "fetch", "-q")
        self.assertFalse(any(f.startswith("workflows/") for f in self.pushed_files()))
        self.assertIn("workflow wf-001", self.git(self.root, "log", "-1", "--format=%s"))
