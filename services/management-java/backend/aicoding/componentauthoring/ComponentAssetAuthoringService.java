package dev.a2flow.management.aicoding.componentauthoring;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

import jakarta.annotation.Resource;

import org.apache.commons.collections4.CollectionUtils;
import org.apache.commons.collections4.MapUtils;
import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.lifecycle.SkillFactoryComponentRegistryService;
import dev.a2flow.management.model.SkillFactoryComponentAsset;
import dev.a2flow.management.model.SkillFactoryRenderPreviewResult;

import lombok.extern.slf4j.Slf4j;

/**
 * 组件中心 AI 创建草稿服务。
 *
 * <p>该服务复用 AI Coding chat 流式协议，为组件中心生成配置化资产草稿、字段校验、预览请求和
 * 保存参数。它不上传 Java/Groovy/JavaScript 代码，不直接写注册表，也不修改 Skill workspace
 * 或 adviser runtime；最终 register/update 仍由 M 端确认后调用组件中心原有 method。
 */
@Slf4j
@Service
public class ComponentAssetAuthoringService {

    private static final String FIELD_SCHEMA_VERSION = "schemaVersion";
    private static final String FIELD_PAYLOAD_TYPE = "payloadType";
    private static final String FIELD_AUTHORING_DOMAIN = "authoringDomain";
    private static final String FIELD_DRAFT_ID = "draftId";
    private static final String FIELD_ASSET_ID = "assetId";
    private static final String FIELD_ASSET_TYPE = "assetType";
    private static final String FIELD_MESSAGE = "message";
    private static final String FIELD_CURRENT_DRAFT = "currentDraft";
    private static final String FIELD_DRAFT = "draft";
    private static final String FIELD_MODE = "mode";
    private static final String FIELD_METHOD = "method";
    private static final String FIELD_PARAMS = "params";
    private static final String FIELD_VALID = "valid";
    private static final String FIELD_ENABLEABLE = "enableable";
    private static final String FIELD_SAVE_ALLOWED = "saveAllowed";
    private static final String FIELD_REQUIRES_HUMAN_APPROVAL = "requiresHumanApproval";
    private static final String FIELD_BLOCKING_ERRORS = "blockingErrors";
    private static final String FIELD_WARNINGS = "warnings";
    private static final String FIELD_MISSING_FIELDS = "missingFields";
    private static final String FIELD_FIELD_RESULTS = "fieldResults";
    private static final String FIELD_RISKS = "risks";
    private static final String FIELD_NEXT_QUESTIONS = "nextQuestions";
    private static final String FIELD_RENDER_PREVIEW_REQUEST = "renderPreviewRequest";
    private static final String FIELD_RENDER_PREVIEW_RESULT = "renderPreviewResult";
    private static final String FIELD_ERRORS = "errors";
    private static final String FIELD_TRACE_ID = "traceId";
    private static final String FIELD_ID = "id";
    private static final String FIELD_COMPONENT_NAME = "componentName";
    private static final String FIELD_COMPONENT_NAME_CN = "componentNameCn";
    private static final String FIELD_DSL_TYPE = "dslType";
    private static final String FIELD_AGENT_UI_DSL = "agentUiDsl";
    private static final String FIELD_PROTOCOL_VERSION = "protocolVersion";
    private static final String FIELD_BUNDLE_URL = "bundleUrl";
    private static final String FIELD_APP_BUNDLE_URL = "appBundleUrl";
    private static final String FIELD_OWNER = "owner";
    private static final String FIELD_SCENE = "scene";
    private static final String FIELD_PARAMS_SCHEMA_JSON = "paramsSchemaJson";
    private static final String FIELD_RENDER_TEMPLATE_JSON = "renderTemplateJson";
    private static final String FIELD_OFFICIAL_DEMO_JSON = "officialDemoJson";
    private static final String FIELD_MESSAGE_DEMO_JSON = "messageDemoJson";
    private static final String FIELD_INTEGRATION_PROMPT = "integrationPrompt";
    private static final String FIELD_ALLOWED_ACTIONS_JSON = "allowedActionsJson";
    private static final String FIELD_RUNTIME_CONFIG_JSON = "runtimeConfigJson";
    private static final String FIELD_SUPPORT_CLIENTS = "supportClients";
    private static final String FIELD_ENABLED = "enabled";
    private static final String FIELD_INPUT_MODE = "inputMode";
    private static final String FIELD_RENDER_TEXT = "renderText";
    private static final String FIELD_SOURCE = "source";
    private static final String FIELD_CLIENT_TYPE = "clientType";
    private static final String FIELD_KEYWORD = "keyword";
    private static final String FIELD_SUMMARY = "summary";
    private static final String FIELD_ITEMS = "items";
    private static final String FIELD_DATA = "data";
    private static final String FIELD_TYPE = "type";
    private static final String FIELD_CARD_TYPE = "cardType";
    private static final String FIELD_TITLE = "title";
    private static final String FIELD_DESCRIPTION = "description";
    private static final String FIELD_REQUIRED = "required";
    private static final String FIELD_PROPERTIES = "properties";

    private static final String AUTHORING_DOMAIN_COMPONENT_CENTER = "COMPONENT_CENTER";
    private static final String SCHEMA_DRAFT = "skillFactory.authoring.componentAssetDraft.v1";
    private static final String SCHEMA_VALIDATION = "skillFactory.authoring.componentAssetValidation.v1";
    private static final String SCHEMA_PREVIEW = "skillFactory.authoring.componentAssetPreview.v1";
    private static final String SCHEMA_SAVE_PREPARE = "skillFactory.authoring.componentAssetSavePrepare.v1";
    private static final String PAYLOAD_COMPONENT_ASSET_DRAFT = "COMPONENT_ASSET_DRAFT";
    private static final String PAYLOAD_COMPONENT_ASSET_VALIDATION_RESULT =
            "COMPONENT_ASSET_VALIDATION_RESULT";
    private static final String PAYLOAD_COMPONENT_ASSET_PREVIEW_RESULT = "COMPONENT_ASSET_PREVIEW_RESULT";
    private static final String PAYLOAD_COMPONENT_ASSET_SAVE_PREPARE = "COMPONENT_ASSET_SAVE_PREPARE";

    private static final String ASSET_TYPE_CARD_COMPONENT = "CARD_COMPONENT";
    private static final String ASSET_TYPE_BUSINESS_DSL = "BUSINESS_DSL";
    private static final String ASSET_TYPE_A2UI_ATOM = "A2UI_ATOM";
    private static final String DSL_TYPE_CARD_CONTAINER = "CARD_CONTAINER";
    private static final String DSL_TYPE_BUSINESS_DSL = "BUSINESS_DSL";
    private static final String INPUT_MODE_BUSINESS_DSL = "BUSINESS_DSL";
    private static final String INPUT_MODE_CARD_CONTAINER = "CARD_CONTAINER";
    private static final String SUPPORT_CLIENT_PC = "PC";
    private static final int DEFAULT_PROTOCOL_VERSION = 1;
    private static final String SOURCE_AUTHORING = "component-center-ai-authoring";
    private static final String METHOD_COMPONENT_REGISTER = "COMPONENT_REGISTER";
    private static final String METHOD_COMPONENT_UPDATE = "COMPONENT_UPDATE";
    private static final String MODE_CREATE = "CREATE";
    private static final String MODE_UPDATE = "UPDATE";
    private static final String JSON_OBJECT = "object";
    private static final String JSON_ARRAY = "array";

    private static final Set<String> ASSET_TYPES = Set.of(
            ASSET_TYPE_CARD_COMPONENT, ASSET_TYPE_BUSINESS_DSL, ASSET_TYPE_A2UI_ATOM);
    private static final Set<String> EXECUTABLE_CODE_KEYS = Set.of(
            "javacode", "groovycode", "javascriptcode", "jscode", "sourcecode", "runtimecode",
            "executablecode", "codefilebase64", "frontendcode", "backendcode", "script",
            "scriptbody", "scriptcontent", "scripttext");
    private static final List<String> COMMON_REQUIRED_FIELDS = List.of(
            FIELD_ASSET_TYPE, FIELD_COMPONENT_NAME, FIELD_PROTOCOL_VERSION);
    private static final List<String> BUSINESS_DSL_REQUIRED_FIELDS = List.of(
            FIELD_AGENT_UI_DSL, FIELD_PARAMS_SCHEMA_JSON, FIELD_RENDER_TEMPLATE_JSON);
    private static final List<String> CARD_COMPONENT_REQUIRED_FIELDS = List.of(
            FIELD_BUNDLE_URL, FIELD_APP_BUNDLE_URL, FIELD_PARAMS_SCHEMA_JSON, FIELD_RENDER_TEMPLATE_JSON);
    private static final List<String> A2UI_ATOM_REQUIRED_FIELDS = Collections.emptyList();

    @Resource
    private SkillFactoryComponentRegistryService componentRegistryService;

    /**
     * 返回组件中心 AI 创建时前端可展示的协议和字段参考。
     */
    public Map<String, Object> schemaReference(Map<String, String> params) {
        String assetType = normalizeAssetType(params.get(FIELD_ASSET_TYPE));
        Map<String, Object> payload = basePayload(SCHEMA_DRAFT, "COMPONENT_ASSET_SCHEMA_REFERENCE",
                draftId(params), assetType);
        payload.put("commonRequiredFields", COMMON_REQUIRED_FIELDS);
        payload.put("businessDslRequiredFields", BUSINESS_DSL_REQUIRED_FIELDS);
        payload.put("cardComponentRequiredFields", CARD_COMPONENT_REQUIRED_FIELDS);
        payload.put("a2uiAtomRequiredFields", A2UI_ATOM_REQUIRED_FIELDS);
        payload.put("designBoundary", List.of(
                "AI chat 只生成配置化资产草稿，不直接保存注册表",
                "页面不能上传 Java/Groovy/JavaScript 可执行代码",
                "BUSINESS_DSL 只指导模型输出 dslType=BUSINESS_DSL + agentUiDsl + params，不要求模型手写完整 A2UI",
                "保存前必须由 M 端用户点击确认"));
        payload.put("fieldHelp", buildFieldHelp(assetType));
        log.info("组件中心AI创建返回字段参考, assetType:{}, draftId:{}", assetType, draftId(params));
        return payload;
    }

    /**
     * 查询当前组件资产摘要，供 AI 创建时避开重名和理解已有协议。
     */
    public Map<String, Object> existingAssets(Map<String, String> params) {
        String assetType = normalizeAssetType(params.get(FIELD_ASSET_TYPE));
        Map<String, String> query = new LinkedHashMap<>();
        query.put(FIELD_ASSET_TYPE, assetType);
        query.put(FIELD_KEYWORD, StringUtils.defaultString(params.get(FIELD_KEYWORD)));
        List<Map<String, Object>> items = new ArrayList<>();
        for (SkillFactoryComponentAsset asset : componentRegistryService.list(query)) {
            items.add(assetDigest(asset));
            if (items.size() >= 20) {
                break;
            }
        }
        Map<String, Object> payload = basePayload(SCHEMA_DRAFT, "COMPONENT_ASSET_EXISTING_ASSETS",
                draftId(params), assetType);
        payload.put(FIELD_ITEMS, items);
        payload.put(FIELD_SUMMARY, "已读取组件中心现有资产 " + items.size() + " 个。");
        log.info("组件中心AI创建读取已有资产完成, assetType:{}, count:{}, draftId:{}",
                assetType, items.size(), draftId(params));
        return payload;
    }

    /**
     * 根据用户输入和当前草稿生成下一版组件资产草稿。
     */
    public Map<String, Object> buildDraft(Map<String, String> params) {
        String assetType = normalizeAssetType(params.get(FIELD_ASSET_TYPE));
        Map<String, Object> draft = currentDraft(params);
        assetType = normalizeAssetType(StringUtils.defaultIfBlank(stringValue(draft.get(FIELD_ASSET_TYPE)),
                assetType));
        String assetId = firstNotBlank(params.get(FIELD_ASSET_ID), params.get(FIELD_ID),
                stringValue(draft.get(FIELD_ID)));
        putIfNotBlank(draft, FIELD_ID, assetId);
        draft.put(FIELD_ASSET_TYPE, assetType);
        if (StringUtils.equals(assetType, ASSET_TYPE_BUSINESS_DSL)) {
            fillBusinessDslDraft(params, draft);
        } else if (StringUtils.equals(assetType, ASSET_TYPE_A2UI_ATOM)) {
            fillA2uiAtomDraft(params, draft);
        } else {
            fillCardComponentDraft(params, draft);
        }
        normalizeCommonDraft(draft);
        ValidationOutcome outcome = validate(draft);

        Map<String, Object> payload = basePayload(SCHEMA_DRAFT, PAYLOAD_COMPONENT_ASSET_DRAFT,
                draftId(params), assetType);
        payload.put(FIELD_MODE, StringUtils.isBlank(assetId) ? MODE_CREATE : MODE_UPDATE);
        payload.put(FIELD_DRAFT, draft);
        payload.put(FIELD_MISSING_FIELDS, outcome.missingFields);
        payload.put(FIELD_BLOCKING_ERRORS, outcome.blockingErrors);
        payload.put(FIELD_WARNINGS, outcome.warnings);
        payload.put(FIELD_RISKS, buildRisks(draft, outcome));
        payload.put(FIELD_NEXT_QUESTIONS, buildNextQuestions(draft, outcome));
        log.info("组件中心AI创建草稿完成, assetType:{}, mode:{}, valid:{}, missingCount:{}, draftId:{}",
                assetType, payload.get(FIELD_MODE), outcome.valid, outcome.missingFields.size(), draftId(params));
        return payload;
    }

    /**
     * 校验 AI 草稿能否进入组件中心保存链路。
     */
    public Map<String, Object> validateDraft(Map<String, String> params, Map<String, Object> draftPayload) {
        Map<String, Object> draft = extractDraft(draftPayload);
        String assetType = normalizeAssetType(stringValue(draft.get(FIELD_ASSET_TYPE)));
        ValidationOutcome outcome = validate(draft);
        Map<String, Object> payload = basePayload(SCHEMA_VALIDATION,
                PAYLOAD_COMPONENT_ASSET_VALIDATION_RESULT, draftId(params), assetType);
        payload.put(FIELD_VALID, outcome.valid);
        payload.put(FIELD_ENABLEABLE, outcome.enableable);
        payload.put(FIELD_BLOCKING_ERRORS, outcome.blockingErrors);
        payload.put(FIELD_WARNINGS, outcome.warnings);
        payload.put(FIELD_MISSING_FIELDS, outcome.missingFields);
        payload.put(FIELD_FIELD_RESULTS, outcome.fieldResults);
        log.info("组件中心AI草稿校验完成, assetType:{}, valid:{}, enableable:{}, errorCount:{}, draftId:{}",
                assetType, outcome.valid, outcome.enableable, outcome.blockingErrors.size(), draftId(params));
        return payload;
    }

    /**
     * 生成组件草稿的预览请求，并尽量调用组件中心 M 端渲染预览能力。
     */
    public Map<String, Object> previewDraft(Map<String, String> params, Map<String, Object> draftPayload) {
        Map<String, Object> draft = extractDraft(draftPayload);
        String assetType = normalizeAssetType(stringValue(draft.get(FIELD_ASSET_TYPE)));
        Map<String, String> previewRequest = buildRenderPreviewRequest(draft);
        Map<String, Object> previewResult = new LinkedHashMap<>();
        List<String> errors = new ArrayList<>();
        try {
            SkillFactoryRenderPreviewResult result = componentRegistryService.renderPreview(previewRequest);
            previewResult = JsonSupport.fromJson(JsonSupport.toJSON(result));
            if (CollectionUtils.isNotEmpty(result.getErrors())) {
                errors.addAll(result.getErrors());
            }
        } catch (Exception e) {
            errors.add("调用组件中心预览失败：" + StringUtils.defaultString(e.getMessage()));
            log.warn("组件中心AI草稿预览失败, assetType:{}, componentName:{}, draftId:{}",
                    assetType, draft.get(FIELD_COMPONENT_NAME), draftId(params), e);
        }
        Map<String, Object> payload = basePayload(SCHEMA_PREVIEW, PAYLOAD_COMPONENT_ASSET_PREVIEW_RESULT,
                draftId(params), assetType);
        payload.put(FIELD_VALID, errors.isEmpty());
        payload.put(FIELD_RENDER_PREVIEW_REQUEST, previewRequest);
        payload.put(FIELD_RENDER_PREVIEW_RESULT, previewResult);
        payload.put(FIELD_ERRORS, errors);
        payload.put(FIELD_TRACE_ID, params.get(FIELD_TRACE_ID));
        log.info("组件中心AI草稿预览完成, assetType:{}, valid:{}, errorCount:{}, draftId:{}",
                assetType, errors.isEmpty(), errors.size(), draftId(params));
        return payload;
    }

    /**
     * 生成保存参数。该方法不落库，前端仍需由用户确认后调用 register/update。
     */
    public Map<String, Object> prepareSave(Map<String, String> params, Map<String, Object> draftPayload,
            Map<String, Object> validationPayload) {
        Map<String, Object> draft = extractDraft(draftPayload);
        String assetType = normalizeAssetType(stringValue(draft.get(FIELD_ASSET_TYPE)));
        ValidationOutcome outcome = validate(draft);
        Map<String, Object> saveParams = toSaveParams(draft, params);
        String method = StringUtils.isNotBlank(stringValue(saveParams.get(FIELD_ID)))
                ? METHOD_COMPONENT_UPDATE : METHOD_COMPONENT_REGISTER;
        Map<String, Object> payload = basePayload(SCHEMA_SAVE_PREPARE,
                PAYLOAD_COMPONENT_ASSET_SAVE_PREPARE, draftId(params), assetType);
        payload.put(FIELD_METHOD, method);
        payload.put(FIELD_PARAMS, saveParams);
        payload.put(FIELD_SAVE_ALLOWED, outcome.valid);
        payload.put(FIELD_REQUIRES_HUMAN_APPROVAL, true);
        payload.put(FIELD_BLOCKING_ERRORS, outcome.blockingErrors);
        payload.put(FIELD_WARNINGS, outcome.warnings);
        payload.put("sourceValidation", validationPayload == null ? Collections.emptyMap() : validationPayload);
        log.info("组件中心AI保存参数准备完成, assetType:{}, method:{}, saveAllowed:{}, draftId:{}",
                assetType, method, outcome.valid, draftId(params));
        return payload;
    }

    /**
     * 生成模型最终可展示摘要。
     */
    public String answerSummary(Map<String, String> params, Map<String, Object> draftPayload,
            Map<String, Object> validationPayload, Map<String, Object> previewPayload) {
        Map<String, Object> draft = extractDraft(draftPayload);
        String componentName = stringValue(draft.get(FIELD_COMPONENT_NAME));
        String assetType = normalizeAssetType(stringValue(draft.get(FIELD_ASSET_TYPE)));
        boolean valid = MapUtils.getBoolean(validationPayload, FIELD_VALID, false);
        boolean previewValid = MapUtils.getBoolean(previewPayload, FIELD_VALID, false);
        StringBuilder builder = new StringBuilder();
        builder.append("已为组件中心生成 ").append(assetType).append(" 草稿");
        if (StringUtils.isNotBlank(componentName)) {
            builder.append("：").append(componentName);
        }
        builder.append("。字段校验").append(valid ? "已通过" : "仍有缺口");
        builder.append("，预览").append(previewValid ? "已通过" : "需要保存或补齐字段后复验");
        builder.append("。请在右侧检查草稿和保存参数，确认后再保存到组件中心。");
        return builder.toString();
    }

    private Map<String, Object> basePayload(String schemaVersion, String payloadType, String draftId,
            String assetType) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put(FIELD_SCHEMA_VERSION, schemaVersion);
        payload.put(FIELD_PAYLOAD_TYPE, payloadType);
        payload.put(FIELD_AUTHORING_DOMAIN, AUTHORING_DOMAIN_COMPONENT_CENTER);
        payload.put(FIELD_DRAFT_ID, draftId);
        payload.put(FIELD_ASSET_TYPE, assetType);
        return payload;
    }

    private Map<String, Object> buildFieldHelp(String assetType) {
        Map<String, Object> help = new LinkedHashMap<>();
        help.put(FIELD_DSL_TYPE, "运行态协议族：CARD_CONTAINER 或 BUSINESS_DSL。");
        help.put(FIELD_AGENT_UI_DSL, "BUSINESS_DSL 的运行态查找键，例如 live_stream_selector。");
        help.put(FIELD_PARAMS_SCHEMA_JSON,
                "Skill 组件输出的 params JSON Schema，只描述 params 的必填、可选和类型约束。");
        help.put(FIELD_RENDER_TEMPLATE_JSON, "把 params 翻译成前端协议 payload 的模板，支持 {{params.xxx}}。");
        help.put(FIELD_RUNTIME_CONFIG_JSON, "类型专属的 renderer、catalog、数据源或预览配置，必须是 JSON 对象。");
        if (!StringUtils.equals(assetType, ASSET_TYPE_CARD_COMPONENT)) {
            help.put(FIELD_INTEGRATION_PROMPT, "给 Skill chat 使用的业务编排或原子组件接入说明。");
        }
        if (StringUtils.equals(assetType, ASSET_TYPE_CARD_COMPONENT)) {
            help.put(FIELD_BUNDLE_URL, "PC 渲染组件必须已有前端 bundle/组件实现；本页面不上传代码。");
            help.put(FIELD_APP_BUNDLE_URL, "APP 渲染组件必须已有前端 bundle/组件实现；本页面不上传代码。");
            help.put(FIELD_OFFICIAL_DEMO_JSON,
                    "只维护最终 card-container payload 的 data 对象，公共外壳由 Adviser 可信补齐。");
            help.put(FIELD_RENDER_TEMPLATE_JSON,
                    "只维护生成最终 data 对象的模板；不得填写 bundle、组件身份或公共外壳字段。");
        }
        return help;
    }

    private Map<String, Object> assetDigest(SkillFactoryComponentAsset asset) {
        Map<String, Object> digest = new LinkedHashMap<>();
        digest.put(FIELD_ID, asset.getId());
        digest.put(FIELD_ASSET_TYPE, asset.getAssetType());
        digest.put(FIELD_COMPONENT_NAME, asset.getComponentName());
        digest.put(FIELD_COMPONENT_NAME_CN, asset.getComponentNameCn());
        digest.put(FIELD_DSL_TYPE, asset.getDslType());
        digest.put(FIELD_AGENT_UI_DSL, asset.getAgentUiDsl());
        digest.put(FIELD_PROTOCOL_VERSION, asset.getProtocolVersion());
        digest.put(FIELD_ENABLED, asset.getEnabled());
        return digest;
    }

    private void fillBusinessDslDraft(Map<String, String> params, Map<String, Object> draft) {
        String message = StringUtils.defaultString(params.get(FIELD_MESSAGE));
        boolean livePlanScene = containsAny(message, "直播", "live", "计划");
        putIfBlank(draft, FIELD_COMPONENT_NAME, livePlanScene ? "LivePlanCreateDsl" : "StoreDiagnosticDsl");
        putIfBlank(draft, FIELD_COMPONENT_NAME_CN, livePlanScene ? "直播计划 A2UI 编排" : "AIDD 诊断 A2UI 编排");
        putIfBlank(draft, FIELD_DSL_TYPE, DSL_TYPE_BUSINESS_DSL);
        putIfBlank(draft, FIELD_AGENT_UI_DSL, livePlanScene ? "live_plan_create" : "store_diagnostic");
        putIfBlank(draft, FIELD_SCENE, livePlanScene ? "Skill 输出直播计划参数后生成 A2UI"
                : "Skill 输出诊断场景后生成 A2UI");
        putIfBlank(draft, FIELD_PARAMS_SCHEMA_JSON, defaultParamsSchemaJson(livePlanScene));
        putIfBlank(draft, FIELD_RENDER_TEMPLATE_JSON, defaultRenderTemplateJson(livePlanScene));
        putIfBlank(draft, FIELD_OFFICIAL_DEMO_JSON, defaultBusinessDslOfficialDemoJson(livePlanScene));
        putIfBlank(draft, FIELD_INTEGRATION_PROMPT, defaultBusinessDslIntegrationPrompt(livePlanScene));
    }

    private void fillCardComponentDraft(Map<String, String> params, Map<String, Object> draft) {
        String message = StringUtils.defaultString(params.get(FIELD_MESSAGE));
        boolean newFrontendScene = containsAny(message, "新组件", "未实现", "还没有", "新页面", "new");
        putIfBlank(draft, FIELD_COMPONENT_NAME, newFrontendScene ? "UnimplementedRenderCard" : "ExistingRenderCard");
        putIfBlank(draft, FIELD_COMPONENT_NAME_CN, newFrontendScene ? "待实现渲染组件" : "已有渲染组件");
        putIfBlank(draft, FIELD_DSL_TYPE, DSL_TYPE_CARD_CONTAINER);
        putIfBlank(draft, FIELD_SCENE, newFrontendScene ? "需要业务工程接入 A2UI 后才能启用"
                : "已有前端渲染组件注册");
        putIfBlank(draft, FIELD_ALLOWED_ACTIONS_JSON, defaultCardActionsJson());
        putIfBlank(draft, FIELD_OFFICIAL_DEMO_JSON, defaultCardOfficialDemoJson(draft));
        putIfBlank(draft, FIELD_MESSAGE_DEMO_JSON, defaultCardMessageDemoJson(draft));
        putIfBlank(draft, FIELD_PARAMS_SCHEMA_JSON, defaultCardSchemaJson());
        putIfBlank(draft, FIELD_RENDER_TEMPLATE_JSON, defaultCardRenderTemplateJson(draft));
        if (newFrontendScene && (isBlank(draft.get(FIELD_BUNDLE_URL))
                || isBlank(draft.get(FIELD_APP_BUNDLE_URL)))) {
            draft.put(FIELD_ENABLED, false);
        }
    }

    private void fillA2uiAtomDraft(Map<String, String> params, Map<String, Object> draft) {
        putIfBlank(draft, FIELD_COMPONENT_NAME, "ChoicePicker");
        putIfBlank(draft, FIELD_COMPONENT_NAME_CN, "A2UI 选择器");
        putIfBlank(draft, FIELD_SCENE, "A2UI 原子组件资产登记");
        putIfBlank(draft, FIELD_OFFICIAL_DEMO_JSON, defaultA2uiAtomOfficialDemoJson());
        putIfBlank(draft, FIELD_INTEGRATION_PROMPT, "当业务 DSL 需要选择器时，可引用 ChoicePicker 原子组件。");
    }

    private void normalizeCommonDraft(Map<String, Object> draft) {
        String assetType = normalizeAssetType(stringValue(draft.get(FIELD_ASSET_TYPE)));
        if (StringUtils.equals(assetType, ASSET_TYPE_BUSINESS_DSL)) {
            draft.put(FIELD_DSL_TYPE, DSL_TYPE_BUSINESS_DSL);
        } else if (StringUtils.equals(assetType, ASSET_TYPE_CARD_COMPONENT)) {
            draft.put(FIELD_DSL_TYPE, DSL_TYPE_CARD_CONTAINER);
            draft.remove(FIELD_AGENT_UI_DSL);
        }
        putIfBlank(draft, FIELD_PROTOCOL_VERSION, DEFAULT_PROTOCOL_VERSION);
        putIfBlank(draft, FIELD_OWNER, "skill-factory");
        putIfBlank(draft, FIELD_SUPPORT_CLIENTS, List.of(SUPPORT_CLIENT_PC));
        if (!draft.containsKey(FIELD_ENABLED)) {
            draft.put(FIELD_ENABLED, false);
        }
    }

    private ValidationOutcome validate(Map<String, Object> draft) {
        ValidationOutcome outcome = new ValidationOutcome();
        String assetType = normalizeAssetType(stringValue(draft.get(FIELD_ASSET_TYPE)));
        requireFields(draft, COMMON_REQUIRED_FIELDS, outcome);
        if (!ASSET_TYPES.contains(assetType)) {
            outcome.blockingErrors.add("assetType 不支持：" + assetType);
        }
        if (StringUtils.equals(assetType, ASSET_TYPE_BUSINESS_DSL)) {
            requireFields(draft, BUSINESS_DSL_REQUIRED_FIELDS, outcome);
            validateJsonFields(draft, outcome, Map.of(
                    FIELD_PARAMS_SCHEMA_JSON, JSON_OBJECT,
                    FIELD_RUNTIME_CONFIG_JSON, JSON_OBJECT,
                    FIELD_OFFICIAL_DEMO_JSON, JSON_OBJECT));
        } else if (StringUtils.equals(assetType, ASSET_TYPE_A2UI_ATOM)) {
            requireFields(draft, A2UI_ATOM_REQUIRED_FIELDS, outcome);
            validateJsonFields(draft, outcome, Map.of(
                    FIELD_RUNTIME_CONFIG_JSON, JSON_OBJECT,
                    FIELD_OFFICIAL_DEMO_JSON, JSON_OBJECT));
        } else {
            requireFields(draft, CARD_COMPONENT_REQUIRED_FIELDS, outcome);
            validateJsonFields(draft, outcome, Map.of(
                    FIELD_PARAMS_SCHEMA_JSON, JSON_OBJECT,
                    FIELD_ALLOWED_ACTIONS_JSON, JSON_ARRAY,
                    FIELD_RUNTIME_CONFIG_JSON, JSON_OBJECT,
                    FIELD_MESSAGE_DEMO_JSON, JSON_OBJECT,
                    FIELD_OFFICIAL_DEMO_JSON, JSON_OBJECT));
        }
        validateExecutableCodeKeys(draft, outcome);
        outcome.valid = outcome.blockingErrors.isEmpty();
        outcome.enableable = outcome.valid && Boolean.TRUE.equals(booleanValue(draft.get(FIELD_ENABLED)));
        if (!outcome.enableable && outcome.valid) {
            outcome.warnings.add("当前草稿 enabled=false，保存后不会出现在 Skill 工作台可用组件列表。");
        }
        fillFieldResults(draft, outcome);
        return outcome;
    }

    private void requireFields(Map<String, Object> draft, List<String> fields, ValidationOutcome outcome) {
        for (String field : fields) {
            if (isBlank(draft.get(field))) {
                outcome.missingFields.add(field);
                outcome.blockingErrors.add(field + " 不能为空");
            }
        }
    }

    private void validateJsonFields(Map<String, Object> draft, ValidationOutcome outcome,
            Map<String, String> jsonTypes) {
        for (Map.Entry<String, String> entry : jsonTypes.entrySet()) {
            Object value = draft.get(entry.getKey());
            if (isBlank(value)) {
                continue;
            }
            Object parsed = parseJson(value);
            if (parsed == null) {
                outcome.blockingErrors.add(entry.getKey() + " 不是合法 JSON");
                continue;
            }
            if (StringUtils.equals(entry.getValue(), JSON_OBJECT) && !(parsed instanceof com.alibaba.fastjson2.JSONObject)) {
                outcome.blockingErrors.add(entry.getKey() + " 必须是 JSON 对象");
            }
            if (StringUtils.equals(entry.getValue(), JSON_ARRAY) && !(parsed instanceof com.alibaba.fastjson2.JSONArray)) {
                outcome.blockingErrors.add(entry.getKey() + " 必须是 JSON 数组");
            }
        }
    }

    private void validateExecutableCodeKeys(Map<String, Object> draft, ValidationOutcome outcome) {
        List<String> codeKeys = new ArrayList<>();
        collectExecutableCodeKeys(draft, codeKeys);
        if (CollectionUtils.isNotEmpty(codeKeys)) {
            outcome.blockingErrors.add("不允许上传可执行代码字段：" + StringUtils.join(codeKeys, ","));
        }
    }

    @SuppressWarnings("unchecked")
    private void collectExecutableCodeKeys(Object value, List<String> codeKeys) {
        if (value instanceof Map) {
            for (Map.Entry<Object, Object> entry : ((Map<Object, Object>) value).entrySet()) {
                String normalizedKey = StringUtils.lowerCase(StringUtils.deleteWhitespace(String.valueOf(
                        entry.getKey())));
                if (EXECUTABLE_CODE_KEYS.contains(normalizedKey)) {
                    codeKeys.add(String.valueOf(entry.getKey()));
                }
                collectExecutableCodeKeys(entry.getValue(), codeKeys);
            }
            return;
        }
        if (value instanceof String) {
            Object parsed = parseJson(value);
            if (parsed != null) {
                collectExecutableCodeKeys(parsed, codeKeys);
            }
        }
    }

    private void fillFieldResults(Map<String, Object> draft, ValidationOutcome outcome) {
        List<String> fields = new ArrayList<>(COMMON_REQUIRED_FIELDS);
        String assetType = normalizeAssetType(stringValue(draft.get(FIELD_ASSET_TYPE)));
        if (StringUtils.equals(assetType, ASSET_TYPE_BUSINESS_DSL)) {
            fields.addAll(BUSINESS_DSL_REQUIRED_FIELDS);
        } else if (StringUtils.equals(assetType, ASSET_TYPE_A2UI_ATOM)) {
            fields.addAll(A2UI_ATOM_REQUIRED_FIELDS);
        } else {
            fields.addAll(CARD_COMPONENT_REQUIRED_FIELDS);
        }
        for (String field : fields) {
            Map<String, Object> result = new LinkedHashMap<>();
            result.put("field", field);
            result.put("ready", !isBlank(draft.get(field)));
            result.put("valueType", draft.get(field) == null ? "" : draft.get(field).getClass().getSimpleName());
            outcome.fieldResults.add(result);
        }
    }

    private List<String> buildRisks(Map<String, Object> draft, ValidationOutcome outcome) {
        List<String> risks = new ArrayList<>();
        if (StringUtils.equals(normalizeAssetType(stringValue(draft.get(FIELD_ASSET_TYPE))),
                ASSET_TYPE_CARD_COMPONENT)
                && (isBlank(draft.get(FIELD_BUNDLE_URL)) || isBlank(draft.get(FIELD_APP_BUNDLE_URL)))) {
            risks.add("渲染组件缺少 PC 或 APP bundleUrl，两个端的业务工程接入未完成，不能启用。");
        }
        if (!outcome.valid) {
            risks.add("草稿仍有必填字段或 JSON 格式缺口，确认保存前需要补齐。");
        }
        return risks;
    }

    private List<String> buildNextQuestions(Map<String, Object> draft, ValidationOutcome outcome) {
        List<String> questions = new ArrayList<>();
        if (outcome.missingFields.contains(FIELD_BUNDLE_URL)) {
            questions.add("这个渲染组件在 PC 工程里的 bundleUrl 是什么？");
        }
        if (outcome.missingFields.contains(FIELD_APP_BUNDLE_URL)) {
            questions.add("这个渲染组件在 APP 工程里的 bundleUrl 是什么？");
        }
        if (isBlank(draft.get(FIELD_RUNTIME_CONFIG_JSON))
                && StringUtils.equals(normalizeAssetType(stringValue(draft.get(FIELD_ASSET_TYPE))),
                ASSET_TYPE_A2UI_ATOM)) {
            questions.add("A2UI 原子组件需要哪些 renderer、catalog 或 dataModel 配置？");
        }
        if (outcome.missingFields.contains(FIELD_AGENT_UI_DSL)) {
            questions.add("这个 BUSINESS_DSL 的 agentUiDsl 查找键是什么？例如 live_stream_selector。");
        }
        if (questions.isEmpty()) {
            questions.add("请确认右侧草稿内容，确认后可以保存到组件中心。");
        }
        return questions;
    }

    private Map<String, String> buildRenderPreviewRequest(Map<String, Object> draft) {
        Map<String, String> request = new LinkedHashMap<>();
        String assetType = normalizeAssetType(stringValue(draft.get(FIELD_ASSET_TYPE)));
        request.put(FIELD_SOURCE, SOURCE_AUTHORING);
        request.put(FIELD_CLIENT_TYPE, SUPPORT_CLIENT_PC);
        request.put(FIELD_ASSET_TYPE, assetType);
        request.put(FIELD_COMPONENT_NAME, stringValue(draft.get(FIELD_COMPONENT_NAME)));
        request.put(FIELD_RENDER_TEXT, stringValue(draft.get(FIELD_MESSAGE_DEMO_JSON)));
        request.put(FIELD_DSL_TYPE, stringValue(draft.get(FIELD_DSL_TYPE)));
        request.put(FIELD_PARAMS_SCHEMA_JSON, stringValue(draft.get(FIELD_PARAMS_SCHEMA_JSON)));
        request.put(FIELD_RENDER_TEMPLATE_JSON, stringValue(draft.get(FIELD_RENDER_TEMPLATE_JSON)));
        if (StringUtils.equals(assetType, ASSET_TYPE_BUSINESS_DSL)) {
            request.put(FIELD_INPUT_MODE, INPUT_MODE_BUSINESS_DSL);
            request.put(FIELD_AGENT_UI_DSL, stringValue(draft.get(FIELD_AGENT_UI_DSL)));
        } else {
            request.put(FIELD_INPUT_MODE, INPUT_MODE_CARD_CONTAINER);
        }
        return request;
    }

    private Map<String, Object> toSaveParams(Map<String, Object> draft, Map<String, String> params) {
        Map<String, Object> saveParams = new LinkedHashMap<>();
        for (Map.Entry<String, Object> entry : draft.entrySet()) {
            if (StringUtils.equals(entry.getKey(), FIELD_SUPPORT_CLIENTS)) {
                saveParams.put(entry.getKey(), supportClientsValue(entry.getValue()));
            } else {
                saveParams.put(entry.getKey(), entry.getValue());
            }
        }
        putIfNotBlank(saveParams, FIELD_ID, firstNotBlank(params.get(FIELD_ASSET_ID), params.get(FIELD_ID),
                stringValue(draft.get(FIELD_ID))));
        return saveParams;
    }

    private String supportClientsValue(Object value) {
        if (value instanceof List) {
            return JsonSupport.toJSON(value);
        }
        return stringValue(value);
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> currentDraft(Map<String, String> params) {
        Object parsed = parseJson(params.get(FIELD_CURRENT_DRAFT));
        if (!(parsed instanceof Map)) {
            return new LinkedHashMap<>();
        }
        Map<String, Object> map = new LinkedHashMap<>((Map<String, Object>) parsed);
        Object innerDraft = map.get(FIELD_DRAFT);
        if (innerDraft instanceof Map) {
            return new LinkedHashMap<>((Map<String, Object>) innerDraft);
        }
        return map;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> extractDraft(Map<String, Object> payload) {
        if (payload == null) {
            return new LinkedHashMap<>();
        }
        Object draft = payload.get(FIELD_DRAFT);
        if (draft instanceof Map) {
            return new LinkedHashMap<>((Map<String, Object>) draft);
        }
        return new LinkedHashMap<>(payload);
    }

    private String draftId(Map<String, String> params) {
        return StringUtils.defaultIfBlank(params.get(FIELD_DRAFT_ID),
                "component_asset_draft_" + UUID.randomUUID().toString().replace("-", ""));
    }

    private String normalizeAssetType(String assetType) {
        String normalized = StringUtils.upperCase(StringUtils.defaultIfBlank(assetType, ASSET_TYPE_BUSINESS_DSL));
        return ASSET_TYPES.contains(normalized) ? normalized : ASSET_TYPE_BUSINESS_DSL;
    }

    private Object parseJson(Object value) {
        if (value == null) {
            return null;
        }
        if (value instanceof com.alibaba.fastjson2.JSONObject || value instanceof com.alibaba.fastjson2.JSONArray) {
            return value;
        }
        String text = stringValue(value);
        if (StringUtils.isBlank(text)) {
            return null;
        }
        try {
            return com.alibaba.fastjson2.JSON.parse(text);
        } catch (Exception e) {
            return null;
        }
    }

    private String defaultParamsSchemaJson(boolean livePlanScene) {
        com.alibaba.fastjson2.JSONObject schema = new com.alibaba.fastjson2.JSONObject();
        schema.put(FIELD_TYPE, JSON_OBJECT);
        com.alibaba.fastjson2.JSONObject properties = new com.alibaba.fastjson2.JSONObject();
        com.alibaba.fastjson2.JSONObject scene = new com.alibaba.fastjson2.JSONObject();
        scene.put(FIELD_TYPE, "string");
        scene.put(FIELD_DESCRIPTION, livePlanScene ? "直播计划业务场景" : "诊断业务场景");
        properties.put(FIELD_SCENE, scene);
        schema.put(FIELD_PROPERTIES, properties);
        schema.put(FIELD_REQUIRED, List.of(FIELD_SCENE));
        return schema.toJSONString();
    }

    private String defaultRenderTemplateJson(boolean livePlanScene) {
        com.alibaba.fastjson2.JSONObject template = new com.alibaba.fastjson2.JSONObject();
        template.put(FIELD_TYPE, "updateComponents");
        template.put("surfaceId", "{{agentUiDsl}}");
        Map<String, Object> textComponent = new LinkedHashMap<>();
        textComponent.put(FIELD_ID, "summary");
        textComponent.put(FIELD_TYPE, "Text");
        textComponent.put("text", livePlanScene ? "已为{{params.scene}}生成直播计划"
                : "已为{{params.scene}}生成经营诊断");
        template.put("components", List.of(textComponent));
        return template.toJSONString();
    }

    private String defaultBusinessDslOfficialDemoJson(boolean livePlanScene) {
        Map<String, Object> demo = new LinkedHashMap<>();
        demo.put(FIELD_DSL_TYPE, DSL_TYPE_BUSINESS_DSL);
        demo.put(FIELD_AGENT_UI_DSL, livePlanScene ? "live_plan_create" : "store_diagnostic");
        demo.put(FIELD_PARAMS, Map.of(FIELD_SCENE, livePlanScene ? "直播" : "短视频"));
        return JsonSupport.toJSON(demo);
    }

    private String defaultBusinessDslIntegrationPrompt(boolean livePlanScene) {
        String agentUiDsl = livePlanScene ? "live_plan_create" : "store_diagnostic";
        String scene = livePlanScene ? "直播" : "短视频";
        return "当用户需要" + (livePlanScene ? "创建直播计划" : "查看业务诊断")
                + "时，只输出 @@KS_COMPONENT_START@@{\"dslType\":\"BUSINESS_DSL\",\"agentUiDsl\":\""
                + agentUiDsl + "\",\"params\":{\"scene\":\"" + scene
                + "\"}}@@KS_COMPONENT_END@@。不要手写完整 A2UI；adviser 会根据组件中心配置确定性生成。";
    }

    private String defaultCardSchemaJson() {
        Map<String, Object> schema = new LinkedHashMap<>();
        schema.put(FIELD_TYPE, JSON_OBJECT);
        schema.put(FIELD_PROPERTIES, Map.of(
                FIELD_TITLE, Map.of(FIELD_TYPE, "string"),
                FIELD_DESCRIPTION, Map.of(FIELD_TYPE, "string")));
        schema.put(FIELD_REQUIRED, List.of(FIELD_TITLE, FIELD_DESCRIPTION));
        return JsonSupport.toJSON(schema);
    }

    private String defaultCardActionsJson() {
        return JsonSupport.toJSON(List.of(Map.of(
                "actionCode", "sample_action",
                FIELD_DESCRIPTION, "示例按钮动作",
                "resultMode", "TEXT",
                "payloadSchema", Map.of(
                        FIELD_TYPE, JSON_OBJECT,
                        FIELD_PROPERTIES, Map.of("id", Map.of(FIELD_TYPE, "string"))))));
    }

    private String defaultCardOfficialDemoJson(Map<String, Object> draft) {
        Map<String, Object> demo = new LinkedHashMap<>();
        demo.put(FIELD_CARD_TYPE, stringValue(draft.get(FIELD_COMPONENT_NAME)));
        demo.put(FIELD_TITLE, "示例卡片");
        demo.put(FIELD_DESCRIPTION, "组件中心 AI 生成的渲染组件 demo 数据");
        return JsonSupport.toJSON(demo);
    }

    private String defaultCardMessageDemoJson(Map<String, Object> draft) {
        Map<String, Object> demo = new LinkedHashMap<>();
        demo.put(FIELD_DSL_TYPE, DSL_TYPE_CARD_CONTAINER);
        demo.put(FIELD_COMPONENT_NAME, stringValue(draft.get(FIELD_COMPONENT_NAME)));
        demo.put(FIELD_PARAMS, Map.of(
                FIELD_TITLE, "示例卡片",
                FIELD_DESCRIPTION, "组件中心 AI 生成的渲染组件 demo 数据"));
        return JsonSupport.toJSON(demo);
    }

    private String defaultCardRenderTemplateJson(Map<String, Object> draft) {
        Map<String, Object> template = new LinkedHashMap<>();
        template.put(FIELD_CARD_TYPE, "{{componentName}}");
        template.put(FIELD_TITLE, "{{params.title}}");
        template.put(FIELD_DESCRIPTION, "{{params.description}}");
        return JsonSupport.toJSON(template);
    }

    private String defaultA2uiAtomOfficialDemoJson() {
        Map<String, Object> demo = new LinkedHashMap<>();
        demo.put("version", DEFAULT_PROTOCOL_VERSION);
        demo.put(FIELD_TYPE, "updateComponents");
        demo.put("components", List.of(Map.of(FIELD_TYPE, "ChoicePicker")));
        return JsonSupport.toJSON(demo);
    }

    private boolean containsAny(String text, String... keywords) {
        for (String keyword : keywords) {
            if (StringUtils.containsIgnoreCase(text, keyword)) {
                return true;
            }
        }
        return false;
    }

    private void putIfBlank(Map<String, Object> target, String key, Object value) {
        if (isBlank(target.get(key)) && value != null) {
            target.put(key, value);
        }
    }

    private void putIfNotBlank(Map<String, Object> target, String key, String value) {
        if (StringUtils.isNotBlank(value)) {
            target.put(key, value);
        }
    }

    private boolean isBlank(Object value) {
        if (value == null) {
            return true;
        }
        if (value instanceof String) {
            return StringUtils.isBlank((String) value);
        }
        if (value instanceof List) {
            return ((List<?>) value).isEmpty();
        }
        if (value instanceof Map) {
            return ((Map<?, ?>) value).isEmpty();
        }
        return false;
    }

    private Boolean booleanValue(Object value) {
        if (value instanceof Boolean) {
            return (Boolean) value;
        }
        if (value == null) {
            return false;
        }
        return Boolean.parseBoolean(String.valueOf(value));
    }

    private String stringValue(Object value) {
        if (value == null) {
            return StringUtils.EMPTY;
        }
        if (value instanceof String) {
            return (String) value;
        }
        if (value instanceof com.alibaba.fastjson2.JSONObject || value instanceof com.alibaba.fastjson2.JSONArray || value instanceof Map
                || value instanceof List) {
            return JsonSupport.toJSON(value);
        }
        return String.valueOf(value);
    }

    private String firstNotBlank(String... values) {
        for (String value : values) {
            if (StringUtils.isNotBlank(value)) {
                return value;
            }
        }
        return StringUtils.EMPTY;
    }

    private static class ValidationOutcome {
        private boolean valid;
        private boolean enableable;
        private final List<String> missingFields = new ArrayList<>();
        private final List<String> blockingErrors = new ArrayList<>();
        private final List<String> warnings = new ArrayList<>();
        private final List<Map<String, Object>> fieldResults = new ArrayList<>();
    }
}
