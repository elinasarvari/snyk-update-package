---
applyTo: "repos/**/pom.xml"
description: "Rules for changing dependency versions in the target repos' Maven poms"
---

# Changing dependency versions

- Before editing a version, find what sets it: an explicit `<version>`, a `<properties>` entry, the parent POM, or an
  imported BOM. Change that **lever**. Don't add a `<version>` to a managed artifact; that silently forks it from the
  rest of its platform.
- Bumping a parent or BOM moves everything it manages (e.g. a Spring Boot parent moves Spring Framework, Jackson,
  Hibernate, Tomcat, JUnit …). Treat it as a platform upgrade via `/dep-upgrade`.
- Libraries the lever doesn't manage but that depend on it (e.g. Camel or springdoc next to Spring Boot) must move to a
  version built for the new platform line. Keep any compatibility comment next to their version property accurate.
- Only edit poms as part of an approved `03-plan.md` step. Verify with the repo's wrapper
  (`./mvnw -B clean verify`). Never skip or disable tests to get green.
