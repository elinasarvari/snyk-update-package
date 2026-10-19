#!/usr/bin/env python3
"""Shared helpers for the bash (*.sh) and PowerShell (*.ps1) versions of the toolkit scripts.

Anything that parses files or writes JSON lives here, once, so both shell versions behave
identically and only differ in how they run processes. Python 3.9, stdlib only, any OS.

    script-helpers.py junit <reports-dir> ...          -> JSON test totals from JUnit XML (TEST-*.xml)
    script-helpers.py pom-declared <pom.xml>           -> one line per parent/managed/dependency/plugin
    script-helpers.py version-props <pom.xml>          -> <...version> entries of <properties>
    script-helpers.py project-java <pom.xml>           -> the <java.version> property, or empty
    script-helpers.py git-snapshot <file>              -> save `git status` of the current folder
    script-helpers.py left-in-repo <file>              -> JSON list of paths that appeared since the snapshot
    script-helpers.py env-info                         -> JSON: branch, commit, java (of the current folder)
    script-helpers.py summary <out.json> [--env] [--fields <file>] [k=v | k:=<json> ...]
                                                       -> write (and print) a summary object. --env adds
                                                          branch/commit/java of the current folder. --fields
                                                          reads the same k=v / k:=json pairs, one per line, from a
                                                          file (used by PowerShell 5.1, which mangles quotes in
                                                          arguments passed to other programs)
    script-helpers.py first-errors <log> [max]         -> the first error-looking lines of a build log
    script-helpers.py filter-tree <tree> <out> <word>...-> module headers + lines containing any word
    script-helpers.py ignore-dirs [--comma]            -> the folders never searched/scanned (toolkit/ignore-dirs.txt)
    script-helpers.py find-poms                        -> ./paths of every pom.xml in the current folder, skipping
                                                          the ignored folders, sorted
    script-helpers.py plan-decide <plan> <which> "<Field>=<value>" ...
                                                       -> set a Decision field for many modules at once. <which>:
                                                          numbers / ranges (1,3,5-9), all, or status:<status>
    script-helpers.py plan-check <plan>                -> list modules whose Decision still has {{gaps}}; exit 1 if any
"""
import glob
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

for _stream in (sys.stdout, sys.stderr):        # Windows consoles default to a legacy code page
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

NS = {"m": "http://maven.apache.org/POM/4.0.0"}
IGNORE_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ignore-dirs.txt")


def load_ignore_dirs():
    with open(IGNORE_FILE, encoding="utf-8") as fh:
        return [l.strip() for l in fh if l.strip() and not l.lstrip().startswith("#")]


def ignore_dirs(comma=False):
    dirs = load_ignore_dirs()
    print(",".join(dirs) if comma else "\n".join(dirs))


def find_poms():
    skip = set(load_ignore_dirs())
    found = []
    for base, dirs, files in os.walk("."):
        dirs[:] = sorted(d for d in dirs if d not in skip)        # never descend into them
        if "pom.xml" in files:
            found.append(os.path.join(base, "pom.xml").replace(os.sep, "/"))
    print("\n".join(sorted(found)))


def run(cmd):
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True,
                              encoding="utf-8", errors="replace")
        return proc.returncode, proc.stdout.strip()
    except OSError:
        return 127, ""


def junit(dirs):
    totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    failed = []
    for base in dirs:
        for path in glob.glob(os.path.join(base, "**", "TEST-*.xml"), recursive=True):
            try:
                suite = ET.parse(path).getroot()
            except ET.ParseError:
                continue
            for key in totals:
                totals[key] += int(suite.get(key, 0) or 0)
            for case in suite.iter("testcase"):
                if case.find("failure") is not None or case.find("error") is not None:
                    failed.append("%s#%s" % (case.get("classname"), case.get("name")))
    totals["failed_tests"] = failed[:50]
    print(json.dumps(totals))


def _text(el, tag):
    found = el.find("m:" + tag, NS)
    return found.text.strip() if found is not None and found.text else ""


def _pom(path):
    return ET.parse(path).getroot()


def pom_declared(pom):
    root = _pom(pom)
    label = pom.replace("\\", "/")
    parent = root.find("m:parent", NS)
    if parent is not None:
        print("%s\tparent\t%s:%s:%s" % (label, _text(parent, "groupId"), _text(parent, "artifactId"), _text(parent, "version")))
    for section, xpath in (("managed", "m:dependencyManagement/m:dependencies/m:dependency"),
                           ("dependency", "m:dependencies/m:dependency"),
                           ("plugin", "m:build/m:plugins/m:plugin")):
        for dep in root.findall(xpath, NS):
            scope = _text(dep, "scope")
            print("%s\t%s\t%s:%s:%s%s" % (label, section, _text(dep, "groupId"), _text(dep, "artifactId"),
                                          _text(dep, "version") or "(managed)", " scope=" + scope if scope else ""))


def version_props(pom):
    props = _pom(pom).find("m:properties", NS)
    for el in (props if props is not None else []):
        tag = el.tag.split("}", 1)[-1]
        if tag.endswith(".version"):
            print("%s: <%s>%s</%s>" % (pom.replace("\\", "/"), tag, (el.text or "").strip(), tag))


def project_java(pom):
    props = _pom(pom).find("m:properties", NS)
    found = props.find("m:java.version", NS) if props is not None else None
    print(found.text.strip() if found is not None and found.text else "")


def _git_changes():
    code, out = run(["git", "status", "--porcelain", "--untracked-files=all"])
    return sorted(line[3:].strip().strip('"') for line in out.splitlines() if code == 0 and line.strip())


def git_snapshot(path):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(_git_changes(), fh)


def left_in_repo(path):
    with open(path, encoding="utf-8") as fh:
        before = set(json.load(fh))
    print(json.dumps([p for p in _git_changes() if p not in before][:50]))


def _env():
    _, branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    _, commit = run(["git", "rev-parse", "--short", "HEAD"])
    _, java = run(["java", "-version"])
    return {"branch": branch, "commit": commit, "java": java.splitlines()[0] if java else ""}


def env_info():
    print(json.dumps(_env()))


def summary(out, args):
    pairs, add_env = [], False
    while args:
        arg = args.pop(0)
        if arg == "--env":
            add_env = True
        elif arg == "--fields":
            with open(args.pop(0), encoding="utf-8-sig") as fh:
                pairs += [line.rstrip("\r\n") for line in fh if line.strip()]
        else:
            pairs.append(arg)
    data = {}
    for pair in pairs:
        if ":=" in pair:
            key, value = pair.split(":=", 1)
            data[key] = json.loads(value)
        else:
            key, _, value = pair.partition("=")
            data[key] = value
    if add_env:
        env = _env()
        keys = list(data)
        ordered = {}
        for key in keys:                              # keep branch/commit/java right after "repo"
            ordered[key] = data[key]
            if key == "repo":
                ordered.update(env)
        data = ordered if "repo" in data else dict(data, **env)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    print(json.dumps(data, indent=2))


def first_errors(log, limit=40):
    pattern = re.compile(r"\[ERROR\]|FAILED|error:|Caused by")
    with open(log, encoding="utf-8", errors="replace") as fh:
        hits = ["%d:%s" % (n, line.rstrip()) for n, line in enumerate(fh, 1) if pattern.search(line)]
    print("\n".join(hits[:int(limit)]))


def filter_tree(tree, out, words):
    with open(tree, encoding="utf-8", errors="replace") as fh, open(out, "w", encoding="utf-8") as dst:
        for line in fh:
            if re.match(r"^[A-Za-z]", line) or any(w in line for w in words):
                dst.write(line)


DECISION_FIELDS = ("In scope?", "Fix chosen", "Target version", "Plan step(s)", "Compatibility / risk", "Verified by")


def _plan_modules(lines):
    """[(number, heading line index, end index, status)] for each '### n. `module`' in ## Vulnerable modules."""
    try:
        start = next(i for i, l in enumerate(lines) if l.startswith("## Vulnerable modules"))
    except StopIteration:
        sys.exit("the plan has no '## Vulnerable modules' section (run parse-snyk.py ... --into-plan first)")
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    heads = [i for i in range(start, end) if re.match(r"^### \d+\. ", lines[i])]
    mods = []
    for k, h in enumerate(heads):
        stop = heads[k + 1] if k + 1 < len(heads) else end
        status = next((l.split("|")[2].strip() for l in lines[h:stop] if l.startswith("| Status (from Snyk) |")), "")
        mods.append((int(re.match(r"^### (\d+)\.", lines[h]).group(1)), h, stop, status))
    return mods


def _select(mods, which):
    if which == "all":
        return mods
    if which.startswith("status:"):
        wanted = which[len("status:"):].strip()
        return [m for m in mods if m[3] == wanted]
    numbers = set()
    for part in which.split(","):
        a, _, b = part.strip().partition("-")
        numbers.update(range(int(a), int(b or a) + 1))
    return [m for m in mods if m[0] in numbers]


def plan_decide(plan, which, assignments):
    with open(plan, encoding="utf-8") as fh:
        lines = fh.read().split("\n")
    pairs = []
    for a in assignments:
        field, sep, value = a.partition("=")
        if not sep or field.strip() not in DECISION_FIELDS:
            sys.exit("'%s': use <Field>=<value> with Field one of: %s" % (a, ", ".join(DECISION_FIELDS)))
        pairs.append((field.strip(), value.strip().replace("|", "/")))
    chosen = _select(_plan_modules(lines), which)
    if not chosen:
        sys.exit("no module matches %r" % which)
    for _, h, stop, _ in chosen:
        for field, value in pairs:
            row = next((i for i in range(h, stop) if lines[i].startswith("| %s |" % field)), None)
            if row is None:
                sys.exit("module at line %d has no '%s' row" % (h + 1, field))
            lines[row] = "| %s | %s |" % (field, value)
    with open(plan, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print("set %s for %d module(s): %s" % (", ".join(f for f, _ in pairs), len(chosen), ", ".join(str(m[0]) for m in chosen)))


def plan_check(plan):
    with open(plan, encoding="utf-8") as fh:
        lines = fh.read().split("\n")
    mods = _plan_modules(lines)
    gaps = []
    for n, h, stop, _ in mods:
        open_fields = [l.split("|")[1].strip() for l in lines[h:stop]
                       if l.startswith("| ") and l.split("|")[1].strip() in DECISION_FIELDS and "{{" in l]
        if open_fields:
            gaps.append("%d. %s: %s" % (n, lines[h].split("`")[1] if "`" in lines[h] else "", ", ".join(open_fields)))
    if gaps:
        print("%d of %d modules still have open decisions:" % (len(gaps), len(mods)))
        print("\n".join("  " + g for g in gaps))
        sys.exit(1)
    print("all %d modules decided" % len(mods))


def main(argv):
    if not argv:
        sys.exit(__doc__)
    cmd, args = argv[0], argv[1:]
    table = {
        "junit": lambda: junit(args), "pom-declared": lambda: pom_declared(args[0]),
        "version-props": lambda: version_props(args[0]), "project-java": lambda: project_java(args[0]),
        "git-snapshot": lambda: git_snapshot(args[0]), "left-in-repo": lambda: left_in_repo(args[0]),
        "env-info": env_info, "summary": lambda: summary(args[0], args[1:]),
        "first-errors": lambda: first_errors(*args[:2]), "filter-tree": lambda: filter_tree(args[0], args[1], args[2:]),
        "ignore-dirs": lambda: ignore_dirs("--comma" in args), "find-poms": find_poms,
        "plan-decide": lambda: plan_decide(args[0], args[1], args[2:]), "plan-check": lambda: plan_check(args[0]),
    }
    if cmd not in table:
        sys.exit("unknown helper %r\n%s" % (cmd, __doc__))
    table[cmd]()


if __name__ == "__main__":
    main(sys.argv[1:])
