package dev.a2flow.management.agentcore.runtime.tool;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;

import jakarta.annotation.Resource;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.lifecycle.RegistryComponentReleaseIdentityResolver;
import dev.a2flow.management.lifecycle.domain.ComponentAsset;
import dev.a2flow.management.model.ComponentToolErrorCode;
import dev.a2flow.management.model.SkillFactoryComponentAsset;
import dev.a2flow.management.release.ReleaseEnvironment;
import dev.a2flow.management.release.dependency.AssetDependencyModels.AssetDependencyReference;
import dev.a2flow.management.release.dependency.AssetDependencyModels.AssetResolutionContext;
import dev.a2flow.management.release.dependency.AssetDependencyModels.ResolvedReleasedAsset;
import dev.a2flow.management.release.dependency.AssetDependencyResolutionException;
import dev.a2flow.management.release.dependency.EnvironmentAwareAssetResolver;
import dev.a2flow.management.storage.db.repository.SkillFactoryComponentAssetRepository;

import lombok.Getter;
import lombok.extern.slf4j.Slf4j;

/**
 * 组件 Tool 的当前环境契约查询服务。
 *
 * <p>上游 {@link QueryComponentToolCallback} 和 {@link QuerySkillDependenciesToolCallback} 只提交组件
 * 稳定名称；本服务先从 Registry Repository 精确定位稳定资产 ID，再用公共环境解析器选择 PRT
 * Build 或 ONLINE Version。输出只保留模型
 * 构造 {@code render_component} 参数所需的 Schema、示例和展示语义，不返回 bundle、模板、动作配置、
 * 资产 ID、版本指针、身份或传输配置。本服务不执行渲染、不缓存快照，也不扫描完整组件目录。
 */
@Service
@Slf4j
public class ComponentToolContractService {

    private static final String DSL_TYPE_CARD_CONTAINER = "CARD_CONTAINER";
    private static final String FIELD_DSL_TYPE = "dslType";
    private static final String FIELD_COMPONENT_NAME = "componentName";
    private static final String FIELD_COMPONENT_NAME_CN = "componentNameCn";
    private static final String FIELD_PARAMS = "params";
    private static final String FIELD_INTERACTION_MODE = "interactionMode";
    private static final String FIELD_SCENE = "scene";
    private static final String FIELD_INTEGRATION_PROMPT = "integrationPrompt";
    private static final String FIELD_PARAMS_SCHEMA_JSON = "paramsSchemaJson";
    private static final String FIELD_RENDER_ARGUMENTS_EXAMPLE = "renderArgumentsExample";
    private static final Set<String> INTERACTION_MODES = Set.of("DISPLAY_ONLY", "INTERACTIVE");
    private static final String ERROR_RELEASE_PAYLOAD_INVALID = "component release payload is invalid";
    private static final String ERROR_RELEASE_IDENTITY_MISMATCH = "component release identity does not match";
    private static final String ERROR_RELEASE_DSL_UNSUPPORTED = "component release dslType is unsupported";
    private static final String ERROR_RELEASE_INTERACTION_MODE_INVALID =
            "component release interactionMode is invalid";
    private static final String ERROR_RELEASE_SCHEMA_INVALID = "component paramsSchemaJson is invalid";
    private static final String ERROR_RELEASE_DEMO_INVALID = "component messageDemoJson is invalid";
    private static final String ERROR_COMPONENT_NOT_FOUND = "component does not exist";
    private static final String ERROR_COMPONENT_DISABLED = "component is disabled";
    private static final String ERROR_COMPONENT_RELEASE_NOT_AVAILABLE =
            "component release is not available in current environment";

    @Resource
    private SkillFactoryComponentAssetRepository componentAssetRepository;

    @Resource
    private EnvironmentAwareAssetResolver environmentAwareAssetResolver;

    @Resource
    private RegistryComponentReleaseIdentityResolver componentReleaseIdentityResolver;

    /**
     * 按可信环境解析一个稳定组件名的当前模型可见契约。
     */
    public Map<String, Object> query(String componentName, ReleaseEnvironment requestedEnvironment,
            Long userId) {
        ComponentAsset current = componentAssetRepository.findCardComponentByName(componentName);
        if (current == null) {
            throw failure(ComponentToolErrorCode.COMPONENT_NOT_FOUND, ERROR_COMPONENT_NOT_FOUND);
        }
        if (!Boolean.TRUE.equals(current.getEnabled())) {
            throw failure(ComponentToolErrorCode.COMPONENT_DISABLED, ERROR_COMPONENT_DISABLED);
        }
        RegistryComponentReleaseIdentityResolver.ComponentReleaseIdentity identity;
        try {
            identity = componentReleaseIdentityResolver.resolve(
                    String.valueOf(current.getId()), current.getAssetType(), current.getComponentName());
        } catch (IllegalArgumentException exception) {
            log.warn("组件Tool发布身份解析失败, componentName:{}, assetType:{}, reason:{}",
                    componentName, current.getAssetType(), exception.getMessage());
            throw failure(ComponentToolErrorCode.COMPONENT_RELEASE_NOT_AVAILABLE,
                    ERROR_COMPONENT_RELEASE_NOT_AVAILABLE);
        }
        ResolvedReleasedAsset resolved;
        try {
            resolved = environmentAwareAssetResolver.resolve(
                    new AssetDependencyReference()
                            .setAssetType(identity.getDependencyType())
                            .setAssetKey(identity.getAssetKey()),
                    new AssetResolutionContext()
                            .setRequestedEnvironment(requestedEnvironment)
                            .setUserId(userId));
        } catch (AssetDependencyResolutionException exception) {
            ComponentToolErrorCode errorCode = exception.getErrorCode() == null
                    ? ComponentToolErrorCode.COMPONENT_RELEASE_NOT_AVAILABLE
                    : switch (exception.getErrorCode()) {
                        case ASSET_DISABLED -> ComponentToolErrorCode.COMPONENT_DISABLED;
                        default -> ComponentToolErrorCode.COMPONENT_RELEASE_NOT_AVAILABLE;
                    };
            throw failure(errorCode, ERROR_COMPONENT_RELEASE_NOT_AVAILABLE);
        }
        SkillFactoryComponentAsset released;
        try {
            released = componentReleaseIdentityResolver.resolveReleasedContract(
                    current, identity, resolved);
        } catch (IllegalArgumentException exception) {
            log.warn("组件Tool发布契约解析失败, componentName:{}, assetType:{}, reason:{}",
                    componentName, current.getAssetType(), exception.getMessage());
            throw failure(ComponentToolErrorCode.COMPONENT_RELEASE_INVALID,
                    ERROR_RELEASE_PAYLOAD_INVALID);
        }
        validateReleasedAsset(componentName, released);
        Map<String, Object> result = new LinkedHashMap<>();
        result.put(FIELD_COMPONENT_NAME, released.getComponentName());
        putIfNotBlank(result, FIELD_COMPONENT_NAME_CN, released.getComponentNameCn());
        result.put(FIELD_DSL_TYPE, DSL_TYPE_CARD_CONTAINER);
        result.put(FIELD_INTERACTION_MODE, released.getInteractionMode());
        putIfNotBlank(result, FIELD_SCENE, released.getScene());
        putIfNotBlank(result, FIELD_INTEGRATION_PROMPT, released.getIntegrationPrompt());
        result.put(FIELD_PARAMS_SCHEMA_JSON, parseJsonObject(
                released.getParamsSchemaJson(), ERROR_RELEASE_SCHEMA_INVALID, false));
        Map<String, Object> argumentsExample = new LinkedHashMap<>();
        argumentsExample.put(FIELD_DSL_TYPE, DSL_TYPE_CARD_CONTAINER);
        argumentsExample.put(FIELD_COMPONENT_NAME, released.getComponentName());
        argumentsExample.put(FIELD_PARAMS, parseMessageDemoParams(released.getMessageDemoJson()));
        result.put(FIELD_RENDER_ARGUMENTS_EXAMPLE, argumentsExample);
        log.info("组件Tool当前环境契约解析完成, componentName:{}, requestedEnvironment:{}, "
                        + "resolvedEnvironment:{}, interactionMode:{}",
                componentName, requestedEnvironment, resolved.getResolvedEnvironment(), released.getInteractionMode());
        return result;
    }

    private void validateReleasedAsset(String requestedName, SkillFactoryComponentAsset asset) {
        if (!StringUtils.equals(requestedName, asset.getComponentName())) {
            throw failure(ComponentToolErrorCode.COMPONENT_RELEASE_INVALID, ERROR_RELEASE_IDENTITY_MISMATCH);
        }
        if (!StringUtils.equals(DSL_TYPE_CARD_CONTAINER, asset.getDslType())) {
            throw failure(ComponentToolErrorCode.COMPONENT_RELEASE_INVALID, ERROR_RELEASE_DSL_UNSUPPORTED);
        }
        if (!INTERACTION_MODES.contains(asset.getInteractionMode())) {
            throw failure(ComponentToolErrorCode.COMPONENT_RELEASE_INVALID,
                    ERROR_RELEASE_INTERACTION_MODE_INVALID);
        }
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> parseJsonObject(String json, String errorMessage, boolean optional) {
        if (StringUtils.isBlank(json)) {
            if (optional) {
                return Collections.emptyMap();
            }
            throw failure(ComponentToolErrorCode.COMPONENT_RELEASE_INVALID, errorMessage);
        }
        try {
            Object parsed = JsonSupport.fromJSON(json, Object.class);
            if (!(parsed instanceof Map<?, ?>)) {
                throw failure(ComponentToolErrorCode.COMPONENT_RELEASE_INVALID, errorMessage);
            }
            return new LinkedHashMap<>((Map<String, Object>) parsed);
        } catch (ComponentContractException exception) {
            throw exception;
        } catch (Exception exception) {
            throw failure(ComponentToolErrorCode.COMPONENT_RELEASE_INVALID, errorMessage);
        }
    }

    private Map<String, Object> parseMessageDemoParams(String messageDemoJson) {
        Map<String, Object> demo = parseJsonObject(messageDemoJson, ERROR_RELEASE_DEMO_INVALID, true);
        if (demo.isEmpty()) {
            return Collections.emptyMap();
        }
        Object params = demo.get(FIELD_PARAMS);
        if (!(params instanceof Map<?, ?>)) {
            throw failure(ComponentToolErrorCode.COMPONENT_RELEASE_INVALID, ERROR_RELEASE_DEMO_INVALID);
        }
        return copyMap(params);
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> copyMap(Object value) {
        return new LinkedHashMap<>((Map<String, Object>) value);
    }

    private void putIfNotBlank(Map<String, Object> result, String field, String value) {
        if (StringUtils.isNotBlank(value)) {
            result.put(field, value);
        }
    }

    private ComponentContractException failure(ComponentToolErrorCode errorCode, String message) {
        return new ComponentContractException(errorCode, message);
    }

    /** 单项查询失败；只携带模型可见稳定错误码和短消息。 */
    @Getter
    public static final class ComponentContractException extends IllegalStateException {

        private final ComponentToolErrorCode errorCode;

        private ComponentContractException(ComponentToolErrorCode errorCode, String message) {
            super(message);
            this.errorCode = errorCode;
        }
    }
}
