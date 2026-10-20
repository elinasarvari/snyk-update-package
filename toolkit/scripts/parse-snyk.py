#!/usr/bin/env python3
"""Summarise one or more `snyk test --json` reports into a full findings inventory.

Produces three views:
  1. Every flagged package  - one row per vulnerable package@version, with all its issues,
                              the fixed-in versions, how it gets into the build, and severity.
  2. Changes to make        - what to edit: an UPGRADE of the direct dependency Snyk names
                              (upgradePath), or an OVERRIDE (pin) of the vulnerable package when no
                              upgrade path exists but a fixed version does, or NONE.
  3. Detailed paths         - every dependency path each package arrives by (`from`), with the fix
                              for that path. A package is only fixed when EVERY path is.

Remediation comes from each finding (upgradePath, isUpgradable, isPatchable, fixedIn) and, when the
report has it, the project-level `remediation` section (upgrade / pin / patch / unresolved). When a finding has no
upgradePath of its own, the remediation section's upgrade for that path's direct dependency is used (if it lists the
issue), then its pin, then the fixed-in override.

Usage:
    python3 -I parse-snyk.py <report.json> [more.json ...]
                             [--md out.md] [--json out.json] [--csv out.csv] [--modules out.md]

--modules writes the "Vulnerable modules" section for 02-plan.md: one itemized entry per vulnerable
module (facts, every Snyk issue, every path) with the decision fields left for the plan to fill in.
--index writes a one-line-per-module summary (what the plan step reads first).
--into-plan <02-plan.md> puts that section straight into the plan (replacing its "## Vulnerable modules"
section), so nobody has to copy it by hand. Decision tables already filled in are kept when it runs again.

Accepts both shapes Snyk emits: a single project object, or a list (`--all-projects`).
Written for Python 3.9 - no match statements or `X | None`.
"""
import argparse
import csv
import json
import os
import re
import sys
from collections import OrderedDict

for _stream in (sys.stdout, sys.stderr):        # Windows consoles default to a legacy code page
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

SEVERITY_ORDER = {"low": 1, "medium": 2, "high": 3, "critical": 4}


def split_coord(coord):
    """'group:artifact@1.2.3' -> ('group:artifact', '1.2.3'). Non-strings -> (None, None)."""
    if not isinstance(coord, str) or "@" not in coord:
        return None, None
    name, _, version = coord.rpartition("@")
    return name, version


def version_key(version):
    """'1.10.0' > '1.9.5': compare numbers as numbers (text order gets this wrong). Qualifiers sort after numbers."""
    parts = re.split(r"[.\-_+]", str(version or ""))
    return [(0, int(x), "") if x.isdigit() else (1, 0, x.lower()) for x in parts]


def fixed_for(fixed_in, current):
    """Snyk's fixed-in version for the line you're on: the LOWEST fixed version above `current`
    (never simply the newest). None when Snyk lists none above it."""
    above = [f for f in fixed_in or [] if version_key(f) > version_key(current)]
    return min(above, key=version_key) if above else None


def highest(versions):
    return max(versions, key=version_key) if versions else None


def worse(a, b):
    return a if SEVERITY_ORDER.get(a, 0) >= SEVERITY_ORDER.get(b, 0) else b


def add_unique(items, value):
    if value and value not in items:
        items.append(value)


OWN_OUTPUTS = ("findings.json",)      # written by this script next to the reports; never a Snyk report


def expand_paths(args):
    """Expand *.json ourselves: PowerShell passes wildcards to programs unexpanded."""
    import glob
    out = []
    for arg in args:
        hits = sorted(glob.glob(arg)) if any(c in arg for c in "*?[") else [arg]
        out += [h for h in hits if os.path.basename(h) not in OWN_OUTPUTS]
    return out


def load_projects(paths):
    projects = []
    for path in expand_paths(paths):
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError) as exc:
            print("WARN: cannot read %s: %s" % (path, exc), file=sys.stderr)
            continue
        source = os.path.basename(path)
        for project in data if isinstance(data, list) else [data]:
            if not isinstance(project, dict) or not ({"vulnerabilities", "ok", "error"} & set(project)):
                print("WARN: %s is not a snyk test --json report, skipped" % source, file=sys.stderr)
                continue
            if "error" in project and not project.get("vulnerabilities"):
                print("WARN: Snyk error in %s (%s): %s"
                      % (source, project.get("path", "?"), project["error"]), file=sys.stderr)
            project["_source"] = source
            projects.append(project)
    return projects


MAX_PATHS_SHOWN = 20          # per package in the markdown (all of them are in the JSON)


def project_remediation(project):
    """Snyk's optional project-level remediation section -> (pins, upgrades, unresolved):
    pins {package name: pin version}; upgrades {direct dependency name: [(Snyk's version, issue ids it fixes)]};
    unresolved: set of issue ids Snyk can't fix."""
    rem = project.get("remediation") or {}
    upgrades = {}
    for coord, info in (rem.get("upgrade") or {}).items():
        name, _ = split_coord(coord)
        _, target = split_coord((info or {}).get("upgradeTo"))
        if name and target:
            upgrades.setdefault(name, []).append((target, set((info or {}).get("vulns") or [])))
    pins = {}
    for coord, info in (rem.get("pin") or {}).items():
        name, _ = split_coord(coord)
        _, target = split_coord((info or {}).get("upgradeTo"))
        if name and target:
            pins[name] = target
    unresolved = {u.get("id") for u in (rem.get("unresolved") or []) if isinstance(u, dict)}
    return pins, upgrades, unresolved


def remediation_upgrade(upgrades, direct_name, vuln_id):
    """Snyk's remediation-section version for this path's direct dependency, if it lists this issue. Several -> the
    highest of Snyk's (so every issue is fixed)."""
    versions = [t for t, ids in upgrades.get(direct_name, []) if vuln_id in ids]
    return highest(versions)


def path_fix(vuln, path, pins, upgrades, unresolved):
    """-> (fix type, text, version to upgrade the direct dependency to) for ONE dependency path of one finding.
    Order: the finding's upgradePath → the remediation section's upgrade → its pin → the fixed-in override."""
    upgrade = vuln.get("upgradePath") or []
    direct_name, direct_version = split_coord(path[1] if len(path) > 1 else None)
    pkg = vuln.get("packageName")
    _, target = split_coord(upgrade[1] if len(upgrade) > 1 else None)
    if vuln.get("isUpgradable") and target and direct_name:
        return "upgrade", "upgrade `%s` %s -> %s" % (direct_name, direct_version, target), target
    remediated = remediation_upgrade(upgrades, direct_name, vuln.get("id")) if direct_name else None
    if remediated:
        return "upgrade", "upgrade `%s` %s -> %s (Snyk remediation)" % (direct_name, direct_version, remediated), remediated
    if pkg in pins:
        return "override", "override `%s` to %s (Snyk pin; no upgrade path)" % (pkg, pins[pkg]), None
    fixed = fixed_for(vuln.get("fixedIn"), vuln.get("version"))
    if fixed:
        return "override", "override `%s` to %s (no upgrade path: dependencyManagement / constraints)" % (pkg, fixed), None
    if vuln.get("isPatchable"):
        return "patch", "Snyk patch only", None
    return "none", "no remediation path" + (" (Snyk: unresolved)" if vuln.get("id") in unresolved else ""), None


def snyk_edit(fix_type, remedy):
    """-> [dependency to edit, Snyk's exact version] for an upgrade/override path, else None."""
    if fix_type == "upgrade":
        m = re.match(r"upgrade `([^`]+)` \S+ -> (\S+)", remedy)
    elif fix_type == "override":
        m = re.match(r"override `([^`]+)` to (\S+)", remedy)
    else:
        return None
    return [m.group(1), m.group(2)] if m else None


def snyk_targets(paths):
    """{dependency to edit: Snyk's version}. When Snyk names several versions for the same dependency (one per
    issue or path), the highest OF SNYK'S versions, so every issue is fixed - never a version Snyk didn't name."""
    named = OrderedDict()
    for entry in paths:
        if entry.get("edit"):
            named.setdefault(entry["edit"][0], []).append(entry["edit"][1])
    return OrderedDict((dep, highest(vs)) for dep, vs in named.items())


def collect(projects):
    packages = OrderedDict()   # view 1, key: package@version
    changes = OrderedDict()    # view 2, key: (fix type, what, current, target)
    totals = OrderedDict((s, 0) for s in ("critical", "high", "medium", "low"))
    seen_issue_rows = set()

    for project in projects:
        name = project.get("projectName") or project.get("path") or "unknown"
        target_file = project.get("displayTargetFile") or ""
        location = "%s (%s)" % (name, target_file) if target_file else name
        pins, upgrades, unresolved = project_remediation(project)

        for vuln in project.get("vulnerabilities", []):
            path = vuln.get("from") or []
            upgrade = vuln.get("upgradePath") or []
            severity = (vuln.get("severity") or "low").lower()
            kind = vuln.get("type") or "vuln"   # "license" for licence-policy findings
            pkg_name, pkg_version = vuln.get("packageName"), vuln.get("version")

            direct_name, direct_version = split_coord(path[1] if len(path) > 1 else None)
            if direct_name is None:
                direct_name, direct_version = pkg_name, pkg_version
            # upgradePath[1] is false/absent when Snyk knows no upgrade route.
            _, target_version = split_coord(upgrade[1] if len(upgrade) > 1 else None)
            is_direct = direct_name == pkg_name

            fix_type, remedy, fix_target = path_fix(vuln, path, pins, upgrades, unresolved)
            if fix_type == "upgrade":
                target_version = fix_target           # upgradePath, or the remediation section's upgrade

            # Same issue appears once per dependency path; count each issue once per project.
            issue_key = (location, vuln.get("id"), pkg_name, pkg_version)
            if issue_key not in seen_issue_rows:
                seen_issue_rows.add(issue_key)
                totals[severity] = totals.get(severity, 0) + 1

            pkg = packages.setdefault("%s@%s" % (pkg_name, pkg_version), {
                "package": pkg_name, "version": pkg_version, "type": kind,
                "max_severity": severity, "issues": [], "issue_details": [], "cves": [], "fixed_in": [],
                "introduced_via": [], "remediation": [], "projects": [], "direct": is_direct,
                "paths": [], "fix_types": [],
            })
            pkg["max_severity"] = worse(severity, pkg["max_severity"])
            add_unique(pkg["issues"], "%s %s (%s)" % (vuln.get("id"), vuln.get("title", ""), severity))
            if vuln.get("id") not in [d["id"] for d in pkg["issue_details"]]:
                ids = vuln.get("identifiers") or {}
                pkg["issue_details"].append({
                    "id": vuln.get("id"), "title": vuln.get("title", ""), "severity": severity,
                    "cvss": vuln.get("cvssScore"), "cves": list(ids.get("CVE") or []), "cwes": list(ids.get("CWE") or []),
                    "exploit": vuln.get("exploit") or "", "fixed_in": list(vuln.get("fixedIn") or []),
                    "url": vuln.get("url") or ("https://security.snyk.io/vuln/%s" % vuln.get("id") if vuln.get("id") else ""),
                })
            for cve in (vuln.get("identifiers") or {}).get("CVE") or []:
                add_unique(pkg["cves"], cve)
            for fixed in vuln.get("fixedIn") or []:
                add_unique(pkg["fixed_in"], fixed)
            if not is_direct:
                add_unique(pkg["introduced_via"], "%s@%s" % (direct_name, direct_version))
            add_unique(pkg["remediation"], remedy)
            add_unique(pkg["projects"], location)
            add_unique(pkg["fix_types"], fix_type)
            entry = {"path": path[1:] or [pkg_name], "project": location, "fix": fix_type, "remediation": remedy,
                     "edit": snyk_edit(fix_type, remedy)}
            if entry not in pkg["paths"]:
                pkg["paths"].append(entry)

            if fix_type == "override":                    # edit: force the vulnerable package itself
                pinned = remedy.split(" to ", 1)[1].split(" ", 1)[0]
                key = ("override", pkg_name, pkg_version, pinned)
                what, current, target = pkg_name, pkg_version, pinned
            else:                                         # edit: the direct dependency (upgrade, or nothing to do)
                key = (fix_type, direct_name, direct_version, target_version)
                what, current, target = direct_name, direct_version, target_version
            change = changes.setdefault(key, {
                "fix": fix_type, "direct_dependency": what, "current_version": current,
                "target_version": target, "max_severity": severity,
                "fixes_packages": [], "issue_count": 0, "projects": [],
            })
            change["max_severity"] = worse(severity, change["max_severity"])
            add_unique(change["fixes_packages"], "%s@%s" % (pkg_name, pkg_version))
            add_unique(change["projects"], location)

    for change in changes.values():
        change["issue_count"] = sum(len(packages[p]["issues"]) for p in change["fixes_packages"])
    for pkg in packages.values():
        kinds = set(pkg["fix_types"])
        pkg["status"] = ("no fix" if kinds == {"none"} else "partly fixable" if "none" in kinds
                         else "needs an override" if "override" in kinds else "fixable by upgrade")

    by_sev = lambda row: -SEVERITY_ORDER.get(row["max_severity"], 0)
    return (sorted(packages.values(), key=by_sev), sorted(changes.values(), key=by_sev), totals)


def scanned_projects(projects):
    rows = []
    for p in projects:
        rows.append("| %s | `%s` | %s | %s | %s |" % (
            p["_source"], p.get("displayTargetFile") or p.get("targetFile") or "?",
            p.get("projectName", "?"), p.get("dependencyCount", "?"),
            p.get("uniqueCount", len(p.get("vulnerabilities", [])))))
    return rows


def to_markdown(packages, changes, totals, projects):
    out = ["## Scan summary", "",
           "| Critical | High | Medium | Low | Flagged packages | Direct changes needed |",
           "|----------|------|--------|-----|------------------|-----------------------|",
           "| %d | %d | %d | %d | %d | %d |" % (totals.get("critical", 0), totals.get("high", 0),
                                              totals.get("medium", 0), totals.get("low", 0),
                                              len(packages), len(changes)),
           "", "### Projects scanned", "",
           "| Report | Target file | Project | Dependencies | Unique issues |",
           "|--------|-------------|---------|--------------|---------------|"]
    out += scanned_projects(projects)

    out += ["", "## 1. Every flagged package", "",
            "| # | Package | Current | Severity | Status | Paths | Issues | CVEs | Fixed in | Introduced via | Remediation | Projects |",
            "|---|---------|---------|----------|--------|-------|--------|------|----------|----------------|-------------|----------|"]
    for i, p in enumerate(packages, 1):
        out.append("| %d | `%s`%s | %s | %s | %s | %d | %s | %s | %s | %s | %s | %s |" % (
            i, p["package"], " (license)" if p["type"] == "license" else "", p["version"],
            p["max_severity"], p["status"], len(p["paths"]), "<br>".join(p["issues"]), ", ".join(p["cves"]) or "-",
            ", ".join(p["fixed_in"]) or "-",
            "direct" if p["direct"] else "<br>".join("`%s`" % v for v in p["introduced_via"]),
            "<br>".join(p["remediation"]), "<br>".join(p["projects"])))

    out += ["", "## 2. Changes to make", "",
            "`upgrade`: bump the direct dependency (or the parent/BOM that sets it). `override`: no upgrade path exists,",
            "so force the vulnerable package itself to its fixed version (Maven `<dependencyManagement>`, Gradle",
            "constraints) - check compatibility. `none`: no remediation path; see the detailed paths.", "",
            "| # | Fix | Edit | Current | Target | Max severity | Issues fixed | Fixes packages | Projects |",
            "|---|-----|------|---------|--------|--------------|--------------|----------------|----------|"]
    for i, c in enumerate(changes, 1):
        out.append("| %d | %s | `%s` | %s | %s | %s | %d | %s | %s |" % (
            i, c["fix"], c["direct_dependency"], c["current_version"],
            c["target_version"] or "_no upgrade path_", c["max_severity"], c["issue_count"],
            "<br>".join("`%s`" % p for p in c["fixes_packages"]), "<br>".join(c["projects"])))

    out += ["", "## 3. Detailed paths", "",
            "Every path a package arrives by, and the fix for that path. A package is only fixed when every one of",
            "its paths is: e.g. upgrading `A` doesn't help if `C` still brings the old version in."]
    for p in packages:
        out += ["", "### `%s@%s` - %s - %s - fixed in %s" % (p["package"], p["version"], p["max_severity"], p["status"],
                                                             ", ".join(p["fixed_in"]) or "none"), "",
                "| # | Path | Fix for this path | Project |", "|---|------|-------------------|---------|"]
        for n, entry in enumerate(p["paths"][:MAX_PATHS_SHOWN], 1):
            out.append("| %d | %s | %s | %s |" % (n, " › ".join("`%s`" % c for c in entry["path"]), entry["remediation"],
                                               entry["project"]))
        if len(p["paths"]) > MAX_PATHS_SHOWN:
            out.append("| | _… %d more paths in findings.json_ | | |" % (len(p["paths"]) - MAX_PATHS_SHOWN))
    return "\n".join(out) + "\n"


def to_modules(packages):
    """The itemized "Vulnerable modules" section of 02-plan.md. Facts are filled in; decisions are {{placeholders}}."""
    out = ["## Vulnerable modules", "",
           "One entry per vulnerable module, generated from the Snyk scan, so none can be missed. The plan fills in the",
           "**Decision** table of every module in scope; a module left out of scope says so and points to its row in",
           "*Out of scope*.", ""]
    for n, p in enumerate(packages, 1):
        lic = " (licence)" if p["type"] == "license" else ""
        out += ["### %d. `%s@%s`%s" % (n, p["package"], p["version"], lic), "",
                "| Fact | Value |", "|------|-------|",
                "| Current version | %s |" % p["version"],
                "| Highest severity | %s |" % p["max_severity"],
                "| Status (from Snyk) | %s |" % p["status"],
                "| Fixed in | %s |" % (", ".join(p["fixed_in"]) or "no fixed version"),
                "| Dependency paths | %d (listed below) |" % len(p["paths"]),
                "| Introduced via | %s |" % ("direct dependency" if p["direct"] else
                                            ", ".join("`%s`" % v for v in p["introduced_via"])),
                "| Projects | %s |" % ", ".join(p["projects"]), "",
                "**Issues**", "",
                "| Snyk issue | Title | Severity | CVSS | CVE | CWE | Exploit | Fixed in |",
                "|------------|-------|----------|------|-----|-----|---------|----------|"]
        for d in p["issue_details"]:
            out.append("| [%s](%s) | %s | %s | %s | %s | %s | %s | %s |" % (
                d["id"], d["url"], d["title"].replace("|", "/"), d["severity"],
                d["cvss"] if d["cvss"] is not None else "-", ", ".join(d["cves"]) or "-", ", ".join(d["cwes"]) or "-",
                d["exploit"] or "-", ", ".join(d["fixed_in"]) or "-"))
        out += ["", "**Paths**", "", "| # | Path | Snyk's fix for this path |", "|---|------|--------------------------|"]
        for i, entry in enumerate(p["paths"][:MAX_PATHS_SHOWN], 1):
            out.append("| %d | %s | %s |" % (i, " › ".join("`%s`" % c for c in entry["path"]), entry["remediation"]))
        if len(p["paths"]) > MAX_PATHS_SHOWN:
            out.append("| | _… %d more paths in snyk/findings.json_ | |" % (len(p["paths"]) - MAX_PATHS_SHOWN))
        fixes = sorted({e["remediation"] for e in p["paths"] if e["fix"] in ("upgrade", "override")})
        no_fix = any(e["fix"] in ("none", "patch") for e in p["paths"])
        targets = "; ".join("`%s` %s" % (dep, v) for dep, v in snyk_targets(p["paths"]).items())
        if targets and not no_fix:
            target_row = targets + " _(Snyk's version, exactly)_"
        elif targets:
            target_row = targets + " _(Snyk's version)_ + {{for the path(s) Snyk can't fix: the LOWEST version that fixes it, with evidence}}"
        else:
            target_row = "{{no Snyk version: the LOWEST version of the introducing library that drops or fixes it, with evidence}}"
        if fixes and not no_fix:
            fix_chosen = "; ".join(fixes) + " _(Snyk's fix for every path)_"
        elif fixes:
            fix_chosen = "; ".join(fixes) + " + {{the path(s) Snyk can't fix: newer introducing library / exclude / out of scope}}"
        else:
            fix_chosen = "{{no Snyk fix: newer introducing library / exclude / out of scope}}"
        out += ["", "**Decision**", "", "| | |", "|---|---|",
                "| In scope? | {{yes / no: see Out of scope #n}} |",
                "| Fix chosen | %s |" % fix_chosen,
                "| Target version | %s |" % target_row,
                "| Plan step(s) | {{Step n, …: every path above is covered}} |",
                "| Compatibility / risk | {{what could break, with evidence from the Impact section}} |",
                "| Verified by | Snyk re-scan shows %s gone · build and tests green |" % ", ".join(d["id"] for d in p["issue_details"]),
                ""]
    return "\n".join(out)


def short_fix(text):
    """'upgrade `g:a` 1 -> 2' -> 'upgrade a→2'; 'override `g:p` to 3 (…)' -> 'override→3'; else 'no fix' / 'patch'."""
    m = re.match(r"upgrade `([^`]+)` \S+ -> (\S+)", text)
    if m:
        return "upgrade %s→%s" % (m.group(1).split(":")[-1], m.group(2))
    m = re.match(r"override `[^`]+` to (\S+)", text)
    if m:
        return "override→%s" % m.group(1)
    return "patch" if text.startswith("Snyk patch") else "no fix"


def to_index(packages):
    """One line per vulnerable module (~30 tokens each): what the plan step reads instead of every full entry."""
    out = ["# Vulnerable modules: index", "",
           "One line per module, same numbering as the plan's *Vulnerable modules*. Read a module's full entry only when",
           "its status isn't `fixable by upgrade`.", "",
           "| # | Module | Severity | Status | Issues | Paths | Snyk's fix |", "|---|--------|----------|--------|--------|-------|-----------|"]
    for n, p in enumerate(packages, 1):
        fixes = sorted({short_fix(e["remediation"]) for e in p["paths"]})
        out.append("| %d | `%s@%s` | %s | %s | %d | %d | %s |" % (
            n, p["package"], p["version"], p["max_severity"], p["status"], len(p["issue_details"]), len(p["paths"]),
            "; ".join(fixes[:4]) + (" (+%d more)" % (len(fixes) - 4) if len(fixes) > 4 else "")))
    return "\n".join(out) + "\n"


DECISION_ROW = re.compile(r"^\| (In scope\?|Fix chosen|Target version|Plan step\(s\)|Compatibility / risk|Verified by) \|")


def _module_decisions(section):
    """{module heading: {field: row}} for every Decision field somebody filled in (no {{placeholder}} left).
    Kept field by field, so partly decided modules don't lose what's already decided."""
    kept, heading = {}, None
    for line in section.splitlines():
        if line.startswith("### "):
            heading = re.sub(r"^### \d+\. ", "### ", line)
        elif heading and DECISION_ROW.match(line) and "{{" not in line:
            kept.setdefault(heading, {})[DECISION_ROW.match(line).group(1)] = line
    return kept


def into_plan(plan_path, modules_md):
    with open(plan_path, encoding="utf-8") as fh:
        plan = fh.read()
    start = plan.find("## Vulnerable modules")
    if start == -1:
        sys.exit("%s has no '## Vulnerable modules' section" % plan_path)
    nxt = re.search(r"^## ", plan[start + 3:], re.M)
    end = start + 3 + nxt.start() if nxt else len(plan)
    kept = _module_decisions(plan[start:end])
    out, heading, carried = [], None, 0
    for line in modules_md.splitlines():
        if line.startswith("### "):
            heading = re.sub(r"^### \d+\. ", "### ", line)
        m = DECISION_ROW.match(line)
        if m and heading in kept and m.group(1) in kept[heading]:
            line = kept[heading][m.group(1)]                       # your decision wins over the regenerated row
            carried += 1
        out.append(line)
    with open(plan_path, "w", encoding="utf-8") as fh:
        fh.write(plan[:start] + "\n".join(out).rstrip("\n") + "\n\n" + plan[end:])
    return carried


def write_csv(path, packages):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["package", "current_version", "type", "max_severity", "status", "paths", "issues", "cves",
                         "fixed_in", "introduced_via", "remediation", "projects"])
        for p in packages:
            writer.writerow([p["package"], p["version"], p["type"], p["max_severity"], p["status"], len(p["paths"]),
                             "; ".join(p["issues"]), "; ".join(p["cves"]), "; ".join(p["fixed_in"]),
                             "direct" if p["direct"] else "; ".join(p["introduced_via"]),
                             "; ".join(p["remediation"]), "; ".join(p["projects"])])


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("reports", nargs="+")
    parser.add_argument("--md", dest="md_out")
    parser.add_argument("--json", dest="json_out")
    parser.add_argument("--csv", dest="csv_out")
    parser.add_argument("--modules", dest="modules_out")
    parser.add_argument("--into-plan", dest="plan_path")
    parser.add_argument("--index", dest="index_out")
    args = parser.parse_args()

    projects = load_projects(args.reports)
    packages, changes, totals = collect(projects)
    markdown = to_markdown(packages, changes, totals, projects)
    if args.md_out:
        with open(args.md_out, "w", encoding="utf-8") as fh:
            fh.write(markdown)
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump({"totals": totals, "packages": packages, "changes": changes}, fh, indent=2)
    if args.csv_out:
        write_csv(args.csv_out, packages)
    if args.modules_out:
        with open(args.modules_out, "w", encoding="utf-8") as fh:
            fh.write(to_modules(packages))
    if args.index_out:
        with open(args.index_out, "w", encoding="utf-8") as fh:
            fh.write(to_index(packages))
    if args.plan_path:
        kept = into_plan(args.plan_path, to_modules(packages))
        print("put %d vulnerable modules into %s (%d filled-in decision fields kept)"
              % (len(packages), args.plan_path, kept), file=sys.stderr)
    sys.stdout.write(markdown)
    print("\n%d flagged packages, %d direct changes, across %d projects."
          % (len(packages), len(changes), len(projects)), file=sys.stderr)


if __name__ == "__main__":
    main()
