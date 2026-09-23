package dev.a2flow.management.a2ui.gateway;

import static dev.a2flow.management.a2ui.gateway.A2uiActionGatewayErrorCode.ACTION_CONTEXT_AUTHORITY_FORBIDDEN;
import static dev.a2flow.management.a2ui.gateway.A2uiActionGatewayErrorCode.ACTION_CONTEXT_INVALID;

import java.nio.charset.StandardCharsets;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

import dev.a2flow.management.support.JsonSupport;
import com.networknt.schema.Error;
import com.networknt.schema.Schema;
import com.networknt.schema.SchemaRegistry;
import com.networknt.schema.SpecificationVersion;

/**
 * 已发布 ActionBinding context schema 与输入资源门禁。
 *
 * <p>上游传入客户端不可信 context 和 Build 内冻结 schema；本类复用 NetworkNT Draft 7 validator，
 * 返回稳定错误码与安全 Pointer。它不补默认身份、不把业务同名字段升级为 authority，也不记录原始值。
 */
final class A2uiActionContextValidator {

    private static final int MAX_CONTEXT_BYTES = 64 * 1024;
    private static final int MAX_CONTEXT_DEPTH = 32;
    private static final String ROOT_POINTER = "/";
    private static final Set<String> FORBIDDEN_AUTHORITY_KEYS = Set.of(
            "authorization", "cookie", "credential", "credentials", "credentialhandle",
            "environment", "transportauthority", "targetendpoint", "url", "host");
    private static final SchemaRegistry SCHEMA_REGISTRY =
            SchemaRegistry.withDefaultDialect(SpecificationVersion.DRAFT_7);

    /** 校验完整 context；任一结构/schema/authority 失败均不返回部分结果。 */
    void validate(Map<String, Object> context, Map<String, Object> schema) {
        if (context == null || schema == null) {
            throw new A2uiActionGatewayException(ACTION_CONTEXT_INVALID, ROOT_POINTER);
        }
        byte[] serialized = JsonSupport.toJSON(context).getBytes(StandardCharsets.UTF_8);
        if (serialized.length > MAX_CONTEXT_BYTES || depth(context, 1) > MAX_CONTEXT_DEPTH) {
            throw new A2uiActionGatewayException(ACTION_CONTEXT_INVALID, ROOT_POINTER);
        }
        validateAuthorityKeys(context);
        try {
            Schema compiled = SCHEMA_REGISTRY.getSchema(A2uiGatewayJsonSupport.toNode(schema));
            List<Error> errors = compiled.validate(A2uiGatewayJsonSupport.toNode(context));
            if (!errors.isEmpty()) {
                Error first = errors.stream()
                        .min(Comparator.comparing(value -> value.getInstanceLocation().toString()))
                        .orElse(errors.get(0));
                throw new A2uiActionGatewayException(
                        ACTION_CONTEXT_INVALID, safePointer(first.getInstanceLocation().toString()));
            }
        } catch (A2uiActionGatewayException e) {
            throw e;
        } catch (RuntimeException e) {
            throw new A2uiActionGatewayException(ACTION_CONTEXT_INVALID, ROOT_POINTER);
        }
    }

    private void validateAuthorityKeys(Object value) {
        if (value instanceof Map) {
            for (Map.Entry<?, ?> entry : ((Map<?, ?>) value).entrySet()) {
                String key = normalize(String.valueOf(entry.getKey()));
                if (FORBIDDEN_AUTHORITY_KEYS.contains(key)) {
                    throw new A2uiActionGatewayException(ACTION_CONTEXT_AUTHORITY_FORBIDDEN);
                }
                validateAuthorityKeys(entry.getValue());
            }
        } else if (value instanceof List) {
            for (Object child : (List<?>) value) {
                validateAuthorityKeys(child);
            }
        }
    }

    private int depth(Object value, int currentDepth) {
        int maxDepth = currentDepth;
        if (value instanceof Map) {
            for (Object child : ((Map<?, ?>) value).values()) {
                maxDepth = Math.max(maxDepth, depth(child, currentDepth + 1));
            }
        } else if (value instanceof List) {
            for (Object child : (List<?>) value) {
                maxDepth = Math.max(maxDepth, depth(child, currentDepth + 1));
            }
        }
        return maxDepth;
    }

    private String normalize(String value) {
        return value.replace("_", "")
                .replace("-", "")
                .toLowerCase(Locale.ROOT);
    }

    private String safePointer(String location) {
        if (location == null || location.isEmpty() || "$".equals(location)) {
            return ROOT_POINTER;
        }
        if (location.startsWith("/")) {
            return location;
        }
        if (location.startsWith("$.")) {
            return "/" + location.substring(2).replace(".", "/");
        }
        return ROOT_POINTER;
    }
}
