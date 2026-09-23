package dev.a2flow.management.agentcore.runtime.engine.model;

import org.apache.commons.lang3.StringUtils;

import dev.a2flow.management.agentcore.runtime.enums.AgentEngineResultCode;

import lombok.Data;

/**

 * Created on 2026-04-23
 */
@Data
public class AgentEngineResult {
    private int code;
    private String errorMsg;
    private String finallyAnswer;
    private long finallyAnswerAgentId;

    public static AgentEngineResult success() {
        AgentEngineResult result = new AgentEngineResult();
        result.setCode(AgentEngineResultCode.success.getCode());
        result.setErrorMsg(AgentEngineResultCode.success.getErrorMsg());
        return result;
    }

    public static AgentEngineResult success(String finallyAnswer) {
        AgentEngineResult result = success();
        result.setFinallyAnswer(finallyAnswer);
        return result;
    }

    public static AgentEngineResult success(String finallyAnswer, long finallyAnswerAgentId) {
        AgentEngineResult result = success();
        result.setFinallyAnswer(finallyAnswer);
        result.setFinallyAnswerAgentId(finallyAnswerAgentId);
        return result;
    }

    public static AgentEngineResult of(int code, String errorMsg) {
        AgentEngineResult result = new AgentEngineResult();
        result.setCode(code);
        result.setErrorMsg(StringUtils.defaultString(errorMsg));
        return result;
    }

    public static AgentEngineResult error(String errorMsg) {
        AgentEngineResult result = new AgentEngineResult();
        result.setCode(AgentEngineResultCode.systemError.getCode());
        result.setErrorMsg(StringUtils.defaultString(errorMsg));
        return result;
    }

    public static AgentEngineResult error(AgentEngineResultCode resultCode) {
        AgentEngineResult result = new AgentEngineResult();
        result.setCode(resultCode.getCode());
        result.setErrorMsg(StringUtils.defaultString(resultCode.getErrorMsg()));
        return result;
    }
}
