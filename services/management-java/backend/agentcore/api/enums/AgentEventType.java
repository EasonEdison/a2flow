package dev.a2flow.management.agentcore.api.enums;

/**

 * Created on 2026-04-25
 */
public enum AgentEventType {
    STARTED,

    ANSWER_TEXT_DELTA,

    THINK_TEXT_DELTA,

    TOOL_CALL,
    TOOL_RESULT,

    USAGE,
    COMPLETED,
    ERROR;
}
