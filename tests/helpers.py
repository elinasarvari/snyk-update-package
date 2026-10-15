"""Shared test helpers: an isolated sandbox copy of the project, fake git remotes, fake tools, and runners.

Nothing here touches the real repos, the user's ~/.gitconfig or the network: every test gets a
temporary project root (toolkit/ copied in), a temporary HOME, and local bare git remotes.

The shell scripts exist twice - bash (*.sh) and PowerShell (*.ps1). Test classes that exercise them
mix in `BashScripts` or `PowerShellScripts`, so every such test runs against both versions.
"""
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(PROJECT, "toolkit", "scripts")
ON_WINDOWS = os.name == "nt"
PYTHON = sys.executable


def find_powershell():
    """$SUP_PS (e.g. 'powershell' for Windows PowerShell 5.1), else pwsh, else powershell (Windows)."""
    wanted = os.environ.get("SUP_PS")
    for name in ([wanted] if wanted else ["pwsh", "powershell"]):
        path = shutil.which(name)
        if path:
            return path
    return None


POWERSHELL = find_powershell()
BASH = None if ON_WINDOWS else shutil.which("bash")


class Sandbox(unittest.TestCase):
    """Base class: self.root is a throwaway project root; self.home a throwaway HOME."""
    shell = "bash"          # which twin runs for *.sh names: "bash" or "powershell"

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
        self.env = dict(os.environ, HOME=self.home, USERPROFILE=self.home, GIT_CONFIG_NOSYSTEM="1",
                        GIT_TERMINAL_PROMPT="0", PYTHONUTF8="1", PYTHONIOENCODING="utf-8",
                        GIT_AUTHOR_NAME="Test", GIT_AUTHOR_EMAIL="test@example.com",
                        GIT_COMMITTER_NAME="Test", GIT_COMMITTER_EMAIL="test@example.com")
        if ON_WINDOWS:   # the Snyk VS Code extension's folders on Windows hang off these
            self.env["LOCALAPPDATA"] = os.path.join(self.home, "AppData", "Local")
            self.env["APPDATA"] = os.path.join(self.home, "AppData", "Roaming")
        self.env.pop("SNYK_TOKEN", None)
        self.env.pop("SNYK_CLI", None)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # --- running things -------------------------------------------------------------------------
    def run_cmd(self, args, cwd=None, env=None, check=False):
        proc = subprocess.run(args, cwd=cwd or self.root, env=env or self.env, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, universal_newlines=True, encoding="utf-8", errors="replace")
        if check and proc.returncode != 0:
            self.fail("command failed (%d): %s\n%s" % (proc.returncode, " ".join(args), proc.stdout))
        return proc

    def script(self, name, *args, **kw):
        """Run toolkit/scripts/<name>: *.py with Python; *.sh with bash or its *.ps1 twin (see `shell`)."""
        path = os.path.join(self.root, "toolkit", "scripts", name)
        if name.endswith(".py"):
            cmd = [PYTHON, "-I", path]
        elif self.shell == "powershell":
            cmd = [POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
                   path[:-3] + ".ps1"]
        else:
            cmd = [BASH, path]
        return self.run_cmd(cmd + list(args), **kw)

    def git(self, cwd, *args):
        return self.run_cmd(["git"] + list(args), cwd=cwd, check=True).stdout.strip()

    # --- fixtures -------------------------------------------------------------------------------
    def write(self, rel_or_abs, text):
        path = rel_or_abs if os.path.isabs(rel_or_abs) else os.path.join(self.root, rel_or_abs)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        return path

    def read(self, rel_or_abs):
        path = rel_or_abs if os.path.isabs(rel_or_abs) else os.path.join(self.root, rel_or_abs)
        with open(path, encoding="utf-8") as fh:
            return fh.read()

    def make_tool(self, path, python_code):
        """A fake command-line program written in Python. Returns the path to run it by:
        `path` itself (an executable launcher) on macOS/Linux, `path + ".cmd"` on Windows."""
        impl = self.write(path + ".tool.py", python_code)
        if ON_WINDOWS:
            launcher = self.write(path + ".cmd", '@"%s" "%s" %%*\r\n' % (PYTHON, impl))
        else:
            launcher = self.write(path, '#!/bin/sh\nexec "%s" "%s" "$@"\n' % (PYTHON, impl))
            os.chmod(launcher, 0o755)
        return launcher

    def python_command(self, script_path):
        """A command line that runs a Python script - valid in bash and in cmd.exe."""
        return '"%s" "%s"' % (PYTHON, script_path)

    def file_url(self, path):
        return pathlib.Path(path).as_uri()

    def make_remote(self, name, files=None):
        """A bare repo with one commit on 'main'; returns (bare_path, work_dir used to push)."""
        bare = os.path.join(self.tmp, "remotes", name + ".git")
        work = os.path.join(self.tmp, "seed", name)
        os.makedirs(work)
        self.git(self.tmp, "init", "-q", "--bare", "-b", "main", bare)
        self.git(work, "init", "-q", "-b", "main")
        self.git(work, "config", "core.autocrlf", "false")
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


class BashScripts:
    """Mixin: run the *.sh scripts (macOS/Linux)."""
    shell = "bash"

    def setUp(self):
        if not BASH:
            self.skipTest("bash scripts are not run on Windows")
        super().setUp()


class PowerShellScripts:
    """Mixin: run the *.ps1 twins (Windows PowerShell 5.1 or PowerShell 7, any OS)."""
    shell = "powershell"

    def setUp(self):
        if not POWERSHELL:
            self.skipTest("PowerShell not found (set SUP_PS, or install pwsh)")
        super().setUp()
