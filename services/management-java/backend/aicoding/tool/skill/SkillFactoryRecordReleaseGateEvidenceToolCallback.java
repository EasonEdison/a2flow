package dev.a2flow.management.aicoding.tool.skill;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import jakarta.annotation.Resource;

import org.apache.commons.lang3.StringUtils;
import org.springframework.ai.chat.model.ToolContext;
import org.springframework.ai.tool.ToolCallback;
import org.springframework.ai.tool.definition.ToolDefinition;
import org.springframework.stereotype.Component;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.agentcore.runtime.tool.ToolException;
import dev.a2flow.management.aicoding.tool.common
        .SkillFactoryToolPathResolver;
import dev.a2flow.management.release.AssetReleaseApplicationService;
import dev.a2flow.management.release.ReleaseAssetType;
import dev.a2flow.management.release
        .ReleaseModels.ReleaseReadinessCheck;
import dev.a2flow.management.release
        .ReleaseModels.ReleaseReadinessInspection;
import dev.a2flow.management.release
        .ReleaseModels.ReleaseValidationEvidence;
import dev.a2flow.management.release
        .ReleaseModels.ReleaseValidationWaiver;

import lombok.extern.slf4j.Slf4j;

/**
 * Skill 综合发布准出证据保存 Tool。
 *
 * <p>mounted Skill 只提交当前摘要、五项固定语义检查和可选调试豁免原因。本 Tool 会重新执行后端
 * 确定性巡检，校验摘要未变化，并由后端生成固定 checkCode、规则版本、可信运行审计和最终状态。
 * 它不接受模型指定资产身份，不修改 workspace，也不触发发布。
 */
@Component
@Slf4j
public class SkillFactoryRecordReleaseGateEvidenceToolCallback implements ToolCallback {

    public static final String TOOL_RECORD_RELEASE_GATE_EVIDENCE = "record_release_gate_evidence";

    private static final String FIELD_EXPECTED_DIGEST = "expectedDigest";
    private static final String FIELD_SUMMARY = "summary";
    private static final String FIELD_SEMANTIC_CHECKS = "semanticChecks";
    private static final String FIELD_DEBUG_RUN_WAIVER_REASON = "debugRunWaiverReason";
    private static final String FIELD_CODE = "code";
    private static final String FIELD_STATUS = "status";
    private static final String FIELD_FINDINGS = "findings";
    private static final String FIELD_RUN_ID = "runId";
    private static final String FIELD_MESSAGE_ID = "messageId";
    private static final String FIELD_USER_NAME = "userName";
    private static final String FIELD_ASSET_TYPE = "assetType";
    private static final String FIELD_ASSET_KEY = "assetKey";
    private static final String SOURCE_MODEL = "MODEL";
    private static final String CHECK_DESCRIPTION_QUALITY = "DESCRIPTION_QUALITY";
    private static final String CHECK_TRIGGER_QUALITY = "TRIGGER_QUALITY";
    private static final String CHECK_INTERNAL_CONSISTENCY = "INTERNAL_CONSISTENCY";
    private static final String CHECK_PEER_TRIGGER_CONFLICT = "PEER_TRIGGER_CONFLICT";
    private static final String CHECK_CONTENT_COMPLIANCE = "CONTENT_COMPLIANCE";
    private static final String ERROR_REQUIRED_SUFFIX = " is required";
    private static final String ERROR_DIGEST_CHANGED =
            "workspace digest changed after inspection, please inspect again";
    private static final String ERROR_SEMANTIC_CHECKS_REQUIRED =
            "semanticChecks must contain exactly the five required checks";
    private static final String ERROR_SEMANTIC_CHECK_INVALID =
            "semanticChecks item is invalid";
    private static final String ERROR_SEMANTIC_CHECK_DUPLICATE =
            "semanticChecks contains duplicate code";
    private static final String ERROR_SEMANTIC_STATUS_INVALID =
            "semantic check status must be PASSED or FAILED";
    private static final String ERROR_WAIVER_NOT_ALLOWED =
            "debugRunWaiverReason is allowed only when DEBUG_RUN_EVIDENCE is FAILED";
    private static final String ERROR_WAIVER_AUDIT_REQUIRED =
            "trusted messageId, runId and operator are required for debug evidence waiver";
    private static final int MAX_SUMMARY_LENGTH = 2000;
    private static final int MAX_WAIVER_REASON_LENGTH = 500;
    private static final int MAX_FINDINGS_PER_CHECK = 50;
    private static final Set<String> INPUT_FIELDS = Set.of(
            FIELD_EXPECTED_DIGEST, FIELD_SUMMARY, FIELD_SEMANTIC_CHECKS,
            FIELD_DEBUG_RUN_WAIVER_REASON);
    private static final Set<String> SEMANTIC_CHECK_FIELDS = Set.of(
            FIELD_CODE, FIELD_STATUS, FIELD_SUMMARY, FIELD_FINDINGS);
    private static final Set<String> REQUIRED_SEMANTIC_CODES = Set.of(
            CHECK_DESCRIPTION_QUALITY, CHECK_TRIGGER_QUALITY, CHECK_INTERNAL_CONSISTENCY,
            CHECK_PEER_TRIGGER_CONFLICT, CHECK_CONTENT_COMPLIANCE);
    private static final Set<String> PASSING_STATUSES = Set.of(
            SkillFactoryReleaseReadinessInspectionService.STATUS_PASSED,
            SkillFactoryReleaseReadinessInspectionService.STATUS_NOT_APPLICABLE,
            SkillFactoryReleaseReadinessInspectionService.STATUS_WAIVED);
    private static final String INPUT_SCHEMA = """
            {
              "type": "object",
              "properties": {
                "expectedDigest": {
                  "type": "string",
                  "description": "inspect_skill_release_readiness 返回的发布来源摘要，包含文件树和 Skill 描述"
                },
                "summary": {
                  "type": "string",
                  "maxLength": 2000,
                  "description": "给发布操作者查看的本次综合准出摘要"
                },
                "semanticChecks": {
                  "type": "array",
                  "minItems": 5,
                  "maxItems": 5,
                  "description": "mounted Skill 完成的五项固定语义检查",
                  "items": {
                    "type": "object",
                    "properties": {
                      "code": {
                        "type": "string",
                        "enum": [
                          "DESCRIPTION_QUALITY",
                          "TRIGGER_QUALITY",
                          "INTERNAL_CONSISTENCY",
                          "PEER_TRIGGER_CONFLICT",
                          "CONTENT_COMPLIANCE"
                        ]
                      },
                      "status": {"type": "string", "enum": ["PASSED", "FAILED"]},
                      "summary": {"type": "string"},
                      "findings": {
                        "type": "array",
                        "maxItems": 50,
                        "items": {"type": "object"}
                      }
                    },
                    "required": ["code", "status", "summary"],
                    "additionalProperties": false
                  }
                },
                "debugRunWaiverReason": {
                  "type": "string",
                  "maxLength": 500,
                  "description": "仅在用户看到缺少调试记录后明确要求跳过时填写"
                }
              },
              "required": ["expectedDigest", "summary", "semanticChecks"],
              "additionalProperties": false
            }
            """;

    @Resource
    private SkillFactoryReleaseReadinessInspectionService inspectionService;

    @Resource
    private AssetReleaseApplicationService assetReleaseApplicationService;

    @Override
    public ToolDefinition getToolDefinition() {
        return ToolDefinition.builder()
                .name(TOOL_RECORD_RELEASE_GATE_EVIDENCE)
                .description("Record one digest-bound aggregate Skill release-readiness result. "
                        + "The backend reruns deterministic checks, validates exactly five semantic checks, "
                        + "derives PASSED or FAILED, and audits the only allowed debug-evidence waiver. "
                        + "The current asset comes from trusted runtime context; this tool does not publish.")
                .inputSchema(INPUT_SCHEMA)
                .build();
    }

    @Override
    public String call(String toolInput) {
        return SkillFactoryDependencyToolSupport.rejectUntrustedCall();
    }

    /**
     * 重跑确定性检查、合并语义检查并保存唯一综合准出证据。
     */
    @Override
    public String call(String toolInput, ToolContext toolContext) {
        String workspaceId = SkillFactoryDependencyToolSupport.trustedWorkspaceId(toolContext);
        Map<String, String> trustedParams =
                SkillFactoryDependencyToolSupport.trustedPatchParams(toolContext);
        Map<String, Object> input = SkillFactoryDependencyToolSupport.parseObject(
                toolInput, new ArrayList<>(INPUT_FIELDS));
        String expectedDigest = required(input, FIELD_EXPECTED_DIGEST, Integer.MAX_VALUE);
        String summary = required(input, FIELD_SUMMARY, MAX_SUMMARY_LENGTH);
        List<ReleaseReadinessCheck> semanticChecks =
                semanticChecks(input.get(FIELD_SEMANTIC_CHECKS));
        Path workspacePath = SkillFactoryToolPathResolver.resolve(".", toolContext).path();
        String operator = StringUtils.defaultString(trustedParams.get(FIELD_USER_NAME));
        ReleaseReadinessInspection inspection =
                inspectionService.inspect(workspaceId, workspacePath, operator);
        if (!StringUtils.equals(expectedDigest, inspection.getWorkspaceDigest())) {
            throw new ToolException(ERROR_DIGEST_CHANGED, ToolException.ErrorCode.VALIDATION_ERROR);
        }

        List<ReleaseReadinessCheck> checks =
                copyChecks(inspection.getDeterministicChecks());
        List<ReleaseValidationWaiver> waivers = applyDebugWaiver(
                input, checks, trustedParams, operator);
        checks.addAll(semanticChecks);
        String aggregateStatus = aggregateStatus(checks);
        ReleaseValidationEvidence request = new ReleaseValidationEvidence()
                .setCheckCode(SkillFactoryReleaseReadinessInspectionService.AGGREGATE_CHECK_CODE)
                .setStatus(aggregateStatus)
                .setRuleVersion(SkillFactoryReleaseReadinessInspectionService.RULE_VERSION)
                .setCheckRunId(StringUtils.defaultString(trustedParams.get(FIELD_RUN_ID)))
                .setSummary(summary)
                .setFindings(failedFindings(checks))
                .setChecks(checks)
                .setWaivers(waivers);
        try {
            ReleaseValidationEvidence evidence =
                    assetReleaseApplicationService.recordTrustedToolValidationEvidence(
                    operator, ReleaseAssetType.SKILL, workspaceId, expectedDigest, request);
            Map<String, Object> result = new LinkedHashMap<>();
            result.put(FIELD_ASSET_TYPE, ReleaseAssetType.SKILL.name());
            result.put(FIELD_ASSET_KEY, workspaceId);
            result.put("evidence", evidence);
            log.info("Skill综合发布准出证据Tool完成, workspaceId:{}, status:{}, boundDigest:{}, "
                            + "checkCount:{}, waiverCount:{}, runId:{}, operator:{}",
                    workspaceId, evidence.getStatus(), evidence.getBoundDigest(),
                    evidence.getChecks().size(), evidence.getWaivers().size(),
                    evidence.getCheckRunId(), operator);
            return JsonSupport.toJSON(result);
        } catch (IllegalArgumentException | IllegalStateException e) {
            log.warn("Skill综合发布准出证据Tool校验失败, workspaceId:{}, expectedDigest:{}, "
                            + "runId:{}, operator:{}, error:{}",
                    workspaceId, expectedDigest, trustedParams.get(FIELD_RUN_ID), operator, e.getMessage());
            throw new ToolException(e.getMessage(), e, ToolException.ErrorCode.VALIDATION_ERROR);
        }
    }

    @SuppressWarnings("unchecked")
    private List<ReleaseReadinessCheck> semanticChecks(Object value) {
        if (!(value instanceof List<?>) || ((List<?>) value).size() != REQUIRED_SEMANTIC_CODES.size()) {
            throw invalid(ERROR_SEMANTIC_CHECKS_REQUIRED);
        }
        List<ReleaseReadinessCheck> checks = new ArrayList<>();
        Set<String> codes = new LinkedHashSet<>();
        for (Object item : (List<?>) value) {
            if (!(item instanceof Map<?, ?>)) {
                throw invalid(ERROR_SEMANTIC_CHECK_INVALID);
            }
            Map<String, Object> check = new LinkedHashMap<>((Map<String, Object>) item);
            if (!SEMANTIC_CHECK_FIELDS.containsAll(check.keySet())) {
                throw invalid(ERROR_SEMANTIC_CHECK_INVALID);
            }
            String code = required(check, FIELD_CODE, Integer.MAX_VALUE);
            if (!REQUIRED_SEMANTIC_CODES.contains(code)) {
                throw invalid(ERROR_SEMANTIC_CHECK_INVALID);
            }
            if (!codes.add(code)) {
                throw invalid(ERROR_SEMANTIC_CHECK_DUPLICATE);
            }
            String status = StringUtils.upperCase(required(check, FIELD_STATUS, Integer.MAX_VALUE));
            if (!StringUtils.equalsAny(status,
                    SkillFactoryReleaseReadinessInspectionService.STATUS_PASSED,
                    SkillFactoryReleaseReadinessInspectionService.STATUS_FAILED)) {
                throw invalid(ERROR_SEMANTIC_STATUS_INVALID);
            }
            checks.add(new ReleaseReadinessCheck()
                    .setCode(code)
                    .setStatus(status)
                    .setRequired(true)
                    .setSource(SOURCE_MODEL)
                    .setSummary(required(check, FIELD_SUMMARY, MAX_SUMMARY_LENGTH))
                    .setFindings(findings(check.get(FIELD_FINDINGS))));
        }
        if (!codes.equals(REQUIRED_SEMANTIC_CODES)) {
            throw invalid(ERROR_SEMANTIC_CHECKS_REQUIRED);
        }
        return checks;
    }

    private List<ReleaseValidationWaiver> applyDebugWaiver(Map<String, Object> input,
            List<ReleaseReadinessCheck> checks, Map<String, String> trustedParams, String operator) {
        String reason = string(input.get(FIELD_DEBUG_RUN_WAIVER_REASON));
        if (StringUtils.isBlank(reason)) {
            return new ArrayList<>();
        }
        if (reason.length() > MAX_WAIVER_REASON_LENGTH) {
            throw invalid(FIELD_DEBUG_RUN_WAIVER_REASON + " is too long");
        }
        ReleaseReadinessCheck debugCheck = checks.stream()
                .filter(check -> StringUtils.equals(check.getCode(),
                        SkillFactoryReleaseReadinessInspectionService.CHECK_DEBUG_RUN_EVIDENCE))
                .findFirst()
                .orElseThrow(() -> invalid(ERROR_WAIVER_NOT_ALLOWED));
        if (!StringUtils.equals(debugCheck.getStatus(),
                SkillFactoryReleaseReadinessInspectionService.STATUS_FAILED)) {
            throw invalid(ERROR_WAIVER_NOT_ALLOWED);
        }
        boolean waivable = debugCheck.getFindings() != null
                && debugCheck.getFindings().stream().anyMatch(finding -> finding != null
                && Boolean.TRUE.equals(finding.get(
                        SkillFactoryReleaseReadinessInspectionService.FINDING_WAIVABLE)));
        if (!waivable) {
            throw invalid(ERROR_WAIVER_NOT_ALLOWED);
        }
        String messageId = trustedParams.get(FIELD_MESSAGE_ID);
        String runId = trustedParams.get(FIELD_RUN_ID);
        if (StringUtils.isAnyBlank(messageId, runId, operator)) {
            throw new ToolException(ERROR_WAIVER_AUDIT_REQUIRED,
                    ToolException.ErrorCode.PERMISSION_DENIED);
        }
        debugCheck.setStatus(SkillFactoryReleaseReadinessInspectionService.STATUS_WAIVED)
                .setSummary("用户已明确豁免缺少预发调试记录")
                .setFindings(new ArrayList<>());
        List<ReleaseValidationWaiver> waivers = new ArrayList<>();
        waivers.add(new ReleaseValidationWaiver()
                .setCheckCode(SkillFactoryReleaseReadinessInspectionService.CHECK_DEBUG_RUN_EVIDENCE)
                .setReason(StringUtils.trim(reason))
                .setMessageId(messageId)
                .setRunId(runId)
                .setOperator(operator)
                .setWaivedAt(System.currentTimeMillis()));
        return waivers;
    }

    private String aggregateStatus(List<ReleaseReadinessCheck> checks) {
        boolean passed = checks.stream()
                .filter(check -> Boolean.TRUE.equals(check.getRequired()))
                .allMatch(check -> PASSING_STATUSES.contains(check.getStatus()));
        return passed ? SkillFactoryReleaseReadinessInspectionService.STATUS_PASSED
                : SkillFactoryReleaseReadinessInspectionService.STATUS_FAILED;
    }

    private List<Map<String, Object>> failedFindings(List<ReleaseReadinessCheck> checks) {
        List<Map<String, Object>> result = new ArrayList<>();
        for (ReleaseReadinessCheck check : checks) {
            if (!StringUtils.equals(check.getStatus(),
                    SkillFactoryReleaseReadinessInspectionService.STATUS_FAILED)) {
                continue;
            }
            if (check.getFindings() == null || check.getFindings().isEmpty()) {
                result.add(finding(
                        FIELD_CODE, check.getCode(),
                        FIELD_SUMMARY, check.getSummary()));
                continue;
            }
            for (Map<String, Object> item : check.getFindings()) {
                Map<String, Object> copy = item == null
                        ? new LinkedHashMap<>() : new LinkedHashMap<>(item);
                copy.put(FIELD_CODE, check.getCode());
                result.add(copy);
            }
        }
        return result;
    }

    private List<ReleaseReadinessCheck> copyChecks(List<ReleaseReadinessCheck> source) {
        List<ReleaseReadinessCheck> result = new ArrayList<>();
        if (source == null) {
            return result;
        }
        for (ReleaseReadinessCheck check : source) {
            result.add(new ReleaseReadinessCheck()
                    .setCode(check.getCode())
                    .setStatus(check.getStatus())
                    .setRequired(check.getRequired())
                    .setSource(check.getSource())
                    .setSummary(check.getSummary())
                    .setFindings(copyFindings(check.getFindings())));
        }
        return result;
    }

    private List<Map<String, Object>> copyFindings(List<Map<String, Object>> source) {
        List<Map<String, Object>> result = new ArrayList<>();
        if (source != null) {
            source.forEach(item -> result.add(item == null
                    ? new LinkedHashMap<>() : new LinkedHashMap<>(item)));
        }
        return result;
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> findings(Object value) {
        if (value == null) {
            return new ArrayList<>();
        }
        if (!(value instanceof List<?>)) {
            throw invalid(FIELD_FINDINGS + " must be an array");
        }
        List<?> items = (List<?>) value;
        if (items.size() > MAX_FINDINGS_PER_CHECK) {
            throw invalid(FIELD_FINDINGS + " exceeds " + MAX_FINDINGS_PER_CHECK);
        }
        List<Map<String, Object>> result = new ArrayList<>();
        for (Object item : items) {
            if (!(item instanceof Map<?, ?>)) {
                throw invalid(FIELD_FINDINGS + " item must be an object");
            }
            result.add(new LinkedHashMap<>((Map<String, Object>) item));
        }
        return result;
    }

    private String required(Map<String, Object> input, String field, int maxLength) {
        String value = StringUtils.trim(string(input.get(field)));
        if (StringUtils.isBlank(value)) {
            throw invalid(field + ERROR_REQUIRED_SUFFIX);
        }
        if (value.length() > maxLength) {
            throw invalid(field + " is too long");
        }
        return value;
    }

    private String string(Object value) {
        return value == null ? null : String.valueOf(value);
    }

    private Map<String, Object> finding(Object... values) {
        Map<String, Object> result = new LinkedHashMap<>();
        for (int index = 0; index + 1 < values.length; index += 2) {
            result.put(String.valueOf(values[index]), values[index + 1]);
        }
        return result;
    }

    private ToolException invalid(String message) {
        return new ToolException(message, ToolException.ErrorCode.INVALID_PARAMS);
    }
}
