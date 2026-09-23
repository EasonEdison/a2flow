package dev.a2flow.management.aicoding.tool.skill;

import java.nio.file.Path;
import dev.a2flow.management.release.ReleaseModels.ReleaseReadinessInspection;
import dev.a2flow.management.release.SkillReleaseAssetAdapter;

/** Read-only evidence inspection port. No successful result exists without a configured implementation. */
public interface SkillFactoryReleaseReadinessInspectionService {
    String AGGREGATE_CHECK_CODE = SkillReleaseAssetAdapter.VALIDATION_SKILL_RELEASE_READINESS;
    String RULE_VERSION = SkillReleaseAssetAdapter.SKILL_RELEASE_READINESS_RULE_VERSION;
    String STATUS_PASSED = "PASSED";
    String STATUS_FAILED = "FAILED";
    String STATUS_NOT_APPLICABLE = "NOT_APPLICABLE";
    String STATUS_WAIVED = "WAIVED";
    String CHECK_DEBUG_RUN_EVIDENCE = "DEBUG_RUN_EVIDENCE";
    String FINDING_WAIVABLE = "waivable";
    ReleaseReadinessInspection inspect(String workspaceId, Path workspacePath, String operator);
}
