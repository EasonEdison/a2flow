package dev.a2flow.management.release;

import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.apache.commons.lang3.StringUtils;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.release.ReleaseModels.AssetSnapshot;
import dev.a2flow.management.release.diff.ReleaseDiffContentType;
import dev.a2flow.management.release.diff.ReleaseDiffResource;

/**
 * Skill 发布元数据的统一规范化工具。
 *
 * <p>上游由 Skill 发布 Adapter 和准出巡检共同调用，下游只生成共享发布摘要与虚拟 Diff 资源。
 * 本类不读取当前草稿、workspace 或历史目录；历史发布只能从传入的不可变快照恢复描述，避免当前 DO
 * 覆盖旧版本元数据。
 */
public final class SkillReleaseMetadataSupport {

    public static final String FIELD_SKILL_DESCRIPTION = "skillDescription";
    public static final String DIFF_RESOURCE_PATH = ".skillfactory/skill-metadata.json";

    private static final String FIELD_FILE_TREE_DIGEST = "fileTreeDigest";
    private static final String FIELD_COMPONENT_BINDINGS = "componentBindings";
    private static final String FIELD_CAPABILITY_BINDINGS = "capabilityBindings";
    private static final String FIELD_ASSET_ID = "assetId";
    private static final String FIELD_COMPONENT_CODE = "componentCode";
    private static final String FIELD_DRAFT_ID = "draftId";
    private static final String FIELD_CAPABILITY_CODE = "capabilityCode";
    private static final String FIELD_BIND_MODE = "bindMode";
    private static final String JSON_LANGUAGE = "json";
    private static final String ERROR_SNAPSHOT_REQUIRED = "Skill发布快照不存在";
    private static final String ERROR_DESCRIPTION_NOT_FROZEN = "Skill发布快照未冻结描述";
    private static final String ERROR_SNAPSHOT_PAYLOAD_INVALID = "Skill发布快照内容解析失败";

    private SkillReleaseMetadataSupport() {
    }

    /** 对文件树摘要和 Skill 描述的规范 JSON 生成统一发布来源摘要。 */
    public static String sourceDigest(String fileTreeDigest, String skillDescription) {
        return sourceDigest(fileTreeDigest, skillDescription, Map.of());
    }

    /**
     * 对文件、描述和稳定依赖关系生成 authoring digest。
     *
     * <p>关系只纳入稳定身份；候选环境事实、当前发布版本和摘要不属于长期 authoring 身份。
     * Build/Version 中的环境解析结果仅作为发布审计，不复制回关系。
     */
    public static String sourceDigest(String fileTreeDigest, String skillDescription,
            Map<String, Object> skillPayload) {
        Map<String, Object> source = new LinkedHashMap<>();
        source.put(FIELD_FILE_TREE_DIGEST, StringUtils.defaultString(fileTreeDigest));
        source.put(FIELD_SKILL_DESCRIPTION, StringUtils.defaultString(skillDescription));
        source.put(FIELD_COMPONENT_BINDINGS,
                stableBindings(skillPayload.get(FIELD_COMPONENT_BINDINGS), true));
        source.put(FIELD_CAPABILITY_BINDINGS,
                stableBindings(skillPayload.get(FIELD_CAPABILITY_BINDINGS), false));
        return ReleaseDigestUtils.sha256(JsonSupport.toJSON(source));
    }

    /** 共享发布参数有冻结描述时使用该值；直接 PACKAGE 兼容入口仍使用当前草稿描述。 */
    public static String publishDescription(String currentDescription, Map<String, String> params) {
        if (params != null && params.containsKey(FIELD_SKILL_DESCRIPTION)) {
            return StringUtils.defaultString(params.get(FIELD_SKILL_DESCRIPTION));
        }
        return StringUtils.defaultString(currentDescription);
    }

    /** 把快照冻结的 Skill 描述映射为共享 Diff 使用的只读虚拟 JSON 资源。 */
    public static ReleaseDiffResource diffResource(AssetSnapshot snapshot) {
        String content = metadataJson(snapshot);
        return new ReleaseDiffResource()
                .setPath(DIFF_RESOURCE_PATH)
                .setContentType(ReleaseDiffContentType.JSON)
                .setLanguage(JSON_LANGUAGE)
                .setDigest(ReleaseDigestUtils.sha256(content))
                .setSize((long) content.getBytes(StandardCharsets.UTF_8).length)
                .setContent(content);
    }

    /**
     * 读取快照中的冻结描述。
     *
     * <p>新快照从 summary 读取；旧正式版本可从既有 payloadJson 恢复。两处都没有字段时明确失败，
     * 不允许调用方回读当前 Skill DO 作为历史发布替代值。
     */
    @SuppressWarnings("unchecked")
    public static String requireSkillDescription(AssetSnapshot snapshot) {
        if (snapshot == null) {
            throw new IllegalArgumentException(ERROR_SNAPSHOT_REQUIRED);
        }
        if (snapshot.getSummary() != null
                && snapshot.getSummary().containsKey(FIELD_SKILL_DESCRIPTION)) {
            return string(snapshot.getSummary().get(FIELD_SKILL_DESCRIPTION));
        }
        if (StringUtils.isBlank(snapshot.getPayloadJson())) {
            throw new IllegalStateException(ERROR_DESCRIPTION_NOT_FROZEN);
        }
        try {
            Map<String, Object> payload = JsonSupport.fromJSON(snapshot.getPayloadJson(), Map.class);
            if (payload != null && payload.containsKey(FIELD_SKILL_DESCRIPTION)) {
                return string(payload.get(FIELD_SKILL_DESCRIPTION));
            }
        } catch (RuntimeException e) {
            throw new IllegalStateException(ERROR_SNAPSHOT_PAYLOAD_INVALID, e);
        }
        throw new IllegalStateException(ERROR_DESCRIPTION_NOT_FROZEN);
    }

    @SuppressWarnings("unchecked")
    private static String metadataJson(AssetSnapshot snapshot) {
        Map<String, Object> payload = new LinkedHashMap<>();
        if (StringUtils.isNotBlank(snapshot.getPayloadJson())) {
            Object parsed = JsonSupport.fromJSON(snapshot.getPayloadJson(), Object.class);
            if (parsed instanceof Map) {
                payload.putAll((Map<String, Object>) parsed);
            }
        }
        Map<String, Object> metadata = new LinkedHashMap<>();
        metadata.put(FIELD_SKILL_DESCRIPTION, requireSkillDescription(snapshot));
        metadata.put(FIELD_COMPONENT_BINDINGS,
                stableBindings(payload.get(FIELD_COMPONENT_BINDINGS), true));
        metadata.put(FIELD_CAPABILITY_BINDINGS,
                stableBindings(payload.get(FIELD_CAPABILITY_BINDINGS), false));
        copyAuditField(snapshot, payload, metadata,
                SkillDependencyReleaseAuditService.FIELD_DEPENDENCY_RESOLUTIONS);
        copyAuditField(snapshot, payload, metadata,
                SkillDependencyReleaseAuditService.FIELD_DEPENDENCY_RESOLUTION_FAILURES);
        return JsonSupport.toJSON(metadata);
    }

    private static void copyAuditField(AssetSnapshot snapshot, Map<String, Object> payload,
            Map<String, Object> metadata, String field) {
        if (snapshot.getSummary() != null && snapshot.getSummary().containsKey(field)) {
            metadata.put(field, snapshot.getSummary().get(field));
        } else if (payload.containsKey(field)) {
            metadata.put(field, payload.get(field));
        }
    }

    private static List<Map<String, Object>> stableBindings(Object value, boolean component) {
        if (!(value instanceof List)) {
            return List.of();
        }
        List<Map<String, Object>> bindings = new ArrayList<>();
        for (Object item : (List<?>) value) {
            if (!(item instanceof Map)) {
                continue;
            }
            Map<?, ?> source = (Map<?, ?>) item;
            Map<String, Object> binding = new LinkedHashMap<>();
            if (component) {
                binding.put(FIELD_ASSET_ID, source.get(FIELD_ASSET_ID));
                binding.put(FIELD_COMPONENT_CODE, source.get(FIELD_COMPONENT_CODE));
            } else {
                binding.put(FIELD_DRAFT_ID, source.get(FIELD_DRAFT_ID));
                binding.put(FIELD_CAPABILITY_CODE, source.get(FIELD_CAPABILITY_CODE));
                binding.put(FIELD_BIND_MODE, source.get(FIELD_BIND_MODE));
            }
            bindings.add(binding);
        }
        bindings.sort(Comparator.comparing(JsonSupport::toJSON));
        return bindings;
    }

    private static String string(Object value) {
        return value == null ? StringUtils.EMPTY : String.valueOf(value);
    }
}
