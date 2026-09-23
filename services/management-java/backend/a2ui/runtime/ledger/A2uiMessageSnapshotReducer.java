package dev.a2flow.management.a2ui.runtime.ledger;

import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.apache.commons.lang3.StringUtils;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.JsonNodeFactory;
import com.fasterxml.jackson.databind.node.ObjectNode;
import dev.a2flow.management.a2ui.runtime.ledger.A2uiRuntimeSurfaceLedger.SurfaceState;

/**
 * A2UI v0.9.1 消息到 A2Flow canonical snapshot 的纯领域 reducer。
 *
 * <p>上游传入当前已提交账本和一个完整消息批次，本类在隔离副本上顺序执行
 * createSurface、updateComponents、updateDataModel、deleteSurface，全部成功后返回新账本。
 * 输出快照按 Surface 创建顺序稳定编码为可从空 MessageProcessor 回放的自包含消息。
 * 本类不做 DB/SSE、Catalog 发布校验、CapabilityAction 执行或旧渲染协议转换。</p>
 */
public class A2uiMessageSnapshotReducer {

    private static final ObjectMapper OBJECT_MAPPER = new ObjectMapper();

    private static final String PROTOCOL_VERSION = "v0.9.1";
    private static final String FIELD_VERSION = "version";
    private static final String FIELD_SURFACE_ID = "surfaceId";
    private static final String FIELD_COMPONENTS = "components";
    private static final String FIELD_COMPONENT_ID = "id";
    private static final String FIELD_PATH = "path";
    private static final String FIELD_VALUE = "value";
    private static final String MESSAGE_CREATE_SURFACE = "createSurface";
    private static final String MESSAGE_UPDATE_COMPONENTS = "updateComponents";
    private static final String MESSAGE_UPDATE_DATA_MODEL = "updateDataModel";
    private static final String MESSAGE_DELETE_SURFACE = "deleteSurface";
    private static final String ROOT_DATA_MODEL_PATH = "/";

    private static final int MAX_BATCH_MESSAGES = 256;
    private static final int MAX_SURFACES = 64;
    private static final int MAX_COMPONENTS_PER_SURFACE = 4096;
    private static final int MAX_JSON_POINTER_LENGTH = 1024;
    private static final int MAX_JSON_POINTER_DEPTH = 64;
    private static final int MAX_SNAPSHOT_BYTES = 1024 * 1024;

    private static final Set<String> SUPPORTED_MESSAGE_TYPES = Collections.unmodifiableSet(
            new HashSet<>(Arrays.asList(MESSAGE_CREATE_SURFACE, MESSAGE_UPDATE_COMPONENTS,
                    MESSAGE_UPDATE_DATA_MODEL, MESSAGE_DELETE_SURFACE)));

    /**
     * 在 staging ledger 上原子应用一个完整批次；任意消息非法时抛错且不修改 current。
     */
    public A2uiRuntimeSurfaceLedger reduce(A2uiRuntimeSurfaceLedger current,
            List<Map<String, Object>> batch) {
        if (current == null) {
            throw new A2uiSnapshotException("current ledger is required");
        }
        if (batch == null || batch.isEmpty()) {
            throw new A2uiSnapshotException("A2UI message batch is required");
        }
        if (batch.size() > MAX_BATCH_MESSAGES) {
            throw new A2uiSnapshotException("A2UI message batch exceeds limit: " + batch.size());
        }

        A2uiRuntimeSurfaceLedger staging = current.copy();
        for (int index = 0; index < batch.size(); index++) {
            applyMessage(staging, batch.get(index), index);
        }
        validateLedgerBounds(staging);
        assertSnapshotSize(toSnapshotMessages(staging));
        return staging;
    }

    /**
     * 将账本稳定编码为自包含消息；组件树和 data model 都是当前态，不包含历史增量。
     */
    public List<Map<String, Object>> toSnapshotMessages(A2uiRuntimeSurfaceLedger ledger) {
        if (ledger == null) {
            throw new A2uiSnapshotException("ledger is required");
        }
        List<Map<String, Object>> messages = new ArrayList<>();
        for (SurfaceState surface : ledger.surfaces().values()) {
            messages.add(message(surface.getProtocolVersion(), MESSAGE_CREATE_SURFACE,
                    surface.getCreateSurface()));
            if (!surface.getComponents().isEmpty()) {
                Map<String, Object> componentBody = new LinkedHashMap<>();
                componentBody.put(FIELD_SURFACE_ID, surface.getCreateSurface().get(FIELD_SURFACE_ID));
                List<Map<String, Object>> components = new ArrayList<>();
                surface.getComponents().values().forEach(component ->
                        components.add(A2uiRuntimeSurfaceLedger.copyMap(component)));
                componentBody.put(FIELD_COMPONENTS, components);
                messages.add(message(surface.getProtocolVersion(), MESSAGE_UPDATE_COMPONENTS, componentBody));
            }
            if (surface.isDataModelDefined()) {
                Map<String, Object> dataBody = new LinkedHashMap<>();
                dataBody.put(FIELD_SURFACE_ID, surface.getCreateSurface().get(FIELD_SURFACE_ID));
                dataBody.put(FIELD_PATH, ROOT_DATA_MODEL_PATH);
                dataBody.put(FIELD_VALUE, OBJECT_MAPPER.convertValue(surface.getDataModel(), Object.class));
                messages.add(message(surface.getProtocolVersion(), MESSAGE_UPDATE_DATA_MODEL, dataBody));
            }
        }
        assertSnapshotSize(messages);
        return messages;
    }

    private void applyMessage(A2uiRuntimeSurfaceLedger ledger, Map<String, Object> message, int index) {
        if (message == null) {
            throw invalid(index, "message is null");
        }
        Object version = message.get(FIELD_VERSION);
        if (!PROTOCOL_VERSION.equals(version)) {
            throw invalid(index, "unsupported version: " + version);
        }
        String messageType = resolveMessageType(message, index);
        Map<String, Object> body = asMap(message.get(messageType), index, messageType + " body");
        String surfaceId = requiredString(body.get(FIELD_SURFACE_ID), index, FIELD_SURFACE_ID);
        switch (messageType) {
            case MESSAGE_CREATE_SURFACE:
                applyCreateSurface(ledger, surfaceId, version.toString(), body, index);
                break;
            case MESSAGE_UPDATE_COMPONENTS:
                applyUpdateComponents(ledger, surfaceId, body, index);
                break;
            case MESSAGE_UPDATE_DATA_MODEL:
                applyUpdateDataModel(ledger, surfaceId, body, index);
                break;
            case MESSAGE_DELETE_SURFACE:
                applyDeleteSurface(ledger, surfaceId, index);
                break;
            default:
                throw invalid(index, "unsupported message type: " + messageType);
        }
    }

    private String resolveMessageType(Map<String, Object> message, int index) {
        String resolved = null;
        for (String key : message.keySet()) {
            if (FIELD_VERSION.equals(key)) {
                continue;
            }
            if (!SUPPORTED_MESSAGE_TYPES.contains(key)) {
                throw invalid(index, "unsupported message type: " + key);
            }
            if (resolved != null) {
                throw invalid(index, "message contains multiple operations");
            }
            resolved = key;
        }
        if (resolved == null) {
            throw invalid(index, "message operation is required");
        }
        return resolved;
    }

    private void applyCreateSurface(A2uiRuntimeSurfaceLedger ledger, String surfaceId, String version,
            Map<String, Object> body, int index) {
        if (ledger.surfaces().containsKey(surfaceId)) {
            throw invalid(index, "surface already exists: " + surfaceId);
        }
        ledger.surfaces().put(surfaceId, new SurfaceState(version, body));
    }

    private void applyUpdateComponents(A2uiRuntimeSurfaceLedger ledger, String surfaceId,
            Map<String, Object> body, int index) {
        SurfaceState surface = requiredSurface(ledger, surfaceId, index);
        Object rawComponents = body.get(FIELD_COMPONENTS);
        if (!(rawComponents instanceof List)) {
            throw invalid(index, "components must be an array");
        }
        Set<String> currentBatchIds = new HashSet<>();
        for (Object rawComponent : (List<?>) rawComponents) {
            Map<String, Object> component = asMap(rawComponent, index, "component");
            String componentId = requiredString(component.get(FIELD_COMPONENT_ID), index, FIELD_COMPONENT_ID);
            if (!currentBatchIds.add(componentId)) {
                throw invalid(index, "duplicate component id in batch: " + componentId);
            }
            surface.getComponents().put(componentId, A2uiRuntimeSurfaceLedger.copyMap(component));
        }
    }

    private void applyUpdateDataModel(A2uiRuntimeSurfaceLedger ledger, String surfaceId,
            Map<String, Object> body, int index) {
        SurfaceState surface = requiredSurface(ledger, surfaceId, index);
        String path = requiredString(body.get(FIELD_PATH), index, FIELD_PATH);
        if (!body.containsKey(FIELD_VALUE)) {
            throw invalid(index, "updateDataModel value is required");
        }
        JsonNode value = OBJECT_MAPPER.valueToTree(body.get(FIELD_VALUE));
        if (ROOT_DATA_MODEL_PATH.equals(path)) {
            surface.setDataModel(value.deepCopy());
            return;
        }
        JsonNode current = surface.isDataModelDefined()
                ? surface.getDataModel().deepCopy() : JsonNodeFactory.instance.objectNode();
        surface.setDataModel(setJsonPointer(current, path, value, index));
    }

    private void applyDeleteSurface(A2uiRuntimeSurfaceLedger ledger, String surfaceId, int index) {
        if (ledger.surfaces().remove(surfaceId) == null) {
            throw invalid(index, "surface does not exist: " + surfaceId);
        }
    }

    private JsonNode setJsonPointer(JsonNode root, String path, JsonNode value, int messageIndex) {
        if (!path.startsWith(ROOT_DATA_MODEL_PATH) || path.length() > MAX_JSON_POINTER_LENGTH) {
            throw invalid(messageIndex, "invalid data model path: " + path);
        }
        String[] rawTokens = path.substring(1).split(ROOT_DATA_MODEL_PATH, -1);
        if (rawTokens.length == 0 || rawTokens.length > MAX_JSON_POINTER_DEPTH) {
            throw invalid(messageIndex, "data model path depth is invalid");
        }
        JsonNode mutableRoot = root;
        if (!mutableRoot.isContainerNode()) {
            throw invalid(messageIndex, "data model root is not a container");
        }
        JsonNode parent = mutableRoot;
        for (int tokenIndex = 0; tokenIndex < rawTokens.length - 1; tokenIndex++) {
            String token = decodePointerToken(rawTokens[tokenIndex], messageIndex);
            String nextToken = decodePointerToken(rawTokens[tokenIndex + 1], messageIndex);
            parent = childContainer(parent, token, nextToken, messageIndex);
        }
        setChild(parent, decodePointerToken(rawTokens[rawTokens.length - 1], messageIndex), value, messageIndex);
        return mutableRoot;
    }

    private JsonNode childContainer(JsonNode parent, String token, String nextToken, int messageIndex) {
        if (parent.isObject()) {
            ObjectNode objectNode = (ObjectNode) parent;
            JsonNode child = objectNode.get(token);
            if (child == null || child.isNull()) {
                child = isArrayIndex(nextToken)
                        ? JsonNodeFactory.instance.arrayNode() : JsonNodeFactory.instance.objectNode();
                objectNode.set(token, child);
            }
            if (!child.isContainerNode()) {
                throw invalid(messageIndex, "data model path crosses scalar: " + token);
            }
            return child;
        }
        if (parent.isArray()) {
            ArrayNode arrayNode = (ArrayNode) parent;
            int arrayIndex = parseArrayIndex(token, messageIndex);
            if (arrayIndex > arrayNode.size()) {
                throw invalid(messageIndex, "data model array index has a gap: " + token);
            }
            if (arrayIndex == arrayNode.size()) {
                JsonNode created = isArrayIndex(nextToken)
                        ? JsonNodeFactory.instance.arrayNode() : JsonNodeFactory.instance.objectNode();
                arrayNode.add(created);
                return created;
            }
            JsonNode child = arrayNode.get(arrayIndex);
            if (child == null || child.isNull()) {
                child = isArrayIndex(nextToken)
                        ? JsonNodeFactory.instance.arrayNode() : JsonNodeFactory.instance.objectNode();
                arrayNode.set(arrayIndex, child);
            }
            if (!child.isContainerNode()) {
                throw invalid(messageIndex, "data model path crosses scalar: " + token);
            }
            return child;
        }
        throw invalid(messageIndex, "data model path parent is not a container");
    }

    private void setChild(JsonNode parent, String token, JsonNode value, int messageIndex) {
        JsonNode copiedValue = value.deepCopy();
        if (parent.isObject()) {
            ((ObjectNode) parent).set(token, copiedValue);
            return;
        }
        if (parent.isArray()) {
            ArrayNode arrayNode = (ArrayNode) parent;
            int arrayIndex = parseArrayIndex(token, messageIndex);
            if (arrayIndex > arrayNode.size()) {
                throw invalid(messageIndex, "data model array index has a gap: " + token);
            }
            if (arrayIndex == arrayNode.size()) {
                arrayNode.add(copiedValue);
            } else {
                arrayNode.set(arrayIndex, copiedValue);
            }
            return;
        }
        throw invalid(messageIndex, "data model path parent is not a container");
    }

    private String decodePointerToken(String token, int messageIndex) {
        StringBuilder decoded = new StringBuilder();
        for (int index = 0; index < token.length(); index++) {
            char current = token.charAt(index);
            if (current != '~') {
                decoded.append(current);
                continue;
            }
            if (index + 1 >= token.length()) {
                throw invalid(messageIndex, "invalid JSON Pointer escape");
            }
            char escaped = token.charAt(++index);
            if (escaped == '0') {
                decoded.append('~');
            } else if (escaped == '1') {
                decoded.append('/');
            } else {
                throw invalid(messageIndex, "invalid JSON Pointer escape: ~" + escaped);
            }
        }
        return decoded.toString();
    }

    private boolean isArrayIndex(String token) {
        if (StringUtils.isBlank(token)) {
            return false;
        }
        for (int index = 0; index < token.length(); index++) {
            if (!Character.isDigit(token.charAt(index))) {
                return false;
            }
        }
        return true;
    }

    private int parseArrayIndex(String token, int messageIndex) {
        if (!isArrayIndex(token)) {
            throw invalid(messageIndex, "invalid data model array index: " + token);
        }
        try {
            return Integer.parseInt(token);
        } catch (NumberFormatException exception) {
            throw invalid(messageIndex, "data model array index is too large: " + token, exception);
        }
    }

    private SurfaceState requiredSurface(A2uiRuntimeSurfaceLedger ledger, String surfaceId, int index) {
        SurfaceState surface = ledger.surfaces().get(surfaceId);
        if (surface == null) {
            throw invalid(index, "surface does not exist: " + surfaceId);
        }
        return surface;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> asMap(Object value, int index, String field) {
        if (!(value instanceof Map)) {
            throw invalid(index, field + " must be an object");
        }
        return (Map<String, Object>) value;
    }

    private String requiredString(Object value, int index, String field) {
        String stringValue = value == null ? null : String.valueOf(value);
        if (StringUtils.isBlank(stringValue)) {
            throw invalid(index, field + " is required");
        }
        return stringValue;
    }

    private void validateLedgerBounds(A2uiRuntimeSurfaceLedger ledger) {
        if (ledger.surfaces().size() > MAX_SURFACES) {
            throw new A2uiSnapshotException("A2UI surface count exceeds limit: " + ledger.surfaces().size());
        }
        for (Map.Entry<String, SurfaceState> entry : ledger.surfaces().entrySet()) {
            if (entry.getValue().getComponents().size() > MAX_COMPONENTS_PER_SURFACE) {
                throw new A2uiSnapshotException("A2UI component count exceeds limit, surfaceId=" + entry.getKey());
            }
        }
    }

    private Map<String, Object> message(String version, String type, Map<String, Object> body) {
        Map<String, Object> message = new LinkedHashMap<>();
        message.put(FIELD_VERSION, version);
        message.put(type, A2uiRuntimeSurfaceLedger.copyMap(body));
        return message;
    }

    private void assertSnapshotSize(List<Map<String, Object>> messages) {
        try {
            int bytes = OBJECT_MAPPER.writeValueAsString(messages).getBytes(StandardCharsets.UTF_8).length;
            if (bytes > MAX_SNAPSHOT_BYTES) {
                throw new A2uiSnapshotException("A2UI snapshot exceeds byte limit: " + bytes);
            }
        } catch (JsonProcessingException exception) {
            throw new A2uiSnapshotException("A2UI snapshot serialization failed", exception);
        }
    }

    private A2uiSnapshotException invalid(int index, String detail) {
        return new A2uiSnapshotException("invalid A2UI message at index " + index + ": " + detail);
    }

    private A2uiSnapshotException invalid(int index, String detail, Throwable cause) {
        return new A2uiSnapshotException("invalid A2UI message at index " + index + ": " + detail, cause);
    }
}
