package dev.a2flow.management.a2ui.application;

/**
 * A2UI Application 编译校验异常。
 *
 * <p>只暴露稳定 errorCode，不回显 draft 消息、凭证或可信上下文；外层如何映射响应由后续 transport
 * 评审决定，本异常不提供 fallback。
 */
public class A2uiApplicationValidationException extends RuntimeException {

    private static final long serialVersionUID = 1L;

    private final String errorCode;

    public A2uiApplicationValidationException(A2uiApplicationErrorCode errorCode) {
        super(errorCode.getMessage());
        this.errorCode = errorCode.getCode();
    }

    public String getErrorCode() {
        return errorCode;
    }
}
