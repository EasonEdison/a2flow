package dev.a2flow.management.model;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * SkillFactory 内部执行结果。
 *
 * <p>该对象用于 agent-service 内部方法执行结果和 gateway 层 PB 响应之间的过渡。业务 handler 只表达
 * 是否成功、错误信息、返回数据和 data 是否数组，最终的 result/error_msg/data/trace_id/is_list 由
 * gateway RPC 实现统一映射。
 */
@Data
@NoArgsConstructor
@AllArgsConstructor
public class SkillFactoryExecutionResult {

    private static final String EMPTY_ERROR_MESSAGE = "";

    private boolean success;

    private String errorMsg;

    private Object data;

    private boolean list;

    public static SkillFactoryExecutionResult success(Object data, boolean list) {
        return new SkillFactoryExecutionResult(true, EMPTY_ERROR_MESSAGE, data, list);
    }

    public static SkillFactoryExecutionResult fail(String errorMsg) {
        return fail(errorMsg, null);
    }

    public static SkillFactoryExecutionResult fail(String errorMsg, Object errorData) {
        return new SkillFactoryExecutionResult(false, errorMsg, errorData, false);
    }
}
