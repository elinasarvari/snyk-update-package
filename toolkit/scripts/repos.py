#!/usr/bin/env python3
"""Manage the repos to fix: the list (repos/repos.txt), their clones, and each workflow's branch.

Every repo is cloned into  <project>/repos/<name>/  (git-ignored) - the code changes happen there.
Your own checkouts elsewhere (e.g. ~/repos/inventory-service) are never touched: a local folder you
pass to `add`/`ensure` is only used to find its git URL, which is what goes in the list.

Each workflow works on its own branch in the clone:  deps/wf-NNN,  created from the latest main
(origin/main; a `branch=` option replaces main). The tracking (STATUS, docs, history) lives in
workflows/wf-NNN-<slug>/ in this project, never in the repo.

repos/repos.txt - one repo per line, '#' starts a comment:
    <name>  <git-url>  [branch=<b>] [path=<subdir>] [smoke=true] [build="<cmd>"]
      branch  the repo's main branch, if it isn't called `main`
      path    sub-folder that holds pom.xml / build.gradle (default: repo root)
      smoke   also boot the packaged app during verification
      build   override the auto-detected build command

Usage (from the project root):
    repos.py add    <git-url | local-folder> [name] [key=value ...]   # local folder -> its origin URL
    repos.py ensure <name | git-url | local-folder> [name] [key=value ...] -> prints the list name (adds if new)
    repos.py clone  [name ...]          # clone missing; fast-forward clean clones that are on main
    repos.py list   [name ...] [--json]
    repos.py status [name ...]
  In a workflow (--workflow 1 | wf-001 | folder; uses the workflow's own repos.txt if it has one):
    repos.py --workflow <id> clone [name ...]     # clone if needed, then put each clone on deps/<id>
    repos.py --workflow <id> status [name ...]    # ... and show whether each clone is on it
    repos.py --workflow <id> release [name ...]   # when the workflow is finished: back to main (branch kept)
  Run as: python3 -I toolkit/scripts/repos.py ...      Options: --manifest <file> uses another list.

`list` prints TSV: name, build_dir, verify_args, url, base_branch, repo_dir.
Written for Python 3.9 - stdlib only.
"""
import argparse
import json
import os
import re
import shlex
import subprocess
import sys

for _stream in (sys.stdout, sys.stderr):        # Windows consoles default to a legacy code page
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REPOS_DIR = os.path.join(ROOT, "repos")                # clones: repos/<name>/
DEFAULT_MANIFEST = os.path.join(REPOS_DIR, "repos.txt")
DEFAULT_BASE = "main"
RESERVED_NAMES = ("repos.txt", "README.md")            # files kept next to the clones
KNOWN_KEYS = ("branch", "path", "smoke", "build")
NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")
# Folders never searched, scanned or counted as changes (build output, dependencies, IDE files).
with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ignore-dirs.txt"),
          encoding="utf-8") as _fh:
    IGNORE_DIRS = [l.strip() for l in _fh if l.strip() and not l.lstrip().startswith("#")]
IGNORED_PATH = re.compile(r"(^|/)(%s)(/|$)" % "|".join(re.escape(d) for d in IGNORE_DIRS))


def git(args, cwd=None):
    proc = subprocess.run(["git"] + args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          universal_newlines=True)
    return proc.returncode, proc.stdout.strip()


# --- the list ---------------------------------------------------------------------------------
def resolve_path(source):
    return os.path.normpath(os.path.join(ROOT, os.path.expanduser(source)))


def looks_like_path(source):
    """/x, ~/x, ./x, ../x - and on Windows C:\\x, .\\x, ..\\x, \\\\server\\share. URLs never match."""
    if "://" in source:
        return False
    return (source.startswith(("/", "~", "./", "../", ".\\", "..\\", "\\\\"))
            or bool(re.match(r"^[A-Za-z]:[\\/]", source)))


def rel(path):
    """A path relative to the project, with / on every OS (for messages and docs)."""
    return os.path.relpath(path, ROOT).replace(os.sep, "/")


def is_working_copy(source):
    """A path to a normal checkout. Bare repos and file:// are clone sources (URLs)."""
    if not looks_like_path(source):
        return False
    return os.path.exists(os.path.join(resolve_path(source), ".git"))


def origin_url(folder):
    code, url = git(["remote", "get-url", "origin"], folder)
    return url if code == 0 and url else None


def parse_manifest(path):
    repos = []
    with open(path, encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, 1):
            line = "" if raw.lstrip().startswith("#") else raw.split(" #", 1)[0].strip()
            if not line:
                continue
            # No backslash escapes: Windows paths (C:\\repos\\x) must survive; quotes still group words.
            lexer = shlex.shlex(line, posix=True)
            lexer.whitespace_split, lexer.escape = True, ""
            parts = list(lexer)
            if len(parts) < 2:
                sys.exit("%s:%d: need '<name> <git-url>'" % (path, lineno))
            repo = {"name": parts[0], "url": parts[1], "branch": "", "path": "", "smoke": False, "build": ""}
            for opt in parts[2:]:
                key, sep, value = opt.partition("=")
                if not sep or key not in KNOWN_KEYS:
                    sys.exit("%s:%d: unknown option %r (use %s)" % (path, lineno, opt, ", ".join(KNOWN_KEYS)))
                repo[key] = value.lower() in ("1", "true", "yes") if key == "smoke" else value
            if repo["name"] in RESERVED_NAMES or not NAME_RE.match(repo["name"]):
                sys.exit("%s:%d: invalid repo name %r (letters, digits, . _ - only; not %s)"
                         % (path, lineno, repo["name"], " or ".join(RESERVED_NAMES)))
            if is_working_copy(repo["url"]):
                url = origin_url(resolve_path(repo["url"]))
                sys.exit("%s:%d: %s is a local checkout - list its git URL instead%s (the workflow works in a "
                         "clone under repos/, never in your own folder)"
                         % (path, lineno, repo["url"], ": %s" % url if url else ""))
            repo["base"] = repo["branch"] or DEFAULT_BASE
            repo["repo_dir"] = os.path.join(REPOS_DIR, repo["name"])
            repo["build_dir"] = os.path.normpath(os.path.join(repo["repo_dir"], repo["path"]))
            args = (["--smoke"] if repo["smoke"] else []) + (["--build-cmd", repo["build"]] if repo["build"] else [])
            repo["verify_args"] = " ".join(shlex.quote(a) for a in args)
            repos.append(repo)
    return repos


def select(repos, names):
    if not names:
        return repos
    unknown = set(names) - {r["name"] for r in repos}
    if unknown:
        sys.exit("not in the list: %s" % ", ".join(sorted(unknown)))
    return [r for r in repos if r["name"] in names]


def normalise_url(url):
    """https://github.com/a/b(.git) and git@github.com:a/b(.git) compare equal."""
    u = re.sub(r"\.git$", "", url.strip().rstrip("/").lower())
    u = re.sub(r"^(https?|ssh|git)://([^@/]+@)?", "", u)
    u = re.sub(r"^[^@/]+@([^:/]+):", r"\1/", u)
    return u


def is_bare_repo(path):
    return os.path.isfile(os.path.join(path, "HEAD")) and os.path.isdir(os.path.join(path, "objects"))


def to_url(ref):
    """A local checkout -> its origin URL (so it can be cloned); a URL or bare-repo path unchanged."""
    if looks_like_path(ref) and not is_working_copy(ref):
        path = resolve_path(ref)
        if not os.path.exists(path):
            sys.exit("%s does not exist" % path)
        if not is_bare_repo(path):
            sys.exit("%s is not a git repository" % path)
        return ref
    if is_working_copy(ref):
        folder = resolve_path(ref)
        url = origin_url(folder)
        if not url:
            sys.exit("%s has no 'origin' remote - push it somewhere first, or give the git URL" % folder)
        return url
    return ref


def find_repo(repos, ref):
    for r in repos:
        if r["name"] == ref:
            return r
    key = normalise_url(to_url(ref)) if (is_working_copy(ref) or not NAME_RE.match(ref)) else None
    return next((r for r in repos if key and normalise_url(r["url"]) == key), None)


def cmd_add(args):
    url = to_url(args.url)
    name = args.name or re.sub(r"\.git$", "", url.rstrip("/").split("/")[-1].split(":")[-1])
    if name in RESERVED_NAMES or not NAME_RE.match(name):
        sys.exit("invalid repo name %r - pass a name: repos.py add <url> <name>" % name)
    repos = parse_manifest(args.manifest)
    if any(r["name"] == name for r in repos):
        sys.exit("%s is already in %s" % (name, rel(args.manifest)))
    if any(normalise_url(r["url"]) == normalise_url(url) for r in repos):
        sys.exit("%s is already in the list" % url)
    for opt in args.options:
        if opt.partition("=")[0] not in KNOWN_KEYS:
            sys.exit("unknown option %r (use %s)" % (opt, ", ".join(KNOWN_KEYS)))
    with open(args.manifest, "a", encoding="utf-8") as fh:
        fh.write("%s  %s%s\n" % (name, url, "".join("  " + (shlex.quote(o) if " " in o else o) for o in args.options)))
    print("added %s -> %s (%s)" % (name, rel(args.manifest), url), file=sys.stderr)


def cmd_ensure(args):
    found = find_repo(parse_manifest(args.manifest), args.ref)
    if found:
        print(found["name"])
        return
    looks_like_source = is_working_copy(args.ref) or not NAME_RE.match(args.ref) or args.ref.endswith(".git")
    if not looks_like_source:
        known = ", ".join(r["name"] for r in parse_manifest(args.manifest)) or "none"
        sys.exit("%r is not in %s (known: %s). Pass its git URL or a local checkout of it to add it."
                 % (args.ref, rel(args.manifest), known))
    args.url = args.ref
    cmd_add(args)
    print(find_repo(parse_manifest(args.manifest), args.ref)["name"])


# --- clones -----------------------------------------------------------------------------------
def repo_state(repo):
    d = repo["repo_dir"]
    if not os.path.exists(os.path.join(d, ".git")):
        return {"cloned": False}
    _, branch = git(["rev-parse", "--abbrev-ref", "HEAD"], d)
    _, commit = git(["rev-parse", "--short", "HEAD"], d)
    _, dirty = git(["status", "--porcelain", "--untracked-files=normal"], d)
    dirty_files = [l for l in dirty.splitlines() if l and not IGNORED_PATH.search(l[3:].strip('"'))]
    code, counts = git(["rev-list", "--left-right", "--count", "@{upstream}...HEAD"], d)
    behind, ahead = counts.split() if code == 0 else ("-", "-")
    return {"cloned": True, "branch": branch, "commit": commit, "dirty": len(dirty_files),
            "ahead": ahead, "behind": behind}


def clone_or_refresh(repo):
    """-> (ok, message). Clones a missing repo; fast-forwards a clean clone that is on its base branch."""
    d, state = repo["repo_dir"], repo_state(repo)
    if not state["cloned"]:
        code, out = git(["clone", "--quiet"] + (["--branch", repo["branch"]] if repo["branch"] else [])
                        + [repo["url"], d])
        if code != 0:
            return False, "CLONE FAILED: " + (out.splitlines()[-1] if out else "")
        return True, "cloned into %s" % rel(d)
    git(["fetch", "--quiet", "--prune"], d)
    if state["dirty"]:
        return True, "kept as is - %d uncommitted file(s) on %s" % (state["dirty"], state["branch"])
    if state["branch"] != repo["base"]:
        return True, "kept as is - on %s (a workflow branch); fetched latest" % state["branch"]
    code, out = git(["merge", "--ff-only", "--quiet", "@{upstream}"], d)
    return (True, "up to date") if code == 0 else (False, "REFRESH FAILED: " + out)


def base_ref(d, base):
    """origin/<base> if it exists (the latest main), else local <base>; None if neither."""
    for ref in ("origin/" + base, base):
        if git(["rev-parse", "--verify", "--quiet", ref + "^{commit}"], d)[0] == 0:
            return ref
    return None


# --- workflow branches ------------------------------------------------------------------------
def resolve_workflow(ref):
    """(wf_id, folder) via workflows.py, so ids resolve exactly the same way everywhere."""
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "workflows.py")
    proc = subprocess.run([sys.executable, "-I", script, "resolve", ref], stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, universal_newlines=True)
    if proc.returncode != 0:
        sys.exit(proc.stdout.strip())
    folder = os.path.join(ROOT, proc.stdout.strip())
    return re.match(r"^(wf-\d+)-", os.path.basename(folder)).group(1), folder


def branch_for(wf_id):
    return "deps/" + wf_id


def use_workflow_branch(repo, wf_id):
    """Put the clone on deps/<id>: create it from the latest base, or switch back to it. -> (ok, message)"""
    d, branch, state = repo["repo_dir"], branch_for(wf_id), repo_state(repo)
    if state["branch"] == branch:
        extra = " | %d uncommitted file(s) from earlier steps" % state["dirty"] if state["dirty"] else ""
        return True, "on %s @ %s%s" % (branch, state["commit"], extra)
    if state["dirty"]:
        owner = " (unpublished changes of workflow %s)" % state["branch"][5:] if state["branch"].startswith("deps/") else ""
        return False, ("BLOCKED: the clone has %d uncommitted file(s) on %s%s. Finish or publish that first; "
                       "nothing was switched" % (state["dirty"], state["branch"], owner))
    if git(["rev-parse", "--verify", "--quiet", "refs/heads/" + branch], d)[0] == 0:
        code, out = git(["switch", "--quiet", branch], d)
        how = "switched back to existing %s" % branch
    else:
        start = base_ref(d, repo["base"])
        if start is None:
            return False, ("NO '%s' BRANCH - if this repo's main branch has another name, add branch=<name> "
                           "to its line in repos/repos.txt" % repo["base"])
        code, out = git(["switch", "--quiet", "--no-track", "-c", branch, start], d)
        how = "created %s from %s" % (branch, start)
    if code != 0:
        return False, "SWITCH FAILED: " + (out.splitlines()[-1] if out else "")
    return True, "%s @ %s" % (how, git(["rev-parse", "--short", "HEAD"], d)[1])


def cmd_clone(args):
    os.makedirs(REPOS_DIR, exist_ok=True)
    wf_id = resolve_workflow(args.workflow)[0] if args.workflow else None
    failed = 0
    for repo in select(parse_manifest(args.manifest), args.names):
        ok, msg = clone_or_refresh(repo)
        if ok and not os.path.isdir(repo["build_dir"]):
            msg += " | WARNING: path=%s does not exist" % repo["path"]
        if ok and wf_id:
            ok, branch_msg = use_workflow_branch(repo, wf_id)
            msg += "\n%-24s %s" % ("", branch_msg)
        failed += not ok
        print("%-24s %s" % (repo["name"], msg))
    sys.exit(1 if failed else 0)


def cmd_release(args):
    """Workflow finished (published or abandoned): put clean clones back on their base branch."""
    if not args.workflow:
        sys.exit("release needs --workflow <id>")
    wf_id = resolve_workflow(args.workflow)[0]
    failed = 0
    for repo in select(parse_manifest(args.manifest), args.names):
        state = repo_state(repo)
        if not state["cloned"] or state["branch"] != branch_for(wf_id):
            print("%-24s not on %s - nothing to do" % (repo["name"], branch_for(wf_id)))
            continue
        if state["dirty"]:
            failed += 1
            print("%-24s KEPT on %s - %d uncommitted file(s)" % (repo["name"], branch_for(wf_id), state["dirty"]))
            continue
        code, out = git(["switch", "--quiet", repo["base"]], repo["repo_dir"])
        failed += code != 0
        print("%-24s %s" % (repo["name"], "back on %s (branch %s kept)" % (repo["base"], branch_for(wf_id))
                            if code == 0 else "SWITCH FAILED: " + out))
    sys.exit(1 if failed else 0)


def cmd_list(args):
    repos = select(parse_manifest(args.manifest), args.names)
    if args.json:
        json.dump(repos, sys.stdout, indent=2)
        print()
        return
    for r in repos:
        print("\t".join([r["name"], r["build_dir"], r["verify_args"], r["url"], r["base"], r["repo_dir"]]))


def cmd_status(args):
    wf_id = resolve_workflow(args.workflow)[0] if args.workflow else None
    row = "%-20s %-8s %-24s %-6s %-6s %-7s %s"
    print(row % ("REPO", "COMMIT", "BRANCH", "DIRTY", "AHEAD", "BEHIND", "CLONE")
          + ("   ON %s?" % branch_for(wf_id) if wf_id else ""))
    for repo in select(parse_manifest(args.manifest), args.names):
        s = repo_state(repo)
        where = rel(repo["repo_dir"])
        if not s["cloned"]:
            print("%-20s not cloned - run: repos.py%s clone %s  (%s)"
                  % (repo["name"], " --workflow " + args.workflow if wf_id else "", repo["name"], where))
            continue
        print(row % (repo["name"], s["commit"], s["branch"], s["dirty"], s["ahead"], s["behind"], where)
              + ("   %s" % ("yes" if s["branch"] == branch_for(wf_id) else "NO") if wf_id else ""))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manifest", default=None)
    parser.add_argument("--workflow", default=None)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("add"); p.add_argument("url"); p.add_argument("name", nargs="?")
    p.add_argument("options", nargs="*"); p.set_defaults(func=cmd_add)
    p = sub.add_parser("ensure"); p.add_argument("ref"); p.add_argument("name", nargs="?")
    p.add_argument("options", nargs="*"); p.set_defaults(func=cmd_ensure)
    p = sub.add_parser("clone"); p.add_argument("names", nargs="*"); p.set_defaults(func=cmd_clone)
    p = sub.add_parser("list"); p.add_argument("names", nargs="*"); p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_list)
    p = sub.add_parser("status"); p.add_argument("names", nargs="*"); p.set_defaults(func=cmd_status)
    p = sub.add_parser("release"); p.add_argument("names", nargs="*"); p.set_defaults(func=cmd_release)
    # Accept --manifest / --workflow anywhere on the line, not only before the subcommand.
    argv = sys.argv[1:]
    for flag in ("--manifest", "--workflow"):
        if flag in argv[1:]:
            i = argv.index(flag)
            argv = argv[i:i + 2] + argv[:i] + argv[i + 2:]
    args = parser.parse_args(argv)
    if args.command in ("add", "ensure") and args.name and "=" in args.name:
        args.options.insert(0, args.name)          # `add <url> key=value` without a name
        args.name = None
    if args.manifest is None:
        own = os.path.join(resolve_workflow(args.workflow)[1], "repos.txt") if args.workflow else ""
        args.manifest = own if own and os.path.isfile(own) else DEFAULT_MANIFEST
    if not os.path.isfile(args.manifest):
        sys.exit("list not found: %s" % args.manifest)
    args.func(args)


if __name__ == "__main__":
    main()
