package dev.a2flow.management.aicoding.validation;

import org.apache.commons.lang3.StringUtils;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Component;

import dev.a2flow.management.agentcore.runtime.engine.AgentEngineExecutor;
import dev.a2flow.management.agentcore.runtime.engine.model.AgentEngineContext;
import dev.a2flow.management.agentcore.runtime.engine.model.AgentEvent;

import lombok.extern.slf4j.Slf4j;

/**
 * SkillFactory peer Agent 本地引擎调用器。
 *
 * <p>该类是 `invoke_agent` 工具调用公共 AgentEngine 的最薄适配层，代码保留在
 * `runtime/skillfactory` 包内，避免在公共 `runtime/engine/impl` 目录新增 SkillFactory 业务桥接类。
 * 它只把公共引擎事件投影为 SkillFactory 本地采集事件，不改变公共 AgentEngine 协议。
 */
@Slf4j
@Component
public class SkillFactoryPeerAgentEngineInvoker {

    private final ObjectProvider<AgentEngineExecutor> agentEngineExecutorProvider;

    public SkillFactoryPeerAgentEngineInvoker(ObjectProvider<AgentEngineExecutor> agentEngineExecutorProvider) {
        this.agentEngineExecutorProvider = agentEngineExecutorProvider;
    }

    /**
     * 执行 peer Agent，并把公共事件转换给 SkillFactory collector。
     */
    public void process(AgentEngineContext childContext, SkillFactoryPeerAgentRunCollector collector) {
        AgentEngineExecutor agentEngineExecutor = agentEngineExecutorProvider.getIfAvailable();
        if (agentEngineExecutor == null) {
            throw new IllegalStateException("SkillFactory invoke_agent 未找到 AgentEngineExecutor");
        }
        log.info("SkillFactory invoke_agent准备调用公共AgentEngine, bizKey={}, agentId={}, sessionId={}, traceId={}",
                childContext == null ? null : childContext.getBizKey(),
                childContext == null ? null : childContext.getAgentId(),
                childContext == null ? null : childContext.getConversationId(),
                childContext == null ? null : childContext.getTraceId());
        agentEngineExecutor.process(childContext, event -> {
            SkillFactoryPeerAgentStreamEvent streamEvent = toStreamEvent(event);
            if (collector != null && streamEvent != null) {
                collector.accept(streamEvent);
            }
        });
    }

    private SkillFactoryPeerAgentStreamEvent toStreamEvent(AgentEvent event) {
        if (event == null) {
            return null;
        }
        return new SkillFactoryPeerAgentStreamEvent()
                .setEventType(event.getEventType() == null ? StringUtils.EMPTY : event.getEventType().name())
                .setContent(StringUtils.defaultString(event.getContent()))
                .setToolCallId(StringUtils.defaultString(event.getToolCallId()))
                .setToolName(StringUtils.defaultString(event.getToolName()))
                .setToolArgs(StringUtils.defaultString(event.getToolArgs()))
                .setSuccess(event.isSuccess())
                .setTimestamp(event.getTimestamp());
    }
}
