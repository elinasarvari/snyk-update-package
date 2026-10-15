---
name: dep-upgrade
description: Snyk-driven dependency upgrade workflow for the Java/Maven repos cloned in workspace/ - clone, scan every flagged package, inventory current vs target, analyse pom/code/config impact with citations, plan, apply on a branch, verify build/tests/boot, publish PRs. Use for Snyk/CVE fixes, library or Spring Boot upgrades, or "what's the next step" on an upgrade.
---

# Dependency upgrade workflow

Read `workflow/WORKFLOW.md` at the project root. It is the single source of truth (phases, gates,
layout, principles, scripts). Run each phase by following its file in `workflow/phases/`. The user-facing
commands are `/dep-upgrade`, `/dep-clone`, `/dep-scan`, `/dep-inventory`, `/dep-analyze`, `/dep-apply`,
`/dep-verify` and `/dep-publish`.
