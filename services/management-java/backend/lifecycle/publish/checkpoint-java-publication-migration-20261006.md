# java-publication-migration-20261006

- Baseline: origin/main ab5c8df.
- Authorized scope: replace management Python publication bridge with direct Java
  PostgreSQL publication; no deployment and no production database mutation.
- Worker: codex/java-publication-migration-20261006/design.
- Implementation: publication package plus publication-only tests. No auth edits.
- JDK 17 local nongit archive Maven compile/test-compile passed.
- Isolated PostgreSQL 15 fixture: Skill PRT/ONLINE publication, exact receipt retry,
  request collision, stale CAS, dependency rejection and Java Ability/Application
  publication passed. Python Runtime repository/reader accepted all three asset
  kinds, versions and digests; 4,996 canonical float/Unicode fixtures matched Python.
- Root owns integration, deployment scripts, old bridge deletion and receipt SQL
  relocation. Worker delivery is not deployment approval or runtime acceptance.
