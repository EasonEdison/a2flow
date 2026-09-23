package dev.a2flow.management.lifecycle;

import lombok.Getter;

/**
 * CapabilityAction 直接验证的稳定参数异常。
 *
 * <p>上游直接 dry-run 服务在请求预览和 HTTP Transport 之前构造本异常；下游统一分发器按
 * errorCode 和 fieldPath 输出可读、可定位的失败结果。该异常不承载 Cookie、原始 curl、请求体或响应体。
 *
 * <p>不负责执行计划校验、远端请求失败包装、凭证持久化或未知系统异常兜底。
 */
@Getter
public class CapabilityActionDryRunValidationException extends IllegalArgumentException {

    private static final long serialVersionUID = 1L;
    private static final String ERROR_CODE_CREDENTIAL_REQUIRED =
            "CAPABILITY_DRY_RUN_CREDENTIAL_REQUIRED";
    private static final String ERROR_MESSAGE_CREDENTIAL_REQUIRED =
            "请填写本次验证 Cookie / curl";
    private static final String FIELD_PATH_CREDENTIAL_INPUT = "credentialInput";

    private final String errorCode;
    private final String fieldPath;

    private CapabilityActionDryRunValidationException(
            String errorCode, String message, String fieldPath) {
        super(message);
        this.errorCode = errorCode;
        this.fieldPath = fieldPath;
    }

    /** 构造一次性验证凭证缺失错误，不接收或复制任何凭证内容。 */
    public static CapabilityActionDryRunValidationException credentialRequired() {
        return new CapabilityActionDryRunValidationException(
                ERROR_CODE_CREDENTIAL_REQUIRED,
                ERROR_MESSAGE_CREDENTIAL_REQUIRED,
                FIELD_PATH_CREDENTIAL_INPUT);
    }
}
