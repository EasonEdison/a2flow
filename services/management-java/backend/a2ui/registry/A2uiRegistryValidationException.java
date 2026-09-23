package dev.a2flow.management.a2ui.registry;

/**
 * A2UI Registry 输入校验异常。
 *
 * <p>该异常只携带稳定错误码，供上层 RPC envelope 映射；不负责权限授予、发布状态判断或
 * 对非法输入提供兼容降级。
 */
public class A2uiRegistryValidationException extends RuntimeException {

    private static final long serialVersionUID = 1L;

    private final String errorCode;

    public A2uiRegistryValidationException(String errorCode) {
        super(errorCode);
        this.errorCode = errorCode;
    }

    public String getErrorCode() {
        return errorCode;
    }
}
