package dev.a2flow.management.event;

import java.util.Map;
import java.util.UUID;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Component;

import dev.a2flow.management.support.JsonSupport;

/**
 * SkillFactory AI Coding 结构化流式事件工厂。
 *
 * <p>该工厂只创建 SkillFactory 内部的 `AiCodingStreamEvent` 子类，不直接返回公共运行时事件。
 * 模型内容必须通过 `AiCodingModelContentEvent` 携带不同类型的
 * `AiCodingModelContentBlock`；工具结果、patch、审批、业务交互、observation、usage、
 * error 和执行 trace 必须通过 `AiCodingRuntimePayloadEvent` 携带 typed payload。
 */
@SuppressWarnings({"checkstyle:ParameterNumber", "checkstyle:MagicNumber"})
@Component
public class AiCodingStreamEventFactory {

    public static final String EVENT_RUN_STARTED = "RUN_STARTED";
    public static final String EVENT_MODEL_CONTENT_DELTA = "MODEL_CONTENT_DELTA";
    public static final String EVENT_TOOL_CALL_STARTED = "TOOL_CALL_STARTED";
    public static final String EVENT_TOOL_CALL_FINISHED = "TOOL_CALL_FINISHED";
    public static final String EVENT_ARTIFACT_CREATED = "ARTIFACT_CREATED";
    public static final String EVENT_BUSINESS_INTERACTION_CREATED = "BUSINESS_INTERACTION_CREATED";

    public static final String EVENT_OBSERVATION_CREATED = "OBSERVATION_CREATED";
    public static final String EVENT_USAGE = "USAGE";
    public static final String EVENT_ERROR = "ERROR";
    public static final String EVENT_RUN_COMPLETED = "RUN_COMPLETED";
    public static final String EVENT_RUN_FAILED = "RUN_FAILED";
    public static final String EVENT_RUN_CANCELLED = "RUN_CANCELLED";
    public static final String EVENT_EXECUTION_TRACE = "AG_UI_EVENT";
    public static final String EVENT_VALIDATION_TASK_STARTED = "VALIDATION_TASK_STARTED";
    public static final String EVENT_VALIDATION_REPORT_CREATED = "VALIDATION_REPORT_CREATED";

    public static final String SOURCE_MODEL = "MODEL";
    public static final String SOURCE_TOOL = "TOOL";
    public static final String SOURCE_RUNTIME = "RUNTIME";
    public static final String SOURCE_SYSTEM = "SYSTEM";

    public static final String PAYLOAD_TOOL_RESULT = "TOOL_RESULT";
    public static final String PAYLOAD_PATCH_ARTIFACT = "PATCH_ARTIFACT";

    public static final String PAYLOAD_BUSINESS_INTERACTION = "BUSINESS_INTERACTION";
    public static final String PAYLOAD_OBSERVATION = "OBSERVATION";
    public static final String PAYLOAD_USAGE = "USAGE";
    public static final String PAYLOAD_ERROR = "ERROR";
    public static final String PAYLOAD_EXECUTION_TRACE = "EXECUTION_TRACE";
    public static final String PAYLOAD_VALIDATION_TASK = "VALIDATION_TASK";
    public static final String PAYLOAD_VALIDATION_REPORT = "VALIDATION_REPORT";
    public static final String PAYLOAD_COMPONENT_ASSET_DRAFT = "COMPONENT_ASSET_DRAFT";
    public static final String PAYLOAD_COMPONENT_ASSET_VALIDATION_RESULT = "COMPONENT_ASSET_VALIDATION_RESULT";
    public static final String PAYLOAD_COMPONENT_ASSET_PREVIEW_RESULT = "COMPONENT_ASSET_PREVIEW_RESULT";
    public static final String PAYLOAD_COMPONENT_ASSET_SAVE_PREPARE = "COMPONENT_ASSET_SAVE_PREPARE";

    private static final String FIELD_MESSAGE_ID = "messageId";
    private static final String FIELD_RUN_ID = "runId";
    private static final String FIELD_SESSION_ID = "sessionId";
    private static final String FIELD_CONVERSATION_ID = "conversationId";
    private static final String FIELD_TRACE_ID = "traceId";
    private static final String FIELD_TOOL_CALL_ID = "toolCallId";
    private static final String FIELD_TOOL_NAME = "toolName";
    private static final String FIELD_RESULT = "result";
    private static final String FIELD_SUCCESS = "success";
    private static final String FIELD_ERROR_MSG = "errorMsg";
    private static final String FIELD_TOKEN_COUNT = "tokenCount";
    private static final String FIELD_ENTER_TOKEN_COUNT = "enterTokenCount";
    private static final String FIELD_OUTPUT_TOKEN_COUNT = "outputTokenCount";
    private static final String EMPTY_PAYLOAD_TYPE = "";
    private static final String EMPTY_PAYLOAD_JSON = "";

    /**
     * AI Coding run 开始。
     */
    public AiCodingStreamEvent runStarted(long agentId, Map<String, String> params) {
        return runtimePayload(agentId, params, EVENT_RUN_STARTED, SOURCE_SYSTEM, EMPTY_PAYLOAD_TYPE,
                EMPTY_PAYLOAD_JSON, "AI Coding 开始处理请求", new AiCodingRuntimePayload().setToolSuccess(true));
    }

    /**
     * AI Coding run 结束。
     */
    public AiCodingStreamEvent runCompleted(long agentId, Map<String, String> params) {
        return runtimePayload(agentId, params, EVENT_RUN_COMPLETED, SOURCE_SYSTEM, EMPTY_PAYLOAD_TYPE,
                EMPTY_PAYLOAD_JSON, StringUtils.EMPTY,
                new AiCodingRuntimePayload().setToolSuccess(true));
    }

    /**
     * AI Coding run 失败终态。
     */
    public AiCodingStreamEvent runFailed(long agentId, Map<String, String> params, String errorMsg) {
        Map<String, Object> payload = Map.of(FIELD_ERROR_MSG, StringUtils.defaultString(errorMsg));
        return runtimePayload(agentId, params, EVENT_RUN_FAILED, SOURCE_SYSTEM, PAYLOAD_ERROR,
                JsonSupport.toJSON(payload), StringUtils.defaultString(errorMsg),
                new AiCodingRuntimePayload().setToolSuccess(false));
    }

    /**
     * AI Coding run 取消终态。
     */
    public AiCodingStreamEvent runCancelled(long agentId, Map<String, String> params) {
        return runtimePayload(agentId, params, EVENT_RUN_CANCELLED, SOURCE_SYSTEM, EMPTY_PAYLOAD_TYPE,
                EMPTY_PAYLOAD_JSON, "本轮 AI Coding 已停止",
                new AiCodingRuntimePayload().setToolSuccess(false));
    }

    /**
     * 模型最终正文增量。
     */
    public AiCodingStreamEvent modelTextDelta(long agentId, Map<String, String> params, String text) {
        String blockId = blockId(AiCodingModelContentBlock.TYPE_TEXT, params);
        AiCodingTextBlock block = (AiCodingTextBlock) new AiCodingTextBlock(StringUtils.defaultString(text))
                .setBlockId(blockId);
        return new AiCodingModelContentEvent(baseMetadata(agentId, params, EVENT_MODEL_CONTENT_DELTA, SOURCE_MODEL)
                .setContent(StringUtils.defaultString(text)), blockId, block);
    }

    /**
     * 可展示的模型 thinking 摘要。
     */
    public AiCodingStreamEvent modelThinkingDelta(long agentId, Map<String, String> params, String text) {
        return modelThinkingDelta(agentId, params, StringUtils.EMPTY, text);
    }

    /**
     * 可展示的模型 thinking 摘要，按一次模型迭代的稳定标识聚合。
     */
    public AiCodingStreamEvent modelThinkingDelta(long agentId, Map<String, String> params, String blockSuffix,
            String text) {
        String blockId = blockId(AiCodingModelContentBlock.TYPE_THINKING, params, blockSuffix);
        AiCodingThinkingBlock block = (AiCodingThinkingBlock) new AiCodingThinkingBlock(StringUtils.defaultString(text))
                .setBlockId(blockId);
        return new AiCodingModelContentEvent(baseMetadata(agentId, params, EVENT_MODEL_CONTENT_DELTA, SOURCE_MODEL)
                .setContent(StringUtils.defaultString(text)), blockId, block);
    }

    /**
     * 模型发起工具调用。
     */
    public AiCodingStreamEvent toolCallStarted(long agentId, Map<String, String> params, String toolCallId,
            String toolName, String toolArgs) {
        String blockId = blockId(AiCodingModelContentBlock.TYPE_TOOL_USE, params, toolCallId);
        AiCodingToolUseBlock block = (AiCodingToolUseBlock) new AiCodingToolUseBlock(
                StringUtils.defaultString(toolCallId), StringUtils.defaultString(toolName), parseJsonOrText(toolArgs))
                .setBlockId(blockId);
        return new AiCodingModelContentEvent(baseMetadata(agentId, params, EVENT_TOOL_CALL_STARTED, SOURCE_MODEL)
                .setContent("模型请求调用工具 " + StringUtils.defaultString(toolName)), blockId, block);
    }

    /**
     * 工具执行完成。
     */
    public AiCodingStreamEvent toolCallFinished(long agentId, Map<String, String> params, String toolCallId,
            String toolName, String result, boolean success, boolean hasKnowledge) {
        Map<String, Object> payload = Map.of(
                FIELD_TOOL_CALL_ID, StringUtils.defaultString(toolCallId),
                FIELD_TOOL_NAME, StringUtils.defaultString(toolName),
                FIELD_RESULT, StringUtils.defaultString(result),
                FIELD_SUCCESS, success);
        return runtimePayload(agentId, params, EVENT_TOOL_CALL_FINISHED, SOURCE_TOOL, PAYLOAD_TOOL_RESULT,
                JsonSupport.toJSON(payload), StringUtils.abbreviate(StringUtils.defaultString(result), 300),
                new AiCodingRuntimePayload()
                        .setToolCallId(StringUtils.defaultString(toolCallId))
                        .setToolName(StringUtils.defaultString(toolName))
                        .setToolSuccess(success)
                        .setHasKnowledge(hasKnowledge));
    }

    /**
     * patch / diff 等文件变更产物。
     */
    public AiCodingStreamEvent artifactCreated(long agentId, Map<String, String> params, String toolCallId,
            String toolName, String payloadJson, boolean success) {
        return runtimePayload(agentId, params, EVENT_ARTIFACT_CREATED, SOURCE_RUNTIME, PAYLOAD_PATCH_ARTIFACT,
                payloadJson, "文件变更产物已生成", toolRuntimePayload(toolCallId, toolName, success));
    }

    /**
     * 非文件类运行态产物，例如组件中心 AI 创建出的资产草稿、校验结果和保存参数。
     */
    public AiCodingStreamEvent runtimeArtifactCreated(long agentId, Map<String, String> params, String toolCallId,
            String toolName, String payloadType, String payloadJson, String content, boolean success) {
        return runtimePayload(agentId, params, EVENT_ARTIFACT_CREATED, SOURCE_RUNTIME, payloadType,
                payloadJson, StringUtils.defaultIfBlank(content, "运行态产物已生成"),
                toolRuntimePayload(toolCallId, toolName, success));
    }

    /**
     * M 端业务交互卡片。
     */
    public AiCodingStreamEvent businessInteractionCreated(long agentId, Map<String, String> params,
            String toolCallId, String toolName, String payloadJson) {
        return runtimePayload(agentId, params, EVENT_BUSINESS_INTERACTION_CREATED, SOURCE_RUNTIME,
                PAYLOAD_BUSINESS_INTERACTION, payloadJson, "业务交互卡片已生成",
                toolRuntimePayload(toolCallId, toolName, true));
    }

    /**
     * Observation 已写入。
     */
    public AiCodingStreamEvent observationCreated(long agentId, Map<String, String> params, String toolCallId,
            String toolName, String payloadJson) {
        return runtimePayload(agentId, params, EVENT_OBSERVATION_CREATED, SOURCE_RUNTIME, PAYLOAD_OBSERVATION,
                payloadJson, "业务动作已记录为 Observation", toolRuntimePayload(toolCallId, toolName, true));
    }

    /**
     * 普通 handler 完成后的领域结果。
     *
     * <p>该事件不表示 Tool 调用或模型 run。成功结果作为可回放的领域产物写入 Authoring 历史；
     * 失败结果保留为诊断错误，避免把失败 Patch 动作伪装成待审阅产物。
     */
    public AiCodingStreamEvent controlDomainResult(long agentId, Map<String, String> params, String payloadType,
            String payloadJson, String content, boolean success) {
        String eventType = success ? EVENT_ARTIFACT_CREATED : EVENT_ERROR;
        String resultPayloadType = success ? payloadType : PAYLOAD_ERROR;
        return runtimePayload(agentId, params, eventType, SOURCE_RUNTIME, resultPayloadType,
                payloadJson, content, new AiCodingRuntimePayload().setToolSuccess(success));
    }

    /**
     * 执行过程 trace 事件。
     */
    public AiCodingStreamEvent executionTrace(long agentId, Map<String, String> params, String toolCallId,
            String toolName, String payloadJson, boolean success) {
        return runtimePayload(agentId, params, EVENT_EXECUTION_TRACE, SOURCE_RUNTIME, PAYLOAD_EXECUTION_TRACE,
                payloadJson, "执行过程已更新", toolRuntimePayload(toolCallId, toolName, success));
    }

    /**
     * 动态运行验证任务开始。
     */
    public AiCodingStreamEvent validationTaskStarted(long agentId, Map<String, String> params, String toolCallId,
            String toolName, String payloadJson) {
        return runtimePayload(agentId, params, EVENT_VALIDATION_TASK_STARTED, SOURCE_RUNTIME, PAYLOAD_VALIDATION_TASK,
                payloadJson, "运行验证任务已启动", toolRuntimePayload(toolCallId, toolName, true));
    }

    /**
     * 动态运行验证报告已生成。
     */
    public AiCodingStreamEvent validationReportCreated(long agentId, Map<String, String> params, String toolCallId,
            String toolName, String payloadJson, boolean success) {
        return runtimePayload(agentId, params, EVENT_VALIDATION_REPORT_CREATED, SOURCE_RUNTIME,
                PAYLOAD_VALIDATION_REPORT, payloadJson, "运行验证报告已生成",
                toolRuntimePayload(toolCallId, toolName, success));
    }

    /**
     * usage 事件。
     */
    public AiCodingStreamEvent usage(long agentId, Map<String, String> params, int tokenCount, int enterTokenCount,
            int outputTokenCount) {
        Map<String, Object> payload = Map.of(
                FIELD_TOKEN_COUNT, tokenCount,
                FIELD_ENTER_TOKEN_COUNT, enterTokenCount,
                FIELD_OUTPUT_TOKEN_COUNT, outputTokenCount);
        AiCodingRuntimePayload runtimePayload = new AiCodingRuntimePayload()
                .setPayloadType(PAYLOAD_USAGE)
                .setPayloadJson(JsonSupport.toJSON(payload))
                .setTokenCount(tokenCount)
                .setEnterTokenCount(enterTokenCount)
                .setOutputTokenCount(outputTokenCount)
                .setToolSuccess(true);
        return new AiCodingRuntimePayloadEvent(baseMetadata(agentId, params, EVENT_USAGE, SOURCE_RUNTIME)
                .setContent(StringUtils.EMPTY), runtimePayload);
    }

    /**
     * 结构化诊断错误事件。
     *
     * <p>该事件只描述执行过程中的错误，不代表 run 已经结束；最终状态必须由
     * RUN_COMPLETED、RUN_FAILED 或 RUN_CANCELLED 三种终态事件之一表达。
     */
    public AiCodingStreamEvent error(long agentId, Map<String, String> params, String errorMsg) {
        Map<String, Object> payload = Map.of(FIELD_ERROR_MSG, StringUtils.defaultString(errorMsg));
        return runtimePayload(agentId, params, EVENT_ERROR, SOURCE_RUNTIME, PAYLOAD_ERROR,
                JsonSupport.toJSON(payload), StringUtils.defaultString(errorMsg),
                new AiCodingRuntimePayload().setToolSuccess(false));
    }

    /**
     * 与 Tool 调用关联的结构化诊断错误。
     */
    public AiCodingStreamEvent toolError(long agentId, Map<String, String> params, String toolCallId,
            String toolName, String payloadJson, String errorMsg) {
        return runtimePayload(agentId, params, EVENT_ERROR, SOURCE_RUNTIME, PAYLOAD_ERROR,
                payloadJson, StringUtils.defaultString(errorMsg),
                toolRuntimePayload(toolCallId, toolName, false));
    }

    private AiCodingStreamEvent runtimePayload(long agentId, Map<String, String> params, String streamEventType,
            String source, String payloadType, String payloadJson, String content,
            AiCodingRuntimePayload runtimePayload) {
        runtimePayload.setPayloadType(StringUtils.defaultString(payloadType))
                .setPayloadJson(StringUtils.defaultString(payloadJson));
        return new AiCodingRuntimePayloadEvent(baseMetadata(agentId, params, streamEventType, source)
                .setContent(StringUtils.defaultString(content)), runtimePayload);
    }

    private AiCodingRuntimePayload toolRuntimePayload(String toolCallId, String toolName, boolean success) {
        return new AiCodingRuntimePayload()
                .setToolCallId(StringUtils.defaultString(toolCallId))
                .setToolName(StringUtils.defaultString(toolName))
                .setToolSuccess(success);
    }

    private AiCodingStreamEventMetadata baseMetadata(long agentId, Map<String, String> params, String streamEventType,
            String source) {
        return new AiCodingStreamEventMetadata()
                .setEventType(streamEventType)
                .setEventId("evt_" + UUID.randomUUID().toString().replace("-", ""))
                .setSource(source)
                .setMessageId(StringUtils.defaultString(params.get(FIELD_MESSAGE_ID)))
                .setRunId(StringUtils.defaultString(params.get(FIELD_RUN_ID)))
                .setThreadId(StringUtils.defaultString(params.get(FIELD_SESSION_ID)))
                .setConversationId(StringUtils.defaultString(params.get(FIELD_CONVERSATION_ID)))
                .setTraceId(StringUtils.defaultString(params.get(FIELD_TRACE_ID)))
                .setTimestamp(System.currentTimeMillis())
                .setAnswerAgentId(agentId);
    }

    private String blockId(String type, Map<String, String> params, String... suffixes) {
        StringBuilder builder = new StringBuilder("block_")
                .append(StringUtils.lowerCase(type))
                .append("_")
                .append(StringUtils.defaultIfBlank(params.get(FIELD_MESSAGE_ID), "message"));
        for (String suffix : suffixes) {
            if (StringUtils.isNotBlank(suffix)) {
                builder.append("_").append(suffix);
            }
        }
        return builder.toString();
    }

    private Object parseJsonOrText(String value) {
        if (StringUtils.isBlank(value)) {
            return StringUtils.EMPTY;
        }
        try {
            return JsonSupport.fromJSON(value, Object.class);
        } catch (Exception e) {
            return value;
        }
    }
}
