package dev.a2flow.management.model;

import dev.a2flow.management.release.ReleaseEnvironment;

import lombok.Builder;
import lombok.Value;

/**
 * 业务能力固定 Tool 的统一返回协议。
 *
 * <p>上游是 CapabilityActionExecutor，下游是模型、后续 Tool 和运行态交互适配层。{@code data}
 * 保留响应上限内的原始业务响应：JSON 返回解析后的值，其他内容返回原始文本，不做字段脱敏、筛选或
 * Demo 改写。日志和持久化审计不得复制该字段的完整内容。
 */
@Value
@Builder
public class CapabilityToolResult {

    private boolean success;
    private String actionCode;
    private String sourceId;
    private String sourceDigest;
    private String rpcStatus;
    private int capabilityVersion;
    private String clientType;
    private ReleaseEnvironment requestedEnvironment;
    private ReleaseEnvironment resolvedEnvironment;
    private int httpStatus;
    private String contentType;
    private String traceId;
    private Object data;
    private CapabilityToolErrorCode errorCode;
    private String message;
}
