package dev.a2flow.management.agentcore.runtime.engine;

import java.util.function.Consumer;

import org.springframework.stereotype.Component;

import dev.a2flow.management.agentcore.runtime.engine.model.AgentEngineContext;
import dev.a2flow.management.agentcore.runtime.engine.model.AgentEvent;
import dev.a2flow.management.agentcore.runtime.enums.AgentEngineResultCode;

import lombok.extern.slf4j.Slf4j;

/**
 * SkillFactory 本地 Agent 引擎执行壳。
 *
 * <p>当前 sellerdata 迁移只直接运行 {@code AiCodingReActEngine}，不再复制原 agent-service 的
 * AgentEngineRegistry 和多策略分发。该类保留给 invoke_agent 校验链路编译使用；如后续要在
 * sellerdata 内部执行其它 Agent，需要在这里接入新的本地 registry。
 */
@Slf4j
@Component
public class AgentEngineExecutor {

    /**
     * 当前迁移阶段不执行公共 AgentEngine，直接返回明确错误事件。
     */
    public void process(AgentEngineContext engineContext, Consumer<AgentEvent> sink) {
        long agentId = engineContext == null ? 0L : engineContext.getAgentId();
        log.warn("SkillFactory本地AgentEngineExecutor未接入公共AgentEngine, agentId={}", agentId);
        sink.accept(AgentEvent.error(agentId, AgentEngineResultCode.notHasEngine.getErrorMsg()));
        sink.accept(AgentEvent.completed(agentId));
    }
}
