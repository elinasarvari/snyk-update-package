#!/usr/bin/env python3
"""Summarise one or more `snyk test --json` reports into a full findings inventory.

Produces two views:
  1. Every flagged package  - one row per vulnerable package@version, with all its issues,
                              the fixed-in versions, how it gets into the build, and severity.
  2. Changes to make        - rows grouped by the *direct* dependency you actually edit in
                              the pom (upgradePath[1]), since many transitive findings are
                              fixed by one direct bump (e.g. the Spring Boot parent).

Usage:
    python3 -I parse-snyk.py <report.json> [more.json ...]
                             [--md out.md] [--json out.json] [--csv out.csv]

Accepts both shapes Snyk emits: a single project object, or a list (`--all-projects`).
Written for Python 3.9 - no match statements or `X | None`.
"""
import argparse
import csv
import json
import os
import sys
from collections import OrderedDict

SEVERITY_ORDER = {"low": 1, "medium": 2, "high": 3, "critical": 4}


def split_coord(coord):
    """'group:artifact@1.2.3' -> ('group:artifact', '1.2.3'). Non-strings -> (None, None)."""
    if not isinstance(coord, str) or "@" not in coord:
        return None, None
    name, _, version = coord.rpartition("@")
    return name, version


def worse(a, b):
    return a if SEVERITY_ORDER.get(a, 0) >= SEVERITY_ORDER.get(b, 0) else b


def add_unique(items, value):
    if value and value not in items:
        items.append(value)


def load_projects(paths):
    projects = []
    for path in paths:
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


def collect(projects):
    packages = OrderedDict()   # view 1, key: package@version
    changes = OrderedDict()    # view 2, key: (direct dep, current, target)
    totals = OrderedDict((s, 0) for s in ("critical", "high", "medium", "low"))
    seen_issue_rows = set()

    for project in projects:
        name = project.get("projectName") or project.get("path") or "unknown"
        target_file = project.get("displayTargetFile") or ""
        location = "%s (%s)" % (name, target_file) if target_file else name

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

            if vuln.get("isUpgradable") and target_version:
                remedy = "upgrade `%s` %s -> %s" % (direct_name, direct_version, target_version)
            elif vuln.get("isPatchable"):
                remedy = "Snyk patch only"
            elif vuln.get("fixedIn"):
                remedy = "no direct upgrade path - pin/override to %s" % ", ".join(vuln["fixedIn"])
            else:
                remedy = "no fix available"

            # Same issue appears once per dependency path; count each issue once per project.
            issue_key = (location, vuln.get("id"), pkg_name, pkg_version)
            if issue_key not in seen_issue_rows:
                seen_issue_rows.add(issue_key)
                totals[severity] = totals.get(severity, 0) + 1

            pkg = packages.setdefault("%s@%s" % (pkg_name, pkg_version), {
                "package": pkg_name, "version": pkg_version, "type": kind,
                "max_severity": severity, "issues": [], "cves": [], "fixed_in": [],
                "introduced_via": [], "remediation": [], "projects": [], "direct": is_direct,
            })
            pkg["max_severity"] = worse(severity, pkg["max_severity"])
            add_unique(pkg["issues"], "%s %s (%s)" % (vuln.get("id"), vuln.get("title", ""), severity))
            for cve in (vuln.get("identifiers") or {}).get("CVE") or []:
                add_unique(pkg["cves"], cve)
            for fixed in vuln.get("fixedIn") or []:
                add_unique(pkg["fixed_in"], fixed)
            if not is_direct:
                add_unique(pkg["introduced_via"], "%s@%s" % (direct_name, direct_version))
            add_unique(pkg["remediation"], remedy)
            add_unique(pkg["projects"], location)

            change = changes.setdefault((direct_name, direct_version, target_version), {
                "direct_dependency": direct_name, "current_version": direct_version,
                "target_version": target_version, "max_severity": severity,
                "fixes_packages": [], "issue_count": 0, "projects": [],
            })
            change["max_severity"] = worse(severity, change["max_severity"])
            add_unique(change["fixes_packages"], "%s@%s" % (pkg_name, pkg_version))
            add_unique(change["projects"], location)

    for change in changes.values():
        change["issue_count"] = sum(len(packages[p]["issues"]) for p in change["fixes_packages"])

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
            "| # | Package | Current | Severity | Issues | CVEs | Fixed in | Introduced via | Remediation | Projects |",
            "|---|---------|---------|----------|--------|------|----------|----------------|-------------|----------|"]
    for i, p in enumerate(packages, 1):
        out.append("| %d | `%s`%s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            i, p["package"], " (license)" if p["type"] == "license" else "", p["version"],
            p["max_severity"], "<br>".join(p["issues"]), ", ".join(p["cves"]) or "-",
            ", ".join(p["fixed_in"]) or "-",
            "direct" if p["direct"] else "<br>".join("`%s`" % v for v in p["introduced_via"]),
            "<br>".join(p["remediation"]), "<br>".join(p["projects"])))

    out += ["", "## 2. Changes to make (grouped by the dependency you edit)", "",
            "| # | Direct dependency | Current | Target | Max severity | Issues fixed | Fixes packages | Projects |",
            "|---|-------------------|---------|--------|--------------|--------------|----------------|----------|"]
    for i, c in enumerate(changes, 1):
        out.append("| %d | `%s` | %s | %s | %s | %d | %s | %s |" % (
            i, c["direct_dependency"], c["current_version"],
            c["target_version"] or "_no upgrade path_", c["max_severity"], c["issue_count"],
            "<br>".join("`%s`" % p for p in c["fixes_packages"]), "<br>".join(c["projects"])))
    return "\n".join(out) + "\n"


def write_csv(path, packages):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["package", "current_version", "type", "max_severity", "issues", "cves",
                         "fixed_in", "introduced_via", "remediation", "projects"])
        for p in packages:
            writer.writerow([p["package"], p["version"], p["type"], p["max_severity"],
                             "; ".join(p["issues"]), "; ".join(p["cves"]), "; ".join(p["fixed_in"]),
                             "direct" if p["direct"] else "; ".join(p["introduced_via"]),
                             "; ".join(p["remediation"]), "; ".join(p["projects"])])


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("reports", nargs="+")
    parser.add_argument("--md", dest="md_out")
    parser.add_argument("--json", dest="json_out")
    parser.add_argument("--csv", dest="csv_out")
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
    sys.stdout.write(markdown)
    print("\n%d flagged packages, %d direct changes, across %d projects."
          % (len(packages), len(changes), len(projects)), file=sys.stderr)


if __name__ == "__main__":
    main()
