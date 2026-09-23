package dev.a2flow.management.a2ui.gateway;

import static dev.a2flow.management.a2ui.gateway.A2uiActionGatewayErrorCode.REQUEST_MAPPING_AUTHORITY_FORBIDDEN;
import static dev.a2flow.management.a2ui.gateway.A2uiActionGatewayErrorCode.REQUEST_MAPPING_INVALID;
import static dev.a2flow.management.a2ui.gateway.A2uiActionGatewayErrorCode.TRUSTED_CONTEXT_MISSING;

import java.util.HashSet;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

import com.fasterxml.jackson.core.JsonPointer;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiCompiledRequestMapping;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiMappingSource;
import dev.a2flow.management.a2ui.gateway.A2uiActionGatewayModels.A2uiMappedCapabilityRequest;
import dev.a2flow.management.a2ui.gateway.A2uiActionGatewayModels.A2uiResolvedAction;

/**
 * 已发布 ActionBinding 的确定性 request mapping 执行器。
 *
 * <p>上游只传 closure 已验证的 Action 和服务端可信 context；下游获得精确 CapabilityAction 引用与
 * JSON arguments。本类只支持 Build 中冻结的 JSON Pointer 和受控 source，不执行脚本/表达式/URL，
 * 不补身份默认值，也不选择 Capability transport 或 Adviser route。
 */
public class A2uiActionRequestMapper {

    private static final Set<String> AUTHORITY_TARGET_SEGMENTS = Set.of(
            "sellerid", "client", "operator", "environment", "credential", "credentials",
            "credentialhandle", "transportauthority", "targetendpoint", "url", "host");

    /** 完整执行当前 binding 的映射；任一 mapping 失败时不返回部分 arguments。 */
    public A2uiMappedCapabilityRequest map(A2uiResolvedAction resolved,
            Map<String, Object> trustedContext) {
        if (resolved == null || resolved.getBinding() == null
                || resolved.getBinding().getCapability() == null
                || resolved.getBinding().getRequestMappings() == null
                || trustedContext == null) {
            throw new A2uiActionGatewayException(REQUEST_MAPPING_INVALID);
        }
        ObjectNode output = JsonSupport.mapper().createObjectNode();
        Set<String> targetPaths = new HashSet<>();
        for (A2uiCompiledRequestMapping mapping : resolved.getBinding().getRequestMappings()) {
            validateMapping(mapping, targetPaths);
            JsonNode value = resolveSource(mapping, resolved.getActionContext(), trustedContext);
            write(output, compilePointer(mapping.getTargetPath()), value);
        }
        return new A2uiMappedCapabilityRequest(
                resolved.getBinding().getCapability(), A2uiGatewayJsonSupport.immutableMap(output));
    }

    private void validateMapping(A2uiCompiledRequestMapping mapping, Set<String> targetPaths) {
        if (mapping == null || mapping.getSource() == null || isBlank(mapping.getTargetPath())
                || !targetPaths.add(mapping.getTargetPath())) {
            throw new A2uiActionGatewayException(REQUEST_MAPPING_INVALID);
        }
        compilePointer(mapping.getTargetPath());
        if (mapping.getSource() != A2uiMappingSource.TRUSTED_CONTEXT
                && containsAuthoritySegment(mapping.getTargetPath())) {
            throw new A2uiActionGatewayException(REQUEST_MAPPING_AUTHORITY_FORBIDDEN);
        }
        if (mapping.getSource() == A2uiMappingSource.CONSTANT) {
            if (!isBlank(mapping.getSourcePath())) {
                throw new A2uiActionGatewayException(REQUEST_MAPPING_INVALID);
            }
        } else if (mapping.getSource() == A2uiMappingSource.CAPABILITY_PREVIOUS_RESULT
                || isBlank(mapping.getSourcePath())) {
            throw new A2uiActionGatewayException(REQUEST_MAPPING_INVALID);
        }
    }

    private JsonNode resolveSource(A2uiCompiledRequestMapping mapping,
            Map<String, Object> actionContext, Map<String, Object> trustedContext) {
        if (mapping.getSource() == A2uiMappingSource.CONSTANT) {
            return A2uiGatewayJsonSupport.toNode(mapping.getConstantValue());
        }
        JsonPointer sourcePointer = compilePointer(mapping.getSourcePath());
        Map<String, Object> source = mapping.getSource() == A2uiMappingSource.TRUSTED_CONTEXT
                ? trustedContext : actionContext;
        JsonNode value = A2uiGatewayJsonSupport.toNode(source).at(sourcePointer);
        if (value.isMissingNode()) {
            A2uiActionGatewayErrorCode error = mapping.getSource() == A2uiMappingSource.TRUSTED_CONTEXT
                    ? TRUSTED_CONTEXT_MISSING : REQUEST_MAPPING_INVALID;
            throw new A2uiActionGatewayException(error, mapping.getSourcePath());
        }
        return value.deepCopy();
    }

    private JsonPointer compilePointer(String path) {
        if (isBlank(path) || !path.startsWith("/")) {
            throw new A2uiActionGatewayException(REQUEST_MAPPING_INVALID);
        }
        try {
            return JsonPointer.compile(path);
        } catch (IllegalArgumentException e) {
            throw new A2uiActionGatewayException(REQUEST_MAPPING_INVALID);
        }
    }

    private void write(ObjectNode root, JsonPointer pointer, JsonNode value) {
        JsonNode current = root;
        JsonPointer remaining = pointer;
        while (!remaining.matches()) {
            JsonPointer tail = remaining.tail();
            boolean leaf = tail.matches();
            if (current instanceof ObjectNode) {
                current = writeObject((ObjectNode) current, remaining, tail, value, leaf);
            } else if (current instanceof ArrayNode) {
                current = writeArray((ArrayNode) current, remaining, tail, value, leaf);
            } else {
                throw new A2uiActionGatewayException(REQUEST_MAPPING_INVALID);
            }
            remaining = tail;
        }
    }

    private JsonNode writeObject(ObjectNode current, JsonPointer pointer,
            JsonPointer tail, JsonNode value, boolean leaf) {
        String property = pointer.getMatchingProperty();
        if (property == null) {
            throw new A2uiActionGatewayException(REQUEST_MAPPING_INVALID);
        }
        if (leaf) {
            current.set(property, value);
            return value;
        }
        JsonNode child = current.get(property);
        if (child == null) {
            child = newContainer(tail);
            current.set(property, child);
        }
        if (!child.isContainerNode()) {
            throw new A2uiActionGatewayException(REQUEST_MAPPING_INVALID);
        }
        return child;
    }

    private JsonNode writeArray(ArrayNode current, JsonPointer pointer,
            JsonPointer tail, JsonNode value, boolean leaf) {
        int index = pointer.getMatchingIndex();
        if (index < 0 || index > current.size()) {
            throw new A2uiActionGatewayException(REQUEST_MAPPING_INVALID);
        }
        if (leaf) {
            if (index == current.size()) {
                current.add(value);
            } else {
                current.set(index, value);
            }
            return value;
        }
        if (index == current.size()) {
            JsonNode child = newContainer(tail);
            current.add(child);
            return child;
        }
        JsonNode child = current.get(index);
        if (!child.isContainerNode()) {
            throw new A2uiActionGatewayException(REQUEST_MAPPING_INVALID);
        }
        return child;
    }

    private JsonNode newContainer(JsonPointer pointer) {
        return pointer.mayMatchElement()
                ? JsonSupport.mapper().createArrayNode()
                : JsonSupport.mapper().createObjectNode();
    }

    private boolean containsAuthoritySegment(String path) {
        JsonPointer pointer = compilePointer(path);
        while (!pointer.matches()) {
            String segment = pointer.getMatchingProperty();
            if (segment != null && AUTHORITY_TARGET_SEGMENTS.contains(normalize(segment))) {
                return true;
            }
            pointer = pointer.tail();
        }
        return false;
    }

    private String normalize(String value) {
        return value.replace("_", "")
                .replace("-", "")
                .toLowerCase(Locale.ROOT);
    }

    private boolean isBlank(String value) {
        return value == null || value.trim().isEmpty();
    }
}
