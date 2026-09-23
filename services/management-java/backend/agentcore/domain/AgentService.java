package dev.a2flow.management.agentcore.domain;

import java.util.List;
import dev.a2flow.management.agentcore.entity.Agent;

/** Agent registry lookup port; requires an authenticated Runtime integration. */
public interface AgentService {
    Agent queryById(String bizKey, long agentId);
    List<Agent> querySubAgent(long agentId);
}
