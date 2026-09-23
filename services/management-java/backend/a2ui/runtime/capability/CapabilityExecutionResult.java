package dev.a2flow.management.a2ui.runtime.capability;

import java.util.LinkedHashMap;
import java.util.Map;

import lombok.Builder;
import lombok.Value;

/**
 * 业务能力的一次强类型执行结果。
 *
 * <p>固定执行元数据使用明确字段；只有不同业务能力自由返回的data保留开放JSON类型。
 * Toolkit协议和ResultAdapter动态映射需要Map时，必须在对应边界显式转换。
 */
@Value
@Builder
public class CapabilityExecutionResult {

    private String actionCode;
    private int capabilityVersion;
    private String clientType;
    private String requestedEnvironment;
    private String resolvedEnvironment;
    private boolean success;
    private Integer httpStatus;
    private String contentType;
    private String traceId;
    private Object data;
    private String errorCode;
    private String message;

    /** 保留既有Toolkit结果字段形状，只在外部动态协议边界使用。 */
    public Map<String, Object> toMap() {
        Map<String, Object> result = baseMetadataMap();
        result.put("data", data);
        result.put("errorCode", errorCode);
        result.put("message", message);
        return result;
    }

    /** 为ResultAdapter提供原有完整固定元数据，不把业务data重复放入元数据根。 */
    public Map<String, Object> toMetadataMap() {
        Map<String, Object> result = baseMetadataMap();
        result.put("errorCode", errorCode);
        result.put("message", message);
        return result;
    }

    private Map<String, Object> baseMetadataMap() {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("actionCode", actionCode);
        result.put("capabilityVersion", capabilityVersion);
        result.put("clientType", clientType);
        result.put("requestedEnvironment", requestedEnvironment);
        result.put("resolvedEnvironment", resolvedEnvironment);
        result.put("success", success);
        result.put("httpStatus", httpStatus);
        result.put("contentType", contentType);
        result.put("traceId", traceId);
        return result;
    }
}
