"""repos.py: the list, URL clones, local folders, and what it must never do to a repo."""
import os

from helpers import Sandbox


class UrlEntries(Sandbox):
    def test_url_is_cloned_into_repos_folder_then_reported_up_to_date(self):
        url, _ = self.make_remote("orders")
        self.manifest("orders  %s" % url)
        first = self.script("repos.py", "clone")
        self.assertEqual(first.returncode, 0, first.stdout)
        self.assertIn("cloned", first.stdout)
        self.assertTrue(os.path.isfile(os.path.join(self.root, "repos", "orders", "pom.xml")))
        again = self.script("repos.py", "clone")
        self.assertIn("up to date", again.stdout)

    def test_clean_clone_is_fast_forwarded_when_remote_moves(self):
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
        self.write(os.path.join(clone, "README.md"), "my local edit\n")
        self.push_new_commit(seed)
        out = self.script("repos.py", "clone").stdout
        self.assertIn("kept as is - 1 uncommitted file(s)", out)
        self.assertEqual(self.git(clone, "rev-parse", "HEAD"), before, "must not pull over local changes")
        self.assertEqual(self.read(os.path.join(clone, "README.md")), "my local edit\n")

    def test_clone_on_deps_branch_is_not_switched(self):
        url, _ = self.make_remote("orders")
        self.manifest("orders  %s" % url)
        self.script("repos.py", "clone", check=True)
        clone = os.path.join(self.root, "repos", "orders")
        self.git(clone, "switch", "-q", "-c", "deps/wf-001")
        out = self.script("repos.py", "clone").stdout
        self.assertIn("kept as is - on branch deps/wf-001", out)
        self.assertEqual(self.git(clone, "rev-parse", "--abbrev-ref", "HEAD"), "deps/wf-001")

    def test_clone_failure_is_reported_with_nonzero_exit(self):
        self.manifest("ghost  file://%s" % os.path.join(self.tmp, "remotes", "nope.git"))
        proc = self.script("repos.py", "clone")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("CLONE FAILED", proc.stdout)

    def test_clones_are_never_tracked_by_this_project(self):
        url, _ = self.make_remote("orders")
        self.manifest("orders  %s" % url)
        self.git(self.root, "init", "-q")
        self.script("repos.py", "clone", check=True)
        tracked_candidates = self.git(self.root, "status", "--porcelain", "--untracked-files=all")
        self.assertNotIn("repos/orders", tracked_candidates)
        self.assertIn("repos/repos.txt", tracked_candidates)
        self.assertFalse(os.path.exists(os.path.join(self.root, ".gitmodules")), "must never create submodules")


class LocalFolders(Sandbox):
    def make_local_checkout(self, name="learning-java"):
        url, seed = self.make_remote(name)
        local = os.path.join(self.home, "repos", name)
        self.git(self.tmp, "clone", "-q", url, local)
        return local, seed

    def test_local_folder_is_used_in_place_and_never_pulled_or_switched(self):
        local, seed = self.make_local_checkout()
        self.git(local, "switch", "-q", "-c", "feature-x")
        head_before = self.git(local, "rev-parse", "HEAD")
        self.push_new_commit(seed)                       # remote main moves on
        self.git(local, "branch", "-q", "--set-upstream-to=origin/main")
        self.manifest("learning-java  ~/repos/learning-java  branch=main")
        out = self.script("repos.py", "clone").stdout
        self.assertIn("local, used in place", out)
        self.assertIn("expected main", out)
        self.assertIn("1 commit(s) behind origin", out)
        self.assertEqual(self.git(local, "rev-parse", "HEAD"), head_before, "local folder must not be pulled")
        self.assertEqual(self.git(local, "rev-parse", "--abbrev-ref", "HEAD"), "feature-x", "must not switch")
        self.assertFalse(os.path.exists(os.path.join(self.root, "repos", "learning-java")), "must not clone a copy")

    def test_local_folder_reports_uncommitted_files_but_keeps_them(self):
        local, _ = self.make_local_checkout()
        self.write(os.path.join(local, "README.md"), "work in progress\n")
        self.manifest("learning-java  ~/repos/learning-java")
        out = self.script("repos.py", "clone").stdout
        self.assertIn("1 uncommitted file(s)", out)
        self.assertEqual(self.read(os.path.join(local, "README.md")), "work in progress\n")

    def test_missing_local_folder_fails(self):
        self.manifest("ghost  ~/repos/does-not-exist")
        proc = self.script("repos.py", "clone")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("LOCAL FOLDER NOT FOUND", proc.stdout)

    def test_list_reports_folder_kind_and_build_dir(self):
        local, _ = self.make_local_checkout()
        url, _ = self.make_remote("orders")
        self.manifest("learning-java  ~/repos/learning-java  path=backend  smoke=true", "orders  %s" % url)
        rows = [l.split("\t") for l in self.script("repos.py", "list", check=True).stdout.strip().splitlines()]
        self.assertEqual(len(rows), 2)
        lj, orders = rows
        self.assertEqual(len(lj), 7, "TSV columns: name build_dir verify_args url branch repo_dir kind")
        self.assertEqual(lj[0], "learning-java")
        self.assertEqual(lj[1], os.path.join(local, "backend"))
        self.assertEqual(lj[2], "--smoke")
        self.assertEqual(lj[5], local)
        self.assertEqual(lj[6], "local")
        self.assertEqual(orders[5], os.path.join(self.root, "repos", "orders"))
        self.assertEqual(orders[6], "clone")


class BareRepoPaths(Sandbox):
    def test_path_to_a_bare_repository_is_cloned_not_used_in_place(self):
        url, _ = self.make_remote("orders")        # url is a plain path to a bare repo
        self.manifest("orders  %s" % url)
        row = self.script("repos.py", "list", check=True).stdout.split("\t")
        self.assertEqual(row[6].strip(), "clone")
        self.assertIn("cloned", self.script("repos.py", "clone", check=True).stdout)


class ManifestAndAdd(Sandbox):
    def test_add_local_folder_stores_home_relative_path(self):
        url, _ = self.make_remote("svc")
        self.git(self.tmp, "clone", "-q", url, os.path.join(self.home, "code", "svc"))
        self.manifest()
        self.script("repos.py", "add", os.path.join(self.home, "code", "svc"), "path=api", check=True)
        self.assertIn("svc  ~/code/svc  path=api", self.read("repos/repos.txt"))

    def test_add_url_derives_name(self):
        self.manifest()
        self.script("repos.py", "add", "git@github.com:acme/orders-service.git", check=True)
        self.assertIn("orders-service  git@github.com:acme/orders-service.git", self.read("repos/repos.txt"))

    def test_add_rejects_reserved_and_invalid_names_and_duplicates(self):
        self.manifest("orders  https://example.com/orders.git")
        for args in (["https://x/README.md.git"], ["https://x/a.git", "bad name"],
                     ["https://example.com/orders.git"], ["https://x/a.git", "a", "colour=blue"]):
            proc = self.script("repos.py", "add", *args)
            self.assertNotEqual(proc.returncode, 0, "should reject: %s" % args)

    def test_add_local_folder_that_is_not_a_git_repo_fails(self):
        os.makedirs(os.path.join(self.home, "plain"))
        self.manifest()
        self.assertNotEqual(self.script("repos.py", "add", os.path.join(self.home, "plain")).returncode, 0)

    def test_unknown_option_in_manifest_is_an_error(self):
        self.manifest("orders  https://example.com/orders.git  colour=blue")
        proc = self.script("repos.py", "list")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("unknown option", proc.stdout)

    def test_alternative_manifest(self):
        self.manifest("a  https://example.com/a.git", "b  https://example.com/b.git")
        alt = self.write("workflows/wf-001-x/repos.txt", "b  https://example.com/b.git\n")
        names = self.script("repos.py", "list", "--manifest", alt, check=True).stdout.split()
        self.assertEqual(names[0], "b")
        self.assertNotIn("a", [l.split("\t")[0] for l in self.script("repos.py", "--manifest", alt, "list").stdout.splitlines()])


class Ensure(Sandbox):
    """repos.py ensure: what /dep-run uses to turn "a repo name, folder or URL" into a list entry."""

    def test_existing_entry_is_found_by_name_folder_or_any_url_form(self):
        url, _ = self.make_remote("svc")
        local = os.path.join(self.home, "repos", "svc")
        self.git(self.tmp, "clone", "-q", url, local)
        self.manifest("svc  ~/repos/svc", "orders  https://github.com/acme/orders-service.git")
        before = self.read("repos/repos.txt")
        for ref in ("svc", local, "~/repos/svc", "orders", "git@github.com:acme/orders-service.git",
                    "https://github.com/acme/orders-service", "https://github.com/ACME/orders-service.git/"):
            expected = "svc" if "svc" in ref and "orders" not in ref else "orders"
            out = self.script("repos.py", "ensure", ref, check=True).stdout.strip().splitlines()[-1]
            self.assertEqual(out, expected, ref)
        self.assertEqual(self.read("repos/repos.txt"), before, "finding must not change the list")

    def test_new_folder_or_url_is_added_once(self):
        url, _ = self.make_remote("svc")
        self.git(self.tmp, "clone", "-q", url, os.path.join(self.home, "code", "svc"))
        self.manifest()
        first = self.script("repos.py", "ensure", os.path.join(self.home, "code", "svc"), "path=api", check=True)
        self.assertEqual(first.stdout.strip().splitlines()[-1], "svc")
        self.script("repos.py", "ensure", "~/code/svc", check=True)
        self.script("repos.py", "ensure", "https://github.com/acme/new-thing.git", check=True)
        lines = [l for l in self.read("repos/repos.txt").splitlines() if l and not l.startswith("#")]
        self.assertEqual(lines, ["svc  ~/code/svc  path=api", "new-thing  https://github.com/acme/new-thing.git"])

    def test_unknown_bare_name_is_an_error_not_a_guess(self):
        self.manifest("svc  https://example.com/svc.git")
        proc = self.script("repos.py", "ensure", "billing")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("known: svc", proc.stdout)
