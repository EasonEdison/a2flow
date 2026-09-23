package dev.a2flow.management.a2ui.runtime.adapter;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.apache.commons.lang3.StringUtils;

import lombok.Getter;

/**
 * A2UI v0.9.1 单条消息的强类型协议信封。
 *
 * <p>上游由ResultAdapter的MESSAGE_TEMPLATE或A2UI_PASSTHROUGH构造，本类固定version与唯一operation，
 * 避免业务代码继续用字符串key判断消息类型。operation payload仍保留开放JSON，
 * 以支持已注册Catalog的动态组件属性、Action context和data model value。
 * 下游只在公共Ledger、Snapshot或SSE wire边界调用
 * {@link #toMap()}；本类不解释组件语义、不修改payload，也不提供协议降级。</p>
 */
@Getter
public final class A2uiProtocolMessage {

    private static final String FIELD_VERSION = "version";
    private static final String ERROR_MESSAGE_REQUIRED = "A2UI message is required";
    private static final String ERROR_VERSION_REQUIRED = "A2UI message version is required";
    private static final String ERROR_OPERATION_REQUIRED = "A2UI message operation is required";
    private static final String ERROR_OPERATION_MULTIPLE = "A2UI message has multiple operations";
    private static final String ERROR_FIELD_UNSUPPORTED = "A2UI message field is unsupported: ";
    private static final String ERROR_PAYLOAD_REQUIRED = "A2UI message operation payload is required";

    private final String version;
    private final Operation operation;
    private final Map<String, Object> payload;

    private A2uiProtocolMessage(String version, Operation operation,
            Map<String, Object> payload) {
        this.version = version;
        this.operation = operation;
        this.payload = Collections.unmodifiableMap(new LinkedHashMap<>(payload));
    }

    /**
     * 从已发布模板或Capability passthrough结果解析固定信封；动态payload保持原结构。
     */
    public static A2uiProtocolMessage fromMap(Map<String, Object> message) {
        if (message == null || message.isEmpty()) {
            throw new IllegalArgumentException(ERROR_MESSAGE_REQUIRED);
        }
        String version = message.get(FIELD_VERSION) instanceof String
                ? (String) message.get(FIELD_VERSION) : null;
        if (StringUtils.isBlank(version)) {
            throw new IllegalArgumentException(ERROR_VERSION_REQUIRED);
        }
        Operation resolvedOperation = null;
        Map<String, Object> resolvedPayload = null;
        for (Map.Entry<String, Object> entry : message.entrySet()) {
            if (FIELD_VERSION.equals(entry.getKey())) {
                continue;
            }
            Operation operation = Operation.fromWireName(entry.getKey());
            if (operation == null) {
                throw new IllegalArgumentException(ERROR_FIELD_UNSUPPORTED + entry.getKey());
            }
            if (resolvedOperation != null) {
                throw new IllegalArgumentException(ERROR_OPERATION_MULTIPLE);
            }
            if (!(entry.getValue() instanceof Map)) {
                throw new IllegalArgumentException(ERROR_PAYLOAD_REQUIRED);
            }
            resolvedOperation = operation;
            resolvedPayload = castMap(entry.getValue());
        }
        if (resolvedOperation == null) {
            throw new IllegalArgumentException(ERROR_OPERATION_REQUIRED);
        }
        return new A2uiProtocolMessage(version, resolvedOperation, resolvedPayload);
    }

    /** 将强类型信封还原成A2UI v0.9.1 wire对象。 */
    public Map<String, Object> toMap() {
        Map<String, Object> message = new LinkedHashMap<>();
        message.put(FIELD_VERSION, version);
        message.put(operation.getWireName(), new LinkedHashMap<>(payload));
        return message;
    }

    /** 在公共Ledger、Snapshot或SSE边界批量恢复wire消息。 */
    public static List<Map<String, Object>> toMaps(List<A2uiProtocolMessage> messages) {
        List<Map<String, Object>> wireMessages = new ArrayList<>(messages.size());
        for (A2uiProtocolMessage message : messages) {
            wireMessages.add(message.toMap());
        }
        return Collections.unmodifiableList(wireMessages);
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> castMap(Object value) {
        return (Map<String, Object>) value;
    }

    /** A2UI v0.9.1当前允许进入Runtime Ledger的四类消息操作。 */
    @Getter
    public enum Operation {
        CREATE_SURFACE("createSurface"),
        UPDATE_COMPONENTS("updateComponents"),
        UPDATE_DATA_MODEL("updateDataModel"),
        DELETE_SURFACE("deleteSurface");

        private final String wireName;

        Operation(String wireName) {
            this.wireName = wireName;
        }

        private static Operation fromWireName(String wireName) {
            for (Operation operation : values()) {
                if (operation.wireName.equals(wireName)) {
                    return operation;
                }
            }
            return null;
        }
    }
}
