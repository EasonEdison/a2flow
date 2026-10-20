# Regression evidence

Baseline: origin/main `5c907ee4054a83a2ea9f6cf831659dd1312de20b`.

Read-only pre-change inventory: all 20 stored BUILD_ARTIFACT rows (a superset of published packages); compressed total 24,613 bytes, largest compressed package 3,624 bytes. ZIP directory metadata: maximum expanded archive 8,022 bytes, maximum individual entry 8,022 bytes, maximum entry count 1. No asset names, content or credentials are retained. The default 32 MiB / 8 MiB / 2000 budgets do not exclude this inventory.

Local JDK 17 targeted compilation: modified artifact/workspace/validation classes against the existing local management dependency/class output; compile succeeded. Standalone PackageRestoreGuardProbe uses only synthetic temporary files and low extraction budgets; no database, HTTP, login or business operation. Final output and repository checks are recorded in readiness.md.

Compatibility checks: no tracked current frontend/CLI calls PACKAGE_VERSION_RESTORE. Existing dispatcher performs session/asset authorization before method dispatch; typed SkillFactoryValidationException preserves explicit errorCode/fieldPath through the established business envelope. Build/Version reset and relation restoration sources are unchanged. Existing immutable artifact ownership/digest checks remain in DatabaseArtifactService/PostgresArtifactRepository and SkillPreprodBuildRestoreService.

Root owns full candidate compilation and real published-package reset acceptance. This branch does not deploy or touch production accounts/assets. No claim is made of a global disk quota, business transaction atomicity beyond the existing implementation, or broad sandboxing.
