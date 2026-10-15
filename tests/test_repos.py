"""repos.py: the list, clones in repos/<name>/, per-workflow branches, and what it must never do."""
import os

from helpers import Sandbox


class Clones(Sandbox):
    def test_repo_is_cloned_into_repos_folder_then_reported_up_to_date(self):
        url, _ = self.make_remote("orders")
        self.manifest("orders  %s" % url)
        first = self.script("repos.py", "clone")
        self.assertEqual(first.returncode, 0, first.stdout)
        self.assertIn("cloned into repos/orders", first.stdout)
        self.assertTrue(os.path.isfile(os.path.join(self.root, "repos", "orders", "pom.xml")))
        self.assertIn("up to date", self.script("repos.py", "clone").stdout)

    def test_clean_clone_on_main_is_fast_forwarded_when_remote_moves(self):
        url, seed = self.make_remote("orders")
        self.manifest("orders  %s" % url)
        self.script("repos.py", "clone", check=True)
        new_head = self.push_new_commit(seed)
        self.script("repos.py", "clone", check=True)
        self.assertEqual(self.git(os.path.join(self.root, "repos", "orders"), "rev-parse", "HEAD"), new_head)

    def test_clone_with_uncommitted_changes_is_left_alone(self):
        url, seed = self.make_remote("orders")
        self.manifest("orders  %s" % url)
        self.script("repos.py", "clone", check=True)
        clone = os.path.join(self.root, "repos", "orders")
        before = self.git(clone, "rev-parse", "HEAD")
        self.write(os.path.join(clone, "README.md"), "edit\n")
        self.push_new_commit(seed)
        self.assertIn("kept as is - 1 uncommitted file(s)", self.script("repos.py", "clone").stdout)
        self.assertEqual(self.git(clone, "rev-parse", "HEAD"), before, "must not pull over changes")
        self.assertEqual(self.read(os.path.join(clone, "README.md")), "edit\n")

    def test_clone_on_a_workflow_branch_is_not_switched_by_a_plain_clone(self):
        url, _ = self.make_remote("orders")
        self.manifest("orders  %s" % url)
        self.script("repos.py", "clone", check=True)
        clone = os.path.join(self.root, "repos", "orders")
        self.git(clone, "switch", "-q", "-c", "deps/wf-001")
        self.assertIn("kept as is - on deps/wf-001", self.script("repos.py", "clone").stdout)
        self.assertEqual(self.git(clone, "rev-parse", "--abbrev-ref", "HEAD"), "deps/wf-001")

    def test_clone_failure_is_reported_with_nonzero_exit(self):
        self.manifest("ghost  file://%s" % os.path.join(self.tmp, "remotes", "nope.git"))
        proc = self.script("repos.py", "clone")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("CLONE FAILED", proc.stdout)

    def test_clones_are_never_tracked_by_this_project_and_no_submodules(self):
        url, _ = self.make_remote("orders")
        self.manifest("orders  %s" % url)
        self.git(self.root, "init", "-q")
        self.script("repos.py", "clone", check=True)
        untracked = self.git(self.root, "status", "--porcelain", "--untracked-files=all")
        self.assertNotIn("repos/orders", untracked)
        self.assertIn("repos/repos.txt", untracked)
        self.assertFalse(os.path.exists(os.path.join(self.root, ".gitmodules")))

    def test_list_columns(self):
        url, _ = self.make_remote("orders")
        self.manifest("orders  %s  path=api  smoke=true  branch=develop" % url)
        row = self.script("repos.py", "list", check=True).stdout.rstrip("\n").split("\t")
        self.assertEqual(row, ["orders", os.path.join(self.root, "repos", "orders", "api"), "--smoke", url, "develop",
                               os.path.join(self.root, "repos", "orders")])


class YourCheckoutIsNeverTouched(Sandbox):
    """A local folder is only a way to find the URL: the work happens in repos/<name>/."""

    def user_checkout(self, name="inventory-service"):
        url, seed = self.make_remote(name)
        local = os.path.join(self.home, "repos", name)
        self.git(self.tmp, "clone", "-q", url, local)
        return url, seed, local

    def test_adding_a_local_folder_stores_its_url_and_clones_into_repos(self):
        url, _, local = self.user_checkout()
        self.git(local, "switch", "-q", "-c", "my-feature")
        self.write(os.path.join(local, "README.md"), "my work in progress\n")
        head = self.git(local, "rev-parse", "HEAD")
        self.manifest()
        self.script("repos.py", "add", local, "path=backend", check=True)
        self.assertIn("inventory-service  %s  path=backend" % url, self.read("repos/repos.txt"))
        wf = self.script("workflows.py", "new", "lj", check=True).stdout.split("\t")[0]
        self.script("repos.py", "--workflow", wf, "clone", check=True)
        self.assertEqual(self.git(os.path.join(self.root, "repos", "inventory-service"), "rev-parse", "--abbrev-ref", "HEAD"),
                         "deps/wf-001", "the work happens in the clone")
        # your checkout: same branch, same commit, same uncommitted work, no workflow branch
        self.assertEqual(self.git(local, "rev-parse", "--abbrev-ref", "HEAD"), "my-feature")
        self.assertEqual(self.git(local, "rev-parse", "HEAD"), head)
        self.assertEqual(self.read(os.path.join(local, "README.md")), "my work in progress\n")
        self.assertNotIn("deps/", self.git(local, "branch", "--list"))

    def test_a_local_folder_line_in_the_list_is_rejected_with_its_url(self):
        url, _, _ = self.user_checkout()
        self.manifest("inventory-service  ~/repos/inventory-service")
        proc = self.script("repos.py", "list")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("list its git URL instead: %s" % url, proc.stdout)

    def test_local_folder_without_a_remote_is_an_error(self):
        plain = os.path.join(self.home, "scratch")
        os.makedirs(plain)
        self.git(plain, "init", "-q")
        self.manifest()
        proc = self.script("repos.py", "add", plain)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("no 'origin' remote", proc.stdout)

    def test_paths_that_are_not_repositories_are_rejected(self):
        os.makedirs(os.path.join(self.home, "just-a-folder"))
        self.manifest()
        for path, message in ((os.path.join(self.home, "just-a-folder"), "is not a git repository"),
                              (os.path.join(self.home, "missing"), "does not exist")):
            proc = self.script("repos.py", "add", path)
            self.assertNotEqual(proc.returncode, 0, path)
            self.assertIn(message, proc.stdout)
        self.assertEqual([l for l in self.read("repos/repos.txt").splitlines() if l and not l.startswith("#")], [])


class WorkflowBranches(Sandbox):
    """repos.py --workflow <id> clone: each workflow gets deps/wf-NNN in the clone, from the latest main."""

    def setUp(self):
        super().setUp()
        self.url, self.seed = self.make_remote("svc")
        self.manifest("svc  %s" % self.url)
        self.clone = os.path.join(self.root, "repos", "svc")

    def workflow(self, slug="svc"):
        return self.script("workflows.py", "new", slug, check=True).stdout.split("\t")[0]

    def branch(self):
        return self.git(self.clone, "rev-parse", "--abbrev-ref", "HEAD")

    def test_branch_is_created_from_the_latest_main_in_the_clone(self):
        self.script("repos.py", "clone", check=True)
        latest = self.push_new_commit(self.seed)          # main moves after the clone was made
        wf = self.workflow()
        out = self.script("repos.py", "--workflow", wf, "clone", check=True).stdout
        self.assertIn("created deps/wf-001 from origin/main", out)
        self.assertEqual(self.branch(), "deps/wf-001")
        self.assertEqual(self.git(self.clone, "rev-parse", "HEAD"), latest, "based on the latest main")

    def test_branch_option_replaces_main(self):
        self.git(self.seed, "switch", "-q", "-c", "develop")
        self.write(os.path.join(self.seed, "dev.txt"), "dev\n")
        self.git(self.seed, "add", "-A")
        self.git(self.seed, "commit", "-q", "-m", "develop work")
        self.git(self.seed, "push", "-q", "origin", "develop")
        develop = self.git(self.seed, "rev-parse", "HEAD")
        self.manifest("svc  %s  branch=develop" % self.url)
        wf = self.workflow()
        self.script("repos.py", "--workflow", wf, "clone", check=True)
        self.assertEqual(self.git(self.clone, "rev-parse", "HEAD"), develop)

    def test_missing_main_branch_is_reported_not_guessed(self):
        self.script("repos.py", "clone", check=True)
        self.manifest("svc  %s  branch=trunk" % self.url)
        wf = self.workflow()
        proc = self.script("repos.py", "--workflow", wf, "clone")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("NO 'trunk' BRANCH", proc.stdout)

    def test_each_workflow_has_its_own_branch_and_switching_keeps_both(self):
        one, two = self.workflow("one"), self.workflow("two")
        self.script("repos.py", "--workflow", one, "clone", check=True)
        self.write(os.path.join(self.clone, "fix-one.txt"), "1\n")
        self.git(self.clone, "add", "-A")
        self.git(self.clone, "commit", "-q", "-m", "wf-001 change")
        self.script("repos.py", "--workflow", two, "clone", check=True)
        self.assertEqual(self.branch(), "deps/wf-002")
        self.assertFalse(os.path.exists(os.path.join(self.clone, "fix-one.txt")), "wf-002 starts clean from main")
        back = self.script("repos.py", "--workflow", one, "clone", check=True).stdout
        self.assertIn("switched back to existing deps/wf-001", back)
        self.assertTrue(os.path.exists(os.path.join(self.clone, "fix-one.txt")), "wf-001's work is still there")

    def test_another_workflows_unpublished_changes_block_the_switch(self):
        one, two = self.workflow("one"), self.workflow("two")
        self.script("repos.py", "--workflow", one, "clone", check=True)
        self.write(os.path.join(self.clone, "README.md"), "applied but not published\n")
        proc = self.script("repos.py", "--workflow", two, "clone")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("BLOCKED", proc.stdout)
        self.assertIn("unpublished changes of workflow wf-001", proc.stdout)
        self.assertEqual(self.branch(), "deps/wf-001", "nothing was switched")
        self.assertEqual(self.read(os.path.join(self.clone, "README.md")), "applied but not published\n")

    def test_resuming_the_same_workflow_keeps_its_uncommitted_work(self):
        wf = self.workflow()
        self.script("repos.py", "--workflow", wf, "clone", check=True)
        self.write(os.path.join(self.clone, "README.md"), "in progress\n")
        out = self.script("repos.py", "--workflow", wf, "clone", check=True).stdout
        self.assertIn("on deps/wf-001", out)
        self.assertIn("1 uncommitted file(s) from earlier steps", out)
        self.assertEqual(self.read(os.path.join(self.clone, "README.md")), "in progress\n")

    def test_status_shows_whether_the_clone_is_on_the_workflow_branch(self):
        wf = self.workflow()
        self.script("repos.py", "clone", check=True)
        self.assertTrue(self.script("repos.py", "--workflow", wf, "status", check=True).stdout.splitlines()[1].endswith("NO"))
        self.script("repos.py", "--workflow", wf, "clone", check=True)
        self.assertTrue(self.script("repos.py", "--workflow", wf, "status", check=True).stdout.splitlines()[1].endswith("yes"))

    def test_release_goes_back_to_main_and_keeps_the_branch(self):
        wf = self.workflow()
        self.script("repos.py", "--workflow", wf, "clone", check=True)
        self.write(os.path.join(self.clone, "README.md"), "dirty\n")
        self.assertIn("KEPT on deps/wf-001", self.script("repos.py", "--workflow", wf, "release").stdout)
        self.git(self.clone, "checkout", "--", "README.md")
        self.script("repos.py", "--workflow", wf, "release", check=True)
        self.assertEqual(self.branch(), "main")
        self.assertIn("deps/wf-001", self.git(self.clone, "branch", "--list"))

    def test_workflow_uses_its_own_repo_list(self):
        other, _ = self.make_remote("other")
        self.manifest("svc  %s" % self.url, "other  %s" % other)
        wf = self.script("workflows.py", "new", "svc-only", "--repo", "svc", check=True).stdout.split("\t")[0]
        names = [l.split("\t")[0] for l in self.script("repos.py", "--workflow", wf, "list", check=True).stdout.splitlines()]
        self.assertEqual(names, ["svc"])


class ManifestAndAdd(Sandbox):
    def test_add_url_derives_name(self):
        self.manifest()
        self.script("repos.py", "add", "git@github.com:acme/orders-service.git", check=True)
        self.assertIn("orders-service  git@github.com:acme/orders-service.git", self.read("repos/repos.txt"))

    def test_add_rejects_reserved_and_invalid_names_duplicates_and_unknown_options(self):
        self.manifest("orders  https://example.com/orders.git")
        for args in (["https://x/README.md.git"], ["https://x/a.git", "bad name"], ["https://example.com/orders.git"],
                     ["https://example.com/orders", "orders2"], ["https://x/a.git", "a", "colour=blue"]):
            self.assertNotEqual(self.script("repos.py", "add", *args).returncode, 0, "should reject: %s" % args)

    def test_unknown_option_in_list_is_an_error(self):
        self.manifest("orders  https://example.com/orders.git  colour=blue")
        proc = self.script("repos.py", "list")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("unknown option", proc.stdout)

    def test_path_to_a_bare_repository_is_a_valid_clone_source(self):
        url, _ = self.make_remote("orders")
        self.manifest("orders  %s" % url)
        self.assertIn("cloned", self.script("repos.py", "clone", check=True).stdout)


class Ensure(Sandbox):
    """repos.py ensure: what /dep-run uses to turn "a repo name, folder or URL" into a list entry."""

    def test_existing_entry_is_found_by_name_any_url_form_or_a_local_checkout(self):
        url, _ = self.make_remote("svc")
        local = os.path.join(self.home, "code", "svc")
        self.git(self.tmp, "clone", "-q", url, local)
        self.manifest("svc  %s" % url, "orders  https://github.com/acme/orders-service.git")
        before = self.read("repos/repos.txt")
        for ref, expected in (("svc", "svc"), (local, "svc"), ("~/code/svc", "svc"), ("orders", "orders"),
                              ("git@github.com:acme/orders-service.git", "orders"),
                              ("https://github.com/acme/orders-service", "orders"),
                              ("https://github.com/ACME/orders-service.git/", "orders")):
            out = self.script("repos.py", "ensure", ref, check=True).stdout.strip().splitlines()[-1]
            self.assertEqual(out, expected, ref)
        self.assertEqual(self.read("repos/repos.txt"), before, "finding must not change the list")

    def test_new_url_or_checkout_is_added_once_as_a_url(self):
        url, _ = self.make_remote("svc")
        local = os.path.join(self.home, "code", "svc")
        self.git(self.tmp, "clone", "-q", url, local)
        self.manifest()
        self.assertEqual(self.script("repos.py", "ensure", local, "path=api", check=True).stdout.strip().splitlines()[-1], "svc")
        self.script("repos.py", "ensure", url, check=True)
        self.script("repos.py", "ensure", "https://github.com/acme/new-thing.git", check=True)
        lines = [l for l in self.read("repos/repos.txt").splitlines() if l and not l.startswith("#")]
        self.assertEqual(lines, ["svc  %s  path=api" % url, "new-thing  https://github.com/acme/new-thing.git"])

    def test_unknown_bare_name_is_an_error_not_a_guess(self):
        self.manifest("svc  https://example.com/svc.git")
        proc = self.script("repos.py", "ensure", "billing")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("known: svc", proc.stdout)
