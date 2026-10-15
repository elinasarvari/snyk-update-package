"""Shared test helpers: an isolated sandbox copy of the project, fake git remotes, and runners.

Nothing here touches the real repos, the user's ~/.gitconfig or the network: every test gets a
temporary project root (toolkit/ copied in), a temporary HOME, and local bare git remotes.
"""
import os
import shutil
import subprocess
import tempfile
import unittest

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(PROJECT, "toolkit", "scripts")


class Sandbox(unittest.TestCase):
    """Base class: self.root is a throwaway project root; self.home a throwaway HOME."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sup-test-")
        self.root = os.path.join(self.tmp, "project")
        self.home = os.path.join(self.tmp, "home")
        os.makedirs(self.home)
        shutil.copytree(os.path.join(PROJECT, "toolkit"), os.path.join(self.root, "toolkit"),
                        ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copy(os.path.join(PROJECT, ".gitignore"), self.root)
        os.makedirs(os.path.join(self.root, "repos"))
        os.makedirs(os.path.join(self.root, "workflows"))
        self.env = dict(os.environ, HOME=self.home, GIT_CONFIG_NOSYSTEM="1", GIT_TERMINAL_PROMPT="0",
                        GIT_AUTHOR_NAME="Test", GIT_AUTHOR_EMAIL="test@example.com",
                        GIT_COMMITTER_NAME="Test", GIT_COMMITTER_EMAIL="test@example.com")
        self.env.pop("SNYK_TOKEN", None)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # --- running things -------------------------------------------------------------------------
    def run_cmd(self, args, cwd=None, env=None, check=False):
        proc = subprocess.run(args, cwd=cwd or self.root, env=env or self.env, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, universal_newlines=True)
        if check and proc.returncode != 0:
            self.fail("command failed (%d): %s\n%s" % (proc.returncode, " ".join(args), proc.stdout))
        return proc

    def script(self, name, *args, **kw):
        path = os.path.join(self.root, "toolkit", "scripts", name)
        cmd = ["python3", "-I", path] if name.endswith(".py") else ["bash", path]
        return self.run_cmd(cmd + list(args), **kw)

    def git(self, cwd, *args):
        return self.run_cmd(["git"] + list(args), cwd=cwd, check=True).stdout.strip()

    # --- fixtures -------------------------------------------------------------------------------
    def write(self, rel_or_abs, text):
        path = rel_or_abs if os.path.isabs(rel_or_abs) else os.path.join(self.root, rel_or_abs)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path

    def read(self, rel_or_abs):
        path = rel_or_abs if os.path.isabs(rel_or_abs) else os.path.join(self.root, rel_or_abs)
        with open(path, encoding="utf-8") as fh:
            return fh.read()

    def make_remote(self, name, files=None):
        """A bare repo with one commit on 'main'; returns (bare_url, work_dir used to push)."""
        bare = os.path.join(self.tmp, "remotes", name + ".git")
        work = os.path.join(self.tmp, "seed", name)
        os.makedirs(work)
        self.git(self.tmp, "init", "-q", "--bare", "-b", "main", bare)
        self.git(work, "init", "-q", "-b", "main")
        for rel, text in (files or {"pom.xml": "<project/>\n", "README.md": "# %s\n" % name}).items():
            self.write(os.path.join(work, rel), text)
        self.git(work, "add", "-A")
        self.git(work, "commit", "-q", "-m", "initial")
        self.git(work, "remote", "add", "origin", bare)
        self.git(work, "push", "-q", "origin", "main")
        return bare, work

    def push_new_commit(self, work, rel="CHANGELOG.md", text="change\n"):
        self.write(os.path.join(work, rel), text)
        self.git(work, "add", "-A")
        self.git(work, "commit", "-q", "-m", "update " + rel)
        self.git(work, "push", "-q", "origin", "main")
        return self.git(work, "rev-parse", "HEAD")

    def manifest(self, *lines):
        return self.write("repos/repos.txt", "# test manifest\n" + "\n".join(lines) + "\n")
