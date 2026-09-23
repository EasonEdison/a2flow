package dev.a2flow.management.agentcore.tool;

import org.apache.commons.lang3.StringUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;

import dev.a2flow.management.agentcore.runtime.engine.model.AgentEngineContext;
import dev.a2flow.management.aicoding.run.SkillFactoryRunControlService;

import lombok.extern.slf4j.Slf4j;

/**
 * SkillFactory 本地 Agent 运行辅助工具。
 *
 * <p>该类把 AI Coding Engine 检查点连接到 SkillFactory 运行控制服务：先读取 Context 本地 token，
 * 必要时再从 Redis 桥接跨实例信号，并记录本轮已经真正观测到取消。它不查询 DB，不生成终态，
 * 也不会读取或删除普通数字员工的 cancel key。
 */
@Slf4j
@Component
public class AgentBizTool {

    @Autowired
    private SkillFactoryRunControlService runControlService;

    /**
     * 检查当前运行的取消信号，并标记 Engine 已观测取消。
     */
    public boolean checkCancellation(String engineName, String cancelSessionId,
            AgentEngineContext engineContext) {
        String invokeId = engineContext == null ? StringUtils.EMPTY : engineContext.getInvokeId();
        if (StringUtils.isBlank(cancelSessionId) || StringUtils.isBlank(invokeId)) {
            return false;
        }
        boolean cancelled = runControlService.isCancellationRequested(cancelSessionId, invokeId,
                engineContext.getCancellationRequested());
        if (cancelled && engineContext.getCancellationObserved().compareAndSet(false, true)) {
            log.info("SkillFactory检测到运行取消信号, engineName={}, sessionId={}, invokeId={}",
                    engineName, cancelSessionId, invokeId);
        }
        return cancelled;
    }
}
