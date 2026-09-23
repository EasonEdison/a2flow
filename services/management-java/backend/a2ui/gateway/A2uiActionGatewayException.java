package dev.a2flow.management.a2ui.gateway;

/**
 * Action Gateway fail-closed 校验异常。
 *
 * <p>异常只暴露稳定 errorCode 和可选安全 JSON Pointer，不携带 session token、幂等键、可信身份、
 * Cookie、credential 或完整业务 payload。物理 transport 如何编码该异常仍由后续评审决定。
 */
public class A2uiActionGatewayException extends RuntimeException {

    private static final long serialVersionUID = 1L;

    private final String errorCode;
    private final String safePointer;

    public A2uiActionGatewayException(A2uiActionGatewayErrorCode errorCode) {
        this(errorCode, null);
    }

    public A2uiActionGatewayException(A2uiActionGatewayErrorCode errorCode, String safePointer) {
        super(errorCode.getMessage());
        this.errorCode = errorCode.getCode();
        this.safePointer = safePointer;
    }

    public String getErrorCode() {
        return errorCode;
    }

    public String getSafePointer() {
        return safePointer;
    }
}
