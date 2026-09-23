package dev.a2flow.management.agentcore.runtime.tool;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;

import jakarta.annotation.Resource;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.model.A2uiApplicationToolErrorCode;
import dev.a2flow.management.release.ReleaseEnvironment;
import dev.a2flow.management.release.dependency.AssetDependencyModels
        .AssetDependencyReference;
import dev.a2flow.management.release.dependency.AssetDependencyModels
        .AssetResolutionContext;
import dev.a2flow.management.release.dependency.AssetDependencyModels
        .ResolvedReleasedAsset;
import dev.a2flow.management.release.dependency.AssetDependencyResolutionException;
import dev.a2flow.management.release.dependency.AssetDependencyType;
import dev.a2flow.management.release.dependency.EnvironmentAwareAssetResolver;

import lombok.Getter;
import lombok.extern.slf4j.Slf4j;

/**
 * A2UI Application Tool 的当前环境模型安全合同查询服务。
 *
 * <p>上游只提交稳定 appCode，环境和 userId 来自可信 ToolContext；本服务通过
 * {@link AssetDependencyType#A2UI_APPLICATION} 读取当前环境不可变 Build，并只投影模型调用
 * {@code render_a2ui_application} 所需的 paramsSchema 和参数示例。它不读取 Registry 草稿，不返回
 * Build/Catalog/执行目标等权威字段，也不回退同名 CARD、其他环境或 latest 资产。
 */
@Service
@Slf4j
public class A2uiApplicationToolContractService {

    private static final String FIELD_APP_CODE = "appCode";
    private static final String FIELD_PARAMS = "params";
    private static final String FIELD_PARAMS_SCHEMA = "paramsSchema";
    private static final String FIELD_ACTION_DECLARATIONS = "actionDeclarations";
    private static final String FIELD_RENDER_ARGUMENTS_EXAMPLE = "renderArgumentsExample";
    private static final String ERROR_RELEASE_NOT_AVAILABLE =
            "A2UI Application release is not available in current environment";
    private static final String ERROR_RELEASE_INVALID =
            "A2UI Application release payload is invalid";
    private static final String ERROR_RELEASE_IDENTITY_MISMATCH =
            "A2UI Application release identity does not match";

    @Resource
    private EnvironmentAwareAssetResolver environmentAwareAssetResolver;

    /** 按可信环境读取一个稳定 appCode 的当前模型可见合同。 */
    @SuppressWarnings("unchecked")
    public Map<String, Object> query(String appCode, ReleaseEnvironment requestedEnvironment,
            Long userId) {
        ResolvedReleasedAsset resolved;
        try {
            resolved = environmentAwareAssetResolver.resolve(
                    new AssetDependencyReference()
                            .setAssetType(AssetDependencyType.A2UI_APPLICATION)
                            .setAssetKey(appCode),
                    new AssetResolutionContext()
                            .setRequestedEnvironment(requestedEnvironment)
                            .setUserId(userId));
        } catch (AssetDependencyResolutionException exception) {
            log.warn("A2UI Application Tool发布源不可用, appCode:{}, environment:{}, errorCode:{}",
                    appCode, requestedEnvironment, exception.getErrorCode());
            throw failure(A2uiApplicationToolErrorCode.A2UI_APPLICATION_RELEASE_NOT_AVAILABLE,
                    ERROR_RELEASE_NOT_AVAILABLE);
        }
        try {
            Map<String, Object> build = JsonSupport.fromJSON(resolved.getPayloadJson(), Map.class);
            Object releasedAppCodeValue = build == null ? null : build.get(FIELD_APP_CODE);
            String releasedAppCode = releasedAppCodeValue instanceof String
                    ? StringUtils.trimToNull((String) releasedAppCodeValue) : null;
            if (!StringUtils.equals(appCode, releasedAppCode)) {
                throw failure(A2uiApplicationToolErrorCode.A2UI_APPLICATION_RELEASE_INVALID,
                        ERROR_RELEASE_IDENTITY_MISMATCH);
            }
            Object paramsSchemaValue = build.get(FIELD_PARAMS_SCHEMA);
            Object actionDeclarationsValue = build.get(FIELD_ACTION_DECLARATIONS);
            if (!(paramsSchemaValue instanceof Map<?, ?>)
                    || !(actionDeclarationsValue instanceof java.util.List<?>)) {
                throw failure(A2uiApplicationToolErrorCode.A2UI_APPLICATION_RELEASE_INVALID,
                        ERROR_RELEASE_INVALID);
            }
            Map<String, Object> result = new LinkedHashMap<>();
            result.put(FIELD_APP_CODE, releasedAppCode);
            result.put(FIELD_PARAMS_SCHEMA,
                    new LinkedHashMap<>((Map<String, Object>) paramsSchemaValue));
            result.put(FIELD_RENDER_ARGUMENTS_EXAMPLE, Map.of(
                    FIELD_APP_CODE, releasedAppCode,
                    FIELD_PARAMS, Collections.emptyMap()));
            log.info("A2UI Application Tool当前环境合同解析完成, appCode:{}, requestedEnvironment:{}, "
                            + "resolvedEnvironment:{}",
                    appCode, requestedEnvironment, resolved.getResolvedEnvironment());
            return result;
        } catch (A2uiApplicationContractException exception) {
            throw exception;
        } catch (RuntimeException exception) {
            log.warn("A2UI Application Tool发布合同解析失败, appCode:{}, environment:{}, errorType:{}",
                    appCode, requestedEnvironment, exception.getClass().getSimpleName());
            throw failure(A2uiApplicationToolErrorCode.A2UI_APPLICATION_RELEASE_INVALID,
                    ERROR_RELEASE_INVALID);
        }
    }

    private A2uiApplicationContractException failure(A2uiApplicationToolErrorCode errorCode,
            String message) {
        return new A2uiApplicationContractException(errorCode, message);
    }

    /** 单个 appCode 查询失败，只携带模型可见稳定错误码和短消息。 */
    @Getter
    public static final class A2uiApplicationContractException extends IllegalStateException {
        private final A2uiApplicationToolErrorCode errorCode;

        private A2uiApplicationContractException(A2uiApplicationToolErrorCode errorCode,
                String message) {
            super(message);
            this.errorCode = errorCode;
        }
    }
}
