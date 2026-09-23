package dev.a2flow.management.lifecycle;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import jakarta.annotation.Resource;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;

import dev.a2flow.management.model.AssetReleaseEnvironmentFacts;
import dev.a2flow.management.model.AssetReleaseEnvironmentFacts.AssetReleaseSourceFact;
import dev.a2flow.management.model.CapabilityActionDraft;
import dev.a2flow.management.model.SkillFactoryComponentAsset;
import dev.a2flow.management.release.AssetReleasePointerQueryService;
import dev.a2flow.management.release.ReleaseAssetType;
import dev.a2flow.management.release.ReleaseEnvironment;
import dev.a2flow.management.release.ReleaseModels.AssetReleaseProjection;
import dev.a2flow.management.release.dependency.AssetDependencyModels.AssetDependencyReference;
import dev.a2flow.management.release.dependency.AssetDependencyModels.ResolvedReleasedAsset;
import dev.a2flow.management.release.dependency.AssetDependencyResolutionException;
import dev.a2flow.management.release.dependency.AssetDependencyType;
import dev.a2flow.management.release.dependency.EnvironmentAwareAssetResolver;

import lombok.extern.slf4j.Slf4j;

/**
 * Skill 工作台稳定绑定候选与当前环境事实服务。
 *
 * <p>候选和关系始终使用 assetId/draftId 作为稳定身份；PRT、ONLINE 和预发实际选择
 * 只通过共享环境解析器计算后返回给页面，不写入关系 Repository，也不实现第二套指针选择规则。
 */
@Service
@Slf4j
public class SkillBindingCandidateService {

    private static final String FIELD_RELEASE_ENVIRONMENT_FACTS = "releaseEnvironmentFacts";
    private static final String FIELD_ASSET_ID = "assetId";
    private static final String FIELD_ASSET_TYPE = "assetType";
    private static final String FIELD_COMPONENT_NAME = "componentName";
    private static final String FIELD_DRAFT_ID = "draftId";
    private static final String FIELD_CAPABILITY_BINDINGS = "capabilityBindings";
    private static final String FIELD_COMPONENT_BINDINGS = "componentBindings";
    private static final String FIELD_REFERENCE_CAPABILITIES = "referenceCapabilities";
    private static final String FIELD_REFERENCE_RENDER_ASSETS = "referenceRenderAssets";
    private static final String STATUS_AVAILABLE = "AVAILABLE";
    private static final String STATUS_NOT_RELEASED = "NOT_RELEASED";
    private static final String PARAM_PUBLISH_STATUS = "publishStatus";
    private static final String STATUS_EDITING = "EDITING";
    private static final String STATUS_ONLINE = "ONLINE";
    private static final String STATUS_ACTIVE = "ACTIVE";
    private static final String STATUS_UNPUBLISHED = "UNPUBLISHED";
    private static final String ERROR_PUBLISH_STATUS_INVALID = "发布状态筛选值不合法";
    private static final String ERROR_ASSET_KEY_REQUIRED = "ASSET_KEY_REQUIRED";
    private static final String MESSAGE_PREPROD_SELECTS_ONLINE = "PRT未发布，预发实际选择ONLINE";
    private static final String MESSAGE_ONLINE_BLOCKED = "当前依赖仅在PRT可用，将阻塞Skill发布到线上";
    private static final String MESSAGE_ASSET_KEY_REQUIRED = "稳定资产标识为空";

    @Resource
    private SkillFactoryComponentRegistryService componentRegistryService;

    @Resource
    private CapabilityActionDraftService capabilityActionDraftService;

    @Resource
    private EnvironmentAwareAssetResolver environmentAwareAssetResolver;

    @Resource
    private RegistryComponentReleaseIdentityResolver componentReleaseIdentityResolver;

    @Resource
    private AssetReleasePointerQueryService assetReleasePointerQueryService;

    /** 查询全部 enabled 组件稳定身份，并附加两环境只读事实。 */
    public List<SkillFactoryComponentAsset> componentCandidates(Map<String, String> params) {
        List<SkillFactoryComponentAsset> candidates = componentRegistryService.listEnabled(params).stream()
                .filter(componentReleaseIdentityResolver::supports)
                .toList();
        for (SkillFactoryComponentAsset candidate : candidates) {
            RegistryComponentReleaseIdentityResolver.ComponentReleaseIdentity identity =
                    componentReleaseIdentityResolver.resolve(candidate);
            candidate.setReleaseEnvironmentFacts(environmentFacts(
                    identity.getDependencyType(), identity.getAssetKey()));
        }
        log.info("Skill工作台查询组件绑定候选完成, count:{}", candidates.size());
        return candidates;
    }

    /** 查询能力稳定草稿身份，并附加两环境只读事实。 */
    public List<CapabilityActionDraft> capabilityCandidates(String userName, Map<String, String> params) {
        String publishStatus = StringUtils.trimToEmpty(params.get(PARAM_PUBLISH_STATUS));
        if (StringUtils.isNotBlank(publishStatus)
                && !StringUtils.equalsAny(publishStatus, STATUS_EDITING, STATUS_ONLINE)) {
            throw new IllegalArgumentException(ERROR_PUBLISH_STATUS_INVALID + "：" + publishStatus);
        }
        List<CapabilityActionDraft> candidates = enrichCapabilities(capabilityActionDraftService.list(params));
        candidates.forEach(item -> putCatalogStatus(userName, item));
        candidates = candidates.stream()
                .filter(item -> StringUtils.isBlank(publishStatus)
                        || (StringUtils.equals(publishStatus, STATUS_EDITING)
                        && Boolean.TRUE.equals(item.getEditing()))
                        || (StringUtils.equals(publishStatus, STATUS_ONLINE)
                        && Boolean.TRUE.equals(item.getOnline())))
                .toList();
        log.info("Skill工作台查询能力绑定候选完成, count:{}", candidates.size());
        return candidates;
    }

    private void putCatalogStatus(String userName, CapabilityActionDraft capability) {
        AssetReleaseProjection projection = assetReleasePointerQueryService.projection(
                userName, ReleaseAssetType.CAPABILITY_ACTION,
                capability.getDraftId());
        boolean online = projection.getEnvironmentPointers().containsKey(STATUS_ONLINE);
        boolean editing = StringUtils.equals(projection.getStatus(), STATUS_ACTIVE)
                || (!online && StringUtils.equals(projection.getStatus(), STATUS_UNPUBLISHED));
        capability.setOnline(online).setEditing(editing);
    }

    /** 为能力列表附加两环境只读事实，不修改能力草稿持久化内容。 */
    public List<CapabilityActionDraft> enrichCapabilities(List<CapabilityActionDraft> capabilities) {
        for (CapabilityActionDraft capability : capabilities) {
            enrichCapability(capability);
        }
        return capabilities;
    }

    /** 为能力详情附加两环境只读事实，不修改能力草稿持久化内容。 */
    public CapabilityActionDraft enrichCapability(CapabilityActionDraft capability) {
        capability.setReleaseEnvironmentFacts(
                environmentFacts(AssetDependencyType.CAPABILITY_ACTION, capability.getDraftId()));
        return capability;
    }

    /** 复制并富化冻结组件关系响应，不修改关系快照本身。 */
    public List<Map<String, Object>> enrichComponentBindings(List<Map<String, Object>> bindings) {
        List<Map<String, Object>> result = new ArrayList<>();
        for (Map<String, Object> binding : bindings) {
            RegistryComponentReleaseIdentityResolver.ComponentReleaseIdentity identity =
                    componentReleaseIdentityResolver.resolve(
                            string(binding.get(FIELD_ASSET_ID)), string(binding.get(FIELD_ASSET_TYPE)),
                            string(binding.get(FIELD_COMPONENT_NAME)));
            Map<String, Object> enriched = new LinkedHashMap<>(binding);
            enriched.put(FIELD_RELEASE_ENVIRONMENT_FACTS,
                    environmentFacts(identity.getDependencyType(), identity.getAssetKey()));
            result.add(enriched);
        }
        return result;
    }

    /** 复制并富化冻结能力关系响应，不修改关系快照本身。 */
    public List<Map<String, Object>> enrichCapabilityBindings(List<Map<String, Object>> bindings) {
        return enrichBindings(bindings, FIELD_DRAFT_ID, AssetDependencyType.CAPABILITY_ACTION);
    }

    /** 富化 Skill 详情中的绑定响应，不修改 workspace 领域快照。 */
    @SuppressWarnings("unchecked")
    public Map<String, Object> enrichSkillDetail(Map<String, Object> detail) {
        Map<String, Object> result = new LinkedHashMap<>(detail);
        List<Map<String, Object>> capabilityBindings = (List<Map<String, Object>>) result.getOrDefault(
                FIELD_CAPABILITY_BINDINGS, List.of());
        List<Map<String, Object>> componentBindings = (List<Map<String, Object>>) result.getOrDefault(
                FIELD_COMPONENT_BINDINGS, List.of());
        List<Map<String, Object>> enrichedCapabilities = enrichCapabilityBindings(capabilityBindings);
        List<Map<String, Object>> enrichedComponents = enrichComponentBindings(componentBindings);
        result.put(FIELD_CAPABILITY_BINDINGS, enrichedCapabilities);
        result.put(FIELD_REFERENCE_CAPABILITIES, enrichedCapabilities);
        result.put(FIELD_COMPONENT_BINDINGS, enrichedComponents);
        result.put(FIELD_REFERENCE_RENDER_ASSETS, enrichedComponents);
        return result;
    }

    /**
     * 校验稳定资产身份可被 Skill 预发绑定，并返回共享控制面选择的不可变来源。
     *
     * <p>该方法只复用 PRT 解析矩阵，不把返回的 Build/Version 写入关系运行时身份；
     * 调用方仍需按领域规则校验当前 Registry/Draft 的展示身份和 enabled 状态。
     */
    public ResolvedReleasedAsset requireEffectivePreprod(
            AssetDependencyType assetType, String assetKey) {
        if (StringUtils.isBlank(assetKey)) {
            throw new IllegalArgumentException(MESSAGE_ASSET_KEY_REQUIRED);
        }
        ResolvedReleasedAsset resolved = environmentAwareAssetResolver.resolve(
                dependency(assetType, assetKey), ReleaseEnvironment.PRT);
        log.info("Skill工作台绑定候选环境解析通过, assetType:{}, assetKey:{}, resolvedEnvironment:{}, "
                        + "sourceType:{}, sourceId:{}",
                assetType, assetKey, resolved.getResolvedEnvironment(),
                resolved.getSourceType(), resolved.getSourceId());
        return resolved;
    }

    /** 按 Registry 资产类型校验组件可被 Skill 预发绑定。 */
    public ResolvedReleasedAsset requireEffectivePreprod(SkillFactoryComponentAsset asset) {
        RegistryComponentReleaseIdentityResolver.ComponentReleaseIdentity identity =
                componentReleaseIdentityResolver.resolve(asset);
        return requireEffectivePreprod(identity.getDependencyType(), identity.getAssetKey());
    }

    private List<Map<String, Object>> enrichBindings(List<Map<String, Object>> bindings,
            String assetKeyField, AssetDependencyType assetType) {
        List<Map<String, Object>> result = new ArrayList<>();
        for (Map<String, Object> binding : bindings) {
            Map<String, Object> enriched = new LinkedHashMap<>(binding);
            enriched.put(FIELD_RELEASE_ENVIRONMENT_FACTS,
                    environmentFacts(assetType, string(binding.get(assetKeyField))));
            result.add(enriched);
        }
        return result;
    }

    private AssetReleaseEnvironmentFacts environmentFacts(AssetDependencyType assetType, String assetKey) {
        if (StringUtils.isBlank(assetKey)) {
            return invalidAssetKeyFacts();
        }
        AssetDependencyReference dependency = dependency(assetType, assetKey);
        AssetReleaseSourceFact preprod;
        AssetReleaseSourceFact effectivePreprod;
        try {
            ResolvedReleasedAsset resolved = environmentAwareAssetResolver.resolve(
                    dependency, ReleaseEnvironment.PRT);
            effectivePreprod = sourceFact(resolved);
            preprod = resolved.getResolvedEnvironment() == ReleaseEnvironment.PRT
                    ? sourceFact(resolved)
                    : unavailableFact(ReleaseEnvironment.PRT, STATUS_NOT_RELEASED,
                            null, MESSAGE_PREPROD_SELECTS_ONLINE);
        } catch (AssetDependencyResolutionException e) {
            preprod = resolutionFailure(e);
            effectivePreprod = resolutionFailure(e);
        }
        AssetReleaseSourceFact online;
        try {
            online = sourceFact(environmentAwareAssetResolver.resolve(dependency, ReleaseEnvironment.ONLINE));
        } catch (AssetDependencyResolutionException e) {
            online = resolutionFailure(e);
        }
        boolean onlineBlocked = Boolean.TRUE.equals(effectivePreprod.getAvailable())
                && StringUtils.equals(effectivePreprod.getResolvedEnvironment(), ReleaseEnvironment.PRT.name())
                && !Boolean.TRUE.equals(online.getAvailable());
        return new AssetReleaseEnvironmentFacts()
                .setPreprod(preprod)
                .setOnline(online)
                .setEffectivePreprod(effectivePreprod)
                .setOnlineBlocked(onlineBlocked)
                .setOnlineBlockedReason(onlineBlocked ? MESSAGE_ONLINE_BLOCKED : StringUtils.EMPTY);
    }

    private AssetReleaseEnvironmentFacts invalidAssetKeyFacts() {
        AssetReleaseSourceFact preprod = unavailableFact(
                ReleaseEnvironment.PRT, ERROR_ASSET_KEY_REQUIRED,
                ERROR_ASSET_KEY_REQUIRED, MESSAGE_ASSET_KEY_REQUIRED);
        AssetReleaseSourceFact online = unavailableFact(
                ReleaseEnvironment.ONLINE, ERROR_ASSET_KEY_REQUIRED,
                ERROR_ASSET_KEY_REQUIRED, MESSAGE_ASSET_KEY_REQUIRED);
        return new AssetReleaseEnvironmentFacts()
                .setPreprod(preprod)
                .setOnline(online)
                .setEffectivePreprod(preprod)
                .setOnlineBlocked(false)
                .setOnlineBlockedReason(StringUtils.EMPTY);
    }

    private AssetReleaseSourceFact sourceFact(ResolvedReleasedAsset resolved) {
        return new AssetReleaseSourceFact()
                .setEnvironment(resolved.getResolvedEnvironment().name())
                .setRequestedEnvironment(resolved.getRequestedEnvironment().name())
                .setResolvedEnvironment(resolved.getResolvedEnvironment().name())
                .setStatus(STATUS_AVAILABLE)
                .setAvailable(true)
                .setSourceType(resolved.getSourceType().name())
                .setSourceId(resolved.getSourceId())
                .setVersion(resolved.getVersion())
                .setDigest(resolved.getDigest());
    }

    private AssetReleaseSourceFact resolutionFailure(AssetDependencyResolutionException exception) {
        String errorCode = exception.getErrorCode().name();
        return unavailableFact(exception.getRequestedEnvironment(), errorCode,
                errorCode, exception.getMessage());
    }

    private AssetReleaseSourceFact unavailableFact(ReleaseEnvironment environment, String status,
            String errorCode, String message) {
        return new AssetReleaseSourceFact()
                .setEnvironment(environment.name())
                .setRequestedEnvironment(environment.name())
                .setStatus(status)
                .setAvailable(false)
                .setErrorCode(errorCode)
                .setMessage(message);
    }

    private AssetDependencyReference dependency(AssetDependencyType assetType, String assetKey) {
        return new AssetDependencyReference()
                .setAssetType(assetType)
                .setAssetKey(assetKey);
    }

    private String string(Object value) {
        return value == null ? StringUtils.EMPTY : String.valueOf(value).trim();
    }
}
