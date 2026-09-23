package dev.a2flow.management.release;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;

import jakarta.annotation.Resource;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Component;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.lifecycle.RegistryComponentReleaseIdentityResolver;
import dev.a2flow.management.lifecycle.RegistryComponentReleaseIdentityResolver.ComponentReleaseIdentity;
import dev.a2flow.management.release.ReleaseModels.AssetSnapshot;
import dev.a2flow.management.release.dependency.AssetDependencyType;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * 从冻结 Skill 发布快照读取直接资产依赖。
 *
 * <p>该读取器只解释 Skill 自己的 componentBindings 和 capabilityBindings。组件关系继续冻结 Registry
 * 数字 assetId，并复用统一解析器把 assetType/componentName 转换为类型化发布身份；环境解析、递归遍历、
 * 环检测和完整路径拼装统一交给共享依赖校验器。本类不查询 Registry 当前态，也不提供环境或身份兜底。
 */
@Component
public class SkillReleaseBindingSnapshotReader {

    private static final String FIELD_COMPONENT_BINDINGS = "componentBindings";
    private static final String FIELD_CAPABILITY_BINDINGS = "capabilityBindings";
    private static final String FIELD_ASSET_ID = "assetId";
    private static final String FIELD_ASSET_TYPE = "assetType";
    private static final String FIELD_COMPONENT_NAME = "componentName";
    private static final String FIELD_COMPONENT_CODE = "componentCode";
    private static final String FIELD_DRAFT_ID = "draftId";
    private static final String FIELD_CAPABILITY_CODE = "capabilityCode";
    private static final String FIELD_ACTION_CODE = "actionCode";
    private static final String ERROR_SNAPSHOT_REQUIRED = "Skill冻结快照为空，无法读取资产依赖";
    private static final String ERROR_PAYLOAD_INVALID = "Skill冻结快照payload格式非法";
    private static final String ERROR_BINDINGS_INVALID = "Skill冻结快照绑定列表格式非法: ";
    private static final String ERROR_COMPONENT_ID_REQUIRED = "Skill冻结组件绑定缺少合法assetId";
    private static final String ERROR_COMPONENT_TYPE_REQUIRED = "Skill冻结组件绑定缺少assetType";
    private static final String ERROR_CAPABILITY_ID_REQUIRED = "Skill冻结能力绑定缺少draftId";

    @Resource
    private RegistryComponentReleaseIdentityResolver componentReleaseIdentityResolver;

    /** 读取并按资产类型和稳定 key 排序直接依赖，保证交给共享校验器的输入确定。 */
    public List<DirectDependency> readDirectDependencies(AssetSnapshot snapshot) {
        Map<String, Object> payload = payload(snapshot);
        List<DirectDependency> dependencies = new ArrayList<>();
        for (Map<String, Object> binding : bindings(payload, FIELD_COMPONENT_BINDINGS)) {
            String assetKey = componentAssetKey(binding);
            String assetType = requiredString(
                    binding.get(FIELD_ASSET_TYPE), ERROR_COMPONENT_TYPE_REQUIRED);
            String componentName = string(binding.get(FIELD_COMPONENT_NAME));
            ComponentReleaseIdentity identity = componentReleaseIdentityResolver.resolve(
                    assetKey, assetType, componentName);
            String code = firstNonBlank(string(binding.get(FIELD_COMPONENT_CODE)),
                    componentName, identity.getAssetKey());
            dependencies.add(dependency(
                    identity.getDependencyType(), identity.getAssetKey(), code));
        }
        for (Map<String, Object> binding : bindings(payload, FIELD_CAPABILITY_BINDINGS)) {
            String assetKey = requiredString(binding.get(FIELD_DRAFT_ID), ERROR_CAPABILITY_ID_REQUIRED);
            String code = firstNonBlank(string(binding.get(FIELD_CAPABILITY_CODE)),
                    string(binding.get(FIELD_ACTION_CODE)), assetKey);
            dependencies.add(dependency(
                    AssetDependencyType.CAPABILITY_ACTION, assetKey, code));
        }
        dependencies.sort(Comparator.comparing(
                        (DirectDependency dependency) -> dependency.getAssetType().name())
                .thenComparing(DirectDependency::getAssetKey));
        return dependencies;
    }

    private Map<String, Object> payload(AssetSnapshot snapshot) {
        if (snapshot == null || StringUtils.isBlank(snapshot.getPayloadJson())) {
            throw new IllegalArgumentException(ERROR_SNAPSHOT_REQUIRED);
        }
        Object parsed = JsonSupport.fromJSON(snapshot.getPayloadJson(), Object.class);
        if (!(parsed instanceof Map<?, ?> parsedMap)) {
            throw new IllegalArgumentException(ERROR_PAYLOAD_INVALID);
        }
        Map<String, Object> payload = new java.util.LinkedHashMap<>();
        parsedMap.forEach((key, value) -> payload.put(String.valueOf(key), value));
        return payload;
    }

    private List<Map<String, Object>> bindings(Map<String, Object> payload, String field) {
        Object value = payload.get(field);
        if (value == null) {
            return List.of();
        }
        if (!(value instanceof List<?> values)) {
            throw new IllegalArgumentException(ERROR_BINDINGS_INVALID + field);
        }
        List<Map<String, Object>> bindings = new ArrayList<>();
        for (Object item : values) {
            if (!(item instanceof Map<?, ?> itemMap)) {
                throw new IllegalArgumentException(ERROR_BINDINGS_INVALID + field);
            }
            Map<String, Object> binding = new java.util.LinkedHashMap<>();
            itemMap.forEach((key, itemValue) -> binding.put(String.valueOf(key), itemValue));
            bindings.add(binding);
        }
        return bindings;
    }

    private String componentAssetKey(Map<String, Object> binding) {
        String value = string(binding.get(FIELD_ASSET_ID));
        try {
            if (Long.parseLong(value) <= 0) {
                throw new IllegalArgumentException(ERROR_COMPONENT_ID_REQUIRED);
            }
            return value;
        } catch (NumberFormatException e) {
            throw new IllegalArgumentException(ERROR_COMPONENT_ID_REQUIRED, e);
        }
    }

    private DirectDependency dependency(AssetDependencyType assetType, String assetKey,
            String displayCode) {
        return new DirectDependency()
                .setAssetType(assetType)
                .setAssetKey(assetKey)
                .setDisplayCode(displayCode);
    }

    private String requiredString(Object value, String message) {
        String result = string(value);
        if (StringUtils.isBlank(result)) {
            throw new IllegalArgumentException(message);
        }
        return result;
    }

    private String firstNonBlank(String... values) {
        for (String value : values) {
            if (StringUtils.isNotBlank(value)) {
                return value;
            }
        }
        return StringUtils.EMPTY;
    }

    private String string(Object value) {
        return value == null ? StringUtils.EMPTY : String.valueOf(value).trim();
    }

    /** Skill 领域从冻结关系声明的稳定直接依赖。 */
    @Data
    @Accessors(chain = true)
    public static class DirectDependency {
        private AssetDependencyType assetType;
        private String assetKey;
        private String displayCode;
    }
}
