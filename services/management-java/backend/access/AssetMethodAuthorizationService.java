package dev.a2flow.management.access;

import java.util.Map;

import jakarta.annotation.Resource;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;

import dev.a2flow.management.lifecycle.WorkflowControlPlaneException;
import dev.a2flow.management.lifecycle.domain.ComponentAsset;
import dev.a2flow.management.method.SkillFactoryMethodEnum;
import dev.a2flow.management.release.ReleaseAssetType;
import dev.a2flow.management.storage.db.repository.SkillFactoryComponentAssetRepository;

import lombok.extern.slf4j.Slf4j;

/**
 * SkillFactory 公开 method 到资产动作的统一授权映射。
 *
 * <p>该类在 dispatcher 进入领域 Service 前识别被修改资产，避免各页面入口重复实现负责人判断。
 * 详情、列表、Diff 和部署详情保持可读；创建入口由领域 Service 在资产落库后初始化负责人。
 */
@Service
@Slf4j
public class AssetMethodAuthorizationService {

    private static final String PARAM_SKILL_CODE = "skillCode";
    private static final String PARAM_WORKSPACE_ID = "workspaceId";
    private static final String PARAM_ID = "id";
    private static final String PARAM_DRAFT_ID = "draftId";
    private static final String PARAM_ASSET_TYPE = "assetType";
    private static final String PARAM_ASSET_KEY = "assetKey";
    private static final String PARAM_WORKFLOW_CODE = "workflowCode";
    private static final String PARAM_FORCE_PUBLISH = "forcePublish";
    private static final String ERROR_ASSET_KEY_REQUIRED = "asset key is required for permission check";
    private static final String ERROR_CODE_WORKFLOW_PARAMETER_INVALID =
            "WORKFLOW_PARAMETER_INVALID";
    private static final String ERROR_WORKFLOW_PARAMETER_INVALID =
            "Workflow请求参数格式错误";
    private static final String ERROR_A2UI_ASSET_NOT_FOUND = "A2UI asset not found";
    private static final String ASSET_TYPE_A2UI_ATOM = "A2UI_ATOM";
    private static final String ASSET_TYPE_A2UI_CATALOG = "A2UI_CATALOG";
    private static final String ASSET_TYPE_A2UI_APPLICATION = "A2UI_APPLICATION";

    @Resource
    private AssetAuthorizationService assetAuthorizationService;

    @Resource
    private SkillFactoryComponentAssetRepository componentAssetRepository;

    /**
     * 对公开 method 执行前置授权；无需授权的只读或创建 method 直接返回。
     */
    public void authorize(String operator, SkillFactoryMethodEnum method, Map<String, String> params) {
        AssetPermissionTarget target = permissionTarget(method, params);
        if (target == null) {
            return;
        }
        log.info("SkillFactory执行公开方法权限校验, operator:{}, method:{}, assetType:{}, assetKey:{}, action:{}",
                operator, method, target.assetType, target.assetKey, target.action);
        assetAuthorizationService.requirePermission(
                operator, target.assetType, target.assetKey, target.action);
    }

    private AssetPermissionTarget permissionTarget(
            SkillFactoryMethodEnum method, Map<String, String> params) {
        return switch (method) {
            case SKILL_UPDATE, ZIP_CONFIRM_IMPORT ->
                    skillTarget(params, PARAM_SKILL_CODE, AssetAction.EDIT);
            case WORKSPACE_FILE_SAVE, WORKSPACE_PATH_DELETE, WORKSPACE_RESET_FROM_VERSION,
                    WORKSPACE_SAVE, SKILL_BINDINGS_REPLACE, RUNTIME_VALIDATE, PACKAGE_BUILD,
                    PACKAGE_VERSION_RESTORE ->
                    skillTarget(params, PARAM_WORKSPACE_ID, AssetAction.EDIT);
            case PACKAGE_PUBLISH_PREPROD, PACKAGE_PUBLISH_ONLINE ->
                    skillTarget(params, PARAM_WORKSPACE_ID, AssetAction.PUBLISH);
            case COMPONENT_BASIC_INFO_UPDATE, COMPONENT_UPDATE -> target(
                    ReleaseAssetType.COMPONENT, required(params, PARAM_ID), AssetAction.EDIT);
            case COMPONENT_OFFLINE -> target(
                    ReleaseAssetType.COMPONENT, required(params, PARAM_ID), AssetAction.OFFLINE);
            case A2UI_CATALOG_COMPONENT_UPDATE -> atomTarget(params, AssetAction.EDIT);
            case A2UI_CATALOG_UPDATE -> catalogTarget(params, AssetAction.EDIT);
            case A2UI_APPLICATION_UPDATE -> applicationTarget(params, AssetAction.EDIT);
            case CAPABILITY_DRAFT_SAVE, CAPABILITY_VALIDATE, CAPABILITY_DRY_RUN -> target(
                    ReleaseAssetType.CAPABILITY_ACTION,
                    required(params, PARAM_DRAFT_ID), AssetAction.EDIT);
            case CAPABILITY_PUBLISH -> target(
                    ReleaseAssetType.CAPABILITY_ACTION,
                    required(params, PARAM_DRAFT_ID), AssetAction.PUBLISH);
            case WORKFLOW_BASIC_INFO_UPDATE, WORKFLOW_DRAFT_UPDATE,
                    WORKFLOW_COMPILED_PLAN_PREVIEW -> workflowTarget(params, AssetAction.EDIT);
            case RELEASE_CHANGE_CREATE -> releaseTarget(params, AssetAction.EDIT);
            case RELEASE_PREPROD_DEPLOY, RELEASE_HISTORY_REDEPLOY ->
                    releaseTarget(params, AssetAction.PUBLISH);
            case RELEASE_ONLINE_DEPLOY -> releaseTarget(params,
                    Boolean.parseBoolean(params.get(PARAM_FORCE_PUBLISH))
                            ? AssetAction.FORCE_PUBLISH : AssetAction.PUBLISH);
            default -> null;
        };
    }

    private AssetPermissionTarget skillTarget(
            Map<String, String> params, String key, AssetAction action) {
        return target(ReleaseAssetType.SKILL, required(params, key), action);
    }

    private AssetPermissionTarget releaseTarget(Map<String, String> params, AssetAction action) {
        ReleaseAssetType assetType = ReleaseAssetType.parse(required(params, PARAM_ASSET_TYPE));
        return target(assetType, required(params, PARAM_ASSET_KEY), action);
    }

    private AssetPermissionTarget workflowTarget(Map<String, String> params, AssetAction action) {
        String workflowCode = params == null ? null : params.get(PARAM_WORKFLOW_CODE);
        if (StringUtils.isBlank(workflowCode)) {
            throw new WorkflowControlPlaneException(
                    ERROR_CODE_WORKFLOW_PARAMETER_INVALID,
                    ERROR_WORKFLOW_PARAMETER_INVALID, null, PARAM_WORKFLOW_CODE);
        }
        return target(ReleaseAssetType.ORCHESTRATION_CONFIG, workflowCode, action);
    }

    private AssetPermissionTarget target(
            ReleaseAssetType assetType, String assetKey, AssetAction action) {
        return new AssetPermissionTarget(assetType, assetKey, action);
    }

    private AssetPermissionTarget atomTarget(Map<String, String> params, AssetAction action) {
        ComponentAsset asset = componentAssetRepository.get(parseId(required(params, PARAM_ID)));
        if (asset == null || !ASSET_TYPE_A2UI_ATOM.equals(asset.getAssetType())) {
            throw new IllegalArgumentException(ERROR_A2UI_ASSET_NOT_FOUND);
        }
        return target(ReleaseAssetType.A2UI_ATOM, asset.getComponentName(), action);
    }

    private AssetPermissionTarget applicationTarget(Map<String, String> params, AssetAction action) {
        ComponentAsset asset = componentAssetRepository.get(parseId(required(params, PARAM_ID)));
        if (asset == null || !ASSET_TYPE_A2UI_APPLICATION.equals(asset.getAssetType())) {
            throw new IllegalArgumentException(ERROR_A2UI_ASSET_NOT_FOUND);
        }
        return target(ReleaseAssetType.A2UI_APPLICATION, asset.getComponentName(), action);
    }

    private AssetPermissionTarget catalogTarget(Map<String, String> params, AssetAction action) {
        ComponentAsset asset = componentAssetRepository.get(parseId(required(params, PARAM_ID)));
        if (asset == null || !ASSET_TYPE_A2UI_CATALOG.equals(asset.getAssetType())) {
            throw new IllegalArgumentException(ERROR_A2UI_ASSET_NOT_FOUND);
        }
        return target(ReleaseAssetType.A2UI_CATALOG, asset.getComponentName(), action);
    }

    private Long parseId(String value) {
        try {
            return Long.valueOf(value);
        } catch (NumberFormatException exception) {
            throw new IllegalArgumentException(ERROR_A2UI_ASSET_NOT_FOUND);
        }
    }

    private String required(Map<String, String> params, String key) {
        String value = params == null ? null : params.get(key);
        if (StringUtils.isBlank(value)) {
            throw new IllegalArgumentException(ERROR_ASSET_KEY_REQUIRED + ": " + key);
        }
        return value;
    }

    private record AssetPermissionTarget(
            ReleaseAssetType assetType, String assetKey, AssetAction action) {
    }
}
