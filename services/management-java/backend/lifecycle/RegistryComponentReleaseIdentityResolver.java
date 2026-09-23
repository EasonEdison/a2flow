package dev.a2flow.management.lifecycle;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Component;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.lifecycle.domain.ComponentAsset;
import dev.a2flow.management.model.SkillFactoryComponentAsset;
import dev.a2flow.management.release.ReleaseAssetType;
import dev.a2flow.management.release.dependency.AssetDependencyModels.ResolvedReleasedAsset;
import dev.a2flow.management.release.dependency.AssetDependencyType;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * 统一解析组件 Registry 的类型化发布身份及其不可变发布契约。
 *
 * <p>Skill 关系继续保存 Registry 数字 assetId；只有 A2UI Application 的发布聚合以 appCode 为 key。
 * 上游先用解析出的身份调用环境解析器，再将其 Build/Version payload 交回本类投影为 Skill 创建侧统一
 * 契约。该解析器不读取指针、不猜测未知资产类型，也不提供 latest、ONLINE、Registry 草稿或全局兜底。
 */
@Component
public class RegistryComponentReleaseIdentityResolver {

    private static final String ASSET_TYPE_A2UI_APPLICATION = "A2UI_APPLICATION";
    private static final String DSL_TYPE_CARD_CONTAINER = "CARD_CONTAINER";
    private static final String INTERACTION_MODE_DISPLAY_ONLY = "DISPLAY_ONLY";
    private static final String INTERACTION_MODE_INTERACTIVE = "INTERACTIVE";
    private static final String FIELD_APP_CODE = "appCode";
    private static final String FIELD_PARAMS_SCHEMA = "paramsSchema";
    private static final String FIELD_ACTION_DECLARATIONS = "actionDeclarations";
    private static final String FIELD_PARAMS = "params";
    private static final Set<String> SKILL_CANDIDATE_ASSET_TYPES = Set.of(
            "CARD_COMPONENT", "BUSINESS_DSL");
    private static final Set<String> LEGACY_COMPONENT_ASSET_TYPES = Set.of(
            "CARD_COMPONENT", "BUSINESS_DSL", "A2UI_ATOM");
    private static final String ERROR_ASSET_ID_REQUIRED = "组件Registry资产缺少合法assetId";
    private static final String ERROR_ASSET_TYPE_REQUIRED = "组件Registry资产缺少assetType";
    private static final String ERROR_APPLICATION_CODE_REQUIRED = "A2UI Application缺少componentName/appCode";
    private static final String ERROR_ASSET_TYPE_UNSUPPORTED = "组件Registry资产类型不支持发布解析: ";
    private static final String ERROR_RELEASE_PAYLOAD_REQUIRED = "组件发布快照payload缺失";
    private static final String ERROR_RELEASE_PAYLOAD_INVALID = "组件发布快照payload非法";
    private static final String ERROR_RELEASE_IDENTITY_MISMATCH = "组件发布快照身份与Registry解析结果不一致";
    private static final String ERROR_APPLICATION_RELEASE_IDENTITY_MISMATCH =
            "A2UI Application发布快照appCode与Registry不一致";
    private static final String ERROR_APPLICATION_SCHEMA_REQUIRED =
            "A2UI Application发布快照缺少paramsSchema";

    /** 从 Registry DTO 解析类型化发布身份。 */
    public ComponentReleaseIdentity resolve(SkillFactoryComponentAsset asset) {
        if (asset == null) {
            throw new IllegalArgumentException(ERROR_ASSET_TYPE_REQUIRED);
        }
        return resolve(asset.getId() == null ? null : String.valueOf(asset.getId()),
                asset.getAssetType(), asset.getComponentName());
    }

    /** 判断 Registry 资产类型是否属于 Skill 新增绑定候选；A2UI Atom/Catalog 仅供 Application 内部编排。 */
    public boolean supports(SkillFactoryComponentAsset asset) {
        return asset != null && supports(asset.getAssetType());
    }

    /** 只按资产类型判断候选资格，不替代 {@link #resolve} 的完整身份校验。 */
    public boolean supports(String assetType) {
        String normalizedAssetType = StringUtils.upperCase(StringUtils.trimToEmpty(assetType));
        return StringUtils.equals(normalizedAssetType, ASSET_TYPE_A2UI_APPLICATION)
                || SKILL_CANDIDATE_ASSET_TYPES.contains(normalizedAssetType);
    }

    /** 从冻结关系字段解析类型化发布身份。 */
    public ComponentReleaseIdentity resolve(String assetId, String assetType, String componentName) {
        String normalizedAssetType = StringUtils.upperCase(StringUtils.trimToEmpty(assetType));
        if (StringUtils.isBlank(normalizedAssetType)) {
            throw new IllegalArgumentException(ERROR_ASSET_TYPE_REQUIRED);
        }
        if (StringUtils.equals(normalizedAssetType, ASSET_TYPE_A2UI_APPLICATION)) {
            String appCode = StringUtils.trimToEmpty(componentName);
            if (StringUtils.isBlank(appCode)) {
                throw new IllegalArgumentException(ERROR_APPLICATION_CODE_REQUIRED);
            }
            return identity(ReleaseAssetType.A2UI_APPLICATION,
                    AssetDependencyType.A2UI_APPLICATION, appCode);
        }
        if (!LEGACY_COMPONENT_ASSET_TYPES.contains(normalizedAssetType)) {
            throw new IllegalArgumentException(ERROR_ASSET_TYPE_UNSUPPORTED + normalizedAssetType);
        }
        return identity(ReleaseAssetType.COMPONENT, AssetDependencyType.COMPONENT_ASSET,
                requireAssetId(assetId));
    }

    /**
     * 将环境解析器返回的不可变发布 payload 投影为 Skill 创建侧统一组件契约。
     *
     * <p>旧组件继续读取其原生 {@link SkillFactoryComponentAsset} 快照；A2UI Application 只从不可变
     * Build 读取 appCode、paramsSchema 和交互声明，Registry 当前态仅补充稳定 ID 与展示字段。本方法不
     * 读取其他环境、不回退 Registry 草稿 schema，也不猜测未知发布类型。
     */
    @SuppressWarnings("unchecked")
    public SkillFactoryComponentAsset resolveReleasedContract(ComponentAsset registryAsset,
            ComponentReleaseIdentity identity, ResolvedReleasedAsset resolved) {
        if (registryAsset == null || identity == null || resolved == null
                || StringUtils.isBlank(resolved.getPayloadJson())) {
            throw new IllegalArgumentException(ERROR_RELEASE_PAYLOAD_REQUIRED);
        }
        if (resolved.getAssetType() != identity.getDependencyType()
                || !StringUtils.equals(resolved.getAssetKey(), identity.getAssetKey())) {
            throw new IllegalArgumentException(ERROR_RELEASE_IDENTITY_MISMATCH);
        }
        if (identity.getDependencyType() == AssetDependencyType.A2UI_APPLICATION) {
            try {
                Map<String, Object> build = JsonSupport.fromJSON(
                        resolved.getPayloadJson(), Map.class);
                Object appCodeValue = build == null ? null : build.get(FIELD_APP_CODE);
                String appCode = appCodeValue instanceof String
                        ? StringUtils.trimToNull((String) appCodeValue) : null;
                if (!StringUtils.equals(registryAsset.getComponentName(), appCode)) {
                    throw new IllegalArgumentException(ERROR_APPLICATION_RELEASE_IDENTITY_MISMATCH);
                }
                Object paramsSchemaValue = build.get(FIELD_PARAMS_SCHEMA);
                if (!(paramsSchemaValue instanceof Map<?, ?>)) {
                    throw new IllegalArgumentException(ERROR_APPLICATION_SCHEMA_REQUIRED);
                }
                Object actionDeclarationsValue = build.get(FIELD_ACTION_DECLARATIONS);
                if (!(actionDeclarationsValue instanceof List<?>)) {
                    throw new IllegalArgumentException(ERROR_RELEASE_PAYLOAD_INVALID);
                }
                List<?> actionDeclarations = (List<?>) actionDeclarationsValue;
                return new SkillFactoryComponentAsset()
                        .setId(registryAsset.getId())
                        .setAssetType(registryAsset.getAssetType())
                        .setComponentName(appCode)
                        .setComponentNameCn(registryAsset.getComponentNameCn())
                        .setDslType(DSL_TYPE_CARD_CONTAINER)
                        .setInteractionMode(actionDeclarations.isEmpty()
                                ? INTERACTION_MODE_DISPLAY_ONLY : INTERACTION_MODE_INTERACTIVE)
                        .setScene(registryAsset.getScene())
                        .setIntegrationPrompt(registryAsset.getIntegrationPrompt())
                        .setParamsSchemaJson(JsonSupport.toJSON(
                                new LinkedHashMap<>((Map<String, Object>) paramsSchemaValue)))
                        .setMessageDemoJson(JsonSupport.toJSON(
                                Collections.singletonMap(FIELD_PARAMS, Collections.emptyMap())))
                        .setEnabled(registryAsset.getEnabled());
            } catch (IllegalArgumentException exception) {
                throw exception;
            } catch (RuntimeException exception) {
                throw new IllegalArgumentException(ERROR_RELEASE_PAYLOAD_INVALID, exception);
            }
        }
        if (identity.getDependencyType() != AssetDependencyType.COMPONENT_ASSET) {
            throw new IllegalArgumentException(ERROR_ASSET_TYPE_UNSUPPORTED
                    + identity.getDependencyType());
        }
        try {
            SkillFactoryComponentAsset asset = JsonSupport.fromJSON(
                    resolved.getPayloadJson(), SkillFactoryComponentAsset.class);
            if (asset == null) {
                throw new IllegalArgumentException(ERROR_RELEASE_PAYLOAD_INVALID);
            }
            return asset;
        } catch (IllegalArgumentException exception) {
            throw exception;
        } catch (RuntimeException exception) {
            throw new IllegalArgumentException(ERROR_RELEASE_PAYLOAD_INVALID, exception);
        }
    }

    private String requireAssetId(String assetId) {
        String normalizedAssetId = StringUtils.trimToEmpty(assetId);
        try {
            if (Long.parseLong(normalizedAssetId) <= 0L) {
                throw new IllegalArgumentException(ERROR_ASSET_ID_REQUIRED);
            }
            return normalizedAssetId;
        } catch (NumberFormatException exception) {
            throw new IllegalArgumentException(ERROR_ASSET_ID_REQUIRED, exception);
        }
    }

    private ComponentReleaseIdentity identity(ReleaseAssetType releaseAssetType,
            AssetDependencyType dependencyType, String assetKey) {
        return new ComponentReleaseIdentity()
                .setReleaseAssetType(releaseAssetType)
                .setDependencyType(dependencyType)
                .setAssetKey(assetKey);
    }

    /** Registry 关系在共享发布状态表和环境依赖解析器中的确定身份。 */
    @Data
    @Accessors(chain = true)
    public static class ComponentReleaseIdentity {
        private ReleaseAssetType releaseAssetType;
        private AssetDependencyType dependencyType;
        private String assetKey;
    }
}
