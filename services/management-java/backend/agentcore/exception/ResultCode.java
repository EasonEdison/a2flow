package dev.a2flow.management.agentcore.exception;

import lombok.Getter;

/**
 * 结果码枚举
 *

 * @date 2026/4/28
 */
@Getter
public enum ResultCode {

    SUCCESS(1, "success"),
    SYSTEM_ERROR(11, "system error"),
    PARAM_ERROR(12, "param error"),
    LOCK_FAIL(13, "lock fail"),
    AGENT_NOT_FOUND(14, "agent not found"),
    AGENT_OWNER_MISMATCH(15, "owner_id does not match agent's owner"),
    AGENT_BIZ_KEY_MISMATCH(15, "biz_key does not match agent's biz_key"),
    SESSION_NOT_FOUND(16, "session not found"),
    SESSION_AGENT_MISMATCH(17, "session does not belong to the specified agent"),
    SESSION_USER_MISMATCH(18, "session does not belong to the specified user"),
    SKILL_NOT_EXIST(19, "skill not exist"),
    SKILL_REGISTER_CONFIG_NOT_EXIST(20, "Skill注册配置不存在, 请检查BizKey"),
    SKILL_FILE_IS_INVALID(21, "SKILL文件暂只支持zip格式"),
    AGENT_BIZ_CONFIG_NOT_REGISTER(22, "agent配置未注册, 请检查BizKey"),
    SESSION_CONCURRENT_LOCK_FAILED(23, "session正在处理中，请等待当前请求完成后再发起新请求"),
    SKILL_MD_NOT_EXIST(24, "SKILL.MD文件不存在"),
    ;

    private final int code;
    private final String message;

    ResultCode(int code, String message) {
        this.code = code;
        this.message = message;
    }
}
