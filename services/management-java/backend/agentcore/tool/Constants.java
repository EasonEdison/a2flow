package dev.a2flow.management.agentcore.tool;

/**

 * @date 2022/11/02 11:51
 **/
public class Constants {

    public static final String KCACHE_NAME = "kcache_kwaishopAiAgentService";

    public static final String PERF_NAMESPACE = "kwaishop.ai.agent.service";
    public static final String AGENT_ERROR_TAG = "agent_error";
    public static final String AGENT_SUCCESS_TAG = "agent_success";
    public static final String AGENT_START_TAG = "agent_start";
    public static final String AGENT_END_TAG = "agent_end";
    public static final String AGENT_EMPTY_ENGINE_TAG = "empty_engine";
    public static final String TOOL_ERROR_TAG = "tool_error";
    public static final String TOOL_SUCCESS_TAG = "tool_success";
    public static final String TOOL_START_TAG = "tool_start";
    public static final String TOOL_END_TAG = "tool_end";

    /**
     * 会话维度锁的 key 前缀
     */
    public static final String SESSION_LOCK_KEY_PREFIX = "agent:invoke:session:";
    /**
     * cancel 信号的 key 前缀（集群部署下跨机器可检测）
     */
    public static final String SESSION_CANCEL_KEY_PREFIX = "agent:cancel:session:";
}
