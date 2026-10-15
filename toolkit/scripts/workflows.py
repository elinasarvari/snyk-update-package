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
    python3 -I toolkit/scripts/workflows.py phase <ref> <0-6> <todo|running|done|blocked|waiting|skipped> [--note N]
    python3 -I toolkit/scripts/workflows.py next <ref> "<next step text>"
    python3 -I toolkit/scripts/workflows.py log <ref> "<event>"
    python3 -I toolkit/scripts/workflows.py index                # rebuild workflows/INDEX.md
    python3 -I toolkit/scripts/workflows.py show <ref>           # one run: steps, next step, repos in scope
    python3 -I toolkit/scripts/workflows.py find-open --repo NAME   # unfinished run scoped to exactly that repo
Written for Python 3.9 - stdlib only.
"""
import argparse
import datetime
import os
import re
import sys

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
    ref = ref.strip().rstrip("/")
    ref = os.path.basename(ref) if os.sep in ref else ref
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
    ] + (rows or ["| | _no workflows yet: start one with `/dep-scan` or `/dep-upgrade`_ | | | | |"])) + "\n")


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


def cmd_new(args):
    slug = slugify(args.slug)
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
    print("%s\t%s" % (wf_id, os.path.relpath(path, ROOT)))


def cmd_resolve(args):
    print(os.path.relpath(resolve(args.ref)[3], ROOT))


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
        print("%-4d %-8s %-40s %-28s %s" % (number, wf_id, title[:40], where[:28], os.path.relpath(path, ROOT)))


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
    print("Folder:  %s" % os.path.relpath(wf[3], ROOT))
    print("Repos:   %s" % (", ".join(scope) if scope else "all of repos/repos.txt"))
    print("Branch:  deps/%s" % wf[1])
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
            print("%s\t%s" % (wf_id, os.path.relpath(path, ROOT)))
            return
    sys.exit(1)                                   # none: the caller starts a new run


def cmd_index(_args):
    rebuild_index()
    print("rebuilt %s" % os.path.relpath(INDEX, ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("new"); p.add_argument("slug"); p.add_argument("--title"); p.add_argument("--source")
    p.add_argument("--repo", action="append", help="limit the run to this repo (repeatable)")
    p.set_defaults(func=cmd_new)
    p = sub.add_parser("resolve"); p.add_argument("ref"); p.set_defaults(func=cmd_resolve)
    p = sub.add_parser("list"); p.set_defaults(func=cmd_list)
    p = sub.add_parser("phase"); p.add_argument("ref"); p.add_argument("number", type=int, choices=range(0, 7))
    p.add_argument("state", choices=sorted(STATES)); p.add_argument("--note"); p.set_defaults(func=cmd_phase)
    p = sub.add_parser("next"); p.add_argument("ref"); p.add_argument("text"); p.set_defaults(func=cmd_next)
    p = sub.add_parser("log"); p.add_argument("ref"); p.add_argument("event"); p.set_defaults(func=cmd_log)
    p = sub.add_parser("index"); p.set_defaults(func=cmd_index)
    p = sub.add_parser("show"); p.add_argument("ref"); p.set_defaults(func=cmd_show)
    p = sub.add_parser("find-open"); p.add_argument("--repo", action="append", required=True)
    p.set_defaults(func=cmd_find_open)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
