package dev.a2flow.management.agentcore.runtime.enums;

import lombok.Getter;

/**

 * Created on 2026-04-25
 */
@Getter
public enum AgentEngineResultCode {
    success(1, "成功"),
    systemError(11, "系统错误"),
    notHasEngine(12, "不存在可执行的Agent"),
    paramInvalid(13, "参数错误"),
    termination(14, "主动终止"),
    ;
    private final int code;
    private final String errorMsg;

    AgentEngineResultCode(int code, String errorMsg) {
        this.code = code;
        this.errorMsg = errorMsg;
    }
}
