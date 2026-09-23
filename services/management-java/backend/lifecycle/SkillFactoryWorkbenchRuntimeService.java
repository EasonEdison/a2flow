package dev.a2flow.management.lifecycle;

import java.io.IOException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import jakarta.annotation.Resource;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.lifecycle.domain.SkillDraft;
import dev.a2flow.management.model.CapabilityActionDraft;
import dev.a2flow.management.model.SkillFactoryComponentAsset;
import dev.a2flow.management.model.SkillFactoryEntityRelationConstants;
import dev.a2flow.management.release.dependency.AssetDependencyModels.ResolvedReleasedAsset;
import dev.a2flow.management.release.dependency.AssetDependencyType;
import dev.a2flow.management.storage.db.entity.EntityRelationDO;
import dev.a2flow.management.storage.db.repository.EntityRelationRepository;
import dev.a2flow.management.storage.db.repository.SkillFactoryWorkspaceRepository;

import lombok.extern.slf4j.Slf4j;

/**
 * SkillFactory 工作台运行态预演 Service。
 *
 * <p>该类只服务 lifecycle/workbench 页面：按 Skill 数字版本完整覆盖业务能力和直接组件关系，
 * 并在绑定前用静态上下文做输出协议识别、注册校验和轻量预览。关系写入只允许通过
 * `SKILL_BINDINGS_REPLACE` 进入，避免旧引用接口与 `entity_relation` 形成双事实源。它不写 Skill
 * 工程文件，不执行 AI Coding patch，也不实现 adviser 生产运行态或真实 B 端绑定。
 */
@Service
@Slf4j
public class SkillFactoryWorkbenchRuntimeService {

    private static final String EMPTY = "";
    private static final String COMMA = ",";
    private static final String PARAM_WORKSPACE_ID = "workspaceId";
    private static final String PARAM_SKILL_CODE = "skillCode";
    private static final String PARAM_REFERENCE_RENDER_ASSETS = "referenceRenderAssets";
    private static final String PARAM_CAPABILITY_BINDINGS = "capabilityBindings";
    private static final String PARAM_COMPONENT_BINDINGS = "componentBindings";
    private static final String PARAM_VERSION = "version";
    private static final String PARAM_SAMPLE_SOURCE = "sampleSource";
    private static final String PARAM_SAMPLE_PAYLOAD = "samplePayload";
    private static final String PARAM_FILE_PATH = "filePath";
    private static final String SAMPLE_SOURCE_AUTO = "AUTO";
    private static final String SAMPLE_SOURCE_FILE = "FILE";
    private static final String SAMPLE_SOURCE_CUSTOM = "CUSTOM";
    private static final String FIELD_WORKSPACE_ID = "workspaceId";
    private static final String FIELD_SKILL_CODE = "skillCode";
    private static final String FIELD_REFERENCE_RENDER_ASSETS = "referenceRenderAssets";
    private static final String FIELD_REFERENCE_COMPONENT_CODES = "referenceComponentCodes";
    private static final String FIELD_REFERENCE_CAPABILITIES = "referenceCapabilities";
    private static final String FIELD_REFERENCE_CAPABILITY_DRAFT_IDS = "referenceCapabilityDraftIds";
    private static final String FIELD_CAPABILITY_BINDINGS = "capabilityBindings";
    private static final String FIELD_COMPONENT_BINDINGS = "componentBindings";
    private static final String FIELD_VERSION = "version";
    private static final String FIELD_BIND_MODE = "bindMode";
    private static final String FIELD_CAPABILITY_CODE = "capabilityCode";
    private static final String FIELD_ASSET_ID = "assetId";
    private static final String FIELD_COMPONENT_CODE = "componentCode";
    private static final String FIELD_COMPONENT_NAME_CN = "componentNameCn";
    private static final String FIELD_COMPONENT_VERSION = "componentVersion";
    private static final String FIELD_UPDATE_TIME = "updateTime";
    private static final String FIELD_SOURCE = "source";
    private static final String FIELD_RENDER_PROTOCOL = "renderProtocol";
    private static final String FIELD_PAYLOAD = "payload";
    private static final String FIELD_CONTENT_DIGEST = "contentDigest";
    private static final String FIELD_STATUS = "status";
    private static final String FIELD_SAMPLES = "samples";
    private static final String FIELD_SAMPLE_SOURCE = "sampleSource";
    private static final String FIELD_PARSED_PAYLOAD = "parsedPayload";
    private static final String FIELD_PROTOCOL_TYPE = "protocolType";
    private static final String FIELD_ROUTE = "route";
    private static final String FIELD_REGISTRY_STATUS = "registryStatus";
    private static final String FIELD_SCHEMA_STATUS = "schemaStatus";
    private static final String FIELD_RUNTIME_STATUS = "runtimeStatus";
    private static final String FIELD_FRONTEND_STATUS = "frontendStatus";
    private static final String FIELD_ACTION_STATUS = "actionStatus";
    private static final String FIELD_ENTITY_CONTEXT_STATUS = "entityContextStatus";
    private static final String FIELD_ERRORS = "errors";
    private static final String FIELD_WARNINGS = "warnings";
    private static final String FIELD_CHECKLIST = "checklist";
    private static final String FIELD_PREVIEW = "preview";
    private static final String FIELD_REPAIR_PROMPT = "repairPrompt";
    private static final String FIELD_PC = "pc";
    private static final String FIELD_APP = "app";
    private static final String FIELD_KEY = "key";
    private static final String FIELD_LABEL = "label";
    private static final String FIELD_MESSAGE = "message";
    private static final String FIELD_CODE = "code";
    private static final String FIELD_NAME = "name";
    private static final String FIELD_ASSET_TYPE = "assetType";
    private static final String FIELD_COMPONENT_NAME = "componentName";
    private static final String FIELD_DSL_CODE = "dslCode";
    private static final String FIELD_LOCAL_METHOD = "localMethod";
    private static final String FIELD_RENDER_PROTOCOL_ASSET = "renderProtocol";
    private static final String FIELD_DSL_TYPE = "dslType";
    private static final String FIELD_AGENT_UI_DSL = "agentUiDsl";
    private static final String FIELD_TYPE = "type";
    private static final String FIELD_ACTIONS = "actions";
    private static final String FIELD_ACTION = "action";
    private static final String FIELD_ACTION_CODE = "actionCode";
    private static final String FIELD_DRAFT_ID = "draftId";
    private static final String FIELD_REVISION = "revision";
    private static final String FIELD_PUBLISHED = "published";
    private static final String FIELD_PUBLISHED_VERSION = "publishedVersion";
    private static final String FIELD_VALIDATION_STATUS = "validationStatus";
    private static final String FIELD_BASIC_INFO = "basicInfo";
    private static final String FIELD_NAME_CN = "nameCn";
    private static final String FIELD_DESCRIPTION = "description";
    private static final String FIELD_BUSINESS_DOMAIN = "businessDomain";
    private static final String FIELD_SUPPORTED_CLIENTS = "supportedClients";
    private static final String FIELD_CLIENT_VARIANTS = "clientVariants";
    private static final String FIELD_API_SOURCE = "apiSource";
    private static final String FIELD_SOURCE_TYPE = "sourceType";
    private static final String SOURCE_TYPE_MIXED = "MIXED";
    private static final String FIELD_RESULT_CONTRACT = "resultContract";
    private static final String FIELD_PRESENTATION_COMPONENTS = "presentationComponents";
    private static final String FIELD_GOVERNANCE = "governance";
    private static final String FIELD_SIDE_EFFECT_LEVEL = "sideEffectLevel";
    private static final String FIELD_APPROVAL_POLICY = "approvalPolicy";
    private static final String FIELD_OFFICIAL_DEMO_JSON = "officialDemoJson";
    private static final String FIELD_SCHEMA_JSON = "schemaJson";
    private static final String FIELD_INTEGRATION_PROMPT = "integrationPrompt";
    private static final String FIELD_OWNER = "owner";
    private static final String FIELD_SCENE = "scene";
    private static final String FIELD_LIFECYCLE_STATUS = "lifecycleStatus";
    private static final String FIELD_ENABLED = "enabled";
    private static final String FIELD_PROTOCOL_VERSION = "protocolVersion";
    private static final String FIELD_INTERACTION_MODE = "interactionMode";
    private static final String FIELD_RENDERER_VERSION = "rendererVersion";
    private static final String FIELD_ALLOWED_ACTIONS_JSON = "allowedActionsJson";
    private static final String FIELD_ATOM_COMPONENTS_JSON = "atomComponentsJson";
    private static final String PROTOCOL_AGENT_UI_DSL = "agentUiDsl";
    private static final String PROTOCOL_COMPONENT_NAME = "componentName";
    private static final String PROTOCOL_LOCAL_METHOD = "localMethod";
    private static final String PROTOCOL_A2UI_DEMO = "A2UI_DEMO";
    private static final String PROTOCOL_TEXT = "TEXT";
    private static final String PROTOCOL_UNKNOWN = "UNKNOWN";
    private static final String STATUS_PASSED = "PASSED";
    private static final String STATUS_FAILED = "FAILED";
    private static final String STATUS_PARTIAL = "PARTIAL";
    private static final String STATUS_SKIPPED = "SKIPPED";
    private static final String ROUTE_AGENT_UI_DSL = "agentUiDsl -> DSL Runtime -> A2UI";
    private static final String ROUTE_LOCAL_METHOD = "localMethod -> localMethod renderer";
    private static final String ROUTE_CARD_CONTAINER = "componentName -> card-container renderer";
    private static final String ROUTE_A2UI_DEMO = "完整 A2UI demo preview";
    private static final String ROUTE_TEXT = "文本 / Markdown";
    private static final String ERROR_REQUIRED_SUFFIX = " is required";
    private static final String ERROR_WORKSPACE_NOT_FOUND = "workspace draft not found";
    private static final String ERROR_SKILL_IDENTITY_MISMATCH = "skillCode and workspaceId mismatch";
    private static final String ERROR_NO_SAMPLE = "未提取到可验证输出样例";
    private static final String ERROR_PROTOCOL_UNKNOWN = "输出协议不可识别";
    private static final String ERROR_ASSET_NOT_REGISTERED = "协议对应组件/DSL未在组件中心或参考资产中命中";
    private static final String ERROR_BINDINGS_FORMAT_SUFFIX = " must be a JSON object array";
    private static final String ERROR_SKILL_VERSION_CONFLICT = "skill version conflict, reload Skill detail";
    private static final String ERROR_CAPABILITY_BIND_MODE_INVALID = "capability bindMode is invalid";
    private static final String ERROR_CAPABILITY_CODE_REQUIRED = "capability actionCode is required";
    private static final String ERROR_CAPABILITY_PRESENTATION_REQUIRED =
            "EXECUTION_AND_RENDER requires capability presentation components";
    private static final String ERROR_CAPABILITY_PRESENTATION_IDENTITY_CONFLICT =
            "capability presentation component identity conflict";
    private static final String ERROR_CAPABILITY_PRESENTATION_VERSION_CONFLICT =
            "capability presentation component version conflict";
    private static final String ERROR_COMPONENT_ID_INVALID = "component assetId is invalid";
    private static final String ERROR_COMPONENT_DISABLED = "component asset is not enabled";
    private static final String ERROR_COMPONENT_CODE_REQUIRED = "component code is required";
    private static final String ERROR_COMPONENT_IDENTITY_CONFLICT = "component binding identity conflict";
    private static final String ERROR_DUPLICATE_BINDING_CODE_SUFFIX = " contains duplicate code";
    private static final String ERROR_INVALID_SUFFIX = " is invalid";
    private static final String WARNING_RUNTIME_NOT_CONNECTED =
            "adviser runtime / renderer / action sandbox 尚未接入真实执行，当前只做 contract 预演";
    private static final String REPAIR_PROMPT_PREFIX = "请根据运行态验证结果修复当前 Skill 输出协议。";
    private static final String BIND_MODE_EXECUTION_ONLY = "EXECUTION_ONLY";
    private static final String BIND_MODE_EXECUTION_AND_RENDER = "EXECUTION_AND_RENDER";
    private static final Set<String> CAPABILITY_BIND_MODES = Set.of(
            BIND_MODE_EXECUTION_ONLY, BIND_MODE_EXECUTION_AND_RENDER);
    private static final Set<String> LOCAL_METHODS = Set.of("selectComponentRefs", "submitMissingInfo",
            "confirmAcceptanceCriteria");

    @Resource
    private SkillFactoryWorkspaceRepository workspaceRepository;

    @Resource
    private EntityRelationRepository entityRelationRepository;

    @Resource
    private SkillFactoryWorkspaceService workspaceService;

    @Resource
    private SkillFactoryComponentRegistryService componentRegistryService;

    @Resource
    private CapabilityActionDraftService capabilityActionDraftService;

    @Resource
    private SkillBindingCandidateService skillBindingCandidateService;

    /**
     * 完整覆盖当前 Skill 的业务能力和直接组件绑定。
     *
     * <p>页面每次提交两类完整目标数组和当前 Skill 数字版本，本方法只信任稳定资产身份和 Skill 期望版本，
     * 再分别从能力/组件 Repository 读取受控事实并生成快照。业务能力的渲染组件保留在 resultContract
     * 中，不复制成直接组件关系；最终由关系 Repository 一次覆盖当前 Skill 版本的完整关系集合，空数组
     * 表示清空。
     */
    public Map<String, Object> replaceBindings(String userName, Map<String, String> params) {
        String workspaceId = required(params, PARAM_WORKSPACE_ID);
        String skillCode = string(params.get(PARAM_SKILL_CODE));
        SkillDraft draft = requireDraft(workspaceId, skillCode);
        int expectedVersion = requiredIntegerParam(params, PARAM_VERSION);
        int currentVersion = currentSkillVersion(draft);
        if (expectedVersion != currentVersion) {
            log.warn("SkillFactory完整覆盖绑定发生Skill版本冲突, workspaceId:{}, skillCode:{}, "
                            + "expectedVersion:{}, currentVersion:{}, userName:{}",
                    workspaceId, draft.getSkillCode(), expectedVersion, currentVersion, userName);
            throw new IllegalStateException(ERROR_SKILL_VERSION_CONFLICT);
        }
        List<Map<String, Object>> capabilityRequests = parseBindingList(
                params.get(PARAM_CAPABILITY_BINDINGS), PARAM_CAPABILITY_BINDINGS);
        List<Map<String, Object>> componentRequests = parseBindingList(
                params.get(PARAM_COMPONENT_BINDINGS), PARAM_COMPONENT_BINDINGS);
        List<Map<String, Object>> capabilityBindings = capabilityRequests.stream()
                .map(this::resolveCapabilityBinding)
                .collect(Collectors.toList());
        List<Map<String, Object>> componentBindings = componentRequests.stream()
                .map(this::resolveComponentBinding)
                .collect(Collectors.toList());
        ensureUniqueBindingCodes(capabilityBindings, FIELD_CAPABILITY_CODE, PARAM_CAPABILITY_BINDINGS);
        ensureUniqueBindingCodes(componentBindings, FIELD_COMPONENT_CODE, PARAM_COMPONENT_BINDINGS);
        List<EntityRelationDO> relations = entityRelationRepository.listBySourceVersion(
                        SkillFactoryEntityRelationConstants.NAMESPACE_SKILL_FACTORY,
                        SkillFactoryEntityRelationConstants.ENTITY_TYPE_SKILL,
                        sourceEntityId(draft), currentVersion)
                .stream()
                .filter(relation -> !isWorkbenchManagedBinding(relation))
                .collect(Collectors.toCollection(ArrayList::new));
        relations.addAll(capabilityRelations(capabilityBindings));
        relations.addAll(componentRelations(componentBindings));
        entityRelationRepository.replaceBySourceVersion(
                SkillFactoryEntityRelationConstants.NAMESPACE_SKILL_FACTORY,
                SkillFactoryEntityRelationConstants.ENTITY_TYPE_SKILL,
                sourceEntityId(draft), currentVersion, relations, userName);
        Map<String, Object> result = new LinkedHashMap<>();
        result.put(FIELD_WORKSPACE_ID, workspaceId);
        result.put(FIELD_SKILL_CODE, draft.getSkillCode());
        result.put(FIELD_VERSION, currentVersion);
        List<Map<String, Object>> enrichedCapabilityBindings =
                skillBindingCandidateService.enrichCapabilityBindings(capabilityBindings);
        List<Map<String, Object>> enrichedComponentBindings =
                skillBindingCandidateService.enrichComponentBindings(componentBindings);
        result.put(FIELD_CAPABILITY_BINDINGS, enrichedCapabilityBindings);
        result.put(FIELD_COMPONENT_BINDINGS, enrichedComponentBindings);
        result.put(FIELD_REFERENCE_CAPABILITIES, enrichedCapabilityBindings);
        result.put(FIELD_REFERENCE_CAPABILITY_DRAFT_IDS, enrichedCapabilityBindings.stream()
                .map(item -> string(item.get(FIELD_DRAFT_ID)))
                .collect(Collectors.toList()));
        result.put(FIELD_REFERENCE_RENDER_ASSETS, enrichedComponentBindings);
        result.put(FIELD_REFERENCE_COMPONENT_CODES, enrichedComponentBindings.stream()
                .map(item -> string(item.get(FIELD_COMPONENT_CODE)))
                .collect(Collectors.joining(COMMA)));
        result.put(FIELD_UPDATE_TIME, System.currentTimeMillis());
        log.info("SkillFactory完整覆盖绑定业务校验完成, userName:{}, workspaceId:{}, skillCode:{}, "
                        + "skillVersion:{}, capabilityCount:{}, componentCount:{}",
                userName, workspaceId, draft.getSkillCode(), currentVersion,
                capabilityBindings.size(), componentBindings.size());
        return result;
    }

    /** 判断关系是否由工作台“能力/组件绑定覆盖”操作管理。 */
    private boolean isWorkbenchManagedBinding(EntityRelationDO relation) {
        return relation != null && (StringUtils.equals(
                SkillFactoryEntityRelationConstants.RELATION_TYPE_SKILL_USES_CAPABILITY,
                relation.getRelationType())
                || StringUtils.equals(
                        SkillFactoryEntityRelationConstants.RELATION_TYPE_SKILL_USES_COMPONENT,
                        relation.getRelationType()));
    }

    /**
     * 对当前 Skill 输出协议做绑定前运行态预演，返回页面可展示的路由、预览和检查清单。
     */
    public Map<String, Object> validateRuntime(String userName, Map<String, String> params) throws IOException {
        String workspaceId = required(params, PARAM_WORKSPACE_ID);
        String skillCode = string(params.get(PARAM_SKILL_CODE));
        SkillDraft draft = requireDraft(workspaceId, skillCode);
        List<Map<String, Object>> samples = samples(workspaceId, params);
        List<Map<String, Object>> referenceAssets = parseAssetList(params.get(PARAM_REFERENCE_RENDER_ASSETS));
        RuntimeDecision decision = decideRuntime(samples, referenceAssets);
        Map<String, Object> result = new LinkedHashMap<>();
        result.put(FIELD_WORKSPACE_ID, workspaceId);
        result.put(FIELD_SKILL_CODE, draft.getSkillCode());
        result.put(FIELD_SAMPLE_SOURCE, string(params.get(PARAM_SAMPLE_SOURCE), SAMPLE_SOURCE_AUTO));
        result.put(FIELD_SAMPLES, samples);
        result.put(FIELD_PARSED_PAYLOAD, decision.parsedPayload);
        result.put(FIELD_PROTOCOL_TYPE, decision.protocolType);
        result.put(FIELD_ROUTE, decision.route);
        result.put(FIELD_REGISTRY_STATUS, decision.registryStatus);
        result.put(FIELD_SCHEMA_STATUS, decision.schemaStatus);
        result.put(FIELD_RUNTIME_STATUS, decision.runtimeStatus);
        result.put(FIELD_FRONTEND_STATUS, decision.frontendStatus);
        result.put(FIELD_ACTION_STATUS, decision.actionStatus);
        result.put(FIELD_ENTITY_CONTEXT_STATUS, decision.entityContextStatus);
        result.put(FIELD_ERRORS, decision.errors);
        result.put(FIELD_WARNINGS, decision.warnings);
        result.put(FIELD_CHECKLIST, decision.checklist);
        result.put(FIELD_PREVIEW, preview(decision.parsedPayload, decision.protocolType, decision.route));
        result.put(FIELD_REPAIR_PROMPT, repairPrompt(decision));
        result.put(FIELD_REFERENCE_RENDER_ASSETS, referenceAssets);
        result.put(FIELD_STATUS, overallStatus(decision));
        log.info("SkillFactory运行态预演完成, userName:{}, workspaceId:{}, protocolType:{}, status:{}, "
                        + "errorCount:{}, warningCount:{}",
                userName, workspaceId, decision.protocolType, result.get(FIELD_STATUS),
                decision.errors.size(), decision.warnings.size());
        return result;
    }

    private SkillDraft requireDraft(String workspaceId, String skillCode) {
        SkillDraft draft = workspaceRepository.findDraftByWorkspaceId(workspaceId);
        if (draft == null) {
            log.warn("SkillFactory工作台运行态操作失败，草稿不存在, workspaceId:{}", workspaceId);
            throw new IllegalArgumentException(ERROR_WORKSPACE_NOT_FOUND);
        }
        if (StringUtils.isNotBlank(skillCode) && !StringUtils.equals(skillCode, draft.getSkillCode())) {
            log.warn("SkillFactory工作台运行态操作失败，Skill身份不一致, workspaceId:{}, paramSkillCode:{}, "
                            + "draftSkillCode:{}",
                    workspaceId, skillCode, draft.getSkillCode());
            throw new IllegalArgumentException(ERROR_SKILL_IDENTITY_MISMATCH);
        }
        return draft;
    }

    private RuntimeDecision decideRuntime(List<Map<String, Object>> samples,
            List<Map<String, Object>> referenceAssets) {
        RuntimeDecision decision = new RuntimeDecision();
        if (samples.isEmpty()) {
            decision.protocolType = PROTOCOL_UNKNOWN;
            decision.route = EMPTY;
            decision.errors.add(ERROR_NO_SAMPLE);
            fillFailedDecision(decision);
            return decision;
        }
        Map<String, Object> sample = samples.get(0);
        Object parsedPayload = parsePayload(sample.get(FIELD_PAYLOAD));
        decision.parsedPayload = parsedPayload;
        decision.protocolType = protocolType(parsedPayload, string(sample.get(FIELD_RENDER_PROTOCOL)));
        decision.route = route(decision.protocolType);
        String targetCode = targetCode(decision.protocolType, parsedPayload);
        if (StringUtils.equals(decision.protocolType, PROTOCOL_UNKNOWN)) {
            decision.errors.add(ERROR_PROTOCOL_UNKNOWN);
            fillFailedDecision(decision);
            return decision;
        }
        boolean registryMatched = registryMatched(decision.protocolType, targetCode, referenceAssets);
        decision.registryStatus = registryMatched || StringUtils.equals(decision.protocolType, PROTOCOL_TEXT)
                ? STATUS_PASSED : STATUS_FAILED;
        if (StringUtils.equals(decision.registryStatus, STATUS_FAILED)) {
            decision.errors.add(ERROR_ASSET_NOT_REGISTERED);
        }
        decision.schemaStatus = schemaStatus(decision.protocolType, parsedPayload, targetCode);
        decision.runtimeStatus = runtimeStatus(decision.protocolType);
        decision.frontendStatus = frontendStatus(decision.protocolType);
        decision.actionStatus = actionStatus(parsedPayload, targetCode);
        decision.entityContextStatus = entityContextStatus(decision.protocolType);
        if (containsPartial(decision)) {
            decision.warnings.add(WARNING_RUNTIME_NOT_CONNECTED);
        }
        decision.checklist = checklist(decision, targetCode);
        return decision;
    }

    private void fillFailedDecision(RuntimeDecision decision) {
        decision.registryStatus = STATUS_FAILED;
        decision.schemaStatus = STATUS_FAILED;
        decision.runtimeStatus = STATUS_SKIPPED;
        decision.frontendStatus = STATUS_SKIPPED;
        decision.actionStatus = STATUS_SKIPPED;
        decision.entityContextStatus = STATUS_SKIPPED;
        decision.checklist = checklist(decision, EMPTY);
    }

    private List<Map<String, Object>> samples(String workspaceId, Map<String, String> params) throws IOException {
        String sampleSource = string(params.get(PARAM_SAMPLE_SOURCE), SAMPLE_SOURCE_AUTO);
        if (StringUtils.equals(sampleSource, SAMPLE_SOURCE_CUSTOM)) {
            String samplePayload = string(params.get(PARAM_SAMPLE_PAYLOAD));
            if (StringUtils.isBlank(samplePayload)) {
                return Collections.emptyList();
            }
            Map<String, Object> sample = new LinkedHashMap<>();
            sample.put(FIELD_SOURCE, SAMPLE_SOURCE_CUSTOM);
            sample.put(FIELD_RENDER_PROTOCOL, PROTOCOL_UNKNOWN);
            sample.put(FIELD_PAYLOAD, samplePayload);
            sample.put(FIELD_CONTENT_DIGEST, EMPTY);
            return List.of(sample);
        }
        Map<String, Object> extractResult = workspaceService.extractRenderSample(workspaceId, params);
        List<Map<String, Object>> samples = castMapList(extractResult.get(FIELD_SAMPLES));
        if (StringUtils.equals(sampleSource, SAMPLE_SOURCE_FILE)) {
            String filePath = string(params.get(PARAM_FILE_PATH));
            return samples.stream()
                    .filter(sample -> StringUtils.equals(filePath, string(sample.get(FIELD_SOURCE))))
                    .collect(Collectors.toList());
        }
        return samples;
    }

    private boolean registryMatched(String protocolType, String targetCode,
            List<Map<String, Object>> referenceAssets) {
        if (StringUtils.equals(protocolType, PROTOCOL_LOCAL_METHOD)) {
            return LOCAL_METHODS.contains(targetCode) || referenceMatched(protocolType, targetCode, referenceAssets);
        }
        if (StringUtils.equals(protocolType, PROTOCOL_TEXT)) {
            return true;
        }
        List<SkillFactoryComponentAsset> registeredAssets =
                componentRegistryService.listPublished(Collections.emptyMap());
        return registeredAssets.stream().anyMatch(asset -> assetMatches(protocolType, targetCode, asset))
                || referenceMatched(protocolType, targetCode, referenceAssets);
    }

    private boolean assetMatches(String protocolType, String targetCode, SkillFactoryComponentAsset asset) {
        if (StringUtils.isBlank(targetCode) || asset == null) {
            return false;
        }
        if (StringUtils.equals(protocolType, PROTOCOL_AGENT_UI_DSL)) {
            return StringUtils.equals(targetCode, asset.getDslType())
                    || StringUtils.equals(targetCode, asset.getComponentName());
        }
        if (StringUtils.equals(protocolType, PROTOCOL_COMPONENT_NAME)) {
            return StringUtils.equals(targetCode, asset.getComponentName());
        }
        if (StringUtils.equals(protocolType, PROTOCOL_A2UI_DEMO)) {
            return StringUtils.equals(targetCode, asset.getComponentName())
                    || StringUtils.contains(asset.getRuntimeConfigJson(), targetCode);
        }
        return false;
    }

    private boolean referenceMatched(String protocolType, String targetCode,
            List<Map<String, Object>> referenceAssets) {
        return referenceAssets.stream().anyMatch(asset ->
                StringUtils.equals(targetCode, string(asset.get(FIELD_CODE)))
                        || StringUtils.equals(targetCode, string(asset.get(FIELD_DSL_CODE)))
                        || StringUtils.equals(targetCode, string(asset.get(FIELD_COMPONENT_NAME)))
                        || StringUtils.equals(targetCode, string(asset.get(FIELD_LOCAL_METHOD))));
    }

    private String protocolType(Object payload, String renderProtocol) {
        Map<String, Object> payloadMap = map(payload);
        if (payloadMap.containsKey(FIELD_AGENT_UI_DSL) || payloadMap.containsKey(FIELD_DSL_CODE)) {
            return PROTOCOL_AGENT_UI_DSL;
        }
        if (payloadMap.containsKey(FIELD_LOCAL_METHOD)) {
            return PROTOCOL_LOCAL_METHOD;
        }
        if (payloadMap.containsKey(FIELD_COMPONENT_NAME)) {
            return PROTOCOL_COMPONENT_NAME;
        }
        if (StringUtils.equalsIgnoreCase(renderProtocol, "A2UI") || payloadMap.containsKey("components")) {
            return PROTOCOL_A2UI_DEMO;
        }
        if (payload instanceof String && StringUtils.isNotBlank((String) payload)) {
            return PROTOCOL_TEXT;
        }
        return PROTOCOL_UNKNOWN;
    }

    private String targetCode(String protocolType, Object payload) {
        Map<String, Object> payloadMap = map(payload);
        if (StringUtils.equals(protocolType, PROTOCOL_AGENT_UI_DSL)) {
            return firstNonBlank(payloadMap.get(FIELD_AGENT_UI_DSL), payloadMap.get(FIELD_DSL_CODE),
                    payloadMap.get(FIELD_TYPE));
        }
        if (StringUtils.equals(protocolType, PROTOCOL_LOCAL_METHOD)) {
            return string(payloadMap.get(FIELD_LOCAL_METHOD));
        }
        if (StringUtils.equals(protocolType, PROTOCOL_COMPONENT_NAME)) {
            return string(payloadMap.get(FIELD_COMPONENT_NAME));
        }
        if (StringUtils.equals(protocolType, PROTOCOL_A2UI_DEMO)) {
            return firstNonBlank(payloadMap.get(FIELD_TYPE), payloadMap.get(FIELD_COMPONENT_NAME));
        }
        return EMPTY;
    }

    private String route(String protocolType) {
        if (StringUtils.equals(protocolType, PROTOCOL_AGENT_UI_DSL)) {
            return ROUTE_AGENT_UI_DSL;
        }
        if (StringUtils.equals(protocolType, PROTOCOL_LOCAL_METHOD)) {
            return ROUTE_LOCAL_METHOD;
        }
        if (StringUtils.equals(protocolType, PROTOCOL_COMPONENT_NAME)) {
            return ROUTE_CARD_CONTAINER;
        }
        if (StringUtils.equals(protocolType, PROTOCOL_A2UI_DEMO)) {
            return ROUTE_A2UI_DEMO;
        }
        if (StringUtils.equals(protocolType, PROTOCOL_TEXT)) {
            return ROUTE_TEXT;
        }
        return EMPTY;
    }

    private String schemaStatus(String protocolType, Object payload, String targetCode) {
        if (StringUtils.equals(protocolType, PROTOCOL_TEXT)) {
            return STATUS_SKIPPED;
        }
        if (StringUtils.isBlank(targetCode) || map(payload).isEmpty()) {
            return STATUS_FAILED;
        }
        return STATUS_PASSED;
    }

    private String runtimeStatus(String protocolType) {
        if (StringUtils.equals(protocolType, PROTOCOL_TEXT)) {
            return STATUS_SKIPPED;
        }
        return STATUS_PARTIAL;
    }

    private String frontendStatus(String protocolType) {
        if (StringUtils.equals(protocolType, PROTOCOL_TEXT)) {
            return STATUS_SKIPPED;
        }
        return STATUS_PARTIAL;
    }

    private String actionStatus(Object payload, String targetCode) {
        Map<String, Object> payloadMap = map(payload);
        if (payloadMap.containsKey(FIELD_ACTIONS) || payloadMap.containsKey(FIELD_ACTION)
                || payloadMap.containsKey(FIELD_ACTION_CODE)) {
            return STATUS_PARTIAL;
        }
        if (StringUtils.isNotBlank(targetCode)) {
            return STATUS_SKIPPED;
        }
        return STATUS_SKIPPED;
    }

    private String entityContextStatus(String protocolType) {
        if (StringUtils.equals(protocolType, PROTOCOL_TEXT)) {
            return STATUS_SKIPPED;
        }
        return STATUS_PARTIAL;
    }

    private List<Map<String, Object>> checklist(RuntimeDecision decision, String targetCode) {
        List<Map<String, Object>> items = new ArrayList<>();
        items.add(check("protocol", "协议可识别",
                StringUtils.equals(decision.protocolType, PROTOCOL_UNKNOWN) ? STATUS_FAILED : STATUS_PASSED,
                decision.protocolType));
        items.add(check("registry", "组件已注册", decision.registryStatus,
                StringUtils.defaultIfBlank(targetCode, "文本输出无需组件注册")));
        items.add(check("schema", "schema 通过", decision.schemaStatus, decision.schemaStatus));
        items.add(check("runtime", "runtime 转换", decision.runtimeStatus, decision.route));
        items.add(check("frontend", "前端渲染", decision.frontendStatus, "PC / APP sandbox preview"));
        items.add(check("action", "action 通过", decision.actionStatus, "actionCode 白名单和参数 schema"));
        items.add(check("entityContext", "EntityContext 通过", decision.entityContextStatus,
                "context 摘要静态校验"));
        return items;
    }

    private Map<String, Object> preview(Object parsedPayload, String protocolType, String route) {
        Map<String, Object> surface = new LinkedHashMap<>();
        surface.put(FIELD_PROTOCOL_TYPE, protocolType);
        surface.put(FIELD_ROUTE, route);
        surface.put(FIELD_PAYLOAD, parsedPayload);
        Map<String, Object> preview = new LinkedHashMap<>();
        preview.put(FIELD_PC, surface);
        preview.put(FIELD_APP, surface);
        return preview;
    }

    private String repairPrompt(RuntimeDecision decision) {
        if (decision.errors.isEmpty() && decision.warnings.isEmpty()) {
            return EMPTY;
        }
        return REPAIR_PROMPT_PREFIX + "\n协议类型：" + decision.protocolType
                + "\n路由：" + decision.route
                + "\n错误：" + String.join(COMMA, decision.errors)
                + "\n风险：" + String.join(COMMA, decision.warnings);
    }

    private String overallStatus(RuntimeDecision decision) {
        if (!decision.errors.isEmpty()) {
            return STATUS_FAILED;
        }
        if (containsPartial(decision)) {
            return STATUS_PARTIAL;
        }
        return STATUS_PASSED;
    }

    private boolean containsPartial(RuntimeDecision decision) {
        return StringUtils.equals(decision.runtimeStatus, STATUS_PARTIAL)
                || StringUtils.equals(decision.frontendStatus, STATUS_PARTIAL)
                || StringUtils.equals(decision.actionStatus, STATUS_PARTIAL)
                || StringUtils.equals(decision.entityContextStatus, STATUS_PARTIAL);
    }

    private Map<String, Object> check(String key, String label, String status, String message) {
        Map<String, Object> item = new LinkedHashMap<>();
        item.put(FIELD_KEY, key);
        item.put(FIELD_LABEL, label);
        item.put(FIELD_STATUS, status);
        item.put(FIELD_MESSAGE, message);
        return item;
    }

    private List<Map<String, Object>> parseAssetList(String value) {
        if (StringUtils.isBlank(value)) {
            return Collections.emptyList();
        }
        try {
            com.alibaba.fastjson2.JSONArray array = com.alibaba.fastjson2.JSON.parseArray(value);
            return array.stream()
                    .filter(item -> item instanceof Map)
                    .map(item -> normalizeAsset((Map<?, ?>) item))
                    .collect(Collectors.toList());
        } catch (Exception e) {
            log.warn("SkillFactory解析参考渲染资产失败, error={}", e.getMessage());
            return Collections.emptyList();
        }
    }

    private Map<String, Object> capabilityReference(CapabilityActionDraft capability) {
        Map<String, Object> canonicalDraft = capability.getDraft() == null
                ? Collections.emptyMap() : capability.getDraft();
        Map<String, Object> basicInfo = map(canonicalDraft.get(FIELD_BASIC_INFO));
        Map<String, Object> governance = map(canonicalDraft.get(FIELD_GOVERNANCE));
        List<?> supportedClients = list(canonicalDraft.get(FIELD_SUPPORTED_CLIENTS));
        Map<String, Object> clientVariants = map(canonicalDraft.get(FIELD_CLIENT_VARIANTS));
        Map<String, Object> reference = new LinkedHashMap<>();
        reference.put(FIELD_DRAFT_ID, capability.getDraftId());
        reference.put(FIELD_REVISION, capability.getRevision());
        reference.put(FIELD_PUBLISHED, capability.getPublished());
        reference.put(FIELD_PUBLISHED_VERSION, capability.getPublishedVersion());
        reference.put(FIELD_VERSION, capability.getPublishedVersion());
        reference.put(FIELD_STATUS, capability.getStatus());
        reference.put(FIELD_VALIDATION_STATUS, capability.getValidationStatus());
        reference.put(FIELD_ACTION_CODE, string(basicInfo.get(FIELD_ACTION_CODE)));
        reference.put(FIELD_NAME_CN, string(basicInfo.get(FIELD_NAME_CN)));
        reference.put(FIELD_DESCRIPTION, string(basicInfo.get(FIELD_DESCRIPTION)));
        reference.put(FIELD_BUSINESS_DOMAIN, string(basicInfo.get(FIELD_BUSINESS_DOMAIN)));
        reference.put(FIELD_SOURCE_TYPE, projectedSourceType(supportedClients, clientVariants));
        reference.put(FIELD_SIDE_EFFECT_LEVEL, string(governance.get(FIELD_SIDE_EFFECT_LEVEL)));
        reference.put(FIELD_APPROVAL_POLICY, string(governance.get(FIELD_APPROVAL_POLICY)));
        reference.put(FIELD_SUPPORTED_CLIENTS, supportedClients);
        reference.put(FIELD_CLIENT_VARIANTS, clientVariants);
        reference.put(FIELD_GOVERNANCE, governance);
        return reference;
    }

    private String projectedSourceType(List<?> supportedClients, Map<String, Object> clientVariants) {
        List<String> sourceTypes = supportedClients.stream()
                .map(this::string)
                .map(client -> map(map(clientVariants.get(client)).get(FIELD_API_SOURCE)))
                .map(apiSource -> string(apiSource.get(FIELD_SOURCE_TYPE)))
                .filter(StringUtils::isNotBlank)
                .distinct()
                .toList();
        return sourceTypes.size() == 1 ? sourceTypes.get(0)
                : sourceTypes.isEmpty() ? StringUtils.EMPTY : SOURCE_TYPE_MIXED;
    }

    /**
     * 根据稳定草稿身份读取业务能力事实，并生成受控绑定快照。
     *
     * <p>请求中的 revision 来自候选或历史关系快照，仅是展示信息，不能作为绑定写入门禁。
     * 能力草稿更新后，旧绑定仍需能够随完整集合一同保存；可用性由共享环境解析器校验，
     * 返回快照的 revision 始终取服务端当前草稿，不信任客户端上传的契约正文。
     */
    private Map<String, Object> resolveCapabilityBinding(Map<String, Object> request) {
        String draftId = requiredValue(request, FIELD_DRAFT_ID);
        String bindMode = string(request.get(FIELD_BIND_MODE));
        if (!CAPABILITY_BIND_MODES.contains(bindMode)) {
            throw new IllegalArgumentException(ERROR_CAPABILITY_BIND_MODE_INVALID);
        }
        skillBindingCandidateService.requireEffectivePreprod(
                AssetDependencyType.CAPABILITY_ACTION, draftId);
        CapabilityActionDraft capability = capabilityActionDraftService.detail(draftId);
        Map<String, Object> reference = capabilityReference(capability);
        String capabilityCode = string(reference.get(FIELD_ACTION_CODE));
        if (StringUtils.isBlank(capabilityCode)) {
            throw new IllegalArgumentException(ERROR_CAPABILITY_CODE_REQUIRED);
        }
        reference.put(FIELD_CAPABILITY_CODE, capabilityCode);
        reference.put(FIELD_BIND_MODE, bindMode);
        if (BIND_MODE_EXECUTION_AND_RENDER.equals(bindMode)) {
            validateCapabilityPresentationComponents(reference, draftId);
        }
        log.info("SkillFactory业务能力稳定绑定解析完成, draftId:{}, currentRevision:{}, bindMode:{}",
                draftId, capability.getRevision(), bindMode);
        return reference;
    }

    /**
     * 校验“执行并渲染”模式引用的能力组件。
     *
     * <p>能力组件仍保留在能力的 resultContract 中，不复制到 Skill 直接组件绑定。该门禁只读取
     * 组件中心事实，确保绑定时组件存在、启用且版本一致；`EXECUTION_ONLY` 不进入此校验。
     */
    private void validateCapabilityPresentationComponents(Map<String, Object> capabilityReference,
            String draftId) {
        List<?> supportedClients = list(capabilityReference.get(FIELD_SUPPORTED_CLIENTS));
        Map<String, Object> clientVariants = map(capabilityReference.get(FIELD_CLIENT_VARIANTS));
        for (Object clientValue : supportedClients) {
            String client = string(clientValue);
            Map<String, Object> resultContract = map(map(clientVariants.get(client)).get(FIELD_RESULT_CONTRACT));
            validateCapabilityPresentationComponents(resultContract, draftId, client);
        }
    }

    private void validateCapabilityPresentationComponents(Map<String, Object> resultContract,
            String draftId, String client) {
        Object componentsValue = resultContract.get(FIELD_PRESENTATION_COMPONENTS);
        if (!(componentsValue instanceof List) || ((List<?>) componentsValue).isEmpty()) {
            log.warn("SkillFactory业务能力渲染绑定被拒绝，端契约未提供包装组件, draftId:{}, client:{}",
                    draftId, client);
            throw new IllegalArgumentException(ERROR_CAPABILITY_PRESENTATION_REQUIRED);
        }
        for (Object item : (List<?>) componentsValue) {
            Map<String, Object> componentReference = map(item);
            long assetId = requiredLong(componentReference, FIELD_ASSET_ID);
            SkillFactoryComponentAsset asset = componentRegistryService.detail(String.valueOf(assetId));
            ResolvedReleasedAsset resolved = skillBindingCandidateService.requireEffectivePreprod(asset);
            if (!Boolean.TRUE.equals(asset.getEnabled())) {
                log.warn("SkillFactory业务能力渲染绑定被拒绝，组件不可用, draftId:{}, assetId:{}, "
                                + "componentName:{}",
                        draftId, assetId, asset.getComponentName());
                throw new IllegalArgumentException(ERROR_COMPONENT_DISABLED);
            }
            String expectedComponentName = string(componentReference.get(FIELD_COMPONENT_NAME));
            if (StringUtils.isBlank(expectedComponentName)
                    || !StringUtils.equals(expectedComponentName, asset.getComponentName())) {
                log.warn("SkillFactory业务能力渲染绑定被拒绝，组件身份不一致, draftId:{}, assetId:{}, "
                                + "expectedComponentName:{}, currentComponentName:{}",
                        draftId, assetId, expectedComponentName, asset.getComponentName());
                throw new IllegalStateException(ERROR_CAPABILITY_PRESENTATION_IDENTITY_CONFLICT);
            }
            String expectedVersion = string(componentReference.get(FIELD_COMPONENT_VERSION));
            String publishedVersion = resolved.getVersion() == null
                    ? StringUtils.EMPTY : String.valueOf(resolved.getVersion());
            if (StringUtils.isBlank(expectedVersion)
                    || !StringUtils.equals(expectedVersion, publishedVersion)) {
                log.warn("SkillFactory业务能力渲染绑定被拒绝，组件版本不一致, draftId:{}, assetId:{}, "
                                + "expectedVersion:{}, currentVersion:{}",
                        draftId, assetId, expectedVersion, publishedVersion);
                throw new IllegalStateException(ERROR_CAPABILITY_PRESENTATION_VERSION_CONFLICT);
            }
        }
        log.info("SkillFactory业务能力渲染绑定组件校验通过, draftId:{}, componentCount:{}",
                draftId, ((List<?>) componentsValue).size());
    }

    /** 根据组件资产 ID 读取已启用资产，并生成直接组件绑定快照。 */
    private Map<String, Object> resolveComponentBinding(Map<String, Object> request) {
        long assetId = requiredLong(request, FIELD_ASSET_ID);
        SkillFactoryComponentAsset asset = componentRegistryService.detail(String.valueOf(assetId));
        skillBindingCandidateService.requireEffectivePreprod(asset);
        if (!Boolean.TRUE.equals(asset.getEnabled())) {
            log.warn("SkillFactory直接组件绑定被拒绝，组件不可用, assetId:{}, componentName:{}, enabled:{}",
                    assetId, asset.getComponentName(), asset.getEnabled());
            throw new IllegalArgumentException(ERROR_COMPONENT_DISABLED);
        }
        String componentCode = componentCode(asset);
        if (StringUtils.isBlank(componentCode)) {
            throw new IllegalArgumentException(ERROR_COMPONENT_CODE_REQUIRED);
        }
        String requestedCode = string(request.get(FIELD_COMPONENT_CODE));
        if (StringUtils.isNotBlank(requestedCode) && !StringUtils.equals(requestedCode, componentCode)) {
            log.warn("SkillFactory直接组件绑定身份冲突, assetId:{}, requestedCode:{}, currentCode:{}",
                    assetId, requestedCode, componentCode);
            throw new IllegalArgumentException(ERROR_COMPONENT_IDENTITY_CONFLICT);
        }
        Map<String, Object> reference = new LinkedHashMap<>();
        reference.put(FIELD_ASSET_ID, asset.getId());
        reference.put(FIELD_COMPONENT_CODE, componentCode);
        reference.put(FIELD_CODE, componentCode);
        reference.put(FIELD_NAME, StringUtils.defaultIfBlank(asset.getComponentNameCn(), asset.getComponentName()));
        reference.put(FIELD_ASSET_TYPE, asset.getAssetType());
        reference.put(FIELD_COMPONENT_NAME, asset.getComponentName());
        reference.put(FIELD_COMPONENT_NAME_CN, asset.getComponentNameCn());
        reference.put(FIELD_DSL_CODE, asset.getAgentUiDsl());
        reference.put(FIELD_AGENT_UI_DSL, asset.getAgentUiDsl());
        reference.put(FIELD_DSL_TYPE, asset.getDslType());
        reference.put(FIELD_RENDER_PROTOCOL_ASSET, asset.getDslType());
        reference.put(FIELD_COMPONENT_VERSION, asset.getPublishedVersion());
        reference.put(FIELD_PROTOCOL_VERSION, asset.getProtocolVersion());
        reference.put(FIELD_INTERACTION_MODE, asset.getInteractionMode());
        reference.put(FIELD_SCENE, asset.getScene());
        reference.put(FIELD_OWNER, asset.getOwner());
        reference.put(FIELD_ENABLED, asset.getEnabled());
        reference.put(FIELD_PUBLISHED, asset.getPublished());
        reference.put(FIELD_PUBLISHED_VERSION, asset.getPublishedVersion());
        reference.put(FIELD_VERSION, asset.getPublishedVersion());
        reference.put(FIELD_INTEGRATION_PROMPT, asset.getIntegrationPrompt());
        reference.put(FIELD_SCHEMA_JSON, asset.getParamsSchemaJson());
        reference.put(FIELD_OFFICIAL_DEMO_JSON, asset.getOfficialDemoJson());
        return reference;
    }

    /** 按资产协议类型提取稳定组件编码。 */
    private String componentCode(SkillFactoryComponentAsset asset) {
        return firstNonBlank(asset.getAgentUiDsl(), asset.getComponentName());
    }

    /** 把受控能力快照转换为 Skill 当前版本的能力关系。 */
    private List<EntityRelationDO> capabilityRelations(List<Map<String, Object>> bindings) {
        return bindings.stream()
                .map(binding -> new EntityRelationDO()
                        .setRelationType(
                                SkillFactoryEntityRelationConstants.RELATION_TYPE_SKILL_USES_CAPABILITY)
                        .setTargetEntityType(
                                SkillFactoryEntityRelationConstants.ENTITY_TYPE_CAPABILITY_ACTION)
                        .setTargetEntityId(string(binding.get(FIELD_DRAFT_ID)))
                        .setTargetEntityCode(string(binding.get(FIELD_CAPABILITY_CODE)))
                        .setTargetVersion(string(binding.get(FIELD_PUBLISHED_VERSION)))
                        .setRelationMode(string(binding.get(FIELD_BIND_MODE)))
                        .setSnapshotJson(JsonSupport.toJSON(binding)))
                .collect(Collectors.toList());
    }

    /** 把受控组件快照转换为 Skill 当前版本的直接组件关系。 */
    private List<EntityRelationDO> componentRelations(List<Map<String, Object>> bindings) {
        return bindings.stream()
                .map(binding -> new EntityRelationDO()
                        .setRelationType(
                                SkillFactoryEntityRelationConstants.RELATION_TYPE_SKILL_USES_COMPONENT)
                        .setTargetEntityType(
                                SkillFactoryEntityRelationConstants.ENTITY_TYPE_COMPONENT_ASSET)
                        .setTargetEntityId(string(binding.get(FIELD_ASSET_ID)))
                        .setTargetEntityCode(string(binding.get(FIELD_COMPONENT_CODE)))
                        .setTargetVersion(string(binding.get(FIELD_PUBLISHED_VERSION)))
                        .setRelationMode(SkillFactoryEntityRelationConstants.RELATION_MODE_DIRECT)
                        .setSnapshotJson(JsonSupport.toJSON(binding)))
                .collect(Collectors.toList());
    }

    /** 读取关系表使用的稳定 Skill 草稿主键。 */
    private String sourceEntityId(SkillDraft draft) {
        if (draft == null || draft.getId() == null || draft.getId() <= 0L) {
            throw new IllegalStateException(ERROR_WORKSPACE_NOT_FOUND);
        }
        return String.valueOf(draft.getId());
    }

    /** 读取当前 Skill 数字版本，拒绝无效草稿版本。 */
    private int currentSkillVersion(SkillDraft draft) {
        if (draft == null || draft.getVersion() == null || draft.getVersion() <= 0) {
            throw new IllegalStateException(ERROR_SKILL_VERSION_CONFLICT);
        }
        return draft.getVersion();
    }

    /** 解析页面提交的完整绑定对象数组，拒绝非对象元素。 */
    private List<Map<String, Object>> parseBindingList(String value, String paramName) {
        if (StringUtils.isBlank(value)) {
            return Collections.emptyList();
        }
        try {
            com.alibaba.fastjson2.JSONArray array = com.alibaba.fastjson2.JSON.parseArray(value);
            List<Map<String, Object>> bindings = new ArrayList<>();
            for (Object item : array) {
                if (!(item instanceof Map)) {
                    throw new IllegalArgumentException(paramName + ERROR_BINDINGS_FORMAT_SUFFIX);
                }
                bindings.add(map(item));
            }
            return bindings;
        } catch (IllegalArgumentException e) {
            throw e;
        } catch (Exception e) {
            log.warn("SkillFactory解析完整绑定数组失败, paramName:{}, error:{}", paramName, e.getMessage());
            throw new IllegalArgumentException(paramName + ERROR_BINDINGS_FORMAT_SUFFIX);
        }
    }

    /** 校验完整目标数组中不存在重复绑定编码。 */
    private void ensureUniqueBindingCodes(List<Map<String, Object>> bindings, String field, String paramName) {
        long uniqueCount = bindings.stream()
                .map(item -> string(item.get(field)))
                .distinct()
                .count();
        if (uniqueCount != bindings.size()) {
            throw new IllegalArgumentException(paramName + ERROR_DUPLICATE_BINDING_CODE_SUFFIX);
        }
    }

    /** 读取对象参数中的必填字符串。 */
    private String requiredValue(Map<String, Object> values, String key) {
        String value = string(values == null ? null : values.get(key));
        if (StringUtils.isBlank(value)) {
            throw new IllegalArgumentException(key + ERROR_REQUIRED_SUFFIX);
        }
        return value;
    }

    /** 读取 M 端字符串参数中的必填整数。 */
    private int requiredIntegerParam(Map<String, String> values, String key) {
        String value = required(values, key);
        try {
            return Integer.parseInt(value);
        } catch (NumberFormatException e) {
            throw new IllegalArgumentException(key + ERROR_INVALID_SUFFIX);
        }
    }

    /** 读取绑定对象中的正数 ID。 */
    private long requiredLong(Map<String, Object> values, String key) {
        String value = requiredValue(values, key);
        try {
            long parsed = Long.parseLong(value);
            if (parsed <= 0L) {
                throw new NumberFormatException(value);
            }
            return parsed;
        } catch (NumberFormatException e) {
            throw new IllegalArgumentException(ERROR_COMPONENT_ID_INVALID);
        }
    }

    private Map<String, Object> normalizeAsset(Map<?, ?> source) {
        Map<String, Object> asset = new LinkedHashMap<>();
        put(asset, FIELD_CODE, source.get(FIELD_CODE));
        put(asset, FIELD_NAME, source.get(FIELD_NAME));
        put(asset, FIELD_ASSET_TYPE, source.get(FIELD_ASSET_TYPE));
        put(asset, FIELD_RENDER_PROTOCOL_ASSET, source.get(FIELD_RENDER_PROTOCOL_ASSET));
        put(asset, FIELD_COMPONENT_NAME, source.get(FIELD_COMPONENT_NAME));
        put(asset, FIELD_DSL_CODE, source.get(FIELD_DSL_CODE));
        put(asset, FIELD_LOCAL_METHOD, source.get(FIELD_LOCAL_METHOD));
        put(asset, FIELD_SCENE, source.get(FIELD_SCENE));
        put(asset, FIELD_OWNER, source.get(FIELD_OWNER));
        put(asset, FIELD_LIFECYCLE_STATUS, source.get(FIELD_LIFECYCLE_STATUS));
        put(asset, FIELD_ENABLED, source.get(FIELD_ENABLED));
        put(asset, FIELD_PROTOCOL_VERSION, source.get(FIELD_PROTOCOL_VERSION));
        put(asset, FIELD_RENDERER_VERSION, source.get(FIELD_RENDERER_VERSION));
        put(asset, FIELD_OFFICIAL_DEMO_JSON, source.get(FIELD_OFFICIAL_DEMO_JSON));
        put(asset, FIELD_SCHEMA_JSON, source.get(FIELD_SCHEMA_JSON));
        put(asset, FIELD_INTEGRATION_PROMPT, source.get(FIELD_INTEGRATION_PROMPT));
        put(asset, FIELD_ALLOWED_ACTIONS_JSON, source.get(FIELD_ALLOWED_ACTIONS_JSON));
        put(asset, FIELD_ATOM_COMPONENTS_JSON, source.get(FIELD_ATOM_COMPONENTS_JSON));
        return asset;
    }

    private Object parsePayload(Object payload) {
        if (!(payload instanceof String)) {
            return payload;
        }
        String text = StringUtils.trimToEmpty((String) payload);
        if (StringUtils.isBlank(text)) {
            return EMPTY;
        }
        try {
            return com.alibaba.fastjson2.JSON.parse(text);
        } catch (Exception e) {
            return text;
        }
    }

    private Map<String, Object> map(Object value) {
        if (value instanceof Map) {
            Map<?, ?> source = (Map<?, ?>) value;
            Map<String, Object> result = new LinkedHashMap<>();
            source.forEach((key, item) -> result.put(String.valueOf(key), item));
            return result;
        }
        return Collections.emptyMap();
    }

    private List<?> list(Object value) {
        return value instanceof List ? (List<?>) value : Collections.emptyList();
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> castMapList(Object value) {
        if (!(value instanceof List)) {
            return Collections.emptyList();
        }
        return ((List<?>) value).stream()
                .filter(item -> item instanceof Map)
                .map(item -> (Map<String, Object>) item)
                .collect(Collectors.toList());
    }

    private String required(Map<String, String> params, String key) {
        String value = string(params == null ? null : params.get(key));
        if (StringUtils.isBlank(value)) {
            throw new IllegalArgumentException(key + ERROR_REQUIRED_SUFFIX);
        }
        return value;
    }

    private String firstNonBlank(Object... values) {
        for (Object value : values) {
            String text = string(value);
            if (StringUtils.isNotBlank(text)) {
                return text;
            }
        }
        return EMPTY;
    }

    private String string(Object value) {
        return value == null ? EMPTY : String.valueOf(value);
    }

    private String string(Object value, String defaultValue) {
        return StringUtils.defaultIfBlank(string(value), defaultValue);
    }

    private void put(Map<String, Object> target, String key, Object value) {
        if (value != null && StringUtils.isNotBlank(String.valueOf(value))) {
            target.put(key, value);
        }
    }

    private static class RuntimeDecision {
        private Object parsedPayload = Collections.emptyMap();
        private String protocolType = PROTOCOL_UNKNOWN;
        private String route = EMPTY;
        private String registryStatus = STATUS_SKIPPED;
        private String schemaStatus = STATUS_SKIPPED;
        private String runtimeStatus = STATUS_SKIPPED;
        private String frontendStatus = STATUS_SKIPPED;
        private String actionStatus = STATUS_SKIPPED;
        private String entityContextStatus = STATUS_SKIPPED;
        private final List<String> errors = new ArrayList<>();
        private final List<String> warnings = new ArrayList<>();
        private List<Map<String, Object>> checklist = Collections.emptyList();
    }
}
