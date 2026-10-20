#!/usr/bin/env python3
"""Workflow runs: unique ids (wf-001, wf-002, ...), folders, step states, history, index.

Every run of the /dep-* workflow gets the next number and its own folder:
    workflows/wf-<NNN>-<slug>/STATUS.md   (+ the numbered docs each step writes)
Numbers are never reused, even if a workflow folder is deleted (workflows/.last-id keeps the
high-water mark). workflows/INDEX.md is regenerated automatically after every change.

Usage (from the project root):
    python3 -I toolkit/scripts/workflows.py new <slug> [--title T] [--source S] [--repo NAME ...]
        -> prints id and folder; --repo limits the run to those repos (writes the run's own repos.txt)
    python3 -I toolkit/scripts/workflows.py resolve <ref>        # 1 | 001 | wf-1 | wf-001 | wf-001-slug -> folder
    python3 -I toolkit/scripts/workflows.py list                 # all workflows: step, state, next step
    python3 -I toolkit/scripts/workflows.py phase <ref> <0-5> <todo|running|done|blocked|waiting|skipped> [--note N]
    python3 -I toolkit/scripts/workflows.py next <ref> "<next step text>"
    python3 -I toolkit/scripts/workflows.py log <ref> "<event>"
    python3 -I toolkit/scripts/workflows.py index                # rebuild workflows/INDEX.md
    python3 -I toolkit/scripts/workflows.py show <ref>           # one run: steps, next step, repos in scope
    python3 -I toolkit/scripts/workflows.py find-open --repo NAME   # unfinished run scoped to exactly that repo
    python3 -I toolkit/scripts/workflows.py save <ref> [--allow-public] [--no-push]
        -> commit that workflow's records (only them) and push to this project's GitHub; refuses while the repo
           is public unless --allow-public. Raw Snyk JSON and logs are never committed (.gitignore).
    python3 -I toolkit/scripts/workflows.py sync                # pull the latest records (before starting a run)
Written for Python 3.9 - stdlib only.
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

for _stream in (sys.stdout, sys.stderr):        # Windows consoles default to a legacy code page
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORKFLOWS_DIR = os.path.join(ROOT, "workflows")
TEMPLATE = os.path.join(ROOT, "toolkit", "templates", "STATUS.md")
COUNTER = os.path.join(WORKFLOWS_DIR, ".last-id")
MANIFEST = os.path.join(ROOT, "repos", "repos.txt")
INDEX = os.path.join(WORKFLOWS_DIR, "INDEX.md")
FOLDER_RE = re.compile(r"^wf-(\d{3,})-([a-z0-9][a-z0-9-]*)$")
STATES = {
    "todo": "⬜ not started", "running": "🟡 in progress", "done": "✅ done",
    "blocked": "⛔ blocked", "waiting": "⏸ awaiting approval", "skipped": "➖ skipped",
}
PHASE_ROW = re.compile(r"^\|\s*(\d)\s*\|")


def rel(path):
    return os.path.relpath(path, ROOT).replace(os.sep, "/")


def now(fmt="%Y-%m-%d %H:%M"):
    return datetime.datetime.now().strftime(fmt)


def workflows():
    """[(number, id, folder_name, abs_path)] sorted by number."""
    found = []
    if os.path.isdir(WORKFLOWS_DIR):
        for name in os.listdir(WORKFLOWS_DIR):
            m = FOLDER_RE.match(name)
            path = os.path.join(WORKFLOWS_DIR, name)
            if m and os.path.isdir(path):
                found.append((int(m.group(1)), "wf-%s" % m.group(1), name, path))
    return sorted(found)


def make_id(number):
    return "wf-%03d" % number


def resolve(ref):
    ref = ref.strip().replace("\\", "/").rstrip("/")
    ref = ref.rsplit("/", 1)[-1]
    m = re.match(r"^(?:wf-?)?0*(\d+)(?:-.*)?$", ref, re.IGNORECASE)
    all_wf = workflows()
    if m:
        number = int(m.group(1))
        hits = [w for w in all_wf if w[0] == number]
    else:
        hits = [w for w in all_wf if w[2] == ref or w[2].split("-", 2)[-1] == ref]
    if not hits:
        known = ", ".join(w[1] for w in all_wf) or "none yet"
        sys.exit("no workflow matches %r (known: %s)" % (ref, known))
    if len(hits) > 1:
        sys.exit("%r is ambiguous: %s" % (ref, ", ".join(w[2] for w in hits)))
    return hits[0]


def status_path(wf):
    path = os.path.join(wf[3], "STATUS.md")
    if not os.path.isfile(path):
        sys.exit("%s has no STATUS.md" % wf[2])
    return path


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def write(path, text):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def slugify(text):
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    if not slug:
        sys.exit("slug must contain letters or digits")
    return slug[:48].rstrip("-")


def last_number():
    highest = max([w[0] for w in workflows()] or [0])
    if os.path.isfile(COUNTER):
        try:
            highest = max(highest, int(read(COUNTER).strip() or 0))
        except ValueError:
            pass
    return highest


def append_history(path, event):
    text = read(path)
    row = "| %s | %s |" % (now(), event.replace("|", "\\|").replace("\n", " "))
    if "## History" not in text:
        text = text.rstrip("\n") + "\n\n## History\n\n| When | Event |\n|------|-------|\n"
    text = text.rstrip("\n") + "\n" + row + "\n"
    write(path, text)


def parse_status(path):
    """Phase rows, the first line of ▶ Next step, and the title."""
    text = read(path)
    title = text.splitlines()[0].lstrip("# ").strip() if text else ""
    phases = []
    for line in text.splitlines():
        if PHASE_ROW.match(line):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) >= 4:
                phases.append({"n": int(cells[0]), "name": cells[1], "state": cells[3]})
    next_step = ""
    m = re.search(r"^## ▶ Next step\s*\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    if m:
        lines = [l.strip() for l in m.group(1).splitlines() if l.strip() and not l.strip().startswith("<!--")]
        next_step = lines[0] if lines else ""
    started = re.search(r"\*\*Started\*\*\s*\|\s*([0-9-]{10})", text)
    return {"title": title, "phases": phases, "next": next_step, "started": started.group(1) if started else ""}


def current_phase(phases):
    for p in phases:
        if not p["state"].startswith(("✅", "➖")):
            return p
    return None


def rebuild_index():
    rows = []
    for number, wf_id, name, path in workflows():
        status = os.path.join(path, "STATUS.md")
        if not os.path.isfile(status):
            rows.append("| %s | `%s` | _no STATUS.md_ | | | |" % (number, wf_id))
            continue
        info = parse_status(status)
        cur = current_phase(info["phases"])
        where = "all steps done ✅" if cur is None else "%d %s: %s" % (cur["n"], cur["name"], cur["state"])
        title = re.sub(r"^(Workflow \d+:|Upgrade:)\s*", "", info["title"])
        nxt = info["next"] if len(info["next"]) <= 110 else info["next"][:107] + "..."
        rows.append("| %d | [`%s`](%s/STATUS.md) | %s | %s | %s | %s |"
                    % (number, wf_id, name, title.replace("|", "\\|"), info["started"], where, nxt.replace("|", "\\|")))
    write(INDEX, "\n".join([
        "# Workflow index",
        "",
        "> Generated by `toolkit/scripts/workflows.py`. Do not edit; it is rebuilt after every step.",
        "",
        "| # | Id | Title | Started | Current step | ▶ Next step |",
        "|---|----|-------|---------|--------------|-------------|",
    ] + (rows or ["| | _no workflows yet: start one with `/dep-run <repo>` or `/dep-scan`_ | | | | |"])) + "\n")


def manifest_lines(path):
    """{name: original line} for the non-comment lines of a repos.txt."""
    lines = {}
    if os.path.isfile(path):
        for raw in read(path).splitlines():
            line = raw.strip()
            if line and not line.startswith("#"):
                lines[line.split()[0]] = line
    return lines


def scoped_repos(path):
    """Repo names a run is limited to (its own repos.txt), or None when it uses the whole list."""
    own = os.path.join(path, "repos.txt")
    return sorted(manifest_lines(own)) if os.path.isfile(own) else None


# --- saving records to git -------------------------------------------------------------------
def git(args):
    proc = subprocess.run(["git"] + args, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          universal_newlines=True, encoding="utf-8", errors="replace")
    return proc.returncode, proc.stdout.strip()


def has_origin():
    return git(["rev-parse", "--is-inside-work-tree"])[0] == 0 and git(["remote", "get-url", "origin"])[0] == 0


def repo_visibility():
    """public | private | unknown - from the GitHub API for origin. SUP_REPO_VISIBILITY overrides (tests, other hosts)."""
    override = os.environ.get("SUP_REPO_VISIBILITY")
    if override:
        return override
    code, url = git(["remote", "get-url", "origin"])
    m = re.match(r"^(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)([^/]+)/([^/]+?)(?:\.git)?/?$", url)
    if code != 0 or not m:
        return "unknown"
    try:
        with urllib.request.urlopen("https://api.github.com/repos/%s/%s" % m.groups(), timeout=10) as resp:
            return "private" if json.load(resp).get("private") else "public"
    except urllib.error.HTTPError as err:
        return "private" if err.code == 404 else "unknown"      # 404: not visible without signing in
    except (urllib.error.URLError, OSError, ValueError):
        return "unknown"


def sync_with_origin():
    """Bring in records pushed from other machines. -> (ok, message). INDEX.md conflicts are rebuilt, others abort."""
    if not has_origin():
        return True, "no git remote - nothing to sync"
    code, out = git(["pull", "--rebase", "--autostash", "--quiet"])
    if code == 0:
        return True, "up to date with origin"
    for _ in range(20):                                   # resolve generated-index conflicts, one commit at a time
        _, conflicted = git(["diff", "--name-only", "--diff-filter=U"])
        files = [f for f in conflicted.splitlines() if f]
        if not files or any(f != "workflows/INDEX.md" for f in files):
            break
        rebuild_index()
        git(["add", "workflows/INDEX.md"])
        code, out = git(["-c", "core.editor=true", "rebase", "--continue"])
        if code == 0:
            return True, "synced (rebuilt workflows/INDEX.md)"
    git(["rebase", "--abort"])
    return False, "could not sync with origin automatically - resolve it with git, then save again:\n" + out


def cmd_sync(_args):
    ok, msg = sync_with_origin()
    print(msg)
    sys.exit(0 if ok else 1)


def cmd_save(args):
    wf = resolve(args.ref)
    if not has_origin() and not args.no_push:
        sys.exit("this project has no git remote 'origin' - nothing to push to (use --no-push to only commit)")
    if not args.no_push and not args.allow_public:
        visibility = repo_visibility()
        if visibility == "public":
            sys.exit("REFUSED: this repository is PUBLIC, and workflow records list your repos and their open\n"
                     "vulnerabilities. Make it private on GitHub (Settings > General > Danger Zone > Change visibility),\n"
                     "then save again - or run with --allow-public if publishing them is really intended.")
        if visibility == "unknown":
            print("Note: couldn't check whether the repository is public (not GitHub, or offline) - saving anyway.")
    rebuild_index()
    paths = [rel(wf[3]), "workflows/INDEX.md"] + (["workflows/_research"] if os.path.isdir(
        os.path.join(WORKFLOWS_DIR, "_research")) else [])
    git(["add", "-A", "--"] + paths)                      # .gitignore keeps raw Snyk JSON and logs out
    code, staged = git(["diff", "--cached", "--name-only", "--"] + paths)
    if staged:
        info = parse_status(status_path(wf))
        cur = current_phase(info["phases"])
        where = "all steps done" if cur is None else "step %d %s" % (cur["n"], cur["name"])
        title = re.sub(r"^(Workflow \d+:|Upgrade:)\s*", "", info["title"])
        code, out = git(["commit", "--quiet", "-m", "workflow %s: %s (%s)" % (wf[1], title, where), "--"] + paths)
        if code != 0:
            sys.exit("commit failed:\n" + out)
        print("committed %d file(s) for %s" % (len(staged.splitlines()), wf[1]))
    else:
        print("%s: nothing new to commit" % wf[1])
    if args.no_push:
        return
    ok, msg = sync_with_origin()
    if not ok:
        sys.exit(msg)
    code, out = git(["push", "--quiet", "origin", "HEAD"])
    if code != 0:
        sys.exit("push failed:\n" + out)
    _, url = git(["remote", "get-url", "origin"])
    print("pushed %s to %s" % (rel(wf[3]), re.sub(r"https://[^@/]+@", "https://", url)))


def cmd_new(args):
    slug = slugify(args.slug)
    if has_origin():                                      # take ids already pushed from other machines into account
        ok, msg = sync_with_origin()
        if not ok:
            print("Note: " + msg.splitlines()[0] + " - the new workflow id may clash with one pushed elsewhere",
                  file=sys.stderr)
    wanted = args.repo or []
    if wanted:
        known = manifest_lines(MANIFEST)
        missing = [r for r in wanted if r not in known]
        if missing:
            sys.exit("not in repos/repos.txt: %s (add them first: repos.py ensure <folder-or-url>)" % ", ".join(missing))
    os.makedirs(WORKFLOWS_DIR, exist_ok=True)
    number = last_number() + 1
    while True:                                   # another run may have taken the number meanwhile
        wf_id, name = make_id(number), "%s-%s" % (make_id(number), slug)
        path = os.path.join(WORKFLOWS_DIR, name)
        try:
            os.makedirs(path)
            break
        except FileExistsError:
            number += 1
    text = read(TEMPLATE)
    for key, value in (("{{WORKFLOW_ID}}", wf_id), ("{{NUMBER}}", str(number)),
                       ("{{TITLE}}", args.title or slug.replace("-", " ")),
                       ("{{DATE}}", now("%Y-%m-%d")), ("{{SOURCE}}", args.source or "not recorded")):
        text = text.replace(key, value)
    status = os.path.join(path, "STATUS.md")
    write(status, text)
    write(COUNTER, "%d\n" % number)
    if wanted:
        write(os.path.join(path, "repos.txt"), "# Repos in scope for %s (lines copied from repos/repos.txt)\n%s\n"
              % (wf_id, "\n".join(known[r] for r in wanted)))
    append_history(status, "Workflow %d created (%s)%s" % (number, wf_id, " for " + ", ".join(wanted) if wanted else ""))
    rebuild_index()
    print("%s\t%s" % (wf_id, rel(path)))


def cmd_resolve(args):
    print(rel(resolve(args.ref)[3]))


def cmd_list(args):
    all_wf = workflows()
    if not all_wf:
        print("no workflows yet")
        return
    print("%-4s %-8s %-40s %-28s %s" % ("#", "ID", "TITLE", "CURRENT STEP", "FOLDER"))
    for number, wf_id, name, path in all_wf:
        info = parse_status(os.path.join(path, "STATUS.md")) if os.path.isfile(os.path.join(path, "STATUS.md")) else None
        cur = current_phase(info["phases"]) if info else None
        where = "done" if info and cur is None else ("%d %s" % (cur["n"], cur["state"]) if cur else "?")
        title = re.sub(r"^(Workflow \d+:|Upgrade:)\s*", "", info["title"]) if info else "?"
        print("%-4d %-8s %-40s %-28s %s" % (number, wf_id, title[:40], where[:28], rel(path)))


def cmd_phase(args):
    wf = resolve(args.ref)
    path = status_path(wf)
    label = STATES[args.state]
    lines, hit = read(path).splitlines(), False
    for i, line in enumerate(lines):
        m = PHASE_ROW.match(line)
        if m and int(m.group(1)) == args.number:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            while len(cells) < 6:
                cells.append("")
            cells[3] = label + (" (%s)" % args.note.replace("|", "/") if args.note else "")
            cells[5] = now("%Y-%m-%d")
            lines[i] = "| " + " | ".join(cells) + " |"
            hit, name = True, cells[1]
    if not hit:
        sys.exit("%s: no row for step %d in the phase tracker" % (wf[1], args.number))
    write(path, "\n".join(lines) + "\n")
    append_history(path, "Step %d %s → %s%s" % (args.number, name, label, (": " + args.note) if args.note else ""))
    rebuild_index()
    print("%s step %d → %s" % (wf[1], args.number, label))


def cmd_next(args):
    wf = resolve(args.ref)
    path = status_path(wf)
    text = read(path)
    block = "## ▶ Next step\n\n%s\n\n" % args.text.strip()
    if re.search(r"^## ▶ Next step\s*\n", text, re.M):
        text = re.sub(r"^## ▶ Next step\s*\n.*?(?=^## |\Z)", lambda _m: block, text, count=1, flags=re.S | re.M)
    else:
        text = text.replace("## Repos", block + "## Repos", 1)
    write(path, text)
    append_history(path, "Next step: " + args.text.strip())
    rebuild_index()
    print("%s next step set" % wf[1])


def cmd_log(args):
    wf = resolve(args.ref)
    append_history(status_path(wf), args.event)
    rebuild_index()
    print("%s logged" % wf[1])


def cmd_show(args):
    wf = resolve(args.ref)
    info = parse_status(status_path(wf))
    scope = scoped_repos(wf[3])
    print("Workflow %d (%s): %s" % (wf[0], wf[1], re.sub(r"^(Workflow \d+:|Upgrade:)\s*", "", info["title"])))
    print("Folder:  %s" % rel(wf[3]))
    print("Repos:   %s" % (", ".join(scope) if scope else "all of repos/repos.txt"))
    print("Branch:  %s" % ("deps/" + wf[1]))   # same rule as repos.py branch_for()
    print("")
    for p in info["phases"]:
        print("  %d  %-28s %s" % (p["n"], p["name"], p["state"]))
    cur = current_phase(info["phases"])
    print("")
    print("Current: %s" % ("all steps done" if cur is None else "%d %s (%s)" % (cur["n"], cur["name"], cur["state"])))
    print("Next:    %s" % (info["next"] or "(not set)"))


def cmd_find_open(args):
    """Most recent unfinished run whose own repos.txt is exactly the given repo(s)."""
    want = sorted(args.repo)
    for number, wf_id, name, path in reversed(workflows()):
        if scoped_repos(path) != want or not os.path.isfile(os.path.join(path, "STATUS.md")):
            continue
        if current_phase(parse_status(os.path.join(path, "STATUS.md"))["phases"]) is not None:
            print("%s\t%s" % (wf_id, rel(path)))
            return
    sys.exit(1)                                   # none: the caller starts a new run


def cmd_index(_args):
    rebuild_index()
    print("rebuilt %s" % rel(INDEX))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("new"); p.add_argument("slug"); p.add_argument("--title"); p.add_argument("--source")
    p.add_argument("--repo", action="append", help="limit the run to this repo (repeatable)")
    p.set_defaults(func=cmd_new)
    p = sub.add_parser("resolve"); p.add_argument("ref"); p.set_defaults(func=cmd_resolve)
    p = sub.add_parser("list"); p.set_defaults(func=cmd_list)
    p = sub.add_parser("phase"); p.add_argument("ref"); p.add_argument("number", type=int, choices=range(0, 6))
    p.add_argument("state", choices=sorted(STATES)); p.add_argument("--note"); p.set_defaults(func=cmd_phase)
    p = sub.add_parser("next"); p.add_argument("ref"); p.add_argument("text"); p.set_defaults(func=cmd_next)
    p = sub.add_parser("log"); p.add_argument("ref"); p.add_argument("event"); p.set_defaults(func=cmd_log)
    p = sub.add_parser("index"); p.set_defaults(func=cmd_index)
    p = sub.add_parser("show"); p.add_argument("ref"); p.set_defaults(func=cmd_show)
    p = sub.add_parser("find-open"); p.add_argument("--repo", action="append", required=True)
    p.set_defaults(func=cmd_find_open)
    p = sub.add_parser("save"); p.add_argument("ref"); p.add_argument("--allow-public", action="store_true")
    p.add_argument("--no-push", action="store_true"); p.set_defaults(func=cmd_save)
    p = sub.add_parser("sync"); p.set_defaults(func=cmd_sync)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
