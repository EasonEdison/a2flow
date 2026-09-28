package dev.a2flow.management.a2ui.application;

/**
 * A2UI Application 编译校验异常。
 *
 * <p>只暴露稳定 errorCode 与可选的安全作者配置路径，不回显 draft 消息、绑定值、凭证或可信上下文；
 * 外层如何映射响应由 transport 决定，本异常不提供 fallback。
 */
public class A2uiApplicationValidationException extends RuntimeException {

    private static final long serialVersionUID = 1L;

    private final String errorCode;
    private final String fieldPath;

    public A2uiApplicationValidationException(A2uiApplicationErrorCode errorCode) {
        this(errorCode, null);
    }

    A2uiApplicationValidationException(A2uiApplicationErrorCode errorCode, String fieldPath) {
        super(errorCode.getMessage());
        this.errorCode = errorCode.getCode();
        this.fieldPath = fieldPath;
    }

    public String getErrorCode() {
        return errorCode;
    }

    /** 仅返回作者配置中的安全定位路径，不包含绑定值、业务结果或可信上下文。 */
    public String getFieldPath() {
        return fieldPath;
    }
}
