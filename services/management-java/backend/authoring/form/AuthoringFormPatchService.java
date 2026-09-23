package dev.a2flow.management.authoring.form;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;

import jakarta.annotation.Resource;

import org.apache.commons.collections4.MapUtils;
import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.event.AiCodingEventPayload;
import dev.a2flow.management.event.AiCodingEventPayloadFactory;

import lombok.extern.slf4j.Slf4j;

/**
 * SkillFactory 通用表单修改提案服务。
 *
 * <p>上游是模型可调用的 {@code propose_form_patch} Tool，下游是前端统一修改审阅。
 * 本服务从可信 ToolContext 读取 formKey、entityId、revision 和 currentDraft，通过领域 provider
 * 校验 RFC 6902 子集并生成 FORM_PATCH_PROPOSED；它不保存业务表单、不写 DB、不改 workspace。
 */
@Service
@Slf4j
public class AuthoringFormPatchService {

    public static final String TOOL_PROPOSE_FORM_PATCH = "propose_form_patch";
    public static final String PAYLOAD_FORM_PATCH_PROPOSED = "FORM_PATCH_PROPOSED";

    private static final String FIELD_AUTHORING_DOMAIN = "authoringDomain";
    private static final String FIELD_FORM_KEY = "formKey";
    private static final String FIELD_ENTITY_ID = "entityId";
    private static final String FIELD_REVISION = "revision";
    private static final String FIELD_CURRENT_DRAFT = "currentDraft";
    private static final String FIELD_OPERATIONS = "operations";
    private static final String FIELD_BASE_REVISION = "baseRevision";
    private static final String FIELD_BASE_FINGERPRINT = "baseFingerprint";
    private static final String FIELD_SUMMARY = "summary";
    private static final String FIELD_OP = "op";
    private static final String FIELD_PATH = "path";
    private static final String FIELD_VALUE = "value";
    private static final String FIELD_WORKSPACE_ID = "workspaceId";
    private static final String FIELD_SESSION_ID = "sessionId";
    private static final String FIELD_TRACE_ID = "traceId";
    private static final String OPERATION_REMOVE = "remove";
    private static final String FINGERPRINT_PREFIX = "fnv1a32:";
    private static final int SUMMARY_MAX_LENGTH = 500;
    private static final long FNV_OFFSET_BASIS_32 = 0x811c9dc5L;
    private static final long FNV_PRIME_32 = 0x01000193L;
    private static final long UNSIGNED_INT_MASK = 0xffffffffL;
    private static final Set<String> ALLOWED_OPERATIONS = Set.of("add", "replace", OPERATION_REMOVE);
    private static final Set<String> FORBIDDEN_POINTER_SEGMENTS = Set.of("__proto__", "prototype", "constructor");

    @Resource
    private List<AuthoringFormPatchProvider> formPatchProviders;

    @Resource
    private AiCodingEventPayloadFactory aiCodingEventPayloadFactory;

    /**
     * 校验并生成可审阅的通用表单修改建议，不产生任何持久化副作用。
     */
    public AiCodingEventPayload propose(Map<String, String> context, Map<String, Object> input) {
        String authoringDomain = required(context, FIELD_AUTHORING_DOMAIN);
        String formKey = required(context, FIELD_FORM_KEY);
        String entityId = required(context, FIELD_ENTITY_ID);
        int revision = positiveRevision(context);
        Map<String, Object> currentDraft = parseObject(required(context, FIELD_CURRENT_DRAFT), FIELD_CURRENT_DRAFT);
        AuthoringFormPatchProvider provider = resolveProvider(formKey);
        provider.validateContext(authoringDomain, formKey, entityId, currentDraft);

        List<?> rawOperations = listValue(input.get(FIELD_OPERATIONS));
        if (rawOperations.isEmpty()) {
            throw new IllegalArgumentException("operations is required");
        }
        List<Map<String, Object>> operations = normalizeOperations(
                provider, formKey, entityId, rawOperations);
        String summary = StringUtils.abbreviate(
                StringUtils.defaultString(MapUtils.getString(input, FIELD_SUMMARY)), SUMMARY_MAX_LENGTH);

        Map<String, Object> proposal = new LinkedHashMap<>();
        proposal.put(FIELD_FORM_KEY, formKey);
        proposal.put(FIELD_ENTITY_ID, entityId);
        proposal.put(FIELD_BASE_REVISION, revision);
        proposal.put(FIELD_BASE_FINGERPRINT, draftFingerprint(currentDraft));
        proposal.put(FIELD_OPERATIONS, operations);
        proposal.put(FIELD_SUMMARY, summary);
        log.info("Authoring生成通用表单修改建议, authoringDomain={}, formKey={}, entityId={}, revision={}, "
                        + "operationCount={}, sessionId={}, traceId={}",
                authoringDomain, formKey, entityId, revision, operations.size(), context.get(FIELD_SESSION_ID),
                context.get(FIELD_TRACE_ID));
        return aiCodingEventPayloadFactory.authoringDraftChange(
                eventContext(context, entityId), PAYLOAD_FORM_PATCH_PROPOSED, proposal);
    }

    private List<Map<String, Object>> normalizeOperations(AuthoringFormPatchProvider provider,
            String formKey, String entityId, List<?> rawOperations) {
        List<Map<String, Object>> operations = new ArrayList<>();
        Set<String> changedPaths = new java.util.HashSet<>();
        for (Object rawOperation : rawOperations) {
            Map<String, Object> operation = mapValue(rawOperation);
            String op = StringUtils.lowerCase(MapUtils.getString(operation, FIELD_OP), Locale.ROOT);
            String path = StringUtils.defaultString(MapUtils.getString(operation, FIELD_PATH));
            validateOperation(op, path);
            if (!changedPaths.add(path)) {
                throw new IllegalArgumentException("同一提案不能重复修改 path: " + path);
            }
            Map<String, Object> normalized = new LinkedHashMap<>();
            normalized.put(FIELD_OP, op);
            normalized.put(FIELD_PATH, path);
            Object value = null;
            if (!OPERATION_REMOVE.equals(op)) {
                if (!operation.containsKey(FIELD_VALUE)) {
                    throw new IllegalArgumentException(op + " 操作必须提供 value: " + path);
                }
                value = operation.get(FIELD_VALUE);
            }
            Object sanitizedValue = provider.validateAndSanitizeValue(formKey, entityId, op, path, value);
            if (!OPERATION_REMOVE.equals(op)) {
                normalized.put(FIELD_VALUE, sanitizedValue);
            }
            operations.add(normalized);
        }
        return operations;
    }

    private void validateOperation(String operation, String path) {
        if (!ALLOWED_OPERATIONS.contains(operation)) {
            throw new IllegalArgumentException("form patch op 只允许 add、replace 或 remove");
        }
        if (StringUtils.isBlank(path) || !StringUtils.startsWith(path, "/") || "/".equals(path)) {
            throw new IllegalArgumentException("form patch path 必须是非根节点 JSON Pointer");
        }
        for (String segment : StringUtils.split(path, '/')) {
            String decoded = StringUtils.replace(StringUtils.replace(segment, "~1", "/"), "~0", "~");
            if (FORBIDDEN_POINTER_SEGMENTS.contains(decoded)) {
                throw new IllegalArgumentException("form patch path 包含禁止字段: " + decoded);
            }
        }
    }

    private AuthoringFormPatchProvider resolveProvider(String formKey) {
        return formPatchProviders.stream()
                .filter(provider -> provider.supports(formKey))
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException("未注册的 Authoring formKey: " + formKey));
    }

    private Map<String, String> eventContext(Map<String, String> context, String entityId) {
        Map<String, String> eventContext = new LinkedHashMap<>(context);
        eventContext.put(FIELD_WORKSPACE_ID,
                StringUtils.defaultIfBlank(eventContext.get(FIELD_WORKSPACE_ID), entityId));
        return eventContext;
    }

    private int positiveRevision(Map<String, String> context) {
        try {
            int revision = Integer.parseInt(required(context, FIELD_REVISION));
            if (revision <= 0) {
                throw new IllegalArgumentException("revision 必须大于 0");
            }
            return revision;
        } catch (NumberFormatException e) {
            throw new IllegalArgumentException("revision 必须是正整数", e);
        }
    }

    private String required(Map<String, String> source, String field) {
        String value = source == null ? StringUtils.EMPTY : StringUtils.defaultString(source.get(field));
        if (StringUtils.isBlank(value)) {
            throw new IllegalArgumentException(field + " is required");
        }
        return value;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> parseObject(String json, String field) {
        try {
            Map<String, Object> result = JsonSupport.fromJSON(json, Map.class);
            if (result == null) {
                throw new IllegalArgumentException(field + " 必须是 JSON 对象");
            }
            return result;
        } catch (Exception e) {
            throw new IllegalArgumentException(field + " 必须是合法 JSON 对象", e);
        }
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> mapValue(Object value) {
        return value instanceof Map ? (Map<String, Object>) value : Collections.emptyMap();
    }

    private List<?> listValue(Object value) {
        return value instanceof List ? (List<?>) value : Collections.emptyList();
    }

    private String draftFingerprint(Map<String, Object> currentDraft) {
        String canonicalJson = JsonSupport.toJSON(stableValue(currentDraft));
        long hash = FNV_OFFSET_BASIS_32;
        for (int index = 0; index < canonicalJson.length(); index++) {
            hash ^= canonicalJson.charAt(index);
            hash = (hash * FNV_PRIME_32) & UNSIGNED_INT_MASK;
        }
        return FINGERPRINT_PREFIX + String.format(Locale.ROOT, "%08x", hash);
    }

    private Object stableValue(Object value) {
        if (value instanceof Map) {
            Map<String, Object> sorted = new TreeMap<>();
            mapValue(value).forEach((key, item) -> sorted.put(key, stableValue(item)));
            return sorted;
        }
        if (value instanceof List) {
            return listValue(value).stream().map(this::stableValue).toList();
        }
        return value;
    }
}
