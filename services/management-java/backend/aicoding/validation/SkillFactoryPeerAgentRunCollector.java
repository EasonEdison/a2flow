package dev.a2flow.management.aicoding.validation;

import java.util.HashMap;
import java.util.Map;
import java.util.function.Consumer;

import org.apache.commons.collections4.MapUtils;
import org.apache.commons.lang3.StringUtils;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.event.AiCodingModelContentBlock;
import dev.a2flow.management.event.AiCodingStreamEventFactory;

import lombok.extern.slf4j.Slf4j;

/**
 * SkillFactory peer Agent 流式事件采集器。
 *
 * <p>peer Agent 的公共运行时事件会在包外 outlet 转成 `SkillFactoryPeerAgentStreamEvent`。
 * 该采集器只解析当前 `invoke_agent` 需要的最小证据：模型回答摘要、
 * `simulate_skill_request` 工具调用和工具结果，不修改公共运行时协议。
 */
@Slf4j
public class SkillFactoryPeerAgentRunCollector implements Consumer<SkillFactoryPeerAgentStreamEvent> {

    private static final String FIELD_SCHEMA_VERSION = "schemaVersion";
    private static final String FIELD_EVENT_TYPE = "eventType";
    private static final String FIELD_CONTENT = "content";
    private static final String FIELD_MODEL_CONTENT_BLOCK = "modelContentBlock";
    private static final String FIELD_PAYLOAD_TYPE = "payloadType";
    private static final String FIELD_PAYLOAD_JSON = "payloadJson";
    private static final String FIELD_TOOL_NAME = "toolName";
    private static final String FIELD_TOOL_CALL_ID = "toolCallId";
    private static final String FIELD_RESULT = "result";
    private static final String FIELD_SUCCESS = "success";
    private static final String FIELD_TYPE = "type";
    private static final String FIELD_TEXT = "text";
    private static final String EVENT_ANSWER_TEXT_DELTA = "ANSWER_TEXT_DELTA";
    private static final String EVENT_TOOL_CALL = "TOOL_CALL";
    private static final String EVENT_TOOL_RESULT = "TOOL_RESULT";
    private static final String EVENT_COMPLETED = "COMPLETED";
    private static final String EVENT_ERROR = "ERROR";
    private static final String STATUS_STARTED = "STARTED";
    private static final String STATUS_FINISHED = "FINISHED";
    private static final int MAX_EVENT_SUMMARY_COUNT = 80;
    private static final int MAX_EVENT_CONTENT_LENGTH = 500;

    private final SkillFactoryPeerAgentRunResult result;
    private final String requiredToolName;
    private final StringBuilder finalAnswer = new StringBuilder();

    public SkillFactoryPeerAgentRunCollector(SkillFactoryPeerAgentRunResult result, String requiredToolName) {
        this.result = result;
        this.requiredToolName = requiredToolName;
    }

    /**
     * 采集 peer Agent 的单个事件。
     */
    @Override
    public void accept(SkillFactoryPeerAgentStreamEvent event) {
        if (event == null) {
            return;
        }
        Map<String, Object> envelope = parseMap(event.getContent());
        collectEventSummary(event, envelope);
        collectModelText(event, envelope);
        collectLifecycle(event);
        collectRequiredToolEvidence(event, envelope);
    }

    public SkillFactoryPeerAgentRunResult finish() {
        result.setFinalAnswer(finalAnswer.toString());
        return result;
    }

    private void collectLifecycle(SkillFactoryPeerAgentStreamEvent event) {
        if (StringUtils.equals(EVENT_COMPLETED, event.getEventType())) {
            result.setCompleted(true);
        }
        if (StringUtils.equals(EVENT_ERROR, event.getEventType())) {
            result.setErrorMessage(StringUtils.defaultIfBlank(result.getErrorMessage(), visibleContent(event)));
        }
    }

    @SuppressWarnings("unchecked")
    private void collectModelText(SkillFactoryPeerAgentStreamEvent event, Map<String, Object> envelope) {
        if (!StringUtils.equals(EVENT_ANSWER_TEXT_DELTA, event.getEventType())) {
            return;
        }
        Object blockObject = envelope.get(FIELD_MODEL_CONTENT_BLOCK);
        if (blockObject instanceof Map) {
            Map<String, Object> block = (Map<String, Object>) blockObject;
            if (StringUtils.equals(AiCodingModelContentBlock.TYPE_TEXT, MapUtils.getString(block, FIELD_TYPE))) {
                finalAnswer.append(StringUtils.defaultString(MapUtils.getString(block, FIELD_TEXT)));
                return;
            }
        }
        if (!isStructuredEnvelope(envelope)) {
            finalAnswer.append(StringUtils.defaultString(event.getContent()));
            return;
        }
        finalAnswer.append(StringUtils.defaultString(MapUtils.getString(envelope, FIELD_CONTENT)));
    }

    private void collectRequiredToolEvidence(SkillFactoryPeerAgentStreamEvent event, Map<String, Object> envelope) {
        String toolName = StringUtils.defaultIfBlank(MapUtils.getString(envelope, FIELD_TOOL_NAME),
                event.getToolName());
        if (!StringUtils.equals(requiredToolName, toolName)) {
            return;
        }
        boolean structuredEnvelope = isStructuredEnvelope(envelope);
        String streamEventType = MapUtils.getString(envelope, FIELD_EVENT_TYPE);
        if ((!structuredEnvelope && StringUtils.equals(EVENT_TOOL_CALL, event.getEventType()))
                || StringUtils.equals(AiCodingStreamEventFactory.EVENT_TOOL_CALL_STARTED, streamEventType)) {
            result.setSimulateToolCalled(true);
            result.getRequiredToolEvidence().add(toolEvidence(event, envelope, STATUS_STARTED, null));
            return;
        }
        if ((!structuredEnvelope && StringUtils.equals(EVENT_TOOL_RESULT, event.getEventType()))
                || StringUtils.equals(AiCodingStreamEventFactory.EVENT_TOOL_CALL_FINISHED, streamEventType)) {
            String resultJson = extractToolResultJson(event, envelope);
            boolean success = extractToolSuccess(event, envelope);
            result.setSimulateToolSucceeded(success);
            result.getRequiredToolEvidence().add(toolEvidence(event, envelope, STATUS_FINISHED, resultJson));
            if (success && StringUtils.isNotBlank(resultJson)) {
                parseSimulationResult(resultJson);
            }
        }
    }

    private void parseSimulationResult(String resultJson) {
        try {
            result.setSimulationResult(JsonSupport.fromJSON(resultJson, SkillSimulationResult.class));
        } catch (Exception e) {
            log.info("SkillFactory peer Agent解析simulate_skill_request结果失败, resultLength={}",
                    StringUtils.length(resultJson), e);
            result.setErrorMessage("simulate_skill_request 结果不是合法 SkillSimulationResult");
        }
    }

    private String extractToolResultJson(SkillFactoryPeerAgentStreamEvent event, Map<String, Object> envelope) {
        Map<String, Object> payload = parseMap(MapUtils.getString(envelope, FIELD_PAYLOAD_JSON));
        String resultJson = MapUtils.getString(payload, FIELD_RESULT);
        if (StringUtils.isNotBlank(resultJson)) {
            return resultJson;
        }
        return isStructuredEnvelope(envelope) ? StringUtils.EMPTY : event.getContent();
    }

    private boolean extractToolSuccess(SkillFactoryPeerAgentStreamEvent event, Map<String, Object> envelope) {
        Map<String, Object> payload = parseMap(MapUtils.getString(envelope, FIELD_PAYLOAD_JSON));
        if (payload.containsKey(FIELD_SUCCESS)) {
            return MapUtils.getBoolean(payload, FIELD_SUCCESS, false);
        }
        return event.isSuccess();
    }

    private Map<String, Object> toolEvidence(SkillFactoryPeerAgentStreamEvent event, Map<String, Object> envelope, String status,
            String resultJson) {
        Map<String, Object> evidence = new HashMap<>();
        evidence.put(FIELD_TOOL_NAME, requiredToolName);
        evidence.put(FIELD_TOOL_CALL_ID, StringUtils.defaultIfBlank(MapUtils.getString(envelope, FIELD_TOOL_CALL_ID),
                event.getToolCallId()));
        evidence.put("status", status);
        evidence.put("success", extractToolSuccess(event, envelope));
        evidence.put("resultPreview", StringUtils.abbreviate(StringUtils.defaultString(resultJson),
                MAX_EVENT_CONTENT_LENGTH));
        return evidence;
    }

    private void collectEventSummary(SkillFactoryPeerAgentStreamEvent event, Map<String, Object> envelope) {
        if (result.getChildEventSummary().size() >= MAX_EVENT_SUMMARY_COUNT) {
            return;
        }
        Map<String, Object> summary = new HashMap<>();
        summary.put("eventType", StringUtils.defaultString(event.getEventType()));
        summary.put("streamEventType", MapUtils.getString(envelope, FIELD_EVENT_TYPE));
        summary.put(FIELD_PAYLOAD_TYPE, MapUtils.getString(envelope, FIELD_PAYLOAD_TYPE));
        summary.put(FIELD_TOOL_NAME, StringUtils.defaultIfBlank(MapUtils.getString(envelope, FIELD_TOOL_NAME),
                event.getToolName()));
        summary.put("content", StringUtils.abbreviate(visibleContent(event), MAX_EVENT_CONTENT_LENGTH));
        summary.put("success", event.isSuccess());
        summary.put("timestamp", event.getTimestamp());
        result.getChildEventSummary().add(summary);
    }

    private String visibleContent(SkillFactoryPeerAgentStreamEvent event) {
        Map<String, Object> envelope = parseMap(event.getContent());
        if (isStructuredEnvelope(envelope)) {
            return MapUtils.getString(envelope, FIELD_CONTENT);
        }
        return StringUtils.defaultString(event.getContent());
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> parseMap(String json) {
        if (StringUtils.isBlank(json)) {
            return Map.of();
        }
        try {
            Object parsed = JsonSupport.fromJSON(json, Object.class);
            if (parsed instanceof Map) {
                return (Map<String, Object>) parsed;
            }
        } catch (Exception ignored) {
            return Map.of();
        }
        return Map.of();
    }

    private boolean isStructuredEnvelope(Map<String, Object> envelope) {
        return StringUtils.isNotBlank(MapUtils.getString(envelope, FIELD_SCHEMA_VERSION));
    }
}
