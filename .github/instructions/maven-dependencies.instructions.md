---
applyTo: "workspace/**/pom.xml"
description: "Rules for changing dependency versions in the cloned repos' Maven poms"
---

# Changing dependency versions

- Before editing a version, find what sets it: an explicit `<version>`, a `<properties>` entry, the parent
  (`spring-boot-starter-parent`) or an imported BOM. Change that **lever**. Don't add a `<version>` to a
  managed artifact; that silently forks it from the rest of the platform.
- A Spring Boot major or minor bump moves Spring Framework, Jackson, Hibernate, Tomcat, JUnit and others.
  Treat it as a platform upgrade via `/dep-upgrade`.
- Libraries the Boot parent doesn't manage (Camel BOM, springdoc, Testcontainers...) must move to a version
  built for the new Boot line. Keep any compatibility comment next to their version property accurate.
- Only edit poms as part of an approved `03-plan.md` step. Verify with the repo's wrapper
  (`./mvnw -B clean verify`). Never skip or disable tests to get green.
