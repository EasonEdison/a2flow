package dev.a2flow.management.aicoding.dependency;

import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.stream.Collectors;

import jakarta.annotation.Resource;

import org.apache.commons.collections4.MapUtils;
import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Component;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.agentcore.runtime.tool.CapabilityCatalogQueryService;
import dev.a2flow.management.lifecycle.RegistryComponentReleaseIdentityResolver;
import dev.a2flow.management.lifecycle.SkillFactoryRenderComponentBindingResolver;
import dev.a2flow.management.lifecycle.domain.ComponentAsset;
import dev.a2flow.management.lifecycle.domain.SkillDraft;
import dev.a2flow.management.model.SkillFactoryComponentAsset;
import dev.a2flow.management.model.SkillFactoryEntityRelationConstants;
import dev.a2flow.management.release.ReleaseEnvironment;
import dev.a2flow.management.release.dependency.AssetDependencyModels.AssetDependencyReference;
import dev.a2flow.management.release.dependency.AssetDependencyModels.ResolvedReleasedAsset;
import dev.a2flow.management.release.dependency.AssetDependencyType;
import dev.a2flow.management.release.dependency.EnvironmentAwareAssetResolver;
import dev.a2flow.management.storage.db.entity.EntityRelationDO;
import dev.a2flow.management.storage.db.repository.EntityRelationRepository;
import dev.a2flow.management.storage.db.repository.SkillFactoryComponentAssetRepository;
import dev.a2flow.management.storage.db.repository.SkillFactoryWorkspaceRepository;

import lombok.Data;
import lombok.experimental.Accessors;
import lombok.extern.slf4j.Slf4j;

/**
 * Skill 创建期依赖上下文服务。
 *
 * <p>该服务从 SkillFactory workspace 草稿读取已经由工作台保存的能力、组件稳定引用，把它们归一化为
 * 模型可见的精简上下文，并为专用 Tool 和工作台“填充到对话中”接口提供可信能力详情与托管依赖清单。
 * 上游是 {@code AiCodingReActEngine}、依赖查询 Tool 和统一方法分发器，下游访问 workspace、实体关系
 * Repository 及作者态 PRT 发布解析器；它不创建绑定、不执行能力、不签发调试权限，也不替代线上
 * 发布准出校验。
 */
@Slf4j
@Component
public class SkillAuthoringDependencyService {

    public static final String TOOL_GET_AUTHORING_CONTEXT = "get_skill_authoring_context";
    public static final String TOOL_QUERY_CAPABILITY_DETAIL = "query_capability_version_detail";
    public static final String TOOL_QUERY_COMPONENT_DETAIL = "query_component_asset_detail";
    public static final String TOOL_SYNC_DEPENDENCY_MANIFEST = "sync_skill_dependency_manifest";

    private static final String FIELD_WORKSPACE_ID = "workspaceId";
    private static final String FIELD_SKILL_CODE = "skillCode";
    private static final String FIELD_SKILL_NAME_CN = "skillNameCn";
    private static final String FIELD_SKILL_NAME_EN = "skillNameEn";
    private static final String FIELD_SKILL_DESCRIPTION = "skillDescription";
    private static final String FIELD_SKILL_VERSION = "skillVersion";
    private static final String FIELD_CAPABILITY_REFERENCES = "capabilityReferences";
    private static final String FIELD_COMPONENT_REFERENCES = "componentReferences";
    private static final String FIELD_CAPABILITY_BINDINGS = "capabilityBindings";
    private static final String FIELD_COMPONENT_BINDINGS = "componentBindings";
    private static final String FIELD_MIGRATION_ISSUES = "migrationIssues";
    private static final String FIELD_DEPENDENCY_IDENTITY_READY = "dependencyIdentityReady";
    private static final String FIELD_ACTION_CODE = "actionCode";
    private static final String FIELD_CAPABILITY_CODE = "capabilityCode";
    private static final String FIELD_COMPONENT_CODE = "componentCode";
    private static final String FIELD_CODE = "code";
    private static final String FIELD_VERSION = "version";
    private static final String FIELD_COMPONENT_VERSION = "componentVersion";
    private static final String FIELD_MODE = "mode";
    private static final String FIELD_BIND_MODE = "bindMode";
    private static final String FIELD_INTENDED_BIND_MODE = "intendedBindMode";
    private static final String FIELD_USAGE = "usage";
    private static final String FIELD_PURPOSE = "purpose";
    private static final String FIELD_REFERENCE = "reference";
    private static final String FIELD_DETAIL = "detail";
    private static final String FIELD_DRAFT_ID = "draftId";
    private static final String FIELD_CAPABILITY_DRAFT_ID = "capabilityDraftId";
    private static final String FIELD_REVISION = "revision";
    private static final String FIELD_SCHEMA_VERSION = "schemaVersion";
    private static final String FIELD_CAPABILITIES = "capabilities";
    private static final String FIELD_BINDING_IDENTITY = "bindingIdentity";
    private static final String FIELD_NAME_CN = "nameCn";
    private static final String FIELD_BUSINESS_DOMAIN = "businessDomain";
    private static final String FIELD_DESCRIPTION = "description";
    private static final String FIELD_SUPPORTED_CLIENTS = "supportedClients";
    private static final String FIELD_CLIENT_VARIANTS = "clientVariants";
    private static final String FIELD_MODEL_CONTRACT = "modelContract";
    private static final String FIELD_INPUT_FIELDS = "inputFields";
    private static final String FIELD_INPUT_EXAMPLE_JSON = "inputExampleJson";
    private static final String FIELD_INPUT_EXAMPLE = "inputExample";
    private static final String FIELD_RESULT_CONTRACT = "resultContract";
    private static final String FIELD_KEY_OUTPUT_FIELDS = "keyOutputFields";
    private static final String FIELD_RESPONSE_DEMO_JSON = "responseDemoJson";
    private static final String FIELD_RESPONSE_EXAMPLE = "responseExample";
    private static final String FIELD_GOVERNANCE = "governance";
    private static final String FIELD_SIDE_EFFECT_LEVEL = "sideEffectLevel";
    private static final String FIELD_APPROVAL_POLICY = "approvalPolicy";
    private static final String FIELD_MODEL_DESCRIPTION = "modelDescription";
    private static final String FIELD_STATUS = "status";
    private static final String FIELD_PRESENTATION = "presentation";
    private static final String FIELD_ENABLED = "enabled";
    private static final String FIELD_RUNTIME_MANAGED = "runtimeManaged";
    private static final String FIELD_INSTRUCTION = "instruction";
    private static final String FIELD_TOOL_FIELD = "toolField";
    private static final String FIELD_TYPE = "type";
    private static final String FIELD_BUSINESS_MEANING = "businessMeaning";
    private static final String FIELD_UNIT = "unit";
    private static final String FIELD_SOURCE = "source";
    private static final String FIELD_REQUIRED = "required";
    private static final String FIELD_EXAMPLES = "examples";
    private static final String FIELD_ALLOWED_VALUES = "allowedValues";
    private static final String FIELD_ITEMS = "items";
    private static final String FIELD_PATH = "path";
    private static final String FIELD_OBSERVED_TYPE = "observedType";
    private static final String DEFAULT_CAPABILITY_MODE = "EXECUTION_ONLY";
    private static final String DEFAULT_COMPONENT_USAGE = "DIRECT_RENDER";
    private static final String AUTHORING_CONTEXT_SCHEMA_VERSION = "skillCapabilityAuthoringContext.v1";
    private static final String DSL_TYPE_CARD_CONTAINER = "CARD_CONTAINER";
    private static final String TOOL_QUERY_DEPENDENCIES = "query_skill_dependencies";
    private static final String TOOL_EXECUTE_BUSINESS_CAPABILITY = "execute_business_capability";
    private static final String COMPONENT_GUIDANCE_MANAGED_NOTICE =
            "> 本区块由 SkillFactory 根据当前 Skill 绑定自动维护，请勿手工修改。";
    private static final String COMPONENT_GUIDANCE_QUERY_NOTICE =
            "> 渲染前先汇总本轮需要的 componentName，一次调用 "
                    + TOOL_QUERY_DEPENDENCIES + "(componentNameList) "
                    + "获取当前环境最新 paramsSchemaJson 和参数示例，再逐个调用 render_component；"
                    + "不得凭历史 Schema 猜测参数。";
    private static final String A2UI_APPLICATION_GUIDANCE_MANAGED_NOTICE =
            "> 本区块由 SkillFactory 根据当前 Skill 绑定自动维护，请勿手工修改。";
    private static final String A2UI_APPLICATION_GUIDANCE_QUERY_NOTICE =
            "> A2UI 渲染前先汇总本轮需要的 appCode，一次调用 "
                    + TOOL_QUERY_DEPENDENCIES + "(a2uiApplicationCodeList) "
                    + "获取当前环境 paramsSchema，再逐个调用 "
                    + "render_a2ui_application({appCode, params})；不得放入 componentNameList，"
                    + "也不得调用 render_component。";
    private static final String CAPABILITY_GUIDANCE_MANAGED_NOTICE =
            "> 本区块由 SkillFactory 根据当前 Skill 绑定自动维护，请勿手工修改。";
    private static final String CAPABILITY_GUIDANCE_QUERY_NOTICE =
            "> 执行前先汇总本轮需要的 actionCode，一次调用 "
                    + TOOL_QUERY_DEPENDENCIES + "(actionCodeList) 获取当前环境完整参数契约；"
                    + "不得从本文档猜测参数，再调用 " + TOOL_EXECUTE_BUSINESS_CAPABILITY + "。";
    private static final String STATUS_AVAILABLE = "AVAILABLE";
    private static final String SIDE_EFFECT_READ = "READ";
    private static final String SIDE_EFFECT_WRITE = "WRITE";
    private static final String SIDE_EFFECT_DESTRUCTIVE = "DESTRUCTIVE";
    private static final String APPROVAL_AUTO_EXECUTE = "AUTO_EXECUTE";
    private static final String APPROVAL_REQUEST_APPROVAL = "REQUEST_APPROVAL";
    private static final String LABEL_SIDE_EFFECT_READ = "只读";
    private static final String LABEL_SIDE_EFFECT_WRITE = "读写";
    private static final String LABEL_SIDE_EFFECT_DESTRUCTIVE = "破坏性操作";
    private static final String LABEL_APPROVAL_AUTO_EXECUTE = "无需审批";
    private static final String LABEL_APPROVAL_REQUEST_APPROVAL = "需要审批";
    private static final String BIND_MODE_EXECUTION_AND_RENDER = "EXECUTION_AND_RENDER";
    private static final String FIELD_SOURCE_MODEL_INPUT = "MODEL_INPUT";
    private static final String PRESENTATION_RENDER_INSTRUCTION =
            "能力执行结果的组件渲染由运行时负责，Skill 只描述何时展示，不得直接拼装组件协议。";
    private static final String PRESENTATION_EXECUTION_ONLY_INSTRUCTION =
            "当前绑定仅用于执行和分析，不生成能力组件展示。";
    private static final Set<String> MODEL_CONTEXT_HIDDEN_FIELD_NAMES = Set.of(
            "sellerid", "userid", "ownerid", "cookie", "authorization", "token", "accesstoken",
            "refreshtoken", "apikey", "password", "secret", "credentialvalue", "accessproxysession",
            "kssecurityencrypt");
    private static final String ERROR_WORKSPACE_REQUIRED = "trusted workspaceId is required";
    private static final String ERROR_WORKSPACE_NOT_FOUND = "Skill workspace is not registered";
    private static final String ERROR_SKILL_DRAFT_ID_REQUIRED = "Skill draft id is required";
    private static final String ERROR_SKILL_VERSION_INVALID = "Skill version is invalid";
    private static final String ERROR_RELATION_SNAPSHOT_INVALID = "entity relation snapshot is invalid";
    private static final String ERROR_FORMAL_CAPABILITY_REQUIRED =
            "capability reference must use published actionCode + version";
    private static final String ERROR_FORMAL_COMPONENT_REQUIRED =
            "component reference must use published componentCode + version";
    private static final String ERROR_CAPABILITY_IDENTITY_REQUIRED =
            "capability reference must use stable actionCode";
    private static final String ERROR_COMPONENT_IDENTITY_REQUIRED =
            "component reference must use stable componentCode";
    private static final String ERROR_DEPENDENCY_IDENTITY_INCOMPLETE =
            "dependency stable identity is incomplete";
    private static final String ERROR_CAPABILITY_BINDING_REQUIRED = "capability binding identity is required";
    private static final String ERROR_CAPABILITY_BINDING_NOT_FOUND =
            "capability revision is not referenced by current Skill";
    private static final String ERROR_CAPABILITY_EXAMPLE_INVALID = "capability example JSON is invalid";
    private static final String ERROR_COMPONENT_RELEASE_PAYLOAD_INVALID =
            "released component payload is invalid";
    private static final String ERROR_COMPONENT_DSL_UNSUPPORTED =
            "only CARD_CONTAINER component can be compiled into current Skill";
    private static final String ERROR_COMPONENT_NAME_REQUIRED =
            "released componentName is required";
    private static final String ERROR_COMPONENT_REGISTRY_ASSET_NOT_FOUND =
            "bound component Registry asset does not exist";
    private static final String ERROR_COMPONENT_GUIDANCE_MARKER_FORBIDDEN =
            "component guidance field contains reserved managed marker";
    private static final String ERROR_A2UI_APPLICATION_GUIDANCE_MARKER_FORBIDDEN =
            "A2UI Application guidance field contains reserved managed marker";
    private static final String ERROR_CAPABILITY_GUIDANCE_MARKER_FORBIDDEN =
            "capability guidance field contains reserved managed marker";
    private static final String ERROR_CAPABILITY_BINDING_ACTION_CODE_REQUIRED =
            "capability binding actionCode is required";
    private static final String ERROR_CAPABILITY_BINDING_DUPLICATED =
            "capability binding actionCode is duplicated";
    private static final String ERROR_CAPABILITY_GUIDANCE_UNAVAILABLE =
            "business capability guidance is unavailable in PRT";
    private static final String ERROR_CAPABILITY_GOVERNANCE_INVALID =
            "business capability governance is invalid";
    private static final String COMPONENT_GUIDANCE_START =
            "<!-- skillfactory-component-guidance:start -->";
    private static final String COMPONENT_GUIDANCE_END =
            "<!-- skillfactory-component-guidance:end -->";
    private static final String A2UI_APPLICATION_GUIDANCE_START =
            "<!-- skillfactory-a2ui-application-guidance:start -->";
    private static final String A2UI_APPLICATION_GUIDANCE_END =
            "<!-- skillfactory-a2ui-application-guidance:end -->";
    private static final String CAPABILITY_GUIDANCE_START =
            "<!-- skillfactory-capability-guidance:start -->";
    private static final String CAPABILITY_GUIDANCE_END =
            "<!-- skillfactory-capability-guidance:end -->";

    @Resource
    private SkillFactoryWorkspaceRepository workspaceRepository;

    @Resource
    private EntityRelationRepository entityRelationRepository;

    @Resource
    private SkillFactoryRenderComponentBindingResolver renderComponentBindingResolver;

    @Resource
    private EnvironmentAwareAssetResolver environmentAwareAssetResolver;

    @Resource
    private SkillFactoryComponentAssetRepository componentAssetRepository;

    @Resource
    private RegistryComponentReleaseIdentityResolver componentReleaseIdentityResolver;

    @Resource
    private CapabilityCatalogQueryService capabilityCatalogQueryService;

    /**
     * 读取当前 workspace 的权威作者上下文。
     *
     * <p>返回值包含注册 Skill 的身份信息、稳定依赖引用和迁移缺口，不把前端 requestBody 中的详情当成
     * 事实源。关系快照中的历史正式版本仅作为可选信息返回，不是作者态编译门禁；当前可用发布源由
     * PRT 环境解析器在实际查询或编译时确定。
     */
    public Map<String, Object> getAuthoringContext(String workspaceId) {
        String trustedWorkspaceId = requireWorkspaceId(workspaceId);
        SkillDraft draft = workspaceRepository.findDraftByWorkspaceId(trustedWorkspaceId);
        if (draft == null) {
            log.warn("Skill创建期依赖上下文读取失败, workspaceId={}, reason=workspace未注册", trustedWorkspaceId);
            throw new IllegalArgumentException(ERROR_WORKSPACE_NOT_FOUND);
        }
        List<String> migrationIssues = new ArrayList<>();
        List<Map<String, Object>> capabilityReferences = normalizeCapabilityReferences(
                currentBindings(draft,
                        SkillFactoryEntityRelationConstants.RELATION_TYPE_SKILL_USES_CAPABILITY),
                migrationIssues);
        List<Map<String, Object>> componentReferences = normalizeComponentReferences(
                currentBindings(draft,
                        SkillFactoryEntityRelationConstants.RELATION_TYPE_SKILL_USES_COMPONENT),
                migrationIssues);
        Map<String, Object> context = new LinkedHashMap<>();
        context.put(FIELD_WORKSPACE_ID, trustedWorkspaceId);
        context.put(FIELD_SKILL_CODE, StringUtils.defaultIfBlank(draft.getSkillCode(), trustedWorkspaceId));
        context.put(FIELD_SKILL_NAME_CN, StringUtils.defaultString(draft.getSkillNameCn()));
        context.put(FIELD_SKILL_NAME_EN, StringUtils.defaultString(draft.getSkillNameEn()));
        context.put(FIELD_SKILL_DESCRIPTION, StringUtils.defaultString(draft.getSkillDescription()));
        context.put(FIELD_SKILL_VERSION, currentSkillVersion(draft));
        context.put(FIELD_CAPABILITY_REFERENCES, capabilityReferences);
        context.put(FIELD_COMPONENT_REFERENCES, componentReferences);
        context.put(FIELD_DEPENDENCY_IDENTITY_READY, migrationIssues.isEmpty());
        context.put(FIELD_MIGRATION_ISSUES, migrationIssues);
        log.info("Skill创建期依赖上下文读取完成, workspaceId={}, skillNameCnPresent={}, "
                        + "skillDescriptionPresent={}, capabilityCount={}, componentCount={}, "
                        + "dependencyIdentityReady={}, skillVersion={}",
                trustedWorkspaceId, StringUtils.isNotBlank(draft.getSkillNameCn()),
                StringUtils.isNotBlank(draft.getSkillDescription()),
                capabilityReferences.size(), componentReferences.size(),
                migrationIssues.isEmpty(), context.get(FIELD_SKILL_VERSION));
        return context;
    }

    /**
     * 读取当前 workspace 已选择的某个正式业务能力版本详情。
     */
    public Map<String, Object> queryCapabilityDetail(String workspaceId, String actionCode, int version) {
        if (StringUtils.isBlank(actionCode) || version <= 0) {
            throw new IllegalArgumentException(ERROR_FORMAL_CAPABILITY_REQUIRED);
        }
        SkillDraft draft = requireDraft(workspaceId);
        for (Map<String, Object> binding : currentBindings(draft,
                SkillFactoryEntityRelationConstants.RELATION_TYPE_SKILL_USES_CAPABILITY)) {
            String currentActionCode = firstNotBlank(MapUtils.getString(binding, FIELD_ACTION_CODE),
                    MapUtils.getString(binding, FIELD_CAPABILITY_CODE));
            int currentVersion = positiveInt(binding.get(FIELD_VERSION));
            if (StringUtils.equals(actionCode, currentActionCode) && version == currentVersion) {
                return detailResult(normalizeCapabilityReference(binding), sanitizedDetail(binding));
            }
        }
        log.warn("Skill创建期能力详情查询被拒绝, workspaceId={}, actionCode={}, version={}, reason=未选择该正式版本",
                workspaceId, actionCode, version);
        throw new IllegalArgumentException("capability version is not referenced by current Skill");
    }

    /**
     * 生成“填充到对话中”使用的单个业务能力可信上下文。
     *
     * <p>入口只接收绑定身份，能力详情必须来自当前 Skill 当前版本保存的关系快照。输出仅保留模型完成
     * SKILL.md 编排所需的业务语义、模型可见参数、关键结果和治理信息，不暴露执行地址、身份注入、
     * 请求映射、Cookie 或组件实现细节。
     */
    public Map<String, Object> getCapabilityAuthoringContext(String workspaceId, String draftId, int revision) {
        if (StringUtils.isBlank(draftId) || revision <= 0) {
            throw new IllegalArgumentException(ERROR_CAPABILITY_BINDING_REQUIRED);
        }
        SkillDraft draft = requireDraft(workspaceId);
        for (Map<String, Object> binding : currentBindings(draft,
                SkillFactoryEntityRelationConstants.RELATION_TYPE_SKILL_USES_CAPABILITY)) {
            if (!StringUtils.equals(draftId, MapUtils.getString(binding, FIELD_DRAFT_ID))
                    || revision != positiveInt(binding.get(FIELD_REVISION))) {
                continue;
            }
            Map<String, Object> result = new LinkedHashMap<>();
            result.put(FIELD_SCHEMA_VERSION, AUTHORING_CONTEXT_SCHEMA_VERSION);
            result.put(FIELD_CAPABILITIES, List.of(buildCapabilityAuthoringItem(binding)));
            log.info("Skill创建期能力对话上下文生成完成, workspaceId:{}, skillCode:{}, draftId:{}, "
                            + "revision:{}, actionCode:{}",
                    workspaceId, draft.getSkillCode(), draftId, revision,
                    firstNotBlank(MapUtils.getString(binding, FIELD_ACTION_CODE),
                            MapUtils.getString(binding, FIELD_CAPABILITY_CODE)));
            return result;
        }
        log.warn("Skill创建期能力对话上下文生成被拒绝, workspaceId:{}, skillCode:{}, draftId:{}, "
                        + "revision:{}, reason:当前Skill版本未绑定该能力",
                workspaceId, draft.getSkillCode(), draftId, revision);
        throw new IllegalArgumentException(ERROR_CAPABILITY_BINDING_NOT_FOUND);
    }

    /**
     * 读取当前 workspace 已选择的某个正式组件版本详情。
     */
    public Map<String, Object> queryComponentDetail(String workspaceId, String componentCode, int version) {
        if (StringUtils.isBlank(componentCode) || version <= 0) {
            throw new IllegalArgumentException(ERROR_FORMAL_COMPONENT_REQUIRED);
        }
        SkillDraft draft = requireDraft(workspaceId);
        for (Map<String, Object> binding : currentBindings(draft,
                SkillFactoryEntityRelationConstants.RELATION_TYPE_SKILL_USES_COMPONENT)) {
            String currentComponentCode = firstNotBlank(MapUtils.getString(binding, FIELD_COMPONENT_CODE),
                    MapUtils.getString(binding, FIELD_CODE));
            int currentVersion = firstPositiveInt(binding.get(FIELD_VERSION), binding.get(FIELD_COMPONENT_VERSION));
            if (StringUtils.equals(componentCode, currentComponentCode) && version == currentVersion) {
                return detailResult(normalizeComponentReference(binding), sanitizedDetail(binding));
            }
        }
        log.warn("Skill创建期组件详情查询被拒绝, workspaceId={}, componentCode={}, version={}, "
                        + "reason=未选择该正式版本",
                workspaceId, componentCode, version);
        throw new IllegalArgumentException("component version is not referenced by current Skill");
    }

    /**
     * 一次性编译 SKILL.md 的组件说明和业务能力说明。
     *
     * <p>组件说明从公共 PRT 环境解析器读取不可变组件快照，同时覆盖直接组件和能力间接展示组件。
     * 输出只包含稳定组件身份和场景语义，并要求模型在实际渲染前通过
     * {@code query_skill_dependencies} 批量获取当前环境的最新 Schema。能力说明只编译稳定业务语义和
     * 治理约束，同样要求执行前刷新完整契约；两类说明都不把易变化的 Schema、示例、bundle、模板、
     * 隐藏接入提示词、身份、凭据、发布指针或运行时配置固化进 Skill 文件。
     */
    public ManagedDependencyCompilation buildManagedDependencyCompilation(String workspaceId) {
        Map<String, Object> context = requireCompleteDependencyIdentityContext(workspaceId);
        List<Map<String, Object>> capabilityReferences = mapList(context.get(FIELD_CAPABILITY_REFERENCES));
        List<ResolvedBoundAsset> boundAssets = resolveBoundAssets(workspaceId);
        ManagedComponentGuidanceCompilation componentCompilation =
                buildManagedComponentGuidanceCompilation(workspaceId, boundAssets);
        A2uiApplicationGuidanceCompilation a2uiApplicationCompilation =
                buildA2uiApplicationGuidanceCompilation(boundAssets);
        CapabilityGuidanceCompilation capabilityCompilation =
                buildManagedCapabilityGuidanceBlock(capabilityReferences);
        log.info("Skill创建期依赖编译完成, workspaceId:{}, componentCount:{}, "
                        + "a2uiApplicationCount:{}, capabilityCount:{}, componentGuidanceLength:{}, "
                        + "a2uiApplicationGuidanceLength:{}, capabilityGuidanceLength:{}",
                workspaceId, componentCompilation.componentCodes.size(),
                a2uiApplicationCompilation.appCodes.size(), capabilityCompilation.actionCodes.size(),
                componentCompilation.guidance.length(), a2uiApplicationCompilation.guidance.length(),
                capabilityCompilation.guidance.length());
        return new ManagedDependencyCompilation()
                .setComponentGuidance(componentCompilation.guidance)
                .setComponentCodes(componentCompilation.componentCodes)
                .setA2uiApplicationGuidance(a2uiApplicationCompilation.guidance)
                .setA2uiApplicationCodes(a2uiApplicationCompilation.appCodes)
                .setCapabilityGuidance(capabilityCompilation.guidance)
                .setActionCodes(capabilityCompilation.actionCodes);
    }

    /**
     * 只编译当前 Skill 绑定组件的稳定使用说明，供只读 Tool 返回给模型。
     *
     * <p>该入口不读取或编译业务能力说明和依赖清单，也不生成 Patch。直接组件和能力间接组件仍通过
     * 同一个可信绑定解析器选择 PRT 发布快照，模型只能得到稳定调用语义。
     */
    public ManagedComponentGuidanceCompilation buildManagedComponentGuidanceCompilation(String workspaceId) {
        return buildManagedComponentGuidanceCompilation(workspaceId, resolveBoundAssets(workspaceId));
    }

    private ManagedComponentGuidanceCompilation buildManagedComponentGuidanceCompilation(
            String workspaceId, List<ResolvedBoundAsset> boundAssets) {
        List<SkillFactoryComponentAsset> assets = projectCardComponents(boundAssets);
        List<String> componentCodes = assets.stream()
                .map(SkillFactoryComponentAsset::getComponentName)
                .collect(Collectors.toList());
        String guidance = buildManagedComponentGuidanceBlock(assets);
        log.info("Skill创建期组件说明编译完成, workspaceId:{}, componentCount:{}, guidanceLength:{}",
                workspaceId, componentCodes.size(), guidance.length());
        return new ManagedComponentGuidanceCompilation()
                .setGuidance(guidance)
                .setComponentCodes(componentCodes);
    }

    /** 校验托管依赖区块需要的稳定身份；发布源可用性由后续 PRT 解析分别校验。 */
    private Map<String, Object> requireCompleteDependencyIdentityContext(String workspaceId) {
        Map<String, Object> context = getAuthoringContext(workspaceId);
        List<String> migrationIssues = stringList(context.get(FIELD_MIGRATION_ISSUES));
        if (!migrationIssues.isEmpty()) {
            throw new IllegalStateException(ERROR_DEPENDENCY_IDENTITY_INCOMPLETE + ": "
                    + StringUtils.join(migrationIssues, "; "));
        }
        return context;
    }

    /** 按当前 Skill 关系快照解析全部直接及能力间接资产，并固定使用作者态 PRT 选择矩阵。 */
    private List<ResolvedBoundAsset> resolveBoundAssets(String workspaceId) {
        SkillDraft draft = requireDraft(workspaceId);
        Map<String, Object> bindingSnapshot = new LinkedHashMap<>();
        bindingSnapshot.put(FIELD_COMPONENT_BINDINGS, currentBindings(draft,
                SkillFactoryEntityRelationConstants.RELATION_TYPE_SKILL_USES_COMPONENT));
        bindingSnapshot.put(FIELD_CAPABILITY_BINDINGS, currentBindings(draft,
                SkillFactoryEntityRelationConstants.RELATION_TYPE_SKILL_USES_CAPABILITY));
        List<ResolvedBoundAsset> assets = new ArrayList<>();
        for (Long assetId : renderComponentBindingResolver.resolveAssetIds(bindingSnapshot)) {
            ComponentAsset registryAsset = componentAssetRepository.get(assetId);
            if (registryAsset == null) {
                log.warn("Skill创建期组件说明解析失败, workspaceId:{}, assetId:{}, reason=Registry资产不存在",
                        workspaceId, assetId);
                throw new IllegalStateException(ERROR_COMPONENT_REGISTRY_ASSET_NOT_FOUND + ": " + assetId);
            }
            RegistryComponentReleaseIdentityResolver.ComponentReleaseIdentity identity =
                    componentReleaseIdentityResolver.resolve(
                            String.valueOf(assetId), registryAsset.getAssetType(),
                            registryAsset.getComponentName());
            ResolvedReleasedAsset resolved = environmentAwareAssetResolver.resolve(
                    new AssetDependencyReference()
                            .setAssetType(identity.getDependencyType())
                            .setAssetKey(identity.getAssetKey()),
                    ReleaseEnvironment.PRT);
            assets.add(new ResolvedBoundAsset(registryAsset, identity.getDependencyType(), resolved));
            log.info("Skill创建期绑定资产解析完成, workspaceId:{}, assetId:{}, assetType:{}, assetKey:{}, "
                            + "resolvedEnvironment:{}, sourceType:{}, sourceId:{}",
                    workspaceId, assetId, identity.getDependencyType(), identity.getAssetKey(),
                    resolved.getResolvedEnvironment(),
                    resolved.getSourceType(), resolved.getSourceId());
        }
        assets.sort(Comparator.comparing(asset ->
                StringUtils.trimToEmpty(asset.registryAsset.getComponentName())));
        return assets;
    }

    /** 只把 COMPONENT_ASSET 发布快照投影为 legacy CARD 调用说明。 */
    private List<SkillFactoryComponentAsset> projectCardComponents(List<ResolvedBoundAsset> boundAssets) {
        List<SkillFactoryComponentAsset> assets = new ArrayList<>();
        for (ResolvedBoundAsset boundAsset : boundAssets) {
            if (boundAsset.dependencyType != AssetDependencyType.COMPONENT_ASSET) {
                continue;
            }
            SkillFactoryComponentAsset asset = resolveReleasedContract(boundAsset);
            validateCompiledComponent(asset);
            assets.add(asset);
        }
        return assets;
    }

    /** 只把 A2UI_APPLICATION 不可变 Build 投影为专用 Tool 的稳定 appCode 说明。 */
    private A2uiApplicationGuidanceCompilation buildA2uiApplicationGuidanceCompilation(
            List<ResolvedBoundAsset> boundAssets) {
        List<SkillFactoryComponentAsset> applications = new ArrayList<>();
        for (ResolvedBoundAsset boundAsset : boundAssets) {
            if (boundAsset.dependencyType != AssetDependencyType.A2UI_APPLICATION) {
                continue;
            }
            SkillFactoryComponentAsset application = resolveReleasedContract(boundAsset);
            if (StringUtils.isBlank(application.getComponentName())) {
                throw new IllegalStateException(ERROR_COMPONENT_NAME_REQUIRED);
            }
            rejectA2uiApplicationManagedMarker(application.getComponentNameCn());
            rejectA2uiApplicationManagedMarker(application.getScene());
            applications.add(application);
        }
        List<String> appCodes = applications.stream()
                .map(SkillFactoryComponentAsset::getComponentName)
                .toList();
        if (applications.isEmpty()) {
            return new A2uiApplicationGuidanceCompilation(StringUtils.EMPTY, List.of());
        }
        StringBuilder guidance = new StringBuilder(A2UI_APPLICATION_GUIDANCE_MANAGED_NOTICE)
                .append('\n')
                .append(A2UI_APPLICATION_GUIDANCE_QUERY_NOTICE)
                .append('\n');
        for (SkillFactoryComponentAsset application : applications) {
            guidance.append("\n### `").append(application.getComponentName()).append('`');
            if (StringUtils.isNotBlank(application.getComponentNameCn())) {
                guidance.append("（").append(markdownText(application.getComponentNameCn())).append("）");
            }
            guidance.append('\n');
            guidance.append("- `appCode`：`").append(application.getComponentName()).append("`\n");
            if (StringUtils.isNotBlank(application.getScene())) {
                guidance.append("- 适用场景：").append(markdownText(application.getScene())).append('\n');
            }
        }
        return new A2uiApplicationGuidanceCompilation(
                guidance.toString().stripTrailing(), appCodes);
    }

    private SkillFactoryComponentAsset resolveReleasedContract(ResolvedBoundAsset boundAsset) {
        try {
            return componentReleaseIdentityResolver.resolveReleasedContract(
                    boundAsset.registryAsset,
                    componentReleaseIdentityResolver.resolve(
                            String.valueOf(boundAsset.registryAsset.getId()),
                            boundAsset.registryAsset.getAssetType(),
                            boundAsset.registryAsset.getComponentName()),
                    boundAsset.resolvedAsset);
        } catch (IllegalArgumentException exception) {
            log.warn("Skill创建期发布契约解析失败, assetId:{}, assetType:{}, reason:{}",
                    boundAsset.registryAsset.getId(), boundAsset.registryAsset.getAssetType(),
                    exception.getMessage());
            throw new IllegalStateException(ERROR_COMPONENT_RELEASE_PAYLOAD_INVALID, exception);
        }
    }

    /** 生成不含版本指针和运行配置的模型可读组件调用说明。 */
    private String buildManagedComponentGuidanceBlock(List<SkillFactoryComponentAsset> assets) {
        if (assets.isEmpty()) {
            return StringUtils.EMPTY;
        }
        StringBuilder guidance = new StringBuilder(COMPONENT_GUIDANCE_MANAGED_NOTICE)
                .append('\n')
                .append(COMPONENT_GUIDANCE_QUERY_NOTICE)
                .append('\n');
        for (SkillFactoryComponentAsset asset : assets) {
            guidance.append("\n### `").append(asset.getComponentName()).append('`');
            if (StringUtils.isNotBlank(asset.getComponentNameCn())) {
                guidance.append("（").append(markdownText(asset.getComponentNameCn())).append("）");
            }
            guidance.append('\n');
            guidance.append("- `componentName`：`").append(asset.getComponentName()).append("`\n");
            if (StringUtils.isNotBlank(asset.getInteractionMode())) {
                guidance.append("- 交互类型：`").append(asset.getInteractionMode()).append("`\n");
            }
            if (StringUtils.isNotBlank(asset.getScene())) {
                guidance.append("- 适用场景：").append(markdownText(asset.getScene())).append('\n');
            }
        }
        return guidance.toString().stripTrailing();
    }

    /**
     * 生成不含参数 Schema、版本和运行时事实的业务能力说明；任一绑定不可用时关闭整次编译。
     */
    private CapabilityGuidanceCompilation buildManagedCapabilityGuidanceBlock(
            List<Map<String, Object>> capabilityReferences) {
        List<Map<String, Object>> sortedReferences = new ArrayList<>(capabilityReferences);
        sortedReferences.sort(Comparator.comparing(reference ->
                StringUtils.trimToEmpty(MapUtils.getString(reference, FIELD_ACTION_CODE))));
        Set<String> seenActionCodes = new LinkedHashSet<>();
        Map<String, String> purposeByActionCode = new LinkedHashMap<>();
        for (Map<String, Object> reference : sortedReferences) {
            String actionCode = StringUtils.trimToEmpty(MapUtils.getString(reference, FIELD_ACTION_CODE));
            if (StringUtils.isBlank(actionCode)) {
                throw new IllegalStateException(ERROR_CAPABILITY_BINDING_ACTION_CODE_REQUIRED);
            }
            if (!seenActionCodes.add(actionCode)) {
                throw new IllegalStateException(ERROR_CAPABILITY_BINDING_DUPLICATED + ": " + actionCode);
            }
            String purpose = markdownText(MapUtils.getString(reference, FIELD_PURPOSE));
            rejectCapabilityManagedMarker(purpose);
            purposeByActionCode.put(actionCode, purpose);
        }
        if (seenActionCodes.isEmpty()) {
            return new CapabilityGuidanceCompilation(StringUtils.EMPTY, List.of());
        }
        StringBuilder guidance = new StringBuilder(CAPABILITY_GUIDANCE_MANAGED_NOTICE)
                .append('\n')
                .append(CAPABILITY_GUIDANCE_QUERY_NOTICE)
                .append('\n');
        List<Map<String, Object>> capabilities = capabilityCatalogQueryService.queryGuidanceByActionCodes(
                new ArrayList<>(seenActionCodes), ReleaseEnvironment.PRT, null);
        for (Map<String, Object> capability : capabilities) {
            String actionCode = MapUtils.getString(capability, FIELD_ACTION_CODE);
            if (!StringUtils.equals(STATUS_AVAILABLE, MapUtils.getString(capability, FIELD_STATUS))) {
                log.warn("Skill创建期能力说明编译失败, actionCode:{}, reason=PRT发布源不可用", actionCode);
                throw new IllegalStateException(ERROR_CAPABILITY_GUIDANCE_UNAVAILABLE + ": " + actionCode);
            }
            appendCapabilityGuidance(guidance, capability, purposeByActionCode.get(actionCode));
        }
        return new CapabilityGuidanceCompilation(guidance.toString().stripTrailing(),
                List.copyOf(seenActionCodes));
    }

    private void appendCapabilityGuidance(StringBuilder guidance, Map<String, Object> capability,
            String purpose) {
        String actionCode = MapUtils.getString(capability, FIELD_ACTION_CODE);
        String nameCn = markdownText(MapUtils.getString(capability, FIELD_NAME_CN));
        String businessDomain = markdownText(MapUtils.getString(capability, FIELD_BUSINESS_DOMAIN));
        String description = markdownText(MapUtils.getString(capability, FIELD_DESCRIPTION));
        String modelDescription = markdownText(MapUtils.getString(capability, FIELD_MODEL_DESCRIPTION));
        rejectCapabilityManagedMarker(actionCode);
        rejectCapabilityManagedMarker(nameCn);
        rejectCapabilityManagedMarker(businessDomain);
        rejectCapabilityManagedMarker(description);
        rejectCapabilityManagedMarker(modelDescription);
        guidance.append("\n### `").append(actionCode).append('`');
        if (StringUtils.isNotBlank(nameCn)) {
            guidance.append("（").append(nameCn).append("）");
        }
        guidance.append('\n');
        guidance.append("- 业务域：").append(businessDomain).append('\n');
        guidance.append("- 调用说明：")
                .append(StringUtils.join(distinctGuidanceParts(purpose, description, modelDescription), "；"))
                .append('\n');
        guidance.append("- 执行约束：副作用=")
                .append(sideEffectLabel(MapUtils.getString(capability, FIELD_SIDE_EFFECT_LEVEL)))
                .append("；审批=")
                .append(approvalPolicyLabel(MapUtils.getString(capability, FIELD_APPROVAL_POLICY)))
                .append("。\n");
    }

    private List<String> distinctGuidanceParts(String... values) {
        Set<String> parts = new LinkedHashSet<>();
        for (String value : values) {
            if (StringUtils.isNotBlank(value)) {
                parts.add(value);
            }
        }
        return new ArrayList<>(parts);
    }

    private String sideEffectLabel(String sideEffectLevel) {
        return switch (StringUtils.defaultString(sideEffectLevel)) {
            case SIDE_EFFECT_READ -> LABEL_SIDE_EFFECT_READ;
            case SIDE_EFFECT_WRITE -> LABEL_SIDE_EFFECT_WRITE;
            case SIDE_EFFECT_DESTRUCTIVE -> LABEL_SIDE_EFFECT_DESTRUCTIVE;
            default -> throw new IllegalStateException(ERROR_CAPABILITY_GOVERNANCE_INVALID);
        };
    }

    private String approvalPolicyLabel(String approvalPolicy) {
        return switch (StringUtils.defaultString(approvalPolicy)) {
            case APPROVAL_AUTO_EXECUTE -> LABEL_APPROVAL_AUTO_EXECUTE;
            case APPROVAL_REQUEST_APPROVAL -> LABEL_APPROVAL_REQUEST_APPROVAL;
            default -> throw new IllegalStateException(ERROR_CAPABILITY_GOVERNANCE_INVALID);
        };
    }

    private void rejectCapabilityManagedMarker(String value) {
        if (StringUtils.contains(value, CAPABILITY_GUIDANCE_START)
                || StringUtils.contains(value, CAPABILITY_GUIDANCE_END)) {
            throw new IllegalStateException(ERROR_CAPABILITY_GUIDANCE_MARKER_FORBIDDEN);
        }
    }

    private void validateCompiledComponent(SkillFactoryComponentAsset asset) {
        if (asset == null) {
            throw new IllegalStateException(ERROR_COMPONENT_RELEASE_PAYLOAD_INVALID);
        }
        if (!StringUtils.equals(DSL_TYPE_CARD_CONTAINER, asset.getDslType())) {
            throw new IllegalStateException(ERROR_COMPONENT_DSL_UNSUPPORTED);
        }
        if (StringUtils.isBlank(asset.getComponentName())) {
            throw new IllegalStateException(ERROR_COMPONENT_NAME_REQUIRED);
        }
        rejectManagedMarker(asset.getComponentNameCn());
        rejectManagedMarker(asset.getScene());
        rejectManagedMarker(asset.getIntegrationPrompt());
    }

    private void rejectManagedMarker(String value) {
        if (StringUtils.contains(value, COMPONENT_GUIDANCE_START)
                || StringUtils.contains(value, COMPONENT_GUIDANCE_END)) {
            throw new IllegalStateException(ERROR_COMPONENT_GUIDANCE_MARKER_FORBIDDEN);
        }
    }

    private void rejectA2uiApplicationManagedMarker(String value) {
        if (StringUtils.contains(value, A2UI_APPLICATION_GUIDANCE_START)
                || StringUtils.contains(value, A2UI_APPLICATION_GUIDANCE_END)) {
            throw new IllegalStateException(ERROR_A2UI_APPLICATION_GUIDANCE_MARKER_FORBIDDEN);
        }
    }

    private String markdownText(String value) {
        return StringUtils.normalizeSpace(StringUtils.defaultString(value));
    }

    /**
     * 构建模型 System runtime context 中的精简依赖事实。
     */
    public String buildModelRuntimeContext(String workspaceId) {
        return "- authoringDependencies: " + JsonSupport.toJSON(getAuthoringContext(workspaceId));
    }

    private SkillDraft requireDraft(String workspaceId) {
        SkillDraft draft = workspaceRepository.findDraftByWorkspaceId(requireWorkspaceId(workspaceId));
        if (draft == null) {
            throw new IllegalArgumentException(ERROR_WORKSPACE_NOT_FOUND);
        }
        return draft;
    }

    private String requireWorkspaceId(String workspaceId) {
        if (StringUtils.isBlank(workspaceId)) {
            throw new IllegalArgumentException(ERROR_WORKSPACE_REQUIRED);
        }
        return workspaceId;
    }

    private List<Map<String, Object>> normalizeCapabilityReferences(List<Map<String, Object>> bindings,
            List<String> migrationIssues) {
        List<Map<String, Object>> result = new ArrayList<>();
        for (Map<String, Object> binding : bindings) {
            Map<String, Object> reference = normalizeCapabilityReference(binding);
            if (StringUtils.isBlank(MapUtils.getString(reference, FIELD_ACTION_CODE))) {
                migrationIssues.add(ERROR_CAPABILITY_IDENTITY_REQUIRED + ": "
                        + firstNotBlank(MapUtils.getString(binding, FIELD_ACTION_CODE),
                                MapUtils.getString(binding, FIELD_CAPABILITY_CODE), "unknown"));
                continue;
            }
            result.add(reference);
        }
        return result;
    }

    private List<Map<String, Object>> normalizeComponentReferences(List<Map<String, Object>> bindings,
            List<String> migrationIssues) {
        List<Map<String, Object>> result = new ArrayList<>();
        for (Map<String, Object> binding : bindings) {
            Map<String, Object> reference = normalizeComponentReference(binding);
            if (StringUtils.isBlank(MapUtils.getString(reference, FIELD_COMPONENT_CODE))) {
                migrationIssues.add(ERROR_COMPONENT_IDENTITY_REQUIRED + ": "
                        + firstNotBlank(MapUtils.getString(binding, FIELD_COMPONENT_CODE),
                                MapUtils.getString(binding, FIELD_CODE), "unknown"));
                continue;
            }
            result.add(reference);
        }
        return result;
    }

    private Map<String, Object> normalizeCapabilityReference(Map<String, Object> binding) {
        Map<String, Object> reference = new LinkedHashMap<>();
        reference.put(FIELD_ACTION_CODE, firstNotBlank(MapUtils.getString(binding, FIELD_ACTION_CODE),
                MapUtils.getString(binding, FIELD_CAPABILITY_CODE)));
        reference.put(FIELD_VERSION, positiveInt(binding.get(FIELD_VERSION)));
        reference.put(FIELD_MODE, firstNotBlank(MapUtils.getString(binding, FIELD_MODE),
                MapUtils.getString(binding, FIELD_BIND_MODE),
                MapUtils.getString(binding, FIELD_INTENDED_BIND_MODE), DEFAULT_CAPABILITY_MODE));
        putIfNotBlank(reference, FIELD_PURPOSE, MapUtils.getString(binding, FIELD_PURPOSE));
        return reference;
    }

    private Map<String, Object> normalizeComponentReference(Map<String, Object> binding) {
        Map<String, Object> reference = new LinkedHashMap<>();
        reference.put(FIELD_COMPONENT_CODE, firstNotBlank(MapUtils.getString(binding, FIELD_COMPONENT_CODE),
                MapUtils.getString(binding, FIELD_CODE)));
        reference.put(FIELD_VERSION,
                firstPositiveInt(binding.get(FIELD_VERSION), binding.get(FIELD_COMPONENT_VERSION)));
        reference.put(FIELD_USAGE,
                firstNotBlank(MapUtils.getString(binding, FIELD_USAGE), DEFAULT_COMPONENT_USAGE));
        putIfNotBlank(reference, FIELD_PURPOSE, MapUtils.getString(binding, FIELD_PURPOSE));
        return reference;
    }

    private Map<String, Object> detailResult(Map<String, Object> reference, Map<String, Object> detail) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put(FIELD_REFERENCE, reference);
        result.put(FIELD_DETAIL, detail);
        return result;
    }

    /** 根据受控关系快照构建模型可见能力信息。 */
    private Map<String, Object> buildCapabilityAuthoringItem(Map<String, Object> binding) {
        Map<String, Object> item = new LinkedHashMap<>();
        Map<String, Object> bindingIdentity = new LinkedHashMap<>();
        bindingIdentity.put(FIELD_DRAFT_ID, MapUtils.getString(binding, FIELD_DRAFT_ID));
        bindingIdentity.put(FIELD_REVISION, positiveInt(binding.get(FIELD_REVISION)));
        item.put(FIELD_BINDING_IDENTITY, bindingIdentity);
        item.put(FIELD_ACTION_CODE, firstNotBlank(MapUtils.getString(binding, FIELD_ACTION_CODE),
                MapUtils.getString(binding, FIELD_CAPABILITY_CODE)));
        item.put(FIELD_NAME_CN, MapUtils.getString(binding, FIELD_NAME_CN));
        item.put(FIELD_BUSINESS_DOMAIN, MapUtils.getString(binding, FIELD_BUSINESS_DOMAIN));
        item.put(FIELD_DESCRIPTION, MapUtils.getString(binding, FIELD_DESCRIPTION));
        String bindMode = firstNotBlank(MapUtils.getString(binding, FIELD_BIND_MODE),
                MapUtils.getString(binding, FIELD_MODE), DEFAULT_CAPABILITY_MODE);
        item.put(FIELD_BIND_MODE, bindMode);
        List<String> supportedClients = stringList(binding.get(FIELD_SUPPORTED_CLIENTS));
        Map<String, Object> sourceVariants = map(binding.get(FIELD_CLIENT_VARIANTS));
        Map<String, Object> clientVariants = new LinkedHashMap<>();
        for (String client : supportedClients) {
            Map<String, Object> sourceVariant = map(sourceVariants.get(client));
            Map<String, Object> variant = new LinkedHashMap<>();
            variant.put(FIELD_MODEL_CONTRACT,
                    buildModelContract(map(sourceVariant.get(FIELD_MODEL_CONTRACT))));
            variant.put(FIELD_RESULT_CONTRACT,
                    buildResultContract(map(sourceVariant.get(FIELD_RESULT_CONTRACT))));
            clientVariants.put(client, variant);
        }
        item.put(FIELD_SUPPORTED_CLIENTS, supportedClients);
        item.put(FIELD_CLIENT_VARIANTS, clientVariants);
        item.put(FIELD_GOVERNANCE, buildGovernance(map(binding.get(FIELD_GOVERNANCE))));
        item.put(FIELD_PRESENTATION, buildPresentation(bindMode));
        return item;
    }

    /** 只保留模型可填写的 Tool 参数及其业务语义。 */
    private Map<String, Object> buildModelContract(Map<String, Object> source) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put(FIELD_DESCRIPTION, MapUtils.getString(source, FIELD_DESCRIPTION));
        List<Map<String, Object>> inputFields = new ArrayList<>();
        Object fields = source.get(FIELD_INPUT_FIELDS);
        if (fields instanceof List<?> list) {
            for (Object fieldValue : list) {
                Map<String, Object> field = map(fieldValue);
                if (!FIELD_SOURCE_MODEL_INPUT.equals(MapUtils.getString(field, FIELD_SOURCE))) {
                    continue;
                }
                inputFields.add(copyFields(field, FIELD_TOOL_FIELD, FIELD_TYPE, FIELD_BUSINESS_MEANING,
                        FIELD_UNIT, FIELD_SOURCE, FIELD_REQUIRED, FIELD_EXAMPLES,
                        FIELD_ALLOWED_VALUES, FIELD_ITEMS));
            }
        }
        result.put(FIELD_INPUT_FIELDS, inputFields);
        result.put(FIELD_INPUT_EXAMPLE, filterInputExample(
                parseExampleJson(MapUtils.getString(source, FIELD_INPUT_EXAMPLE_JSON), FIELD_INPUT_EXAMPLE_JSON),
                inputFields));
        return result;
    }

    /** 只保留模型需要理解的关键结果路径和脱敏成功样例。 */
    private Map<String, Object> buildResultContract(Map<String, Object> source) {
        Map<String, Object> result = new LinkedHashMap<>();
        List<Map<String, Object>> keyOutputFields = new ArrayList<>();
        Object fields = source.get(FIELD_KEY_OUTPUT_FIELDS);
        if (fields instanceof List<?> list) {
            for (Object fieldValue : list) {
                keyOutputFields.add(copyFields(map(fieldValue), FIELD_PATH, FIELD_DESCRIPTION, FIELD_OBSERVED_TYPE));
            }
        }
        result.put(FIELD_KEY_OUTPUT_FIELDS, keyOutputFields);
        result.put(FIELD_RESPONSE_EXAMPLE, sanitizeModelExample(
                parseExampleJson(MapUtils.getString(source, FIELD_RESPONSE_DEMO_JSON), FIELD_RESPONSE_DEMO_JSON)));
        return result;
    }

    /** 生成 Skill 编排必须遵守的副作用和审批约束。 */
    private Map<String, Object> buildGovernance(Map<String, Object> source) {
        return copyFields(source, FIELD_SIDE_EFFECT_LEVEL, FIELD_APPROVAL_POLICY);
    }

    /** 告诉模型是否允许展示，但不暴露能力绑定的具体组件实现。 */
    private Map<String, Object> buildPresentation(String bindMode) {
        boolean enabled = BIND_MODE_EXECUTION_AND_RENDER.equals(bindMode);
        Map<String, Object> presentation = new LinkedHashMap<>();
        presentation.put(FIELD_ENABLED, enabled);
        presentation.put(FIELD_RUNTIME_MANAGED, true);
        presentation.put(FIELD_INSTRUCTION,
                enabled ? PRESENTATION_RENDER_INSTRUCTION : PRESENTATION_EXECUTION_ONLY_INSTRUCTION);
        return presentation;
    }

    private Map<String, Object> copyFields(Map<String, Object> source, String... fields) {
        Map<String, Object> result = new LinkedHashMap<>();
        for (String field : fields) {
            if (source.containsKey(field)) {
                result.put(field, source.get(field));
            }
        }
        return result;
    }

    private Object parseExampleJson(String json, String fieldName) {
        if (StringUtils.isBlank(json)) {
            return null;
        }
        try {
            return JsonSupport.fromJSON(json, Object.class);
        } catch (Exception e) {
            log.warn("Skill创建期能力样例解析失败, fieldName:{}, error:{}", fieldName, e.getMessage());
            throw new IllegalStateException(ERROR_CAPABILITY_EXAMPLE_INVALID + ": " + fieldName, e);
        }
    }

    /** 输入样例只允许保留当前投影中可见 Tool 字段。 */
    @SuppressWarnings("unchecked")
    private Object filterInputExample(Object example, List<Map<String, Object>> inputFields) {
        if (example == null) {
            return null;
        }
        if (!(example instanceof Map<?, ?>)) {
            throw new IllegalStateException(ERROR_CAPABILITY_EXAMPLE_INVALID + ": " + FIELD_INPUT_EXAMPLE_JSON);
        }
        Set<String> visibleToolFields = inputFields.stream()
                .map(field -> MapUtils.getString(field, FIELD_TOOL_FIELD))
                .filter(StringUtils::isNotBlank)
                .collect(Collectors.toSet());
        Map<String, Object> filtered = new LinkedHashMap<>();
        ((Map<String, Object>) example).forEach((key, value) -> {
            if (visibleToolFields.contains(key) && !isHiddenModelContextField(key)) {
                filtered.put(key, sanitizeModelExample(value));
            }
        });
        return filtered;
    }

    /** 递归移除运行态身份和凭证字段，避免脱敏草稿被后续误编辑时进入模型上下文。 */
    @SuppressWarnings("unchecked")
    private Object sanitizeModelExample(Object value) {
        if (value instanceof Map<?, ?>) {
            Map<String, Object> sanitized = new LinkedHashMap<>();
            ((Map<String, Object>) value).forEach((key, item) -> {
                if (!isHiddenModelContextField(key)) {
                    sanitized.put(key, sanitizeModelExample(item));
                }
            });
            return sanitized;
        }
        if (value instanceof List<?> list) {
            return list.stream().map(this::sanitizeModelExample).toList();
        }
        return value;
    }

    private boolean isHiddenModelContextField(String fieldName) {
        String normalized = StringUtils.defaultString(fieldName)
                .replaceAll("[^a-zA-Z0-9]", StringUtils.EMPTY)
                .toLowerCase(Locale.ROOT);
        return MODEL_CONTEXT_HIDDEN_FIELD_NAMES.contains(normalized);
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> map(Object value) {
        if (!(value instanceof Map<?, ?>)) {
            return Collections.emptyMap();
        }
        return new LinkedHashMap<>((Map<String, Object>) value);
    }

    private Map<String, Object> sanitizedDetail(Map<String, Object> binding) {
        Map<String, Object> detail = new LinkedHashMap<>(binding);
        detail.remove(FIELD_DRAFT_ID);
        detail.remove(FIELD_CAPABILITY_DRAFT_ID);
        detail.remove(FIELD_REVISION);
        return detail;
    }

    private void putIfNotBlank(Map<String, Object> target, String key, String value) {
        if (StringUtils.isNotBlank(value)) {
            target.put(key, value);
        }
    }

    private int firstPositiveInt(Object... values) {
        for (Object value : values) {
            int number = positiveInt(value);
            if (number > 0) {
                return number;
            }
        }
        return 0;
    }

    private int positiveInt(Object value) {
        if (value instanceof Number number) {
            return Math.max(number.intValue(), 0);
        }
        try {
            return Math.max(Integer.parseInt(StringUtils.trimToEmpty(Objects.toString(value, ""))), 0);
        } catch (NumberFormatException ignored) {
            return 0;
        }
    }

    private String firstNotBlank(String... values) {
        for (String value : values) {
            if (StringUtils.isNotBlank(value)) {
                return value;
            }
        }
        return StringUtils.EMPTY;
    }

    /**
     * 按当前 Skill 数字版本读取指定类型关系的受控快照。
     *
     * <p>查询身份直接使用 `skill_draft.id + skill_draft.version`，不读取独立关系版本或头指针。
     */
    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> currentBindings(SkillDraft draft, String relationType) {
        if (draft == null || draft.getId() == null || draft.getId() <= 0L) {
            throw new IllegalStateException(ERROR_SKILL_DRAFT_ID_REQUIRED);
        }
        List<Map<String, Object>> result = new ArrayList<>();
        List<EntityRelationDO> relations = entityRelationRepository.listBySourceVersion(
                SkillFactoryEntityRelationConstants.NAMESPACE_SKILL_FACTORY,
                SkillFactoryEntityRelationConstants.ENTITY_TYPE_SKILL,
                String.valueOf(draft.getId()), currentSkillVersion(draft));
        for (EntityRelationDO relation : relations) {
            if (!StringUtils.equals(relationType, relation.getRelationType())) {
                continue;
            }
            try {
                Object snapshot = JsonSupport.fromJSON(relation.getSnapshotJson(), Object.class);
                if (!(snapshot instanceof Map<?, ?>)) {
                    throw new IllegalStateException(ERROR_RELATION_SNAPSHOT_INVALID);
                }
                result.add(new LinkedHashMap<>((Map<String, Object>) snapshot));
            } catch (Exception e) {
                log.warn("Skill创建期实体关系快照解析失败, skillCode:{}, skillVersion:{}, "
                                + "relationId:{}, relationType:{}, error:{}",
                        draft.getSkillCode(), draft.getVersion(), relation.getId(), relation.getRelationType(),
                        e.getMessage());
                throw new IllegalStateException(ERROR_RELATION_SNAPSHOT_INVALID, e);
            }
        }
        return result;
    }

    /** 读取当前 Skill 数字版本并拒绝无效草稿版本。 */
    private int currentSkillVersion(SkillDraft draft) {
        if (draft == null || draft.getVersion() == null || draft.getVersion() <= 0) {
            throw new IllegalStateException(ERROR_SKILL_VERSION_INVALID);
        }
        return draft.getVersion();
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> mapList(Object value) {
        if (!(value instanceof List<?> list)) {
            return Collections.emptyList();
        }
        return list.stream()
                .filter(Map.class::isInstance)
                .map(item -> (Map<String, Object>) item)
                .toList();
    }

    private List<String> stringList(Object value) {
        if (!(value instanceof List<?> list)) {
            return Collections.emptyList();
        }
        return list.stream().map(String::valueOf).filter(StringUtils::isNotBlank).toList();
    }

    /** 一次受管依赖编译的确定性输出；Tool 只消费这些后端生成字段，模型不能传入正文。 */
    @Data
    @Accessors(chain = true)
    public static class ManagedDependencyCompilation {
        private String componentGuidance;
        private List<String> componentCodes = Collections.emptyList();
        private String a2uiApplicationGuidance;
        private List<String> a2uiApplicationCodes = Collections.emptyList();
        private String capabilityGuidance;
        private List<String> actionCodes = Collections.emptyList();
    }

    /** 组件说明 Tool 的确定性输出；不包含 Patch、文件摘要或业务能力编译状态。 */
    @Data
    @Accessors(chain = true)
    public static class ManagedComponentGuidanceCompilation {
        private String guidance;
        private List<String> componentCodes = Collections.emptyList();
    }

    /** 能力说明正文及其稳定 actionCode 列表，二者在一次目录解析中共同生成。 */
    private static final class CapabilityGuidanceCompilation {
        private final String guidance;
        private final List<String> actionCodes;

        private CapabilityGuidanceCompilation(String guidance, List<String> actionCodes) {
            this.guidance = guidance;
            this.actionCodes = actionCodes;
        }
    }

    /** A2UI Application说明正文及稳定appCode列表。 */
    private static final class A2uiApplicationGuidanceCompilation {
        private final String guidance;
        private final List<String> appCodes;

        private A2uiApplicationGuidanceCompilation(String guidance, List<String> appCodes) {
            this.guidance = guidance;
            this.appCodes = appCodes;
        }
    }

    /** 一条Registry绑定及其按类型解析出的PRT不可变发布事实。 */
    private static final class ResolvedBoundAsset {
        private final ComponentAsset registryAsset;
        private final AssetDependencyType dependencyType;
        private final ResolvedReleasedAsset resolvedAsset;

        private ResolvedBoundAsset(ComponentAsset registryAsset,
                AssetDependencyType dependencyType, ResolvedReleasedAsset resolvedAsset) {
            this.registryAsset = registryAsset;
            this.dependencyType = dependencyType;
            this.resolvedAsset = resolvedAsset;
        }
    }
}
