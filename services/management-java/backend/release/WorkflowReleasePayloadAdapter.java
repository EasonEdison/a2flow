package dev.a2flow.management.release;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Component;

import com.fasterxml.jackson.core.JsonProcessingException;
import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.lifecycle.domain.WorkflowReleaseSourceView;
import dev.a2flow.management.lifecycle.domain.graph.CompiledNode;
import dev.a2flow.management.lifecycle.domain.graph.CompiledPlan;
import dev.a2flow.management.lifecycle.domain.graph.WorkflowCompiledPlanBuilder;
import dev.a2flow.management.lifecycle.domain.graph.WorkflowGraphAggregate;
import dev.a2flow.management.lifecycle.domain.graph.WorkflowGraphAggregateParser;
import dev.a2flow.management.lifecycle.domain.graph.WorkflowGraphCompilationException;
import dev.a2flow.management.lifecycle.domain.graph.WorkflowGraphDataException;
import dev.a2flow.management.lifecycle.domain.graph.WorkflowNodeType;
import dev.a2flow.management.release.ReleaseModels.AssetSnapshot;
import dev.a2flow.management.release.dependency.AssetDependencyModels.ResolvedReleasedAsset;

/**
 * Workflow common-v2 冻结 payload 的唯一构造和校验边界。
 *
 * <p>上游发布 Adapter 提供已授权的当前草稿事实，本类使用严格 graph parser 和 compiler 生成完整
 * 自包含 payload；下游发布、递归依赖和历史恢复只读取这里校验通过的不可变正文。校验会重新解析并
 * 编译 graph，逐项核对三层 contract version、compiledPlan 和 canonical digest，不读取当前草稿、
 * latest 版本或环境指针，也不提供 PINNED/TRACK/fallback。
 */
@Component
public class WorkflowReleasePayloadAdapter {

    public static final int PAYLOAD_CONTRACT_VERSION = 1;
    public static final int WORKFLOW_SNAPSHOT_CONTRACT_VERSION =
            WorkflowGraphAggregateParser.SNAPSHOT_CONTRACT_VERSION_V2;
    public static final int COMPILED_PLAN_CONTRACT_VERSION = 1;
    public static final int SUPPORTED_DRAFT_CONTRACT_VERSION = WORKFLOW_SNAPSHOT_CONTRACT_VERSION;

    public static final String ERROR_CODE_RELEASE_SOURCE_INVALID = "WORKFLOW_RELEASE_SOURCE_INVALID";
    public static final String ERROR_CODE_CONTRACT_VERSION_UNSUPPORTED =
            "WORKFLOW_CONTRACT_VERSION_UNSUPPORTED";
    public static final String ERROR_CODE_SNAPSHOT_IDENTITY_INVALID =
            "WORKFLOW_SNAPSHOT_IDENTITY_INVALID";
    public static final String ERROR_CODE_PAYLOAD_INVALID = "WORKFLOW_RELEASE_PAYLOAD_INVALID";

    private static final String FIELD_DRAFT_PAYLOAD_JSON = "draftPayloadJson";
    private static final String FIELD_PAYLOAD = "payload";
    private static final String FIELD_DRAFT_CONTRACT_VERSION = "draftContractVersion";
    private static final String FIELD_PAYLOAD_CONTRACT_VERSION = "payloadContractVersion";
    private static final String FIELD_WORKFLOW_SNAPSHOT_CONTRACT_VERSION = "workflowSnapshotContractVersion";
    private static final String FIELD_COMPILED_PLAN_CONTRACT_VERSION = "compiledPlanContractVersion";
    private static final String FIELD_WORKFLOW_CODE = "workflowCode";
    private static final String FIELD_SPECIALIST_CODE = "specialistCode";
    private static final String FIELD_DRAFT_REVISION = "draftRevision";
    private static final String FIELD_DRAFT_DIGEST = "draftDigest";
    private static final String FIELD_DISPLAY_NAME = "displayName";
    private static final String FIELD_DESCRIPTION = "description";
    private static final String FIELD_WORKFLOW_GRAPH = "workflowGraph";
    private static final String FIELD_FROZEN_WORKFLOW_GRAPH = "payload.workflowGraph";
    private static final String FIELD_COMPILED_PLAN = "compiledPlan";
    private static final String FIELD_COMPILED_PLAN_DIGEST = "compiledPlanDigest";
    private static final String FIELD_CANONICAL_DIGEST = "canonicalDigest";

    private static final Set<String> PAYLOAD_FIELDS = Set.of(
            FIELD_PAYLOAD_CONTRACT_VERSION,
            FIELD_WORKFLOW_SNAPSHOT_CONTRACT_VERSION,
            FIELD_COMPILED_PLAN_CONTRACT_VERSION,
            FIELD_WORKFLOW_CODE,
            FIELD_SPECIALIST_CODE,
            FIELD_DRAFT_REVISION,
            FIELD_DRAFT_DIGEST,
            FIELD_DISPLAY_NAME,
            FIELD_DESCRIPTION,
            FIELD_WORKFLOW_GRAPH,
            FIELD_COMPILED_PLAN,
            FIELD_COMPILED_PLAN_DIGEST,
            FIELD_CANONICAL_DIGEST);

    private static final String ERROR_RELEASE_SOURCE_INVALID = "Workflow发布源字段不完整";
    private static final String ERROR_PAYLOAD_INVALID = "Workflow冻结发布payload非法";
    private static final String ERROR_PAYLOAD_FIELDS_INVALID = "Workflow冻结发布payload包含未知字段";
    private static final String ERROR_SNAPSHOT_IDENTITY_INVALID = "Workflow冻结发布快照身份不一致";
    private static final String ERROR_CONTRACT_VERSION_INVALID = "Workflow冻结发布契约版本不支持";
    private static final String ERROR_COMPILED_PLAN_INVALID = "Workflow冻结compiledPlan与graph不一致";
    private static final String ERROR_CANONICAL_DIGEST_INVALID = "Workflow冻结payload canonical digest不一致";

    /** 从当前 Workflow v2 草稿事实构造完整自包含冻结 payload；compiledPlan 继续固定为 v1。 */
    public WorkflowReleasePayload create(WorkflowReleaseSourceView source) {
        requireValidSource(source);
        WorkflowGraphAggregate aggregate = parseWorkflowGraph(
                source.getDraftPayloadJson(), source.getWorkflowCode(), FIELD_DRAFT_PAYLOAD_JSON);
        if (!StringUtils.equals(source.getWorkflowCode(), aggregate.getWorkflowCode())) {
            throw validationFailure(ERROR_CODE_SNAPSHOT_IDENTITY_INVALID,
                    ERROR_SNAPSHOT_IDENTITY_INVALID, source.getWorkflowCode(), FIELD_WORKFLOW_CODE);
        }
        requireMatchingGraphVersion(
                source.getDraftContractVersion(), aggregate, source.getWorkflowCode(),
                FIELD_DRAFT_CONTRACT_VERSION);
        CompiledPlan compiledPlan = compileWorkflowGraph(
                aggregate, source.getWorkflowCode(), FIELD_DRAFT_PAYLOAD_JSON);
        WorkflowReleasePayload payload = new WorkflowReleasePayload()
                .setPayloadContractVersion(PAYLOAD_CONTRACT_VERSION)
                .setWorkflowSnapshotContractVersion(aggregate.getSnapshotContractVersion())
                .setCompiledPlanContractVersion(COMPILED_PLAN_CONTRACT_VERSION)
                .setWorkflowCode(source.getWorkflowCode())
                .setSpecialistCode(source.getSpecialistCode())
                .setDraftRevision(source.getDraftRevision())
                .setDraftDigest(source.getDraftDigest())
                .setDisplayName(source.getDisplayName())
                .setDescription(source.getDescription())
                .setWorkflowGraph(aggregate)
                .setCompiledPlan(compiledPlan)
                .setCompiledPlanDigest(compiledPlan.getCompiledPlanDigest());
        return payload.setCanonicalDigest(canonicalDigest(payload));
    }

    /** 在编译前解析冻结 graph，供统一 Skill 存在性与店长全量/普通专员关系重验。 */
    public WorkflowGraphAggregate requireWorkflowGraph(
            AssetSnapshot snapshot, String expectedWorkflowCode) {
        if (snapshot == null || StringUtils.isBlank(snapshot.getPayloadJson())) {
            throw validationFailure(ERROR_CODE_PAYLOAD_INVALID,
                    ERROR_PAYLOAD_INVALID, expectedWorkflowCode, FIELD_WORKFLOW_GRAPH);
        }
        validateSnapshotIdentity(snapshot, expectedWorkflowCode);
        Map<String, Object> raw = parsePayloadMap(snapshot.getPayloadJson(), expectedWorkflowCode);
        requireExactPayloadFields(raw, expectedWorkflowCode);
        requireVersion(raw, FIELD_PAYLOAD_CONTRACT_VERSION, PAYLOAD_CONTRACT_VERSION);
        requireVersion(raw, FIELD_WORKFLOW_SNAPSHOT_CONTRACT_VERSION,
                WORKFLOW_SNAPSHOT_CONTRACT_VERSION);
        int snapshotContractVersion = WORKFLOW_SNAPSHOT_CONTRACT_VERSION;
        requireVersion(raw, FIELD_COMPILED_PLAN_CONTRACT_VERSION, COMPILED_PLAN_CONTRACT_VERSION);
        String workflowCode = requireString(raw, FIELD_WORKFLOW_CODE, expectedWorkflowCode);
        if (!StringUtils.equals(expectedWorkflowCode, workflowCode)) {
            throw validationFailure(ERROR_CODE_SNAPSHOT_IDENTITY_INVALID,
                    ERROR_SNAPSHOT_IDENTITY_INVALID, expectedWorkflowCode, FIELD_WORKFLOW_CODE);
        }
        WorkflowGraphAggregate aggregate = parseWorkflowGraph(
                JsonSupport.toJSON(requireMap(raw, FIELD_WORKFLOW_GRAPH, workflowCode)),
                workflowCode, FIELD_FROZEN_WORKFLOW_GRAPH);
        if (!StringUtils.equals(workflowCode, aggregate.getWorkflowCode())) {
            throw validationFailure(ERROR_CODE_SNAPSHOT_IDENTITY_INVALID,
                    ERROR_SNAPSHOT_IDENTITY_INVALID, expectedWorkflowCode, FIELD_WORKFLOW_CODE);
        }
        requireMatchingGraphVersion(
                snapshotContractVersion, aggregate, workflowCode,
                FIELD_WORKFLOW_SNAPSHOT_CONTRACT_VERSION);
        return aggregate;
    }

    /** 解析 common-v2 快照并重新编译 graph，任何身份或 digest 不一致均失败关闭。 */
    public WorkflowReleasePayload requirePayload(AssetSnapshot snapshot, String expectedWorkflowCode) {
        if (snapshot == null || StringUtils.isBlank(snapshot.getPayloadJson())) {
            throw validationFailure(ERROR_CODE_PAYLOAD_INVALID,
                    ERROR_PAYLOAD_INVALID, expectedWorkflowCode, FIELD_WORKFLOW_GRAPH);
        }
        validateSnapshotIdentity(snapshot, expectedWorkflowCode);
        Map<String, Object> raw = parsePayloadMap(snapshot.getPayloadJson(), expectedWorkflowCode);
        requireExactPayloadFields(raw, expectedWorkflowCode);
        requireVersion(raw, FIELD_PAYLOAD_CONTRACT_VERSION, PAYLOAD_CONTRACT_VERSION);
        requireVersion(raw, FIELD_WORKFLOW_SNAPSHOT_CONTRACT_VERSION,
                WORKFLOW_SNAPSHOT_CONTRACT_VERSION);
        int snapshotContractVersion = WORKFLOW_SNAPSHOT_CONTRACT_VERSION;
        requireVersion(raw, FIELD_COMPILED_PLAN_CONTRACT_VERSION, COMPILED_PLAN_CONTRACT_VERSION);
        String workflowCode = requireString(raw, FIELD_WORKFLOW_CODE, expectedWorkflowCode);
        if (!StringUtils.equals(expectedWorkflowCode, workflowCode)) {
            throw validationFailure(ERROR_CODE_SNAPSHOT_IDENTITY_INVALID,
                    ERROR_SNAPSHOT_IDENTITY_INVALID, expectedWorkflowCode, FIELD_WORKFLOW_CODE);
        }
        WorkflowGraphAggregate aggregate = parseWorkflowGraph(
                JsonSupport.toJSON(requireMap(raw, FIELD_WORKFLOW_GRAPH, workflowCode)),
                workflowCode, FIELD_FROZEN_WORKFLOW_GRAPH);
        if (!StringUtils.equals(workflowCode, aggregate.getWorkflowCode())) {
            throw validationFailure(ERROR_CODE_SNAPSHOT_IDENTITY_INVALID,
                    ERROR_SNAPSHOT_IDENTITY_INVALID, expectedWorkflowCode, FIELD_WORKFLOW_CODE);
        }
        requireMatchingGraphVersion(
                snapshotContractVersion, aggregate, workflowCode,
                FIELD_WORKFLOW_SNAPSHOT_CONTRACT_VERSION);
        CompiledPlan compiledPlan = compileWorkflowGraph(
                aggregate, workflowCode, FIELD_FROZEN_WORKFLOW_GRAPH);
        validateCompiledPlan(raw, compiledPlan, workflowCode);
        String canonicalDigest = requireString(raw, FIELD_CANONICAL_DIGEST, workflowCode);
        String calculatedDigest = canonicalDigest(raw);
        if (!StringUtils.equals(canonicalDigest, calculatedDigest)
                || !StringUtils.equals(snapshot.getDigest(), canonicalDigest)) {
            throw validationFailure(ERROR_CODE_PAYLOAD_INVALID,
                    ERROR_CANONICAL_DIGEST_INVALID, workflowCode, FIELD_CANONICAL_DIGEST);
        }
        return new WorkflowReleasePayload()
                .setPayloadContractVersion(PAYLOAD_CONTRACT_VERSION)
                .setWorkflowSnapshotContractVersion(snapshotContractVersion)
                .setCompiledPlanContractVersion(COMPILED_PLAN_CONTRACT_VERSION)
                .setWorkflowCode(workflowCode)
                .setSpecialistCode(requireString(raw, FIELD_SPECIALIST_CODE, workflowCode))
                .setDraftRevision(requireLong(raw, FIELD_DRAFT_REVISION, workflowCode))
                .setDraftDigest(optionalString(raw.get(FIELD_DRAFT_DIGEST), FIELD_DRAFT_DIGEST, workflowCode))
                .setDisplayName(optionalString(raw.get(FIELD_DISPLAY_NAME), FIELD_DISPLAY_NAME, workflowCode))
                .setDescription(optionalString(raw.get(FIELD_DESCRIPTION), FIELD_DESCRIPTION, workflowCode))
                .setWorkflowGraph(aggregate)
                .setCompiledPlan(compiledPlan)
                .setCompiledPlanDigest(compiledPlan.getCompiledPlanDigest())
                .setCanonicalDigest(canonicalDigest);
    }

    /** 将环境解析结果转换为 Workflow common-v2 快照并执行完整 payload 校验。 */
    public WorkflowReleasePayload requirePayload(ResolvedReleasedAsset resolvedAsset) {
        if (resolvedAsset == null) {
            throw validationFailure(ERROR_CODE_PAYLOAD_INVALID,
                    ERROR_PAYLOAD_INVALID, null, FIELD_WORKFLOW_GRAPH);
        }
        return requirePayload(new AssetSnapshot()
                .setAssetType(ReleaseAssetType.ORCHESTRATION_CONFIG.name())
                .setAssetKey(resolvedAsset.getAssetKey())
                .setDigest(resolvedAsset.getDigest())
                .setArtifactRef(resolvedAsset.getArtifactRef())
                .setSummary(resolvedAsset.getSummary())
                .setPayloadJson(resolvedAsset.getPayloadJson()), resolvedAsset.getAssetKey());
    }

    /** 仅从重新编译并验证通过的 compiledPlan 提取稳定 Skill 身份，去重后字典序输出。 */
    public List<String> skillCodes(WorkflowReleasePayload payload) {
        if (payload == null || payload.getCompiledPlan() == null) {
            throw new IllegalStateException(ERROR_COMPILED_PLAN_INVALID);
        }
        Set<String> skillCodes = new TreeSet<>();
        for (CompiledNode node : payload.getCompiledPlan().getNodeMap().values()) {
            if (node.getNodeType() == WorkflowNodeType.SKILL) {
                if (StringUtils.isBlank(node.getSkillCode())) {
                    throw new IllegalStateException(ERROR_COMPILED_PLAN_INVALID);
                }
                skillCodes.add(node.getSkillCode());
            }
        }
        return new ArrayList<>(skillCodes);
    }

    /** 返回稳定 canonical digest，覆盖完整 graph、compiledPlan 和全部发布执行字段。 */
    public String canonicalDigest(WorkflowReleasePayload payload) {
        Map<String, Object> raw = parseMap(JsonSupport.toJSON(payload));
        return canonicalDigest(raw);
    }

    private String canonicalDigest(Map<String, Object> raw) {
        Map<String, Object> digestSource = new LinkedHashMap<>(raw);
        digestSource.remove(FIELD_CANONICAL_DIGEST);
        return ReleaseDigestUtils.sha256(JsonSupport.toJSON(canonicalize(digestSource)));
    }

    private void validateCompiledPlan(
            Map<String, Object> raw, CompiledPlan compiledPlan, String workflowCode) {
        String declaredDigest = requireString(raw, FIELD_COMPILED_PLAN_DIGEST, workflowCode);
        if (!StringUtils.equals(declaredDigest, compiledPlan.getCompiledPlanDigest())) {
            throw validationFailure(ERROR_CODE_PAYLOAD_INVALID,
                    ERROR_COMPILED_PLAN_INVALID, workflowCode, FIELD_COMPILED_PLAN_DIGEST);
        }
        Map<String, Object> frozenPlan = requireMap(raw, FIELD_COMPILED_PLAN, workflowCode);
        Map<String, Object> rebuiltPlan = parseMap(JsonSupport.toJSON(compiledPlan));
        if (!canonicalize(frozenPlan).equals(canonicalize(rebuiltPlan))) {
            throw validationFailure(ERROR_CODE_PAYLOAD_INVALID,
                    ERROR_COMPILED_PLAN_INVALID, workflowCode, FIELD_COMPILED_PLAN);
        }
    }

    private void validateSnapshotIdentity(AssetSnapshot snapshot, String expectedWorkflowCode) {
        if (!StringUtils.equals(ReleaseAssetType.ORCHESTRATION_CONFIG.name(), snapshot.getAssetType())
                || !StringUtils.equals(expectedWorkflowCode, snapshot.getAssetKey())
                || StringUtils.isBlank(snapshot.getDigest())) {
            throw validationFailure(ERROR_CODE_SNAPSHOT_IDENTITY_INVALID,
                    ERROR_SNAPSHOT_IDENTITY_INVALID, expectedWorkflowCode, FIELD_WORKFLOW_CODE);
        }
    }

    void requireValidSource(WorkflowReleaseSourceView source) {
        if (source == null) {
            throw validationFailure(ERROR_CODE_RELEASE_SOURCE_INVALID,
                    ERROR_RELEASE_SOURCE_INVALID, null, FIELD_WORKFLOW_CODE);
        }
        String workflowCode = source.getWorkflowCode();
        requireSourceField(StringUtils.isNotBlank(workflowCode), workflowCode, FIELD_WORKFLOW_CODE);
        requireSourceField(StringUtils.isNotBlank(source.getSpecialistCode()),
                workflowCode, FIELD_SPECIALIST_CODE);
        requireSourceField(source.getDraftRevision() != null, workflowCode, FIELD_DRAFT_REVISION);
        requireSourceField(StringUtils.isNotBlank(source.getDraftPayloadJson()),
                workflowCode, FIELD_DRAFT_PAYLOAD_JSON);
        if (!Integer.valueOf(SUPPORTED_DRAFT_CONTRACT_VERSION)
                .equals(source.getDraftContractVersion())) {
            throw validationFailure(ERROR_CODE_CONTRACT_VERSION_UNSUPPORTED,
                    ERROR_CONTRACT_VERSION_INVALID + ": " + FIELD_DRAFT_CONTRACT_VERSION,
                    workflowCode, FIELD_DRAFT_CONTRACT_VERSION);
        }
    }

    private void requireSourceField(boolean valid, String workflowCode, String fieldPath) {
        if (!valid) {
            throw validationFailure(ERROR_CODE_RELEASE_SOURCE_INVALID,
                    ERROR_RELEASE_SOURCE_INVALID + ": " + fieldPath, workflowCode, fieldPath);
        }
    }

    private WorkflowReleasePayloadValidationException validationFailure(String errorCode,
            String message, String workflowCode, String fieldPath) {
        return validationFailure(errorCode, message, workflowCode, fieldPath, null);
    }

    private WorkflowReleasePayloadValidationException validationFailure(String errorCode,
            String message, String workflowCode, String fieldPath, Throwable cause) {
        return new WorkflowReleasePayloadValidationException(
                errorCode, message, workflowCode, fieldPath, cause);
    }

    private void requireExactPayloadFields(Map<String, Object> raw, String workflowCode) {
        if (!PAYLOAD_FIELDS.equals(raw.keySet())) {
            throw validationFailure(ERROR_CODE_PAYLOAD_INVALID,
                    ERROR_PAYLOAD_FIELDS_INVALID, workflowCode, FIELD_PAYLOAD);
        }
    }

    private WorkflowGraphAggregate parseWorkflowGraph(
            String json, String workflowCode, String fieldPath) {
        try {
            return WorkflowGraphAggregateParser.parse(json);
        } catch (WorkflowGraphDataException exception) {
            throw validationFailure(exception.getErrorCode(), exception.getMessage(), workflowCode,
                    joinFieldPath(fieldPath, exception.getFieldPath()), exception);
        }
    }

    private CompiledPlan compileWorkflowGraph(
            WorkflowGraphAggregate aggregate, String workflowCode, String fieldPathRoot) {
        try {
            return WorkflowCompiledPlanBuilder.build(aggregate);
        } catch (WorkflowGraphCompilationException exception) {
            throw validationFailure(exception.getErrorCode(), exception.getMessage(), workflowCode,
                    joinFieldPath(fieldPathRoot, exception.getFieldPath()), exception);
        }
    }

    private String joinFieldPath(String root, String child) {
        if (StringUtils.isBlank(root)) {
            return child;
        }
        if (StringUtils.isBlank(child) || "$".equals(child)) {
            return root;
        }
        if (child.startsWith("$.")) {
            return root + child.substring(1);
        }
        if (root.endsWith(".") && child.startsWith(".")) {
            return root + child.substring(1);
        }
        if (root.endsWith(".") || child.startsWith(".")) {
            return root + child;
        }
        return root + "." + child;
    }

    private void requireVersion(Map<String, Object> source, String field, int expected) {
        Object value = source.get(field);
        if (!(value instanceof Integer) || ((Integer) value) != expected) {
            throw validationFailure(ERROR_CODE_CONTRACT_VERSION_UNSUPPORTED,
                    ERROR_CONTRACT_VERSION_INVALID + ": " + field,
                    stringValue(source.get(FIELD_WORKFLOW_CODE)), field);
        }
    }

    private void requireMatchingGraphVersion(
            Integer declaredVersion, WorkflowGraphAggregate aggregate,
            String workflowCode, String fieldPath) {
        if (declaredVersion == null
                || declaredVersion != aggregate.getSnapshotContractVersion()) {
            throw validationFailure(ERROR_CODE_CONTRACT_VERSION_UNSUPPORTED,
                    ERROR_CONTRACT_VERSION_INVALID + ": " + fieldPath,
                    workflowCode, fieldPath);
        }
    }

    private String stringValue(Object value) {
        return value instanceof String ? (String) value : null;
    }

    private String requireString(Map<String, Object> source, String field, String workflowCode) {
        Object value = source.get(field);
        if (!(value instanceof String) || StringUtils.isBlank((String) value)) {
            throw validationFailure(ERROR_CODE_PAYLOAD_INVALID,
                    ERROR_PAYLOAD_INVALID + ": " + field, workflowCode, field);
        }
        return (String) value;
    }

    private Long requireLong(Map<String, Object> source, String field, String workflowCode) {
        Object value = source.get(field);
        if (value instanceof Integer) {
            return ((Integer) value).longValue();
        }
        if (value instanceof Long) {
            return (Long) value;
        }
        throw validationFailure(ERROR_CODE_PAYLOAD_INVALID,
                ERROR_PAYLOAD_INVALID + ": " + field, workflowCode, field);
    }

    private String optionalString(Object value, String field, String workflowCode) {
        if (value == null) {
            return null;
        }
        if (!(value instanceof String)) {
            throw validationFailure(ERROR_CODE_PAYLOAD_INVALID,
                    ERROR_PAYLOAD_INVALID + ": " + field, workflowCode, field);
        }
        return (String) value;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> parsePayloadMap(String json, String workflowCode) {
        try {
            Object value = JsonSupport.mapper().readValue(json, Map.class);
            if (!(value instanceof Map)) {
                throw validationFailure(ERROR_CODE_PAYLOAD_INVALID,
                        ERROR_PAYLOAD_INVALID, workflowCode, FIELD_PAYLOAD);
            }
            return (Map<String, Object>) value;
        } catch (JsonProcessingException exception) {
            throw validationFailure(ERROR_CODE_PAYLOAD_INVALID,
                    ERROR_PAYLOAD_INVALID, workflowCode, FIELD_PAYLOAD, exception);
        }
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> parseMap(String json) {
        Object value = JsonSupport.fromJSON(json, Map.class);
        if (!(value instanceof Map)) {
            throw new IllegalStateException(ERROR_PAYLOAD_INVALID);
        }
        return (Map<String, Object>) value;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> requireMap(
            Map<String, Object> source, String field, String workflowCode) {
        Object value = source.get(field);
        if (!(value instanceof Map)) {
            throw validationFailure(ERROR_CODE_PAYLOAD_INVALID,
                    ERROR_PAYLOAD_INVALID + ": " + field, workflowCode, field);
        }
        return (Map<String, Object>) value;
    }

    private Object canonicalize(Object value) {
        if (value instanceof Map) {
            Map<String, Object> sorted = new TreeMap<>();
            ((Map<?, ?>) value).forEach((key, child) ->
                    sorted.put(String.valueOf(key), canonicalize(child)));
            return sorted;
        }
        if (value instanceof List) {
            List<Object> ordered = new ArrayList<>();
            for (Object child : (List<?>) value) {
                ordered.add(canonicalize(child));
            }
            return ordered;
        }
        return value;
    }
}
