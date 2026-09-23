package dev.a2flow.management.lifecycle;

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
import dev.a2flow.management.model.CapabilityActionValidationResult;

import lombok.extern.slf4j.Slf4j;

/**
 * SkillFactory 结构化 Authoring 草稿变更服务。
 *
 * <p>上游是模型可调用的 `propose_authoring_change` / `validate_capability_draft` Tool，
 * 下游是统一 AI Coding runtime payload 和能力中心前端受控表单。该服务只生成可审阅的快照、
 * RFC 6902 风格增量和只读校验报告，不直接保存草稿、不执行外部接口，也不授予 CapabilityAction
 * 运行权限。未来新增 Authoring 域时应在这里增加明确 provider，而不是复用 Skill 文件 patch。
 */
@Service
@Slf4j
public class AuthoringDraftChangeService {

    public static final String TOOL_PROPOSE_AUTHORING_CHANGE = "propose_authoring_change";
    public static final String TOOL_VALIDATE_CAPABILITY_DRAFT = "validate_capability_draft";

    private static final String DOMAIN_CAPABILITY_CENTER = "CAPABILITY_CENTER";
    private static final String CHANGE_TYPE_SNAPSHOT = "SNAPSHOT";
    private static final String CHANGE_TYPE_PATCH = "PATCH";
    private static final String PAYLOAD_CAPABILITY_DRAFT_SNAPSHOT = "CAPABILITY_DRAFT_SNAPSHOT";
    private static final String PAYLOAD_CAPABILITY_DRAFT_PATCH = "CAPABILITY_DRAFT_PATCH";
    private static final String PAYLOAD_CAPABILITY_VALIDATION_REPORT = "CAPABILITY_VALIDATION_REPORT";
    private static final String FIELD_AUTHORING_DOMAIN = "authoringDomain";
    private static final String FIELD_DRAFT_ID = "draftId";
    private static final String FIELD_REVISION = "revision";
    private static final String FIELD_CURRENT_DRAFT = "currentDraft";
    private static final String FIELD_CHANGE_TYPE = "changeType";
    private static final String FIELD_DRAFT = "draft";
    private static final String FIELD_OPERATIONS = "operations";
    private static final String FIELD_CHANGED_PATHS = "changedPaths";
    private static final String FIELD_BASE_REVISION = "baseRevision";
    private static final String FIELD_RESULT_REVISION = "resultRevision";
    private static final String FIELD_BASE_DRAFT_FINGERPRINT = "baseDraftFingerprint";
    private static final String FIELD_SUMMARY = "summary";
    private static final String FIELD_REVIEW_DELTA = "reviewDelta";
    private static final String FIELD_OP = "op";
    private static final String FIELD_PATH = "path";
    private static final String FIELD_VALUE = "value";
    private static final String FIELD_WORKSPACE_ID = "workspaceId";
    private static final String FIELD_SESSION_ID = "sessionId";
    private static final String FIELD_MESSAGE_ID = "messageId";
    private static final String FIELD_RUN_ID = "runId";
    private static final String FIELD_CONVERSATION_ID = "conversationId";
    private static final String FIELD_TRACE_ID = "traceId";
    private static final long FNV_OFFSET_BASIS_32 = 0x811c9dc5L;
    private static final long FNV_PRIME_32 = 0x01000193L;
    private static final long UNSIGNED_INT_MASK = 0xffffffffL;
    private static final Set<String> ALLOWED_OPERATIONS = Set.of("add", "replace", "remove");
    private static final List<String> ALLOWED_ROOT_PATHS = List.of(
            "/basicInfo", "/supportedClients", "/clientVariants", "/governance");
    private static final Set<String> SUPPORTED_CLIENT_VARIANTS = Set.of("PC", "APP", "COMMON");
    private static final Set<String> CLIENT_TECHNICAL_SECTIONS = Set.of(
            "apiSource", "modelContract", "executionBinding", "resultContract");

    @Resource
    private CapabilityActionDraftService capabilityActionDraftService;

    @Resource
    private AiCodingEventPayloadFactory aiCodingEventPayloadFactory;

    /**
     * 校验并生成模型草稿修改建议，不持久化页面草稿。
     */
    public AiCodingEventPayload propose(Map<String, String> context, Map<String, Object> input) {
        requireCapabilityDomain(context);
        String draftId = required(context, FIELD_DRAFT_ID);
        int revision = positiveRevision(context);
        String changeType = StringUtils.upperCase(MapUtils.getString(input, FIELD_CHANGE_TYPE), Locale.ROOT);
        Map<String, Object> change;
        String payloadType;
        if (CHANGE_TYPE_SNAPSHOT.equals(changeType)) {
            change = snapshotChange(draftId, revision, input);
            payloadType = PAYLOAD_CAPABILITY_DRAFT_SNAPSHOT;
        } else if (CHANGE_TYPE_PATCH.equals(changeType)) {
            change = patchChange(draftId, revision, input);
            payloadType = PAYLOAD_CAPABILITY_DRAFT_PATCH;
        } else {
            throw new IllegalArgumentException("changeType 只允许 SNAPSHOT 或 PATCH");
        }
        String baseDraftFingerprint = draftFingerprint(required(context, FIELD_CURRENT_DRAFT));
        change.put(FIELD_BASE_DRAFT_FINGERPRINT, baseDraftFingerprint);
        log.info("Authoring生成能力草稿修改建议, draftId={}, revision={}, changeType={}, changedPathCount={}, "
                        + "baseDraftFingerprint={}, sessionId={}, traceId={}",
                draftId, revision, changeType, listValue(change.get(FIELD_CHANGED_PATHS)).size(),
                baseDraftFingerprint, context.get(FIELD_SESSION_ID), context.get(FIELD_TRACE_ID));
        return aiCodingEventPayloadFactory.authoringDraftChange(eventContext(context, draftId), payloadType, change);
    }

    /**
     * 对前端传入的当前能力草稿执行只读静态校验。
     */
    public AiCodingEventPayload validateCapabilityDraft(Map<String, String> context) {
        requireCapabilityDomain(context);
        String draftId = required(context, FIELD_DRAFT_ID);
        int revision = positiveRevision(context);
        Map<String, Object> currentDraft = parseObject(required(context, FIELD_CURRENT_DRAFT), FIELD_CURRENT_DRAFT);
        CapabilityActionValidationResult result =
                capabilityActionDraftService.validateAuthoringDraft(draftId, revision, currentDraft);
        Map<String, Object> validation = parseObject(JsonSupport.toJSON(result), "validationResult");
        log.info("Authoring能力草稿静态校验完成, draftId={}, revision={}, valid={}, errorCount={}, traceId={}",
                draftId, revision, result.getValid(), result.getErrors().size(), context.get(FIELD_TRACE_ID));
        return aiCodingEventPayloadFactory.capabilityDraftValidated(
                eventContext(context, draftId), PAYLOAD_CAPABILITY_VALIDATION_REPORT, validation);
    }

    private Map<String, Object> snapshotChange(String draftId, int revision, Map<String, Object> input) {
        Map<String, Object> proposedDraft = mapValue(input.get(FIELD_DRAFT));
        if (proposedDraft.isEmpty()) {
            throw new IllegalArgumentException("SNAPSHOT 必须提供 draft 对象");
        }
        Map<String, Object> canonical = capabilityActionDraftService.canonicalizeAuthoringDraft(proposedDraft);
        Map<String, Object> change = baseChange(draftId, revision, input);
        change.put(FIELD_DRAFT, canonical);
        change.put(FIELD_CHANGED_PATHS, new ArrayList<>(ALLOWED_ROOT_PATHS));
        return change;
    }

    private Map<String, Object> patchChange(String draftId, int revision, Map<String, Object> input) {
        List<?> rawOperations = listValue(input.get(FIELD_OPERATIONS));
        if (rawOperations.isEmpty()) {
            throw new IllegalArgumentException("PATCH 必须提供 operations");
        }
        List<Map<String, Object>> operations = new ArrayList<>();
        List<String> changedPaths = new ArrayList<>();
        for (Object rawOperation : rawOperations) {
            Map<String, Object> operation = mapValue(rawOperation);
            String op = StringUtils.lowerCase(MapUtils.getString(operation, FIELD_OP), Locale.ROOT);
            String path = MapUtils.getString(operation, FIELD_PATH);
            validateOperation(op, path);
            Map<String, Object> normalized = new LinkedHashMap<>();
            normalized.put(FIELD_OP, op);
            normalized.put(FIELD_PATH, path);
            if (!"remove".equals(op)) {
                normalized.put(FIELD_VALUE,
                        capabilityActionDraftService.sanitizeAuthoringValue(operation.get(FIELD_VALUE)));
            }
            operations.add(normalized);
            changedPaths.add(path);
        }
        Map<String, Object> change = baseChange(draftId, revision, input);
        change.put(FIELD_OPERATIONS, operations);
        change.put(FIELD_CHANGED_PATHS, changedPaths);
        return change;
    }

    private Map<String, Object> baseChange(String draftId, int revision, Map<String, Object> input) {
        Map<String, Object> change = new LinkedHashMap<>();
        change.put(FIELD_DRAFT_ID, draftId);
        change.put(FIELD_BASE_REVISION, revision);
        change.put(FIELD_RESULT_REVISION, revision + 1);
        change.put(FIELD_SUMMARY, StringUtils.defaultString(MapUtils.getString(input, FIELD_SUMMARY)));
        List<String> reviewDelta = listValue(input.get(FIELD_REVIEW_DELTA)).stream()
                .map(String::valueOf)
                .filter(StringUtils::isNotBlank)
                .toList();
        change.put(FIELD_REVIEW_DELTA, reviewDelta);
        return change;
    }

    private Map<String, String> eventContext(Map<String, String> context, String draftId) {
        Map<String, String> eventContext = new LinkedHashMap<>(context);
        eventContext.put(FIELD_WORKSPACE_ID,
                StringUtils.defaultIfBlank(eventContext.get(FIELD_WORKSPACE_ID), draftId));
        return eventContext;
    }

    private void validateOperation(String op, String path) {
        if (!ALLOWED_OPERATIONS.contains(op)) {
            throw new IllegalArgumentException("patch op 只允许 add、replace 或 remove");
        }
        if (!isAllowedPatchPath(path)) {
            throw new IllegalArgumentException("patch path 不在能力草稿允许范围内: " + path);
        }
        String root = ALLOWED_ROOT_PATHS.stream().filter(
                allowed -> StringUtils.equals(path, allowed) || StringUtils.startsWith(path, allowed + "/"))
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException("patch path 不在能力草稿允许范围内: " + path));
        if ("remove".equals(op) && StringUtils.equals(path, root)) {
            throw new IllegalArgumentException("不能删除能力草稿顶层 section: " + path);
        }
    }

    /**
     * 校验能力草稿公共字段和端侧技术契约的规范 JSON Pointer，不接受旧根级技术字段或未知端。
     */
    private boolean isAllowedPatchPath(String path) {
        if (StringUtils.isBlank(path) || StringUtils.endsWith(path, "/")) {
            return false;
        }
        if (StringUtils.equals(path, "/basicInfo") || StringUtils.startsWith(path, "/basicInfo/")
                || StringUtils.equals(path, "/governance") || StringUtils.startsWith(path, "/governance/")) {
            return true;
        }
        if (StringUtils.equals(path, "/supportedClients") || StringUtils.equals(path, "/clientVariants")) {
            return true;
        }
        if (!StringUtils.startsWith(path, "/clientVariants/")) {
            return false;
        }
        String[] segments = StringUtils.split(path, '/');
        if (segments.length < 2 || !SUPPORTED_CLIENT_VARIANTS.contains(segments[1])) {
            return false;
        }
        return segments.length == 2 || CLIENT_TECHNICAL_SECTIONS.contains(segments[2]);
    }

    private void requireCapabilityDomain(Map<String, String> context) {
        String domain = StringUtils.upperCase(required(context, FIELD_AUTHORING_DOMAIN), Locale.ROOT);
        if (!DOMAIN_CAPABILITY_CENTER.equals(domain)) {
            throw new IllegalArgumentException("propose_authoring_change 暂不支持 authoringDomain=" + domain);
        }
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

    /**
     * 对模型本轮看到的 currentDraft 计算稳定指纹，供前端匹配请求基线并执行三方 Diff。
     *
     * <p>对象 key 递归排序、数组顺序保持不变，避免普通 JSON Map 顺序差异导致误判。该指纹只用于
     * Authoring 并发保护，不替代服务端 revision 乐观锁，也不包含额外身份或凭证信息。
     */
    private String draftFingerprint(String currentDraftJson) {
        Map<String, Object> currentDraft = parseObject(currentDraftJson, FIELD_CURRENT_DRAFT);
        String canonicalJson = JsonSupport.toJSON(stableValue(currentDraft));
        long hash = FNV_OFFSET_BASIS_32;
        for (int index = 0; index < canonicalJson.length(); index++) {
            hash ^= canonicalJson.charAt(index);
            hash = (hash * FNV_PRIME_32) & UNSIGNED_INT_MASK;
        }
        return String.format(Locale.ROOT, "%08x", hash);
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
