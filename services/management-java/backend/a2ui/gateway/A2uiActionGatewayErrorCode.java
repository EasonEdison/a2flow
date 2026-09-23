package dev.a2flow.management.a2ui.gateway;

/**
 * A2UI Action Gateway 的稳定领域错误码。
 *
 * <p>上游 transport 只按 code 和安全 JSON Pointer 映射响应，下游 CapabilityAction 不接收异常中的
 * 原始 Action/context。本枚举不绑定 HTTP/SSE 状态，也不定义 CARD、Adviser 或跨环境 fallback。
 */
public enum A2uiActionGatewayErrorCode {
    ACTION_INVALID("A2UI_ACTION_INVALID", "A2UI Action 结构不合法"),
    ACTION_NOT_BOUND("A2UI_ACTION_NOT_BOUND", "Action 未绑定已发布业务能力"),
    ACTION_SOURCE_INVALID("A2UI_ACTION_SOURCE_INVALID", "Action 来源组件不合法"),
    RUNTIME_SESSION_MISMATCH("A2UI_RUNTIME_SESSION_MISMATCH", "运行会话与 Build 不匹配"),
    BUILD_ACTION_CLOSURE_INVALID("A2UI_BUILD_ACTION_CLOSURE_INVALID", "Build Action 闭合关系损坏"),
    ACTION_CONTEXT_INVALID("A2UI_ACTION_CONTEXT_INVALID", "Action context 校验失败"),
    ACTION_CONTEXT_AUTHORITY_FORBIDDEN(
            "A2UI_ACTION_CONTEXT_AUTHORITY_FORBIDDEN", "Action context 包含受保护执行字段"),
    REQUEST_MAPPING_INVALID("A2UI_REQUEST_MAPPING_INVALID", "请求映射不合法"),
    REQUEST_MAPPING_AUTHORITY_FORBIDDEN(
            "A2UI_REQUEST_MAPPING_AUTHORITY_FORBIDDEN", "非可信输入不能写入执行 authority"),
    TRUSTED_CONTEXT_MISSING("A2UI_TRUSTED_CONTEXT_MISSING", "缺少服务端可信上下文");

    private final String code;
    private final String message;

    A2uiActionGatewayErrorCode(String code, String message) {
        this.code = code;
        this.message = message;
    }

    public String getCode() {
        return code;
    }

    public String getMessage() {
        return message;
    }
}
