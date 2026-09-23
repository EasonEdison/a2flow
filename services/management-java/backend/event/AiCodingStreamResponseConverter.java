package dev.a2flow.management.event;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Component;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.protobuf.SkillFactoryChatResponse;

/**
 * SkillFactory AI Coding 内部事件到 Chat 响应的统一转换器。
 *
 * <p>上游既可以是模型 Chat 流，也可以是普通 handler 完成后的控制面领域事件；本类只负责把
 * {@link AiCodingStreamEvent} 投影为可持久化、可回放的 {@link SkillFactoryChatResponse}。
 * 它不执行模型、不修改 workspace，也不决定 Patch 审批状态。
 */
@Component
public class AiCodingStreamResponseConverter {

    /**
     * 转换结构化事件，并保留调用方传入的 invokeId 作为历史关联键。
     */
    public SkillFactoryChatResponse convert(AiCodingStreamEvent event, String invokeId) {
        AiCodingStreamEnvelope envelope = toEnvelope(event);
        SkillFactoryChatResponse.Builder builder = SkillFactoryChatResponse.newBuilder()
                .setSchemaVersion(AiCodingStreamEnvelopeCodec.SCHEMA_VERSION)
                .setEventType(StringUtils.defaultString(envelope.getEventType()))
                .setEventId(StringUtils.defaultString(envelope.getEventId()))
                .setBlockId(StringUtils.defaultString(envelope.getBlockId()))
                .setSource(StringUtils.defaultString(envelope.getSource()))
                .setMessageId(StringUtils.defaultString(envelope.getMessageId()))
                .setRunId(StringUtils.defaultString(envelope.getRunId()))
                .setThreadId(StringUtils.defaultString(envelope.getThreadId()))
                .setConversationId(StringUtils.defaultString(envelope.getConversationId()))
                .setTraceId(StringUtils.defaultString(envelope.getTraceId()))
                .setTimestamp(event.getTimestamp())
                .setAnswerAgentId(event.getAnswerAgentId())
                .setInvokeId(StringUtils.defaultString(invokeId));

        if (StringUtils.isNotBlank(envelope.getContent())) {
            builder.setContent(envelope.getContent());
        }
        if (envelope.getModelContentBlock() != null) {
            builder.setModelContentBlockJson(JsonSupport.toJSON(envelope.getModelContentBlock()));
        }
        if (StringUtils.isNotBlank(envelope.getPayloadType())) {
            builder.setPayloadType(envelope.getPayloadType());
        }
        if (StringUtils.isNotBlank(envelope.getPayloadJson())) {
            builder.setPayloadJson(envelope.getPayloadJson());
        }
        fillModelContentFields(builder, event);
        fillRuntimePayloadFields(builder, event);
        return builder.build();
    }

    private void fillModelContentFields(SkillFactoryChatResponse.Builder builder, AiCodingStreamEvent event) {
        if (!(event instanceof AiCodingModelContentEvent modelContentEvent)) {
            return;
        }
        if (modelContentEvent.getModelContentBlock() instanceof AiCodingToolUseBlock toolUseBlock) {
            builder.setToolCallId(StringUtils.defaultString(toolUseBlock.getToolCallId()));
            builder.setToolName(StringUtils.defaultString(toolUseBlock.getToolName()));
            builder.setToolArgs(JsonSupport.toJSON(toolUseBlock.getToolArgs()));
        }
    }

    private void fillRuntimePayloadFields(SkillFactoryChatResponse.Builder builder, AiCodingStreamEvent event) {
        if (!(event instanceof AiCodingRuntimePayloadEvent runtimePayloadEvent)) {
            return;
        }
        builder.setToolCallId(StringUtils.defaultString(runtimePayloadEvent.getToolCallId()));
        builder.setToolName(StringUtils.defaultString(runtimePayloadEvent.getToolName()));
        builder.setToolArgs(StringUtils.defaultString(runtimePayloadEvent.getToolArgs()));
        builder.setToolSuccess(runtimePayloadEvent.isToolSuccess());
        builder.setTokenCount(runtimePayloadEvent.getTokenCount());
        builder.setEnterTokenCount(runtimePayloadEvent.getEnterTokenCount());
        builder.setOutputTokenCount(runtimePayloadEvent.getOutputTokenCount());
        builder.setHasKnowledge(runtimePayloadEvent.isHasKnowledge());
    }

    private AiCodingStreamEnvelope toEnvelope(AiCodingStreamEvent event) {
        if (event instanceof AiCodingModelContentEvent modelContentEvent) {
            return baseEnvelope(modelContentEvent)
                    .setBlockId(modelContentEvent.getBlockId())
                    .setModelContentBlock(modelContentEvent.getModelContentBlock());
        }
        if (event instanceof AiCodingRuntimePayloadEvent runtimePayloadEvent) {
            return baseEnvelope(runtimePayloadEvent)
                    .setPayloadType(StringUtils.defaultString(runtimePayloadEvent.getPayloadType()))
                    .setPayloadJson(StringUtils.defaultString(runtimePayloadEvent.getPayloadJson()))
                    .setToolCallId(StringUtils.defaultString(runtimePayloadEvent.getToolCallId()))
                    .setToolName(StringUtils.defaultString(runtimePayloadEvent.getToolName()))
                    .setToolArgs(StringUtils.defaultString(runtimePayloadEvent.getToolArgs()))
                    .setToolSuccess(runtimePayloadEvent.isToolSuccess())
                    .setTokenCount(runtimePayloadEvent.getTokenCount())
                    .setEnterTokenCount(runtimePayloadEvent.getEnterTokenCount())
                    .setOutputTokenCount(runtimePayloadEvent.getOutputTokenCount())
                    .setHasKnowledge(runtimePayloadEvent.isHasKnowledge());
        }
        return baseEnvelope(event);
    }

    private AiCodingStreamEnvelope baseEnvelope(AiCodingStreamEvent event) {
        return new AiCodingStreamEnvelope()
                .setEventType(event.getEventType())
                .setEventId(event.getEventId())
                .setSource(event.getSource())
                .setMessageId(event.getMessageId())
                .setRunId(event.getRunId())
                .setThreadId(event.getThreadId())
                .setConversationId(event.getConversationId())
                .setTraceId(event.getTraceId())
                .setContent(StringUtils.defaultString(event.getContent()))
                .setTimestamp(event.getTimestamp())
                .setAnswerAgentId(event.getAnswerAgentId());
    }
}
