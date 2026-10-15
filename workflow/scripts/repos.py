#!/usr/bin/env python3
"""Manage the target repositories listed in repos/repos.txt: add, clone/refresh, list, status.

Each line points at a repo in one of two ways:
  - a LOCAL FOLDER you already have (e.g. ~/repos/learning-java): used in place - never cloned,
    never pulled; upgrade changes land on a deps/<upgrade-id> branch in that folder.
  - a GIT URL: cloned into <project>/repos/<name>/ (git-ignored) and fast-forwarded when clean.
Either way, snyk-update-package never stores the repo's code or changes.

repos/repos.txt - one repo per line, '#' starts a comment:
    <name>  <local-folder | git-url>  [branch=<b>] [path=<subdir>] [smoke=true] [build="<cmd>"]
      local-folder  starts with / ~ ./ or ../ (relative to the project root)
      branch  URL: branch to clone/refresh. Local: the branch you expect it on (only checked)
      path    sub-folder that holds pom.xml / build.gradle (default: repo root)
      smoke   also boot the packaged app during verification
      build   override the auto-detected build command

Usage (from the project root):
    python3 -I workflow/scripts/repos.py add <local-folder | git-url> [name] [key=value ...]
    python3 -I workflow/scripts/repos.py clone  [name ...]     # URLs: clone/fast-forward. Local: check only
    python3 -I workflow/scripts/repos.py list   [name ...] [--json]
    python3 -I workflow/scripts/repos.py status [name ...]
    Options: --manifest <file>  use another list, e.g. upgrades/<id>/repos.txt (same format)

`list` prints TSV: name, build_dir, verify_args, url, branch, repo_dir, kind (local|clone) - for scripts.
Written for Python 3.9 - stdlib only.
"""
import argparse
import json
import os
import re
import shlex
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REPOS_DIR = os.path.join(ROOT, "repos")          # clones go to repos/<name>/
DEFAULT_MANIFEST = os.path.join(REPOS_DIR, "repos.txt")
# Files kept in repos/ next to the clones - a repo may not use these names.
RESERVED_NAMES = ("repos.txt", "README.md")
KNOWN_KEYS = ("branch", "path", "smoke", "build")


def git(args, cwd=None):
    proc = subprocess.run(["git"] + args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          universal_newlines=True)
    return proc.returncode, proc.stdout.strip()


def is_local(source):
    """A local folder starts with / ~ ./ ../ - anything else (https://, git@host:, ssh://) is a URL."""
    return source.startswith(("/", "~", "./", "../"))


def resolve_local(source):
    return os.path.normpath(os.path.join(ROOT, os.path.expanduser(source)))


def parse_manifest(path):
    repos = []
    with open(path, encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.split("#", 1)[0].strip() if not raw.lstrip().startswith("#") else ""
            if not line:
                continue
            parts = shlex.split(line)
            if len(parts) < 2:
                sys.exit("%s:%d: need '<name> <local-folder | git-url>'" % (path, lineno))
            repo = {"name": parts[0], "source": parts[1], "url": "", "branch": "", "path": "", "smoke": False,
                    "build": "", "kind": "local" if is_local(parts[1]) else "clone"}
            for opt in parts[2:]:
                key, sep, value = opt.partition("=")
                if not sep or key not in KNOWN_KEYS:
                    sys.exit("%s:%d: unknown option %r (use %s)" % (path, lineno, opt, ", ".join(KNOWN_KEYS)))
                repo[key] = value.lower() in ("1", "true", "yes") if key == "smoke" else value
            if repo["name"] in RESERVED_NAMES or not re.match(r"^[A-Za-z0-9._-]+$", repo["name"]):
                sys.exit("%s:%d: invalid repo name %r (letters, digits, . _ - only; not %s)"
                         % (path, lineno, repo["name"], " or ".join(RESERVED_NAMES)))
            if repo["kind"] == "local":
                repo["clone_dir"] = resolve_local(repo["source"])
                if repo["clone_dir"] == REPOS_DIR or repo["clone_dir"] == ROOT:
                    sys.exit("%s:%d: %s is this project itself, not a target repo" % (path, lineno, parts[1]))
                _, origin = git(["remote", "get-url", "origin"], repo["clone_dir"]) if os.path.isdir(
                    repo["clone_dir"]) else (1, "")
                repo["url"] = origin if origin and "fatal" not in origin else ""
            else:
                repo["url"] = repo["source"]
                repo["clone_dir"] = os.path.join(REPOS_DIR, repo["name"])
            repo["build_dir"] = os.path.normpath(os.path.join(repo["clone_dir"], repo["path"]))
            args = (["--smoke"] if repo["smoke"] else []) + (["--build-cmd", repo["build"]] if repo["build"] else [])
            repo["verify_args"] = " ".join(shlex.quote(a) for a in args)
            repos.append(repo)
    return repos


def select(repos, names):
    if not names:
        return repos
    unknown = set(names) - {r["name"] for r in repos}
    if unknown:
        sys.exit("not in manifest: %s" % ", ".join(sorted(unknown)))
    return [r for r in repos if r["name"] in names]


def repo_state(repo):
    d = repo["clone_dir"]
    if not os.path.isdir(os.path.join(d, ".git")):
        return {"cloned": False}
    _, branch = git(["rev-parse", "--abbrev-ref", "HEAD"], d)
    _, commit = git(["rev-parse", "--short", "HEAD"], d)
    _, dirty = git(["status", "--porcelain", "--untracked-files=normal"], d)
    dirty_files = [l for l in dirty.splitlines() if l and not re.search(r"(^|/)(target|build)/", l)]
    code, counts = git(["rev-list", "--left-right", "--count", "@{upstream}...HEAD"], d)
    behind, ahead = counts.split() if code == 0 else ("?", "?")
    return {"cloned": True, "branch": branch, "commit": commit, "dirty": len(dirty_files),
            "ahead": ahead, "behind": behind}


def cmd_add(args):
    url = args.url
    if is_local(url):
        folder = resolve_local(url)
        if not os.path.isdir(os.path.join(folder, ".git")):
            sys.exit("%s is not a git repository (no .git folder)" % folder)
        # Store ~/... for paths under the home folder so the line reads naturally.
        home = os.path.expanduser("~")
        url = "~" + folder[len(home):] if folder.startswith(home + os.sep) else folder
    name = args.name or re.sub(r"\.git$", "", url.rstrip("/").split("/")[-1].split(":")[-1])
    if name in RESERVED_NAMES or not re.match(r"^[A-Za-z0-9._-]+$", name):
        sys.exit("invalid repo name %r - pass a name: repos.py add <folder-or-url> <name>" % name)
    if any(r["name"] == name for r in parse_manifest(args.manifest)):
        sys.exit("%s is already in %s" % (name, args.manifest))
    for opt in args.options:
        if opt.partition("=")[0] not in KNOWN_KEYS:
            sys.exit("unknown option %r (use %s)" % (opt, ", ".join(KNOWN_KEYS)))
    with open(args.manifest, "a", encoding="utf-8") as fh:
        fh.write("%s  %s%s\n" % (name, url, "".join("  " + shlex.quote(o) if " " in o else "  " + o
                                                       for o in args.options)))
    print("added %s -> %s" % (name, args.manifest))


def cmd_clone(args):
    os.makedirs(REPOS_DIR, exist_ok=True)
    failed = 0
    for repo in select(parse_manifest(args.manifest), args.names):
        d, state = repo["clone_dir"], repo_state(repo)
        if repo["kind"] == "local":
            code, msg = check_local(repo, state)
        elif not state["cloned"]:
            cmd = ["clone", "--quiet"] + (["--branch", repo["branch"]] if repo["branch"] else []) + [repo["url"], d]
            code, out = git(cmd)
            msg = "cloned" if code == 0 else "CLONE FAILED: " + out.splitlines()[-1] if out else "CLONE FAILED"
        elif state["dirty"]:
            code, msg = 0, "kept as is - %d uncommitted file(s) on %s" % (state["dirty"], state["branch"])
        elif repo["branch"] and state["branch"] != repo["branch"] or state["branch"].startswith("deps/"):
            code, msg = 0, "kept as is - on branch %s (upgrade in progress?)" % state["branch"]
        else:
            git(["fetch", "--quiet", "--prune"], d)
            code, out = git(["merge", "--ff-only", "--quiet", "@{upstream}"], d)
            msg = "up to date" if code == 0 else "REFRESH FAILED: " + out
        if not os.path.isdir(repo["build_dir"]) and os.path.isdir(d):
            msg += " | WARNING: path=%s does not exist" % repo["path"]
        failed += code != 0
        print("%-24s %s" % (repo["name"], msg))
    sys.exit(1 if failed else 0)


def check_local(repo, state):
    """Local folders are the user's own checkout: look, fetch remote refs, but never change the work tree."""
    if not state["cloned"]:
        return 1, "LOCAL FOLDER NOT FOUND or not a git repo: %s" % repo["clone_dir"]
    if repo["url"]:
        git(["fetch", "--quiet"], repo["clone_dir"])     # updates origin/* only; files are untouched
        state.update(repo_state(repo))
    notes = []
    if repo["branch"] and state["branch"] != repo["branch"]:
        notes.append("on %s, expected %s - switch it yourself if needed" % (state["branch"], repo["branch"]))
    if state["dirty"]:
        notes.append("%d uncommitted file(s) - /dep-apply will wait until you commit them" % state["dirty"])
    if state["behind"] not in ("0", "?"):
        notes.append("%s commit(s) behind origin - run git pull there if you want the latest" % state["behind"])
    return 0, "local, used in place (%s @ %s)%s" % (state["branch"], state["commit"],
                                                    "".join(" | " + n for n in notes))


def cmd_list(args):
    repos = select(parse_manifest(args.manifest), args.names)
    if args.json:
        json.dump(repos, sys.stdout, indent=2)
        print()
        return
    for r in repos:
        print("\t".join([r["name"], r["build_dir"], r["verify_args"], r["url"], r["branch"], r["clone_dir"],
                         r["kind"]]))


def cmd_status(args):
    row = "%-20s %-6s %-8s %-28s %-6s %-6s %-7s %s"
    print(row % ("REPO", "TYPE", "COMMIT", "BRANCH", "DIRTY", "AHEAD", "BEHIND", "FOLDER"))
    home = os.path.expanduser("~")
    for repo in select(parse_manifest(args.manifest), args.names):
        s = repo_state(repo)
        folder = repo["clone_dir"].replace(home, "~", 1)
        if not s["cloned"]:
            hint = "folder not found" if repo["kind"] == "local" else "not cloned - run: repos.py clone %s" % repo["name"]
            print("%-20s %-6s %s  (%s)" % (repo["name"], repo["kind"], hint, folder))
            continue
        print(row % (repo["name"], repo["kind"], s["commit"], s["branch"], s["dirty"], s["ahead"], s["behind"], folder))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("add"); p.add_argument("url"); p.add_argument("name", nargs="?")
    p.add_argument("options", nargs="*"); p.set_defaults(func=cmd_add)
    p = sub.add_parser("clone"); p.add_argument("names", nargs="*"); p.set_defaults(func=cmd_clone)
    p = sub.add_parser("list"); p.add_argument("names", nargs="*"); p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_list)
    p = sub.add_parser("status"); p.add_argument("names", nargs="*"); p.set_defaults(func=cmd_status)
    # Accept --manifest anywhere on the line, not only before the subcommand.
    argv = sys.argv[1:]
    if "--manifest" in argv[1:]:
        i = argv.index("--manifest")
        argv = argv[i:i + 2] + argv[:i] + argv[i + 2:]
    args = parser.parse_args(argv)
    # `add <url> key=value` without a name: treat the first key=value as an option.
    if args.command == "add" and args.name and "=" in args.name:
        args.options.insert(0, args.name)
        args.name = None
    if not os.path.isfile(args.manifest):
        sys.exit("manifest not found: %s" % args.manifest)
    args.func(args)


if __name__ == "__main__":
    main()
