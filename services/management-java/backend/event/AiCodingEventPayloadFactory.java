package dev.a2flow.management.event;

import java.util.List;
import java.util.Map;

import org.apache.commons.collections4.MapUtils;
import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Component;

import com.google.common.collect.Maps;
import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.aicoding.domain.SkillFactoryPatchApplyResult;
import dev.a2flow.management.aicoding.validation.ValidationReport;

import dev.a2flow.management.storage.db.entity.AgentObservationEventDO;

/**
 * SkillFactory AI Coding 事件 payload 工厂。
 *
 * <p>该工厂把 patch、observation 等后端事实规范化为统一的 AiCodingEventPayload。
 * 上游业务服务只传入真实领域对象，下游统一由 codec 序列化。它不执行审批、不写文件、不查询 DB。
 */
@SuppressWarnings("checkstyle:ParameterNumber")
@Component
public class AiCodingEventPayloadFactory {

    private static final String FIELD_CHANGED_FILES = "changedFiles";
    private static final String FIELD_RISK_ITEMS = "riskItems";
    private static final String FIELD_SUMMARY = "summary";
    private static final String FIELD_BASE_FILE_TREE_DIGEST = "baseFileTreeDigest";
    private static final String FIELD_FILE_TREE_DIGEST = "fileTreeDigest";
    private static final String FIELD_BASE_FILE_DIGEST_MAP = "baseFileDigestMap";
    private static final String FIELD_ERROR_CODE = "errorCode";
    private static final String FIELD_CONFLICT_FILES = "conflictFiles";

    private static final String FIELD_AUTO_APPLIED = "autoApplied";
    private static final String FIELD_ERROR_MSG = "errorMsg";
    private static final String FIELD_ACTION_CODE = "actionCode";
    private static final String FIELD_SURFACE_ID = "surfaceId";
    private static final String FIELD_SOURCE_COMPONENT_ID = "sourceComponentId";
    private static final String FIELD_A2UI = "a2ui";
    private static final String FIELD_TYPE = "type";
    private static final String FIELD_STAGE_ID = "stageId";
    private static final String FIELD_STATUS = "status";
    private static final String FIELD_TOOL_CALL_ID = "toolCallId";
    private static final String FIELD_TOOL_NAME = "toolName";
    private static final String FIELD_REPORT = "report";
    private static final String FIELD_TASK_ID = "taskId";
    private static final String FIELD_SKILL_CODE = "skillCode";
    private static final String FIELD_TEST_INPUT = "testInput";
    private static final String FIELD_PROTOCOL = "protocol";
    private static final String FIELD_ISSUE_COUNT = "issueCount";
    private static final String FIELD_PAYLOAD_TYPE = "payloadType";
    private static final String FIELD_VALID = "valid";
    private static final String FIELD_WORKSPACE_ID = "workspaceId";
    private static final String FIELD_SESSION_ID = "sessionId";
    private static final String FIELD_MESSAGE_ID = "messageId";
    private static final String FIELD_RUN_ID = "runId";
    private static final String FIELD_CONVERSATION_ID = "conversationId";
    private static final String FIELD_TRACE_ID = "traceId";
    private static final String STATUS_PENDING = "PENDING";
    private static final String STATUS_NOT_REQUIRED = "NOT_REQUIRED";
    private static final String DECISION_APPROVE = "approve";
    private static final String DECISION_REJECT = "reject";
    private static final String RISK_LEVEL_MEDIUM = "MEDIUM";

    /**
     * 生成 patch 草稿事件。
     */
    public AiCodingEventPayload patchProposed(String workspaceId, String sessionId, String patchId,
            String traceId, Map<String, Object> patch) {
        Map<String, Object> content = Maps.newHashMap();
        content.put(FIELD_SUMMARY, MapUtils.getString(patch, FIELD_SUMMARY));
        content.put(FIELD_BASE_FILE_TREE_DIGEST, patch.get(FIELD_BASE_FILE_TREE_DIGEST));
        content.put(FIELD_BASE_FILE_DIGEST_MAP, patch.get(FIELD_BASE_FILE_DIGEST_MAP));
        content.put(FIELD_CHANGED_FILES, patch.get(FIELD_CHANGED_FILES));
        content.put(FIELD_RISK_ITEMS, patch.get(FIELD_RISK_ITEMS));

        content.put(FIELD_AUTO_APPLIED, false);
        return base(AiCodingEventCode.PATCH_PROPOSED, AiCodingEventCategory.PATCH, workspaceId, sessionId,
                patchId, traceId)
                .setTitle("文件变更草稿")
                .setSuccess(true)
                .setContent(content);
    }

    /**
     * 生成 patch 确认冲突事件。
     */
    public AiCodingEventPayload patchConflict(SkillFactoryPatchApplyResult result, String sessionId, String traceId) {
        Map<String, Object> content = Maps.newHashMap();
        content.put(FIELD_ERROR_MSG, result.getErrorMsg());
        content.put(FIELD_ERROR_CODE, result.getErrorCode());
        content.put(FIELD_BASE_FILE_TREE_DIGEST, result.getBaseFileTreeDigest());
        content.put(FIELD_FILE_TREE_DIGEST, result.getFileTreeDigest());
        content.put(FIELD_CONFLICT_FILES, result.getConflictFiles());
        return base(AiCodingEventCode.PATCH_CONFLICT, AiCodingEventCategory.PATCH, result.getWorkspaceId(),
                sessionId, result.getPatchId(), traceId)
                .setTitle("Patch 确认冲突")
                .setSuccess(false)
                .setErrorMsg(result.getErrorMsg())
                .setContent(content);
    }

    /**
     * 生成 patch 应用事件。
     */
    public AiCodingEventPayload patchApplied(SkillFactoryPatchApplyResult result, String sessionId, String traceId,
            AgentObservationEventDO observationDO, boolean autoApplied) {
        Map<String, Object> content = Maps.newHashMap();
        content.put(FIELD_FILE_TREE_DIGEST, result.getFileTreeDigest());
        content.put(FIELD_CHANGED_FILES, result.getChangedFiles());
        content.put(FIELD_AUTO_APPLIED, autoApplied);
        return base(AiCodingEventCode.PATCH_APPLIED, AiCodingEventCategory.PATCH, result.getWorkspaceId(),
                sessionId, result.getPatchId(), traceId)
                .setTitle("Patch 已应用")
                .setSuccess(result.isSuccess())
                .setErrorMsg(result.getErrorMsg())
                .setObservationId(result.getObservationId())
                .setContent(content)
                .setObservation(observationInfo(observationDO));
    }

    /**
     * 生成 patch 丢弃事件。
     */
    public AiCodingEventPayload patchDiscarded(SkillFactoryPatchApplyResult result, String sessionId, String traceId,
            AgentObservationEventDO observationDO) {
        Map<String, Object> content = Maps.newHashMap();
        content.put(FIELD_FILE_TREE_DIGEST, result.getFileTreeDigest());
        content.put(FIELD_CHANGED_FILES, result.getChangedFiles());
        return base(AiCodingEventCode.PATCH_DISCARDED, AiCodingEventCategory.PATCH, result.getWorkspaceId(),
                sessionId, result.getPatchId(), traceId)
                .setTitle("Patch 已丢弃")
                .setSuccess(result.isSuccess())
                .setErrorMsg(result.getErrorMsg())
                .setObservationId(result.getObservationId())
                .setContent(content)
                .setObservation(observationInfo(observationDO));
    }

    /**
     * 生成失败事件。
     */
    public AiCodingEventPayload failed(String workspaceId, String sessionId, String patchId, String traceId,
            String errorMsg) {
        Map<String, Object> content = Maps.newHashMap();
        content.put(FIELD_ERROR_MSG, StringUtils.defaultString(errorMsg));
        return base(AiCodingEventCode.FAILED, AiCodingEventCategory.ERROR, workspaceId, sessionId, patchId, traceId)
                .setTitle("AI Coding 执行失败")
                .setSuccess(false)
                .setErrorMsg(StringUtils.defaultString(errorMsg))
                .setContent(content);
    }

    /**
     * 生成 M 端创作态 A2UI 业务卡片事件。
     */
    public AiCodingEventPayload a2uiMessage(String workspaceId, String sessionId, String messageId, String runId,
            String conversationId, String traceId, String surfaceId, Map<String, Object> a2uiPayload) {
        Map<String, Object> content = Maps.newHashMap();
        content.put(FIELD_A2UI, a2uiPayload);
        content.putAll(a2uiPayload);
        return base(AiCodingEventCode.A2UI_MESSAGE, AiCodingEventCategory.AUTHORING_UI, workspaceId, sessionId,
                null, traceId)
                .setTitle("业务确认卡片")
                .setSuccess(true)
                .setMessageId(messageId)
                .setRunId(runId)
                .setThreadId(sessionId)
                .setConversationId(conversationId)
                .setSurfaceId(surfaceId)
                .setContent(content);
    }

    /**
     * 生成 M 端业务 action 写入 observation 后的事件。
     */
    public AiCodingEventPayload authoringObservation(String workspaceId, String sessionId, String messageId,
            String runId, String conversationId, String traceId, String surfaceId, String actionCode,
            String sourceComponentId, AgentObservationEventDO observationDO) {
        Map<String, Object> content = Maps.newHashMap();
        content.put(FIELD_ACTION_CODE, StringUtils.defaultString(actionCode));
        content.put(FIELD_SURFACE_ID, StringUtils.defaultString(surfaceId));
        content.put(FIELD_SOURCE_COMPONENT_ID, StringUtils.defaultString(sourceComponentId));
        if (observationDO != null) {
            content.put(FIELD_SUMMARY, observationDO.getSummary());
        }
        return base(AiCodingEventCode.AUTHORING_OBSERVATION, AiCodingEventCategory.OBSERVATION, workspaceId,
                sessionId, null, traceId)
                .setTitle("业务动作已记录")
                .setSuccess(true)
                .setObservationId(observationDO == null ? null : observationDO.getObservationId())
                .setMessageId(messageId)
                .setRunId(runId)
                .setThreadId(sessionId)
                .setConversationId(conversationId)
                .setSurfaceId(surfaceId)
                .setContent(content)
                .setObservation(observationInfo(observationDO));
    }

    /**
     * 生成结构化 Authoring 草稿快照或增量修改建议。
     *
     * <p>上游 Tool 负责校验 domain、revision 和草稿内容；本方法只统一补充流式事件元数据，
     * 不保存草稿，也不替操作者确认修改。
     */
    public AiCodingEventPayload authoringDraftChange(Map<String, String> context, String payloadType,
            Map<String, Object> draftChange) {
        Map<String, Object> content = Maps.newLinkedHashMap();
        content.put(FIELD_PAYLOAD_TYPE, StringUtils.defaultString(payloadType));
        if (MapUtils.isNotEmpty(draftChange)) {
            content.putAll(draftChange);
        }
        return base(AiCodingEventCode.AUTHORING_DRAFT_CHANGE, AiCodingEventCategory.AUTHORING_DRAFT,
                context.get(FIELD_WORKSPACE_ID), context.get(FIELD_SESSION_ID), null, context.get(FIELD_TRACE_ID))
                .setTitle("AI 草稿修改建议")
                .setSuccess(true)
                .setMessageId(context.get(FIELD_MESSAGE_ID))
                .setRunId(context.get(FIELD_RUN_ID))
                .setThreadId(context.get(FIELD_SESSION_ID))
                .setConversationId(context.get(FIELD_CONVERSATION_ID))
                .setContent(content);
    }

    /**
     * 生成能力草稿静态校验报告事件。
     */
    public AiCodingEventPayload capabilityDraftValidated(Map<String, String> context, String payloadType,
            Map<String, Object> validationResult) {
        Map<String, Object> content = Maps.newLinkedHashMap();
        content.put(FIELD_PAYLOAD_TYPE, StringUtils.defaultString(payloadType));
        if (MapUtils.isNotEmpty(validationResult)) {
            content.putAll(validationResult);
        }
        return base(AiCodingEventCode.CAPABILITY_DRAFT_VALIDATED, AiCodingEventCategory.AUTHORING_DRAFT,
                context.get(FIELD_WORKSPACE_ID), context.get(FIELD_SESSION_ID), null, context.get(FIELD_TRACE_ID))
                .setTitle("能力草稿静态校验")
                .setSuccess(MapUtils.getBoolean(content, FIELD_VALID, false))
                .setMessageId(context.get(FIELD_MESSAGE_ID))
                .setRunId(context.get(FIELD_RUN_ID))
                .setThreadId(context.get(FIELD_SESSION_ID))
                .setConversationId(context.get(FIELD_CONVERSATION_ID))
                .setContent(content);
    }

    /**
     * 生成 workspace 外部变更 observation 事件。
     */
    public AiCodingEventPayload workspaceChangedObservation(String workspaceId, String sessionId, String messageId,
            String runId, String conversationId, String traceId, AgentObservationEventDO observationDO) {
        Map<String, Object> content = Maps.newHashMap();
        if (observationDO != null) {
            content.put(FIELD_SUMMARY, observationDO.getSummary());
        }
        return base(AiCodingEventCode.WORKSPACE_CHANGED_OBSERVATION, AiCodingEventCategory.OBSERVATION, workspaceId,
                sessionId, null, traceId)
                .setTitle("工作区文件已变化")
                .setSuccess(true)
                .setObservationId(observationDO == null ? null : observationDO.getObservationId())
                .setMessageId(messageId)
                .setRunId(runId)
                .setThreadId(sessionId)
                .setConversationId(conversationId)
                .setContent(content)
                .setObservation(observationInfo(observationDO));
    }

    /**
     * 生成 AG-UI-like 执行过程事件。
     *
     * <p>该事件只表达 AI Coding 引擎真实执行状态，例如 run、step、tool activity 和错误。
     * 业务交互卡片仍由 A2UI_MESSAGE 承接，文件变更仍由 patch 事件承接。
     */
    public AiCodingEventPayload agUiEvent(String workspaceId, String sessionId, String messageId, String runId,
            String conversationId, String traceId, String eventType, String stageId, String title,
            String summary, String status, String toolCallId, String toolName, Boolean success,
            Map<String, Object> extraContent) {
        Map<String, Object> content = Maps.newHashMap();
        content.put(FIELD_TYPE, StringUtils.defaultString(eventType));
        content.put(FIELD_STAGE_ID, StringUtils.defaultString(stageId));
        content.put(FIELD_SUMMARY, StringUtils.defaultString(summary));
        content.put(FIELD_STATUS, StringUtils.defaultString(status));
        content.put(FIELD_TOOL_CALL_ID, StringUtils.defaultString(toolCallId));
        content.put(FIELD_TOOL_NAME, StringUtils.defaultString(toolName));
        if (MapUtils.isNotEmpty(extraContent)) {
            content.putAll(extraContent);
        }
        return base(AiCodingEventCode.AG_UI_EVENT, AiCodingEventCategory.EXECUTION_TRACE, workspaceId,
                sessionId, null, traceId)
                .setTitle(StringUtils.defaultString(title))
                .setSuccess(success)
                .setMessageId(messageId)
                .setRunId(runId)
                .setThreadId(sessionId)
                .setConversationId(conversationId)
                .setContent(content);
    }

    /**
     * 生成动态运行验证报告事件。
     */
    public AiCodingEventPayload validationReport(String workspaceId, String sessionId, String messageId,
            String runId, String conversationId, String traceId, ValidationReport report) {
        Map<String, Object> content = Maps.newHashMap();
        content.put(FIELD_REPORT, reportToMap(report));
        content.put(FIELD_TASK_ID, report == null ? StringUtils.EMPTY : report.getTaskId());
        content.put(FIELD_SKILL_CODE, report == null ? StringUtils.EMPTY : report.getSkillCode());
        content.put(FIELD_TEST_INPUT, report == null ? StringUtils.EMPTY : report.getTestInput());
        content.put(FIELD_STATUS, report == null ? StringUtils.EMPTY : report.getStatus());
        content.put(FIELD_PROTOCOL, report == null ? null : report.getProtocol());
        content.put(FIELD_ISSUE_COUNT, report == null ? 0 : report.getIssues().size());
        return base(AiCodingEventCode.VALIDATION_REPORT_CREATED, AiCodingEventCategory.VALIDATION, workspaceId,
                sessionId, null, traceId)
                .setTitle("运行验证报告")
                .setSuccess(report != null && !StringUtils.equals(ValidationReport.STATUS_FAILED,
                        report.getStatus()))
                .setMessageId(messageId)
                .setRunId(runId)
                .setThreadId(sessionId)
                .setConversationId(conversationId)
                .setContent(content);
    }

    private AiCodingEventPayload base(AiCodingEventCode eventCode, AiCodingEventCategory category,
            String workspaceId, String sessionId, String patchId, String traceId) {
        return new AiCodingEventPayload()
                .setSchemaVersion(AiCodingEventPayload.SCHEMA_VERSION)
                .setEventCode(eventCode.getCode())
                .setEventType(eventCode.getCode())
                .setCategory(category.getCode())
                .setWorkspaceId(workspaceId)
                .setSessionId(sessionId)
                .setPatchId(patchId)
                .setTraceId(traceId)
                .setTimestamp(System.currentTimeMillis());
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> reportToMap(ValidationReport report) {
        if (report == null) {
            return Maps.newHashMap();
        }
        try {
            Map<String, Object> result = JsonSupport.fromJson(JsonSupport.toJSON(report));
            return result == null ? Maps.newHashMap() : result;
        } catch (Exception e) {
            Map<String, Object> result = Maps.newHashMap();
            result.put(FIELD_TASK_ID, report.getTaskId());
            result.put(FIELD_STATUS, report.getStatus());
            result.put(FIELD_SKILL_CODE, report.getSkillCode());
            result.put(FIELD_TEST_INPUT, report.getTestInput());
            result.put(FIELD_PROTOCOL, report.getProtocol());
            result.put(FIELD_ISSUE_COUNT, report.getIssues().size());
            return result;
        }
    }

    private AiCodingEventPayload.ObservationInfo observationInfo(AgentObservationEventDO observationDO) {
        if (observationDO == null) {
            return null;
        }
        return new AiCodingEventPayload.ObservationInfo()
                .setObservationId(observationDO.getObservationId())
                .setObservationType(observationDO.getObservationType())
                .setSource(observationDO.getSource())
                .setSummary(observationDO.getSummary())
                .setVisibleToModel(Integer.valueOf(1).equals(observationDO.getVisibleToModel()))
                .setStateDelta(parseStateDelta(observationDO.getStateDeltaJson()));
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> parseStateDelta(String stateDeltaJson) {
        if (StringUtils.isBlank(stateDeltaJson)) {
            return null;
        }
        return JsonSupport.fromJSON(stateDeltaJson, Map.class);
    }
}
