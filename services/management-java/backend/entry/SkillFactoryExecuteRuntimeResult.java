package dev.a2flow.management.entry;

import lombok.Data;

/**
 * SkillFactory 非流式执行结果。
 *
 * <p>该对象是 `runtime/skillfactory` 内部返回给 RPC 壳的统一结果，负责承载成功标记、
 * 错误信息、JSON data 和列表标识。它不依赖具体 PB 类型，避免非 chat 入口编排和 gateway
 * 响应格式强耦合；真正的 PB 包装由 gateway 层完成。
 */
@Data
public class SkillFactoryExecuteRuntimeResult {

    private boolean success;
    private String errorMsg;
    private String data;
    private boolean list;

    public static SkillFactoryExecuteRuntimeResult success(String data, boolean list) {
        SkillFactoryExecuteRuntimeResult result = new SkillFactoryExecuteRuntimeResult();
        result.setSuccess(true);
        result.setData(data);
        result.setList(list);
        return result;
    }

    public static SkillFactoryExecuteRuntimeResult fail(String errorMsg) {
        return fail(errorMsg, null);
    }

    public static SkillFactoryExecuteRuntimeResult fail(String errorMsg, String data) {
        SkillFactoryExecuteRuntimeResult result = new SkillFactoryExecuteRuntimeResult();
        result.setSuccess(false);
        result.setErrorMsg(errorMsg);
        result.setData(data);
        return result;
    }
}
