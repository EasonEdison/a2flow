package dev.a2flow.management.model;

import java.util.Map;

import lombok.Builder;
import lombok.Value;

/**
 * 业务能力 Protobuf gRPC 请求的瞬时安全预览。
 *
 * <p>上游是能力中心直接 dry-run，下游与真实执行共用 {@code CapabilityActionExecutor} 的计划校验、
 * 参数映射与可信上下文校验。本对象不包含传输凭据，也不会进入草稿和发布证据。
 */
@Value
@Builder
public class CapabilityActionExecutionPreview {

    private String configuredHost;
    private String protocol;
    private String targetKey;
    private String serviceName;
    private String methodName;
    private String httpMethod;
    private String path;
    private Map<String, Object> effectiveArguments;
    private Map<String, Object> effectiveRequestBody;
    private boolean cookieInjected;
}
