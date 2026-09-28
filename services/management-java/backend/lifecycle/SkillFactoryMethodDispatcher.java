package dev.a2flow.management.lifecycle;

import java.io.IOException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import jakarta.annotation.Resource;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.a2ui.application.A2uiApplicationActionScanService;
import dev.a2flow.management.a2ui.application.A2uiApplicationBlueprintService;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiApplicationActionScanResult;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiInteractionMode;
import dev.a2flow.management.a2ui.application.A2uiApplicationRegistryService;
import dev.a2flow.management.a2ui.application.A2uiApplicationValidationException;
import dev.a2flow.management.a2ui.application.A2uiImmutableJsonSupport;
import dev.a2flow.management.a2ui.catalog.A2uiCatalogRegistryService;
import dev.a2flow.management.a2ui.catalog.A2uiCatalogValidationException;
import dev.a2flow.management.a2ui.gateway.A2uiActionGatewayException;
import dev.a2flow.management.a2ui.registry.A2uiAtomAuthoringProjection;
import dev.a2flow.management.a2ui.registry.A2uiAtomRegistryService;
import dev.a2flow.management.a2ui.registry.A2uiRegistryValidationException;
import dev.a2flow.management.a2ui.release.A2uiReleaseProjectionService;
import dev.a2flow.management.access.AssetAuthorizationService;
import dev.a2flow.management.access.AssetMethodAuthorizationService;
import dev.a2flow.management.access.AssetNotFoundException;
import dev.a2flow.management.access.AssetPermissionDeniedException;
import dev.a2flow.management.agentcore.runtime.tool.CapabilityActionExecutor.CapabilityExecutionException;
import dev.a2flow.management.lifecycle.domain.ComponentAsset;
import dev.a2flow.management.lifecycle.domain.graph.WorkflowGraphCompilationException;
import dev.a2flow.management.lifecycle.domain.graph.WorkflowGraphDataException;
import dev.a2flow.management.method.SkillFactoryMethodEnum;
import dev.a2flow.management.model.SkillFactoryExecutionResult;
import dev.a2flow.management.release.AssetReleaseApplicationService;
import dev.a2flow.management.release.ReleaseAssetType;
import dev.a2flow.management.release.WorkflowReleasePayloadValidationException;
import dev.a2flow.management.release.dependency.AssetDependencyResolutionException;

import lombok.extern.slf4j.Slf4j;

/**
 * SkillFactory 统一执行入口的方法分发器。
 *
 * <p>该类把 adviser 传来的 `method + params` envelope 路由到 sellerdata SkillFactory 内部能力。它只做
 * lifecycle/component/runtime 方法的白名单分发和基础参数校验，不承担 M 端登录态鉴权、
 * seller/specialist 权限校验或 adviser Chat SSE 编排。
 */
@Service
@Slf4j
public class SkillFactoryMethodDispatcher {

    private static final String PARAM_WORKSPACE_ID = "workspaceId";
    private static final String PARAM_FILE_PATH = "filePath";
    private static final String PARAM_CONTENT = "content";
    private static final String PARAM_PACKAGE_TYPE = "packageType";
    private static final String PARAM_PACKAGE_URL = "packageUrl";
    private static final String PARAM_ZIP_FILE_NAME = "zipFileName";
    private static final String PARAM_SKILL_CODE = "skillCode";
    private static final String PARAM_ID = "id";
    private static final String PARAM_PREVIEW_JSON = "previewJson";
    private static final String PARAM_ASSETS_JSON = "assetsJson";
    private static final String PARAM_DRAFT_ID = "draftId";
    private static final String PARAM_REVISION = "revision";
    private static final String PARAM_SESSION_ID = "sessionId";
    private static final String PARAM_INVOKE_ID = "invokeId";
    private static final String PARAM_ASSET_TYPE = "assetType";
    private static final String PARAM_ASSET_KEY = "assetKey";
    private static final String PARAM_OWNERS_JSON = "ownersJson";
    private static final String PARAM_WORKFLOW_CODE = "workflowCode";
    private static final String PARAM_DISPLAY_NAME = "displayName";
    private static final String PARAM_DESCRIPTION = "description";
    private static final String PARAM_SPECIALIST_CODE = "specialistCode";
    private static final String PARAM_PAGE_TOKEN = "pageToken";
    private static final String PARAM_LIMIT = "limit";
    private static final String PARAM_OFFSET = "offset";
    private static final String PARAM_DRAFT_PAYLOAD_JSON = "draftPayloadJson";
    private static final String PARAM_EXPECTED_DRAFT_REVISION = "expectedDraftRevision";
    private static final String PARAM_COMPONENT_JSON = "componentJson";
    private static final String PARAM_CATALOG_JSON = "catalogJson";
    private static final String PARAM_SOURCE_URL = "sourceUrl";
    private static final String PARAM_APPLICATION_JSON = "applicationJson";
    private static final String PARAM_BLUEPRINT_CODE = "blueprintCode";
    private static final String FIELD_CATALOG_ID = "catalogId";
    private static final String FIELD_CATALOG = "catalog";
    private static final String FIELD_INTERACTION_MODE = "interactionMode";
    private static final String FIELD_RELEASE_BLOCKERS = "releaseBlockers";
    private static final String FIELD_REVISION = "revision";
    private static final String FIELD_DIGEST = "digest";
    private static final String FIELD_ENABLED = "enabled";
    private static final String A2UI_CATALOG_ID = "a2flow.digital-employee.pc.v1";
    private static final String A2UI_PROTOCOL_VERSION = "v0.9.1";
    private static final String A2UI_PROTOCOL_STATUS = "CURRENT_PRODUCTION";
    private static final String FIELD_STATUS = "status";
    private static final String STATUS_ALL = "ALL";
    private static final String EMPTY = "";
    private static final int DEFAULT_WORKFLOW_LIST_LIMIT = 30;
    private static final String ERROR_USER_NAME_REQUIRED = "userName is required";
    private static final String ERROR_UNSUPPORTED_METHOD_PREFIX = "unsupported SkillFactory method: ";
    private static final String ERROR_REQUIRED_SUFFIX = " is required";
    private static final String ERROR_CODE_WORKFLOW_PARAMETER_INVALID =
            "WORKFLOW_PARAMETER_INVALID";
    private static final String ERROR_WORKFLOW_PARAMETER_INVALID =
            "Workflow请求参数格式错误";
    private static final String ERROR_CODE_DRAFT_CONFLICT = "DRAFT_CONFLICT";
    private static final String ERROR_CODE_INTERNAL = "INTERNAL_SERVER_ERROR";
    private static final String ERROR_INTERNAL = "服务端处理失败，请稍后重试";
    private static final String ERROR_FIELD_CODE = "errorCode";
    private static final String ERROR_FIELD_ASSET_TYPE = "assetType";
    private static final String ERROR_FIELD_ASSET_CODE = "assetCode";
    private static final String ERROR_FIELD_OPERATION = "operation";
    private static final String ERROR_FIELD_FIELD_PATH = "fieldPath";
    private static final String ERROR_FIELD_REQUESTED_ENVIRONMENT = "requestedEnvironment";
    private static final String ERROR_FIELD_CAUSE_CODE = "causeCode";
    private static final String ERROR_FIELD_WORKFLOW_CODE = "workflowCode";
    private static final String ERROR_FIELD_NODE_CODE = "nodeCode";
    private static final String ERROR_FIELD_SKILL_CODE = "skillCode";
    private static final String ERROR_FIELD_SPECIALIST_CODE = "workflowSpecialistCode";
    private static final String ERROR_FIELD_EDGE_ID = "edgeId";
    private static final String ERROR_FIELD_CYCLE_PATH = "cyclePath";

    @Resource
    private SkillFactoryWorkspaceService workspaceService;

    @Resource
    private SkillFactoryWorkspaceZipExportService workspaceZipExportService;

    @Resource
    private SkillFactoryComponentRegistryService componentRegistryService;

    @Resource
    private SkillFactoryPageConfigService pageConfigService;

    @Resource
    private SkillFactoryWorkbenchRuntimeService workbenchRuntimeService;

    @Resource
    private CapabilityActionDraftService capabilityActionDraftService;

    @Resource
    private CapabilityActionDryRunService capabilityActionDryRunService;

    @Resource
    private SkillBindingCandidateService skillBindingCandidateService;

    @Resource
    private AssetReleaseApplicationService assetReleaseApplicationService;

    @Resource
    private AssetAuthorizationService assetAuthorizationService;

    @Resource
    private SkillFactorySkillMetadataService skillMetadataService;

    @Resource
    private AssetMethodAuthorizationService assetMethodAuthorizationService;

    @Resource
    private WorkflowDefinitionService workflowDefinitionService;

    @Resource
    private WorkflowSpecialistSkillSelector workflowSpecialistSkillSelector;

    @Resource
    private WorkflowGraphPreviewService workflowGraphPreviewService;

    @Resource
    private A2uiAtomRegistryService a2uiAtomRegistryService;

    @Resource
    private A2uiCatalogRegistryService a2uiCatalogRegistryService;

    @Resource
    private A2uiApplicationRegistryService a2uiApplicationRegistryService;

    @Resource
    private A2uiApplicationBlueprintService a2uiApplicationBlueprintService;

    @Resource
    private A2uiApplicationActionScanService a2uiApplicationActionScanService;

    @Resource
    private A2uiReleaseProjectionService a2uiReleaseProjectionService;

    /**
     * 执行 SkillFactory 非流式方法，并把异常转成统一执行结果。
     */
    public SkillFactoryExecutionResult execute(String userName, String method, Map<String, String> params) {
        Map<String, String> safeParams = params == null ? Collections.emptyMap() : params;
        log.info("SkillFactory开始分发方法, userName:{}, method:{}, workspaceId:{}",
                userName, method, safeParams.get(PARAM_WORKSPACE_ID));
        try {
            if (StringUtils.isBlank(userName)) {
                log.warn("SkillFactory方法分发失败，用户名为空, method:{}", method);
                return SkillFactoryExecutionResult.fail(ERROR_USER_NAME_REQUIRED);
            }
            SkillFactoryMethodEnum skillFactoryMethod = SkillFactoryMethodEnum.of(method)
                    .orElse(null);
            if (skillFactoryMethod == null) {
                log.warn("SkillFactory方法不在白名单内, userName:{}, method:{}", userName, method);
                return SkillFactoryExecutionResult.fail(ERROR_UNSUPPORTED_METHOD_PREFIX + method);
            }
            if (skillFactoryMethod.name().startsWith("CODING_")
                    || skillFactoryMethod.name().startsWith("AUTHORING_SESSION_")
                    || skillFactoryMethod == SkillFactoryMethodEnum.CAPABILITY_SKILL_CREATOR_CONTEXT) {
                return SkillFactoryExecutionResult.fail("AI_ASSISTANCE_DISABLED: management is in manual-entry mode");
            }
            assetMethodAuthorizationService.authorize(userName, skillFactoryMethod, safeParams);
            SkillFactoryExecutionResult result = dispatch(userName, skillFactoryMethod, safeParams);
            log.info("SkillFactory方法执行完成, userName:{}, method:{}, success:{}",
                    userName, method, result.isSuccess());
            return result;
        } catch (Exception exception) {
            SkillFactoryExecutionResult knownFailure = knownFailure(exception);
            if (knownFailure != null) {
                log.warn("SkillFactory方法领域校验失败, userName:{}, method:{}, errorType:{}, errorCode:{}",
                        userName, method, exception.getClass().getSimpleName(),
                        errorCodeOf(knownFailure));
                return knownFailure;
            }
            log.error("SkillFactory服务端发生未预期异常, userName:{}, method:{}, workspaceId:{}",
                    userName, method, safeParams.get(PARAM_WORKSPACE_ID), exception);
            return SkillFactoryExecutionResult.fail(
                    ERROR_INTERNAL, errorData(ERROR_CODE_INTERNAL, null, null));
        }
    }

    private SkillFactoryExecutionResult dispatch(String userName, SkillFactoryMethodEnum method,
            Map<String, String> params)
            throws IOException {
        if (method == SkillFactoryMethodEnum.SKILL_FACTORY_CONFIG) {
            return success(pageConfigService.getConfig(), false);
        }
        SkillFactoryExecutionResult accessResult = dispatchAccess(userName, method, params);
        if (accessResult != null) {
            return accessResult;
        }
        SkillFactoryExecutionResult workflowResult = dispatchWorkflow(userName, method, params);
        if (workflowResult != null) {
            return workflowResult;
        }
        if (method == SkillFactoryMethodEnum.SKILL_LIST) {
            return success(SkillListPage.from(workspaceService.listSkills(params), params), false);
        }
        if (method == SkillFactoryMethodEnum.SKILL_DETAIL) {
            return success(skillBindingCandidateService.enrichSkillDetail(
                    workspaceService.skillDetail(required(params, PARAM_SKILL_CODE), params)), false);
        }
        if (method == SkillFactoryMethodEnum.SKILL_METADATA_BATCH_QUERY) {
            return success(skillMetadataService.query(params), true);
        }
        if (method == SkillFactoryMethodEnum.SKILL_UPDATE) {
            return success(workspaceService.updateSkillName(
                    required(params, PARAM_SKILL_CODE), params, userName), false);
        }
        if (method == SkillFactoryMethodEnum.SKILL_COMPONENT_CANDIDATE_LIST) {
            return success(skillBindingCandidateService.componentCandidates(params), true);
        }
        if (method == SkillFactoryMethodEnum.SKILL_CAPABILITY_CANDIDATE_LIST) {
            return success(skillBindingCandidateService.capabilityCandidates(userName, params), true);
        }
        if (method == SkillFactoryMethodEnum.ZIP_CONFIRM_IMPORT) {
            return success(workspaceService.confirmZipImport(
                    required(params, PARAM_SKILL_CODE),
                    required(params, PARAM_ZIP_FILE_NAME),
                    params), false);
        }
        if (method == SkillFactoryMethodEnum.WORKSPACE_CREATE) {
            return success(workspaceService.createWorkspace(userName, params), false);
        }
        if (method == SkillFactoryMethodEnum.WORKSPACE_TREE) {
            return success(workspaceService.tree(required(params, PARAM_WORKSPACE_ID), params), false);
        }
        if (method == SkillFactoryMethodEnum.WORKSPACE_FILE_CONTENT) {
            return success(workspaceService.fileContent(
                    required(params, PARAM_WORKSPACE_ID), required(params, PARAM_FILE_PATH), params), false);
        }
        if (method == SkillFactoryMethodEnum.WORKSPACE_ZIP_EXPORT) {
            return success(workspaceZipExportService.export(
                    required(params, PARAM_WORKSPACE_ID), params), false);
        }
        if (method == SkillFactoryMethodEnum.WORKSPACE_FILE_SAVE) {
            return success(workspaceService.saveFile(
                    required(params, PARAM_WORKSPACE_ID),
                    required(params, PARAM_FILE_PATH),
                    string(params.get(PARAM_CONTENT)), params), false);
        }
        SkillFactoryExecutionResult workspaceMutationResult = dispatchWorkspaceMutation(method, params);
        if (workspaceMutationResult != null) {
            return workspaceMutationResult;
        }
        if (method == SkillFactoryMethodEnum.WORKSPACE_DIFF) {
            return success(workspaceService.workspaceDiff(required(params, PARAM_WORKSPACE_ID), params), false);
        }
        if (method == SkillFactoryMethodEnum.WORKSPACE_RENDER_SAMPLE_EXTRACT) {
            return success(workspaceService.extractRenderSample(
                    required(params, PARAM_WORKSPACE_ID), params), false);
        }
        SkillFactoryExecutionResult workbenchResult = dispatchWorkbenchRuntime(userName, method, params);
        if (workbenchResult != null) {
            return workbenchResult;
        }
        if (method == SkillFactoryMethodEnum.PACKAGE_BUILD) {
            return success(workspaceService.buildPackage(
                    required(params, PARAM_WORKSPACE_ID), string(params.get(PARAM_PACKAGE_TYPE)), params), false);
        }
        if (method == SkillFactoryMethodEnum.PACKAGE_RELEASE_OPTIONS) {
            return success(workspaceService.releaseOptions(required(params, PARAM_WORKSPACE_ID), params), false);
        }
        if (method == SkillFactoryMethodEnum.PACKAGE_ONLINE_PUBLISH_DIFF) {
            return success(workspaceService.onlinePublishDiff(required(params, PARAM_WORKSPACE_ID), params), false);
        }
        if (method == SkillFactoryMethodEnum.PACKAGE_PUBLISH_PREPROD) {
            return success(workspaceService.publishPreprodPackage(
                    required(params, PARAM_WORKSPACE_ID), params), false);
        }
        if (method == SkillFactoryMethodEnum.PACKAGE_PUBLISH_ONLINE) {
            return success(workspaceService.publishOnlinePackage(required(params, PARAM_WORKSPACE_ID), params), false);
        }
        if (method == SkillFactoryMethodEnum.PACKAGE_VERSION_RESTORE) {
            return success(workspaceService.restorePackage(
                    required(params, PARAM_WORKSPACE_ID), string(params.get(PARAM_PACKAGE_URL)), params), false);
        }
        if (method == SkillFactoryMethodEnum.COMPONENT_LIST) {
            return success(componentRegistryService.list(params), true);
        }
        if (method == SkillFactoryMethodEnum.COMPONENT_ENABLED_LIST) {
            return success(componentRegistryService.listEnabled(params), true);
        }
        if (method == SkillFactoryMethodEnum.COMPONENT_PUBLISHED_LIST) {
            return success(componentRegistryService.listPublished(params), true);
        }
        if (method == SkillFactoryMethodEnum.COMPONENT_DETAIL) {
            return success(componentRegistryService.detail(required(params, PARAM_ID)), false);
        }
        if (method == SkillFactoryMethodEnum.COMPONENT_REGISTER) {
            return success(componentRegistryService.register(userName, params), false);
        }
        if (method == SkillFactoryMethodEnum.COMPONENT_BASIC_INFO_UPDATE) {
            return success(componentRegistryService.updateCardBasicInfo(userName, params), false);
        }
        if (method == SkillFactoryMethodEnum.COMPONENT_UPDATE) {
            return success(componentRegistryService.update(userName, params), false);
        }
        if (method == SkillFactoryMethodEnum.COMPONENT_OFFLINE) {
            return success(componentRegistryService.offline(userName, required(params, PARAM_ID)), false);
        }
        if (method == SkillFactoryMethodEnum.COMPONENT_PREVIEW) {
            return success(componentRegistryService.preview(
                    required(params, PARAM_ID), string(params.get(PARAM_PREVIEW_JSON))), false);
        }
        SkillFactoryExecutionResult a2uiResult = dispatchA2ui(userName, method, params);
        if (a2uiResult != null) {
            return a2uiResult;
        }
        SkillFactoryExecutionResult componentRuntimeResult =
                dispatchComponentRuntime(method, params);
        if (componentRuntimeResult != null) {
            return componentRuntimeResult;
        }
        SkillFactoryExecutionResult capabilityResult = dispatchCapability(userName, method, params);
        if (capabilityResult != null) {
            return capabilityResult;
        }
        SkillFactoryExecutionResult releaseResult = dispatchRelease(userName, method, params);
        if (releaseResult != null) {
            return releaseResult;
        }
        return SkillFactoryExecutionResult.fail(ERROR_UNSUPPORTED_METHOD_PREFIX + method.name());
    }

    /**
     * 分发 Workflow M 端配置方法。
     *
     * <p>本方法只复用既有 Workflow 领域 Service，不实现发布状态机；Diff、审批、PRT/ONLINE、
     * 历史与恢复继续由通用 RELEASE_* 方法进入 publish-center-common-v2。日志不输出完整草稿内容。
     */
    private SkillFactoryExecutionResult dispatchWorkflow(String userName,
            SkillFactoryMethodEnum method, Map<String, String> params) {
        if (method == SkillFactoryMethodEnum.WORKFLOW_CREATE) {
            return success(workflowDefinitionService.createWorkflow(
                    userName, string(params.get(PARAM_DISPLAY_NAME)),
                    string(params.get(PARAM_DESCRIPTION)),
                    string(params.get(PARAM_SPECIALIST_CODE))), false);
        }
        if (method == SkillFactoryMethodEnum.WORKFLOW_DETAIL) {
            return success(workflowDefinitionService.getWorkflow(
                    userName, requiredWorkflow(params, PARAM_WORKFLOW_CODE)), false);
        }
        if (method == SkillFactoryMethodEnum.WORKFLOW_LIST) {
            rejectWorkflowOffset(params);
            return success(workflowDefinitionService.getWorkflowList(
                    userName, string(params.get(PARAM_SPECIALIST_CODE)),
                    string(params.get(PARAM_PAGE_TOKEN)), workflowListLimit(params)), false);
        }
        if (method == SkillFactoryMethodEnum.WORKFLOW_BASIC_INFO_UPDATE) {
            return success(workflowDefinitionService.updateWorkflowBasicInfo(
                    userName, requiredWorkflow(params, PARAM_WORKFLOW_CODE),
                    params.get(PARAM_DISPLAY_NAME), params.get(PARAM_DESCRIPTION)), false);
        }
        if (method == SkillFactoryMethodEnum.WORKFLOW_DRAFT_DETAIL) {
            return success(workflowDefinitionService.getWorkflowDraftPayload(
                    userName, requiredWorkflow(params, PARAM_WORKFLOW_CODE)), false);
        }
        if (method == SkillFactoryMethodEnum.WORKFLOW_DRAFT_UPDATE) {
            return success(workflowDefinitionService.updateWorkflowDraft(
                    userName, requiredWorkflow(params, PARAM_WORKFLOW_CODE),
                    string(params.get(PARAM_DRAFT_PAYLOAD_JSON)),
                    requiredWorkflowLong(params, PARAM_EXPECTED_DRAFT_REVISION)), false);
        }
        if (method == SkillFactoryMethodEnum.WORKFLOW_SKILL_CANDIDATES) {
            return success(workflowSpecialistSkillSelector.getSkillsForWorkflow(
                    userName, requiredWorkflow(params, PARAM_WORKFLOW_CODE)), true);
        }
        if (method == SkillFactoryMethodEnum.WORKFLOW_COMPILED_PLAN_PREVIEW) {
            return success(workflowGraphPreviewService.preview(
                    userName, requiredWorkflow(params, PARAM_WORKFLOW_CODE),
                    string(params.get(PARAM_DRAFT_PAYLOAD_JSON))), false);
        }
        return null;
    }

    /**
     * 分发组件运行态查询与工作台预览；非组件运行态方法返回 null。
     */
    private SkillFactoryExecutionResult dispatchComponentRuntime(
            SkillFactoryMethodEnum method, Map<String, String> params) {
        if (method == SkillFactoryMethodEnum.COMPONENT_RUNTIME_DETAIL) {
            return success(componentRegistryService.runtimeDetail(params), false);
        }
        if (method == SkillFactoryMethodEnum.COMPONENT_RUNTIME_BATCH_GET) {
            return success(componentRegistryService.runtimeBatchGet(
                    string(params.get(PARAM_ASSETS_JSON)), params), true);
        }
        if (method == SkillFactoryMethodEnum.COMPONENT_RENDER_PREVIEW) {
            return success(componentRegistryService.renderPreview(params), false);
        }
        return null;
    }

    /**
     * 分发业务能力注册、查询和编辑方法；非业务能力方法返回 null。
     */
    private SkillFactoryExecutionResult dispatchCapability(String userName, SkillFactoryMethodEnum method,
            Map<String, String> params) {
        if (method == SkillFactoryMethodEnum.CAPABILITY_LIST) {
            return success(skillBindingCandidateService.capabilityCandidates(userName, params), true);
        }
        if (method == SkillFactoryMethodEnum.CAPABILITY_PUBLISHED_LIST) {
            return success(skillBindingCandidateService.enrichCapabilities(
                    capabilityActionDraftService.listPublished(params)), true);
        }
        if (method == SkillFactoryMethodEnum.CAPABILITY_DRAFT_CREATE) {
            return success(capabilityActionDraftService.create(userName, params), false);
        }
        if (method == SkillFactoryMethodEnum.CAPABILITY_DRAFT_DETAIL) {
            return success(skillBindingCandidateService.enrichCapability(
                    capabilityActionDraftService.detail(required(params, PARAM_DRAFT_ID))), false);
        }
        if (method == SkillFactoryMethodEnum.CAPABILITY_DRAFT_SAVE) {
            return success(capabilityActionDraftService.save(userName, params), false);
        }
        if (method == SkillFactoryMethodEnum.CAPABILITY_VALIDATE) {
            return success(capabilityActionDraftService.validate(userName, params), false);
        }
        if (method == SkillFactoryMethodEnum.CAPABILITY_DRY_RUN) {
            return success(capabilityActionDryRunService.execute(userName, params), false);
        }
        if (method == SkillFactoryMethodEnum.CAPABILITY_PUBLISH) {
            return success(capabilityActionDraftService.publish(userName, params), false);
        }
        return null;
    }

    /**
     * 分发通用资产权限查询和管理员负责人替换方法。非权限方法返回 null。
     */
    private SkillFactoryExecutionResult dispatchAccess(String userName, SkillFactoryMethodEnum method,
            Map<String, String> params) {
        ReleaseAssetType assetType = method == SkillFactoryMethodEnum.ASSET_ACCESS_GET
                                     || method == SkillFactoryMethodEnum.ASSET_OWNER_REPLACE
                                     ? ReleaseAssetType.parse(required(params, PARAM_ASSET_TYPE)) : null;
        if (method == SkillFactoryMethodEnum.ASSET_ACCESS_GET) {
            return success(assetAuthorizationService.getAccess(
                    userName, assetType, required(params, PARAM_ASSET_KEY)), false);
        }
        if (method == SkillFactoryMethodEnum.ASSET_OWNER_REPLACE) {
            return success(assetAuthorizationService.replaceOwners(
                    userName, assetType, required(params, PARAM_ASSET_KEY),
                    required(params, PARAM_OWNERS_JSON)), false);
        }
        return null;
    }

    /**
     * 分发工作区摘要保存和受控删除方法。非工作区变更方法返回 null。
     */
    private SkillFactoryExecutionResult dispatchWorkspaceMutation(SkillFactoryMethodEnum method,
            Map<String, String> params) throws IOException {
        if (method == SkillFactoryMethodEnum.WORKSPACE_PATH_DELETE) {
            return success(workspaceService.deletePath(
                    required(params, PARAM_WORKSPACE_ID), required(params, PARAM_FILE_PATH), params), false);
        }
        if (method == SkillFactoryMethodEnum.WORKSPACE_RESET_FROM_VERSION) {
            return success(workspaceService.resetWorkspaceFromVersion(
                    required(params, PARAM_WORKSPACE_ID), params), false);
        }
        if (method == SkillFactoryMethodEnum.WORKSPACE_SAVE) {
            return success(workspaceService.saveWorkspace(required(params, PARAM_WORKSPACE_ID), params), false);
        }
        return null;
    }

    /**
     * 分发 Skill 工作台的完整关系覆盖和运行态校验方法。非工作台运行方法返回 null。
     */
    private SkillFactoryExecutionResult dispatchWorkbenchRuntime(String userName,
            SkillFactoryMethodEnum method, Map<String, String> params) throws IOException {
        if (method == SkillFactoryMethodEnum.SKILL_BINDINGS_REPLACE) {
            return success(workbenchRuntimeService.replaceBindings(userName, params), false);
        }
        if (method == SkillFactoryMethodEnum.RUNTIME_VALIDATE) {
            return success(workbenchRuntimeService.validateRuntime(userName, params), false);
        }
        return null;
    }

    /**
     * 分发共享发布控制面方法。非发布方法返回 null，由主分发链继续处理。
     */
    private SkillFactoryExecutionResult dispatchRelease(String userName, SkillFactoryMethodEnum method,
            Map<String, String> params) {
        if (method == SkillFactoryMethodEnum.RELEASE_OVERVIEW) {
            return success(assetReleaseApplicationService.overview(userName, params), false);
        }
        if (method == SkillFactoryMethodEnum.RELEASE_CHANGE_CREATE) {
            return success(assetReleaseApplicationService.createChange(userName, params), false);
        }
        if (method == SkillFactoryMethodEnum.RELEASE_DIFF) {
            return success(assetReleaseApplicationService.diff(userName, params), false);
        }
        if (method == SkillFactoryMethodEnum.RELEASE_PREPROD_DEPLOY) {
            return success(assetReleaseApplicationService.deployPreprod(userName, params), false);
        }
        if (method == SkillFactoryMethodEnum.RELEASE_ONLINE_DEPLOY) {
            return success(assetReleaseApplicationService.deployOnline(userName, params), false);
        }
        if (method == SkillFactoryMethodEnum.RELEASE_HISTORY_REDEPLOY) {
            return success(assetReleaseApplicationService.redeployHistory(userName, params), false);
        }
        if (method == SkillFactoryMethodEnum.RELEASE_GRAY_START) {
            return success(assetReleaseApplicationService.startGray(userName, params), false);
        }
        if (method == SkillFactoryMethodEnum.RELEASE_GRAY_ADJUST) {
            return success(assetReleaseApplicationService.adjustGray(userName, params), false);
        }
        if (method == SkillFactoryMethodEnum.RELEASE_GRAY_STOP) {
            return success(assetReleaseApplicationService.stopGray(userName, params), false);
        }
        if (method == SkillFactoryMethodEnum.RELEASE_GRAY_PROMOTE) {
            return success(assetReleaseApplicationService.promoteGray(userName, params), false);
        }
        if (method == SkillFactoryMethodEnum.RELEASE_DEPLOYMENT_DETAIL) {
            return success(assetReleaseApplicationService.deploymentDetail(userName, params), false);
        }
        return null;
    }

    private SkillFactoryExecutionResult knownFailure(Exception exception) {
        if (exception instanceof SkillFactoryValidationException validation) {
            return SkillFactoryExecutionResult.fail(validation.getMessage(), errorData(
                    validation.getErrorCode(), null, validation.getFieldPath()));
        }
        if (exception instanceof CapabilityExecutionException execution) {
            return SkillFactoryExecutionResult.fail(execution.getMessage(), errorData(
                    execution.getErrorCode().name(), null, null));
        }
        if (exception instanceof CapabilityActionDryRunValidationException validation) {
            return SkillFactoryExecutionResult.fail(validation.getMessage(), errorData(
                    validation.getErrorCode(), null, validation.getFieldPath()));
        }
        if (exception instanceof A2uiRegistryValidationException registry) {
            return SkillFactoryExecutionResult.fail(registry.getMessage(), errorData(
                    registry.getErrorCode(), null, null));
        }
        if (exception instanceof A2uiCatalogValidationException catalog) {
            return SkillFactoryExecutionResult.fail(catalog.getMessage(), errorData(
                    catalog.getErrorCode(), null, null));
        }
        if (exception instanceof A2uiApplicationValidationException validation) {
            return SkillFactoryExecutionResult.fail(validation.getMessage(), errorData(
                    validation.getErrorCode(), null, validation.getFieldPath()));
        }
        if (exception instanceof A2uiActionGatewayException gateway) {
            return SkillFactoryExecutionResult.fail(gateway.getMessage(), errorData(
                    gateway.getErrorCode(), null, gateway.getSafePointer()));
        }
        if (exception instanceof AssetDependencyResolutionException dependency) {
            Map<String, Object> data = errorData(
                    dependency.getErrorCode().name(), null, dependency.getFieldPath());
            data.put(ERROR_FIELD_ASSET_TYPE, dependency.getAssetType() == null
                    ? null : dependency.getAssetType().name());
            data.put(ERROR_FIELD_ASSET_CODE, dependency.getAssetKey());
            data.put(ERROR_FIELD_REQUESTED_ENVIRONMENT,
                    dependency.getRequestedEnvironment() == null
                            ? null : dependency.getRequestedEnvironment().name());
            data.put(ERROR_FIELD_CAUSE_CODE, dependency.getCauseCode());
            return SkillFactoryExecutionResult.fail(dependency.getMessage(), data);
        }
        if (exception instanceof AssetNotFoundException missing) {
            Map<String, Object> data = errorData(
                    missing.getErrorCode(), null, null);
            data.put(ERROR_FIELD_ASSET_TYPE, missing.getAssetType());
            data.put(ERROR_FIELD_ASSET_CODE, missing.getAssetCode());
            return SkillFactoryExecutionResult.fail(missing.getMessage(), data);
        }
        if (exception instanceof AssetPermissionDeniedException denied) {
            Map<String, Object> data = errorData(
                    denied.getErrorCode(), denied.getAssetCode(), denied.getFieldPath());
            data.put(ERROR_FIELD_ASSET_TYPE, denied.getAssetType());
            data.put(ERROR_FIELD_ASSET_CODE, denied.getAssetCode());
            data.put(ERROR_FIELD_OPERATION, denied.getOperation());
            return SkillFactoryExecutionResult.fail(denied.getMessage(), data);
        }
        if (exception instanceof WorkflowControlPlaneException controlPlane) {
            return SkillFactoryExecutionResult.fail(controlPlane.getMessage(), errorData(
                    controlPlane.getErrorCode(), controlPlane.getWorkflowCode(),
                    controlPlane.getFieldPath()));
        }
        if (exception instanceof WorkflowSkillReferenceValidationException reference) {
            Map<String, Object> data = errorData(
                    reference.getErrorCode(), null, reference.getFieldPath());
            data.put(ERROR_FIELD_NODE_CODE, reference.getNodeCode());
            data.put(ERROR_FIELD_SKILL_CODE, reference.getSkillCode());
            data.put(ERROR_FIELD_SPECIALIST_CODE, reference.getWorkflowSpecialistCode());
            return SkillFactoryExecutionResult.fail(reference.getMessage(), data);
        }
        if (exception instanceof WorkflowDraftConflictException conflict) {
            return SkillFactoryExecutionResult.fail(ERROR_CODE_DRAFT_CONFLICT, errorData(
                    ERROR_CODE_DRAFT_CONFLICT, conflict.getWorkflowCode(), null));
        }
        if (exception instanceof WorkflowGraphDataException graphData) {
            return SkillFactoryExecutionResult.fail(graphData.getMessage(), errorData(
                    graphData.getErrorCode(), null, graphData.getFieldPath()));
        }
        if (exception instanceof WorkflowGraphCompilationException compilation) {
            Map<String, Object> data = errorData(
                    compilation.getErrorCode(), null, compilation.getFieldPath());
            data.put(ERROR_FIELD_NODE_CODE, compilation.getNodeCode());
            data.put(ERROR_FIELD_EDGE_ID, compilation.getEdgeId());
            data.put(ERROR_FIELD_CYCLE_PATH, compilation.getCyclePath());
            return SkillFactoryExecutionResult.fail(compilation.getMessage(), data);
        }
        if (exception instanceof WorkflowReleasePayloadValidationException payload) {
            return SkillFactoryExecutionResult.fail(payload.getMessage(), errorData(
                    payload.getErrorCode(), payload.getWorkflowCode(), payload.getFieldPath()));
        }
        return null;
    }

    /** 领域失败日志只记录稳定错误码，不输出请求参数或完整业务 payload。 */
    private Object errorCodeOf(SkillFactoryExecutionResult result) {
        if (!(result.getData() instanceof Map)) {
            return null;
        }
        return ((Map<?, ?>) result.getData()).get(ERROR_FIELD_CODE);
    }

    private Map<String, Object> errorData(
            String errorCode, String workflowCode, String fieldPath) {
        Map<String, Object> data = new LinkedHashMap<>();
        data.put(ERROR_FIELD_CODE, errorCode);
        data.put(ERROR_FIELD_WORKFLOW_CODE, workflowCode);
        data.put(ERROR_FIELD_FIELD_PATH, fieldPath);
        return data;
    }

    private SkillFactoryExecutionResult success(Object data, boolean list) {
        return SkillFactoryExecutionResult.success(data, list);
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> jsonObject(Map<String, String> params, String key) {
        return JsonSupport.fromJSON(required(params, key), Map.class);
    }

    private SkillFactoryExecutionResult dispatchA2ui(String userName, SkillFactoryMethodEnum method,
            Map<String, String> params) {
        if (method == SkillFactoryMethodEnum.A2UI_CATALOG_LIST) {
            return success(projectCatalogs(a2uiCatalogRegistryService.list(params)), true);
        }
        if (method == SkillFactoryMethodEnum.A2UI_CATALOG_DETAIL) {
            return success(projectCatalog(
                    a2uiCatalogRegistryService.detail(required(params, PARAM_ID))), false);
        }
        if (method == SkillFactoryMethodEnum.A2UI_CATALOG_CREATE) {
            return success(projectCatalog(a2uiCatalogRegistryService.create(userName,
                    jsonObject(params, PARAM_CATALOG_JSON))), false);
        }
        if (method == SkillFactoryMethodEnum.A2UI_CATALOG_UPDATE) {
            return success(projectCatalog(a2uiCatalogRegistryService.update(
                    userName, required(params, PARAM_ID),
                    jsonObject(params, PARAM_CATALOG_JSON))), false);
        }
        if (method == SkillFactoryMethodEnum.A2UI_CATALOG_OFFICIAL_IMPORT) {
            return success(projectCatalog(a2uiCatalogRegistryService.importOfficial(userName)), false);
        }
        if (method == SkillFactoryMethodEnum.A2UI_CATALOG_MANAGED_IMPORT) {
            return success(projectCatalog(a2uiCatalogRegistryService.importManaged(
                    userName, params.get(PARAM_SOURCE_URL), params.get(PARAM_CATALOG_JSON))), false);
        }
        if (method == SkillFactoryMethodEnum.A2UI_CATALOG_COMPONENT_LIST) {
            return success(projectAtoms(a2uiAtomRegistryService.list(params)), true);
        }
        if (method == SkillFactoryMethodEnum.A2UI_CATALOG_COMPONENT_DETAIL) {
            return success(projectAtom(a2uiAtomRegistryService.detail(required(params, PARAM_ID))), false);
        }
        if (method == SkillFactoryMethodEnum.A2UI_CATALOG_COMPONENT_CREATE) {
            return success(a2uiAtomRegistryService.create(userName,
                    jsonObject(params, PARAM_COMPONENT_JSON)), false);
        }
        if (method == SkillFactoryMethodEnum.A2UI_CATALOG_COMPONENT_UPDATE) {
            return success(a2uiAtomRegistryService.update(userName, required(params, PARAM_ID),
                    jsonObject(params, PARAM_COMPONENT_JSON)), false);
        }
        if (method == SkillFactoryMethodEnum.A2UI_APPLICATION_LIST) {
            return success(projectApplications(a2uiApplicationRegistryService.list(params), params), true);
        }
        if (method == SkillFactoryMethodEnum.A2UI_APPLICATION_DETAIL) {
            return success(projectApplication(
                    a2uiApplicationRegistryService.detail(required(params, PARAM_ID))), false);
        }
        if (method == SkillFactoryMethodEnum.A2UI_APPLICATION_CREATE) {
            return success(projectSavedApplication(a2uiApplicationRegistryService.create(userName,
                    jsonObject(params, PARAM_APPLICATION_JSON))), false);
        }
        if (method == SkillFactoryMethodEnum.A2UI_APPLICATION_UPDATE) {
            return success(projectSavedApplication(a2uiApplicationRegistryService.update(
                    userName, required(params, PARAM_ID),
                    jsonObject(params, PARAM_APPLICATION_JSON))), false);
        }
        if (method == SkillFactoryMethodEnum.A2UI_APPLICATION_BLUEPRINT_LIST) {
            return success(a2uiApplicationBlueprintService.listBlueprints(), true);
        }
        if (method == SkillFactoryMethodEnum.A2UI_APPLICATION_BLUEPRINT_IMPORT) {
            return success(a2uiApplicationBlueprintService.importDraft(
                    required(params, PARAM_BLUEPRINT_CODE)), false);
        }
        if (method == SkillFactoryMethodEnum.A2UI_APPLICATION_ACTION_SCAN) {
            return success(a2uiApplicationActionScanService.scan(
                    jsonObject(params, PARAM_APPLICATION_JSON)), false);
        }
        return null;
    }

    private List<Map<String, Object>> projectAtoms(List<ComponentAsset> assets) {
        List<Map<String, Object>> result = new ArrayList<>();
        if (assets != null && !assets.isEmpty()) {
            // 所有 Atom 共用同一 Catalog，在当前请求内只生成一次发布投影。
            Map<String, Object> release = projectionRelease();
            assets.forEach(asset -> result.add(A2uiAtomAuthoringProjection.project(asset, release)));
        }
        return result;
    }

    private List<Map<String, Object>> projectCatalogs(List<Map<String, Object>> catalogs) {
        List<Map<String, Object>> result = new ArrayList<>();
        if (catalogs != null) {
            catalogs.forEach(catalog -> result.add(projectCatalog(catalog)));
        }
        return result;
    }

    /** 为 Catalog 管理态附加服务端 PRT/ONLINE 精确发布投影。 */
    private Map<String, Object> projectCatalog(Map<String, Object> catalog) {
        Map<String, Object> result = catalog == null
                ? new LinkedHashMap<>() : new LinkedHashMap<>(catalog);
        Map<String, Object> release = a2uiReleaseProjectionService.catalogProjection(
                string(result.get(FIELD_CATALOG_ID)));
        result.put("releases", release.get("releases"));
        result.put("componentTypes", release.get("componentTypes"));
        result.put("componentOrigins", release.get("componentOrigins"));
        return result;
    }

    private Map<String, Object> projectAtom(
            ComponentAsset asset) {
        return A2uiAtomAuthoringProjection.project(
                asset, projectionRelease());
    }

    private List<Map<String, Object>> projectApplications(
            List<ComponentAsset> assets, Map<String, String> params) {
        List<Map<String, Object>> result = new ArrayList<>();
        Map<String, Map<String, Object>> dependencies = new LinkedHashMap<>();
        String status = params.get(FIELD_STATUS);
        if (assets != null) {
            for (ComponentAsset asset : assets) {
                Map<String, Object> projected = projectApplication(asset, dependencies);
                if (StringUtils.isBlank(status) || STATUS_ALL.equals(status)
                        || status.equals(projected.get(FIELD_STATUS))) {
                    result.add(projected);
                }
            }
        }
        return result;
    }

    private Map<String, Object> projectApplication(ComponentAsset asset) {
        return projectApplication(asset, new LinkedHashMap<>());
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> projectApplication(
            ComponentAsset asset, Map<String, Map<String, Object>> dependencyProjections) {
        Map<String, Object> source = asset == null || StringUtils.isBlank(asset.getRuntimeConfigJson())
                ? new LinkedHashMap<>() : JsonSupport.fromJSON(asset.getRuntimeConfigJson(), Map.class);
        String catalogId = string(source.get(FIELD_CATALOG_ID));
        Map<String, Object> dependencies = dependencyProjections.computeIfAbsent(
                catalogId, this::projectApplicationDependencies);
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("id", asset == null ? null : String.valueOf(asset.getId()));
        result.put("appCode", source.get("appCode"));
        result.put("nameCn", source.get("nameCn"));
        result.put("description", source.get("description"));
        result.put(FIELD_INTERACTION_MODE, source.getOrDefault(
                FIELD_INTERACTION_MODE, A2uiInteractionMode.DISPLAY_ONLY.name()));
        result.put("protocolVersion", A2UI_PROTOCOL_VERSION);
        result.put("protocolStatus", A2UI_PROTOCOL_STATUS);
        result.put(FIELD_CATALOG, dependencies.get(FIELD_CATALOG));
        result.put(FIELD_RELEASE_BLOCKERS, dependencies.get(FIELD_RELEASE_BLOCKERS));
        result.put("showTemplate", source.get("showTemplate"));
        result.put("loadBindings", source.getOrDefault("loadBindings", Collections.emptyList()));
        result.put("actionBindings", source.getOrDefault("actionBindings", Collections.emptyList()));
        String sourceDigest = A2uiImmutableJsonSupport.digest(source);
        result.putAll(a2uiReleaseProjectionService.applicationProjection(string(source.get("appCode")), sourceDigest));
        result.put("sourceDigest", sourceDigest);
        result.put("createTime", asset == null ? null : asset.getCreateTime());
        result.put("updateTime", asset == null ? null : asset.getUpdateTime());
        return result;
    }

    private Map<String, Object> projectSavedApplication(ComponentAsset saved) {
        Map<String, Object> result = projectApplication(saved);
        A2uiApplicationActionScanResult actionScan =
                a2uiApplicationRegistryService.scanCanonicalSource(saved);
        Object releaseBlockers = result.get(FIELD_RELEASE_BLOCKERS);
        if (releaseBlockers instanceof List) {
            Set<String> mergedBlockers = new LinkedHashSet<>();
            if (actionScan.getReleaseBlockers() != null) {
                mergedBlockers.addAll(actionScan.getReleaseBlockers());
            }
            ((List<?>) releaseBlockers).forEach(blocker -> mergedBlockers.add(String.valueOf(blocker)));
            actionScan.setReleaseBlockers(new ArrayList<>(mergedBlockers));
        }
        result.put("actionScan", actionScan);
        return result;
    }

    /**
     * 生成 Application 管理面依赖投影。
     *
     * <p>已保存草稿允许暂时缺少 Catalog 发布闭包；此处只把服务端确定的阻塞原因投影出来，
     * 不改变严格发布投影，也不生成其他环境、latest 或默认 Catalog 权威值。
     */
    private Map<String, Object> projectApplicationDependencies(String catalogId) {
        try {
            return a2uiReleaseProjectionService.applicationDependencyProjection(catalogId);
        } catch (A2uiRegistryValidationException exception) {
            log.info("A2UI Application 草稿依赖未闭合，保留草稿投影, catalogId:{}, blocker:{}",
                    catalogId, exception.getErrorCode());
            Map<String, Object> catalog = new LinkedHashMap<>();
            catalog.put(FIELD_CATALOG_ID, StringUtils.defaultString(catalogId));
            catalog.put(FIELD_REVISION, EMPTY);
            catalog.put(FIELD_DIGEST, EMPTY);
            catalog.put(FIELD_ENABLED, false);

            Map<String, Object> result = new LinkedHashMap<>();
            result.put(FIELD_CATALOG, catalog);
            result.put(FIELD_RELEASE_BLOCKERS, List.of(exception.getErrorCode()));
            return result;
        }
    }

    private Map<String, Object> projectionCatalog() {
        return a2uiReleaseProjectionService.catalogProjection(A2UI_CATALOG_ID);
    }

    private Map<String, Object> projectionRelease() {
        return projectionCatalog();
    }

    private String required(Map<String, String> params, String key) {
        String value = string(params.get(key));
        if (StringUtils.isBlank(value)) {
            throw new IllegalArgumentException(key + ERROR_REQUIRED_SUFFIX);
        }
        return value;
    }

    private String requiredWorkflow(Map<String, String> params, String key) {
        String value = string(params.get(key));
        if (StringUtils.isBlank(value)) {
            throw workflowParameterInvalid(params, key, null);
        }
        return value;
    }

    private long requiredWorkflowLong(Map<String, String> params, String key) {
        String value = requiredWorkflow(params, key);
        try {
            long parsed = Long.parseLong(value);
            if (parsed <= 0) {
                throw workflowParameterInvalid(params, key, null);
            }
            return parsed;
        } catch (NumberFormatException exception) {
            throw workflowParameterInvalid(params, key, exception);
        }
    }

    private int workflowListLimit(Map<String, String> params) {
        String value = string(params.get(PARAM_LIMIT));
        if (StringUtils.isBlank(value)) {
            return DEFAULT_WORKFLOW_LIST_LIMIT;
        }
        try {
            return Integer.parseInt(value);
        } catch (NumberFormatException exception) {
            throw workflowParameterInvalid(params, PARAM_LIMIT, exception);
        }
    }

    private void rejectWorkflowOffset(Map<String, String> params) {
        if (params.containsKey(PARAM_OFFSET)) {
            throw workflowParameterInvalid(params, PARAM_OFFSET, null);
        }
    }

    private WorkflowControlPlaneException workflowParameterInvalid(
            Map<String, String> params, String fieldPath, Throwable cause) {
        String workflowCode = string(params.get(PARAM_WORKFLOW_CODE));
        if (cause == null) {
            return new WorkflowControlPlaneException(
                    ERROR_CODE_WORKFLOW_PARAMETER_INVALID,
                    ERROR_WORKFLOW_PARAMETER_INVALID, workflowCode, fieldPath);
        }
        return new WorkflowControlPlaneException(
                ERROR_CODE_WORKFLOW_PARAMETER_INVALID,
                ERROR_WORKFLOW_PARAMETER_INVALID, workflowCode, fieldPath, cause);
    }

    private String string(Object value) {
        return value == null ? EMPTY : String.valueOf(value);
    }

}
