package dev.a2flow.management.lifecycle;

import java.math.BigDecimal;
import java.net.URI;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.regex.Pattern;
import java.util.stream.Stream;

import jakarta.annotation.Resource;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.access.AssetAction;
import dev.a2flow.management.access.AssetAuthorizationService;
import dev.a2flow.management.access.AssetCreationTransactionService;
import dev.a2flow.management.model.CapabilityActionDraft;
import dev.a2flow.management.model.CapabilityActionValidationResult;
import dev.a2flow.management.model.CapabilityIntegerSupport;
import dev.a2flow.management.release.AssetReleaseEditGuard;
import dev.a2flow.management.release.PublishedAssetQueryService;
import dev.a2flow.management.release.ReleaseAssetType;
import dev.a2flow.management.release.ReleaseModels.PublishedAssetSnapshot;
import dev.a2flow.management.storage.db.repository.CapabilityActionDraftRepository;

import lombok.extern.slf4j.Slf4j;

/**
 * 能力中心草稿 Service。
 *
 * <p>该类承接统一 SkillFactory handler 的能力注册/编辑、静态校验和发布拦截。上游是 adviser
 * 已有的 M 端 method 分发，下游是 CapabilityActionDraftRepository；它不调用 API Center、
 * 不执行 KRPC/HTTP、不注册运行时 Tool，也不替代后续 CapabilityActionVersion 发布治理。
 */
@Service
@Slf4j
public class CapabilityActionDraftService {

    private static final String PARAM_DRAFT_ID = "draftId";
    private static final String PARAM_KEYWORD = "keyword";
    private static final String PARAM_LIST_BUSINESS_DOMAIN = "businessDomain";
    private static final String PARAM_LIST_CAPABILITY_DOMAIN = "capabilityDomain";
    private static final String PARAM_LIST_SPECIALIST_ID = "specialistId";
    private static final String PARAM_DRAFT_JSON = "draftJson";
    private static final String PARAM_BASE_REVISION = "baseRevision";
    private static final String PARAM_OWNERS_JSON = "ownersJson";
    private static final String PARAM_BUSINESS_DOMAIN = "businessDomain";
    private static final String PARAM_CAPABILITY_DOMAIN = "capabilityDomain";
    private static final String PARAM_SPECIALIST_IDS = "specialistIds";
    private static final String ACTION_SAVE_CAPABILITY = "保存业务能力";
    private static final String STATUS_DRAFT = "DRAFT";
    private static final String VALIDATION_STATUS_INVALID = "INVALID";
    private static final String VALIDATION_STATUS_VALID = "VALID";
    private static final String PAYLOAD_TYPE_SNAPSHOT = "CAPABILITY_DRAFT_SNAPSHOT";
    private static final String MODE_CREATE = "CREATE";
    private static final String SIDE_EFFECT_READ = "READ";
    private static final String APPROVAL_REQUEST = "REQUEST_APPROVAL";
    private static final String FIELD_PAYLOAD_TYPE = "payloadType";
    private static final String FIELD_MODE = "mode";
    private static final String FIELD_BASIC_INFO = "basicInfo";
    private static final String FIELD_SUPPORTED_CLIENTS = "supportedClients";
    private static final String FIELD_CLIENT_VARIANTS = "clientVariants";
    private static final String FIELD_API_SOURCE = "apiSource";
    private static final String FIELD_MODEL_CONTRACT = "modelContract";
    private static final String FIELD_EXECUTION_BINDING = "executionBinding";
    private static final String FIELD_RESULT_CONTRACT = "resultContract";
    private static final String FIELD_GOVERNANCE = "governance";
    private static final String FIELD_ACTION_CODE = "actionCode";
    private static final String FIELD_NAME_CN = "nameCn";
    private static final String FIELD_DESCRIPTION = "description";
    private static final String FIELD_BUSINESS_DOMAIN = "businessDomain";
    private static final String FIELD_CAPABILITY_DOMAIN = "capabilityDomain";
    private static final String FIELD_SPECIALIST_IDS = "specialistIds";
    private static final String FIELD_TECHNICAL_OWNER = "technicalOwner";
    private static final String FIELD_BUSINESS_OWNER = "businessOwner";
    private static final String FIELD_LEGACY_TOOL_NAME = "toolName";
    private static final String FIELD_LEGACY_RELEASE_APPROVER = "releaseApprover";
    private static final String FIELD_CLUSTER_CODE = "clusterCode";
    private static final String ERROR_CLUSTER_SOURCE = "集群标识只允许用于 API_CENTER 来源";
    private static final String FIELD_SOURCE_TYPE = "sourceType";
    private static final String FIELD_SERVICE_DEFINITION_ID = "serviceDefinitionId";
    private static final String FIELD_API_CENTER_ID = "apiCenterId";
    private static final String FIELD_INPUT_FIELDS = "inputFields";
    private static final String FIELD_INPUT_EXAMPLE_JSON = "inputExampleJson";
    private static final String FIELD_KEY_OUTPUT_FIELDS = "keyOutputFields";
    private static final String FIELD_RESPONSE_DEMO_JSON = "responseDemoJson";
    private static final String FIELD_TECHNICAL_OUTPUT_SCHEMA = "technicalOutputSchema";
    private static final String FIELD_OBSERVED_TYPE = "observedType";
    private static final String FIELD_TOOL_FIELD = "toolField";
    private static final String FIELD_FIELD_TYPE = "type";
    private static final String FIELD_PROPERTIES = "properties";
    private static final String FIELD_ITEMS = "items";
    private static final String FIELD_FIELD_SOURCE = "source";
    private static final String FIELD_BUSINESS_MEANING = "businessMeaning";
    private static final String FIELD_UNIT = "unit";
    private static final String FIELD_REQUIRED = "required";
    private static final String FIELD_EXAMPLES = "examples";
    private static final String FIELD_ALLOWED_VALUES = "allowedValues";
    private static final String FIELD_VALUE = "value";
    private static final String FIELD_LABEL = "label";
    private static final String FIELD_CONSTANT_VALUE = "constantValue";
    private static final String FIELD_SYSTEM_VARIABLE = "systemVariable";
    private static final String FIELD_VALUE_MAPPING = "valueMapping";
    private static final String FIELD_BINDING_TYPE = "bindingType";
    private static final String FIELD_TARGET = "target";
    private static final String FIELD_KESS_NAME = "kessName";
    private static final String FIELD_SERVICE_CLASS = "serviceClass";
    private static final String FIELD_METHOD_NAME = "methodName";
    private static final String FIELD_REGISTERED_URL = "registeredUrl";
    private static final String FIELD_PRE_RELEASE_URL = "preReleaseUrl";
    private static final String FIELD_PRODUCTION_URL = "productionUrl";
    private static final String FIELD_PATH = "path";
    private static final String FIELD_HTTP_METHOD = "httpMethod";
    private static final String FIELD_CONTENT_TYPE = "contentType";
    private static final String FIELD_AUTH_MODE = "authMode";
    private static final String FIELD_STATIC_HEADERS_JSON = "staticHeadersJson";
    private static final String FIELD_ENVIRONMENT_HEADERS_JSON = "environmentHeadersJson";
    private static final String FIELD_REQUEST_MAPPINGS_JSON = "requestMappingsJson";
    private static final String FIELD_CONTEXT_MAPPINGS_JSON = "contextMappingsJson";
    private static final String FIELD_TIMEOUT_MS = "timeoutMs";
    private static final String FIELD_MAX_RESPONSE_BYTES = "maxResponseBytes";
    private static final String FIELD_SUCCESS_STATUS_CODES = "successStatusCodes";
    private static final String FIELD_RESPONSE_POLICY = "responsePolicy";
    private static final String FIELD_IDEMPOTENCY = "idempotency";
    private static final String FIELD_ERROR_MAPPINGS = "errorMappings";
    private static final String FIELD_REQUIRED_REVIEWS = "requiredReviews";
    private static final String FIELD_PRESENTATION_COMPONENTS = "presentationComponents";
    private static final String FIELD_ASSET_ID = "assetId";
    private static final String FIELD_COMPONENT_NAME = "componentName";
    private static final String FIELD_COMPONENT_NAME_CN = "componentNameCn";
    private static final String FIELD_ASSET_TYPE = "assetType";
    private static final String FIELD_RENDER_PROTOCOL = "renderProtocol";
    private static final String FIELD_COMPONENT_VERSION = "componentVersion";
    private static final String FIELD_PROTOCOL_VERSION = "protocolVersion";
    private static final String FIELD_USAGE = "usage";
    private static final String FIELD_PARAMS_MAPPING = "paramsMapping";
    private static final String FIELD_SIDE_EFFECT_LEVEL = "sideEffectLevel";
    private static final String FIELD_APPROVAL_POLICY = "approvalPolicy";
    private static final String CLIENT_PC = "PC";
    private static final String CLIENT_APP = "APP";
    private static final String CLIENT_COMMON = "COMMON";
    private static final Set<List<String>> CLIENT_MODES = Set.of(
            List.of(CLIENT_PC), List.of(CLIENT_APP), List.of(CLIENT_PC, CLIENT_APP), List.of(CLIENT_COMMON));
    private static final String SOURCE_TYPE_API_CENTER = "API_CENTER";
    private static final String SOURCE_TYPE_HTTP_REQUEST = "HTTP_REQUEST";
    private static final String SOURCE_TYPE_LOCAL_METHOD = "LOCAL_METHOD";
    private static final Set<String> ALLOWED_SOURCE_TYPES = Set.of(
            "GRPC");
    private static final String BINDING_TYPE_KRPC = "KRPC";
    private static final String BINDING_TYPE_CONTROLLED_HTTP = "CONTROLLED_HTTP";
    private static final String BINDING_TYPE_LOCAL_METHOD = "LOCAL_METHOD";
    private static final String ERROR_LOCAL_METHOD_BINDING_REQUIRED =
            "LOCAL_METHOD sourceType requires LOCAL_METHOD bindingType";
    private static final String ERROR_LOCAL_METHOD_SOURCE_REQUIRED =
            "LOCAL_METHOD bindingType requires LOCAL_METHOD sourceType";
    private static final int DEFAULT_HTTP_TIMEOUT_MS = 3000;
    private static final int MAX_HTTP_TIMEOUT_MS = 120000;
    private static final int DEFAULT_MAX_RESPONSE_BYTES = 1024 * 1024;
    private static final int MAX_RESPONSE_BYTES = 5 * 1024 * 1024;
    private static final String CONTENT_TYPE_JSON = "application/json";
    private static final String AUTH_MODE_NONE = "NONE";
    private static final String AUTH_MODE_TRUSTED_COOKIE = "TRUSTED_COOKIE";
    private static final String IDEMPOTENCY_NONE = "NONE";
    private static final String RESPONSE_POLICY_ORIGINAL = "ORIGINAL";
    private static final String SUCCESS_STATUS_2XX = "2XX";
    private static final int HTTP_STATUS_MIN = 100;
    private static final int HTTP_STATUS_MAX = 599;
    private static final Set<String> SUPPORTED_HTTP_METHODS = Set.of("GET", "POST", "PUT", "PATCH", "DELETE");
    private static final String SIDE_EFFECT_WRITE = "WRITE";
    private static final String SIDE_EFFECT_DESTRUCTIVE = "DESTRUCTIVE";
    private static final String APPROVAL_AUTO_EXECUTE = "AUTO_EXECUTE";
    private static final String FIELD_SOURCE_MODEL_INPUT = "MODEL_INPUT";
    private static final String FIELD_SOURCE_CONSTANT = "CONSTANT";
    private static final String FIELD_SOURCE_SYSTEM_VARIABLE = "SYSTEM_VARIABLE";
    private static final String SYSTEM_VARIABLE_USER_ID = "userId";
    private static final String SYSTEM_VARIABLE_CLIENT = "client";
    private static final String FIELD_TYPE_STRING = "string";
    private static final String FIELD_TYPE_NUMBER = "number";
    private static final String FIELD_TYPE_INTEGER = "integer";
    private static final String FIELD_TYPE_BOOLEAN = "boolean";
    private static final String FIELD_TYPE_ARRAY = "array";
    private static final String FIELD_TYPE_OBJECT = "object";
    private static final int MAX_INPUT_SCHEMA_DEPTH = 8;
    private static final String ERROR_DRAFT_JSON_REQUIRED = "draftJson is required";
    private static final String ERROR_DRAFT_JSON_INVALID = "draftJson is not valid JSON object";
    private static final String ERROR_SUPPORTED_CLIENTS_INVALID =
            "supportedClients 必须精确为 [PC]、[APP]、[PC,APP] 或 [COMMON]。";
    private static final String ERROR_CLIENT_VARIANTS_INVALID =
            "clientVariants 必须与 supportedClients 精确对应。";
    private static final String ERROR_MIXED_CLIENT_CONTRACT =
            "新格式草稿不能同时携带根级技术契约。";
    private static final String ERROR_BUSINESS_DOMAIN_REQUIRED = "业务域关系不能为空。";
    private static final String ERROR_CAPABILITY_DOMAIN_REQUIRED = "能力域关系不能为空。";
    private static final String ERROR_SPECIALIST_REQUIRED = "所属专员关系不能为空。";
    private static final String ERROR_EXAMPLES_MUST_BE_SINGLE_STRING =
            ".examples 必须是单个示例字符串；枚举候选请填写 allowedValues。";
    private static final String ERROR_ACTION_CODE_INVALID =
            "基础信息.actionCode 必须使用至少三段、以字母开头且仅含字母和数字的点分命名，"
                    + "例如 live.plan.getById。";
    private static final String ERROR_PUBLISH_BLOCKED =
            "capability draft cannot publish before approved binding and dry-run evidence";
    private static final String PUBLISH_BLOCKER_DRY_RUN =
            "缺少经批准的服务端执行绑定和 PRT dry-run 证据，当前草稿不能发布。";
    private static final String REDACTED_VALUE = "[REDACTED]";
    private static final String REDACTED_REQUEST_VALUE = "[REDACTED_SENSITIVE_REQUEST]";
    private static final Set<String> SENSITIVE_FIELD_NAMES = Set.of(
            "cookie", "authorization", "token", "accesstoken", "refreshtoken", "apikey",
            "password", "secret", "credentialvalue", "accessproxysession", "kssecurityencrypt");
    private static final Pattern SENSITIVE_REQUEST_TEXT_PATTERN = Pattern.compile(
            "(?is)(?:^|\\s)(?:-b|--cookie)\\s+|(?:cookie|authorization)\\s*:");
    private static final Pattern KEY_OUTPUT_PATH_SEGMENT_PATTERN = Pattern.compile("^[^.\\[\\]]+(?:\\[\\])?$");
    private static final Pattern COMPONENT_PARAM_PATH_PATTERN = Pattern.compile(
            "^[A-Za-z_][A-Za-z0-9_]*(?:\\.[A-Za-z_][A-Za-z0-9_]*)*$");
    private static final Set<String> PRESENTATION_USAGES = Set.of(
            "SUCCESS_RESULT", "APPROVAL_INTERACTION", "ERROR_RESULT");
    private static final Pattern ACTION_CODE_PATTERN = Pattern.compile(
            "^[A-Za-z][A-Za-z0-9]*(?:\\.[A-Za-z][A-Za-z0-9]*){2,}$");

    @Resource
    private CapabilityActionDraftRepository capabilityActionDraftRepository;

    @Resource
    private PublishedAssetQueryService publishedAssetQueryService;

    @Resource
    private AssetReleaseEditGuard assetReleaseEditGuard;

    @Resource
    private AssetAuthorizationService assetAuthorizationService;

    @Resource
    private AssetCreationTransactionService assetCreationTransactionService;

    @Resource
    private CapabilityActionClassificationRelationService classificationRelationService;
    @Resource
    private CapabilityActionMutationTransactionService capabilityMutationTransactionService;

    /** 创建新的 canonical capability draft。 */
    public CapabilityActionDraft create(String operator, Map<String, String> params) {
        String draftJson = value(params, PARAM_DRAFT_JSON);
        Optional<CapabilityActionClassificationRelationService.ClassificationSelection> selection =
                classificationRelationService.resolveCreateSelection(value(params, PARAM_BUSINESS_DOMAIN),
                        value(params, PARAM_CAPABILITY_DOMAIN),
                        value(params, PARAM_SPECIALIST_IDS));
        Map<String, Object> canonicalDraft = selection.isEmpty()
                ? CapabilityActionMinimalRegistrationDraftFactory.canonicalize(
                        sanitizeDraft(parseDraftJson(draftJson)))
                : canonicalizeAuthoringDraft(StringUtils.isBlank(draftJson)
                        ? Collections.emptyMap() : parseDraftJson(draftJson));
        String draftId = "cap_draft_" + UUID.randomUUID().toString().replace("-", "");
        CapabilityActionDraft draft = new CapabilityActionDraft()
                .setDraftId(draftId)
                .setStatus(STATUS_DRAFT)
                .setDraft(canonicalDraft)
                .setCreator(operator)
                .setModifier(operator);
        assetAuthorizationService.validateCreationOwners(
                operator, ReleaseAssetType.CAPABILITY_ACTION, draftId, params.get(PARAM_OWNERS_JSON));
        log.info("能力中心创建草稿, draftId:{}, operator:{}, nameOnly:{}", draftId, operator, selection.isEmpty());
        if (selection.isEmpty()) {
            return assetCreationTransactionService.createCapabilityRegistration(
                    operator, draft, params.get(PARAM_OWNERS_JSON));
        }
        return assetCreationTransactionService.createCapability(
                operator, draft, selection.get(), params.get(PARAM_OWNERS_JSON));
    }
    /**
     * 查询能力草稿列表。
     */
    public List<CapabilityActionDraft> list(Map<String, String> params) {
        String keyword = value(params, PARAM_KEYWORD);
        log.info("能力中心查询草稿列表, keyword:{}", keyword);
        return capabilityActionDraftRepository.list(keyword).stream()
                .map(classificationRelationService::project)
                .filter(item -> classificationRelationService.matches(item,
                        value(params, PARAM_LIST_BUSINESS_DOMAIN),
                        value(params, PARAM_LIST_CAPABILITY_DOMAIN),
                        value(params, PARAM_LIST_SPECIALIST_ID)))
                .toList();
    }

    /**
     * 查询 Skill 工作台可绑定的当前 ONLINE 正式能力版本。
     *
     * <p>结果来自共享发布聚合冻结快照；没有 ONLINE 指针的草稿和仅发布到 PRT 的能力不会返回。
     */
    public List<CapabilityActionDraft> listPublished(Map<String, String> params) {
        String keyword = value(params, PARAM_KEYWORD);
        String normalizedKeyword = StringUtils.lowerCase(keyword);
        List<CapabilityActionDraft> result = publishedAssetQueryService
                .listOnline(ReleaseAssetType.CAPABILITY_ACTION)
                .stream()
                .map(this::publishedDraft)
                .filter(item -> matchesPublishedKeyword(item, normalizedKeyword))
                .toList();
        log.info("能力中心查询ONLINE正式列表, keyword:{}, count:{}", keyword, result.size());
        return result;
    }

    /** 按能力草稿稳定 ID 读取当前 ONLINE 正式快照。 */
    public CapabilityActionDraft publishedDetail(String draftId) {
        return publishedDraft(publishedAssetQueryService.requireOnline(
                ReleaseAssetType.CAPABILITY_ACTION, draftId));
    }

    /**
     * 查询单个能力草稿。
     */
    public CapabilityActionDraft detail(String draftId) {
        CapabilityActionDraft draft = capabilityActionDraftRepository.find(draftId);
        if (draft == null) {
            throw new IllegalArgumentException("capability draft not found");
        }
        log.info("能力中心读取草稿详情, draftId:{}, revision:{}", draftId, draft.getRevision());
        return classificationRelationService.project(draft);
    }

    /**
     * 保存前端确认后的完整 canonical draft，并进行 revision 校验。
     */
    public CapabilityActionDraft save(String operator, Map<String, String> params) {
        String draftId = required(params, PARAM_DRAFT_ID);
        assetAuthorizationService.requirePermission(
                operator, ReleaseAssetType.CAPABILITY_ACTION, draftId, AssetAction.EDIT);
        int baseRevision = integer(required(params, PARAM_BASE_REVISION), PARAM_BASE_REVISION);
        CapabilityActionDraft current = detail(draftId);
        assetReleaseEditGuard.requireEditableChange(
                ReleaseAssetType.CAPABILITY_ACTION, draftId, ACTION_SAVE_CAPABILITY, operator);
        CapabilityActionDraft draft = new CapabilityActionDraft()
                .setDraftId(draftId)
                .setStatus(current.getStatus())
                .setDraft(canonicalizeAuthoringDraft(parseDraftJson(required(params, PARAM_DRAFT_JSON))))
                .setValidationErrors(Collections.emptyList())
                .setValidationWarnings(Collections.emptyList())
                .setValidationStatus(null)
                .setModifier(operator);
        CapabilityActionClassificationRelationService.ClassificationSelection selection =
                classificationRelationService.resolveSelection(
                        required(params, PARAM_BUSINESS_DOMAIN),
                        required(params, PARAM_CAPABILITY_DOMAIN),
                        required(params, PARAM_SPECIALIST_IDS));
        log.info("能力中心保存草稿, draftId:{}, baseRevision:{}, operator:{}, actionCode:{}",
                draftId, baseRevision, operator, nestedString(draft.getDraft(), FIELD_BASIC_INFO, FIELD_ACTION_CODE));
        return capabilityMutationTransactionService.save(operator, draft, baseRevision, selection);
    }

    /**
     * 执行草稿静态校验并保存校验结论。
     */
    public CapabilityActionValidationResult validate(String operator, Map<String, String> params) {
        String draftId = required(params, PARAM_DRAFT_ID);
        assetAuthorizationService.requirePermission(
                operator, ReleaseAssetType.CAPABILITY_ACTION, draftId, AssetAction.EDIT);
        CapabilityActionDraft current = detail(draftId);
        current.setDraft(canonicalizeAuthoringDraft(current.getDraft()));
        CapabilityActionValidationResult result = validateDraft(current);
        appendClassificationErrors(current, result);
        CapabilityActionDraft toSave = new CapabilityActionDraft()
                .setDraftId(current.getDraftId())
                .setStatus(current.getStatus())
                .setDraft(current.getDraft())
                .setValidationErrors(result.getErrors())
                .setValidationWarnings(result.getWarnings())
                .setValidationStatus(result.getStatus())
                .setModifier(operator);
        CapabilityActionDraft saved = capabilityMutationTransactionService.saveWithInheritedRelations(
                operator, toSave, current.getRevision());
        result.setRevision(saved.getRevision());
        log.info("能力中心草稿静态校验完成, draftId:{}, revision:{}, valid:{}, errorCount:{}, blockerCount:{}",
                draftId, saved.getRevision(), result.getValid(), result.getErrors().size(),
                result.getPublishBlockers().size());
        return result;
    }

    /** 持久化能力的静态校验必须同时校验 relation-backed 分类完整性。 */
    private void appendClassificationErrors(CapabilityActionDraft draft,
            CapabilityActionValidationResult result) {
        if (StringUtils.isBlank(draft.getBusinessDomain())) {
            result.getErrors().add(ERROR_BUSINESS_DOMAIN_REQUIRED);
        }
        if (StringUtils.isBlank(draft.getCapabilityDomain())) {
            result.getErrors().add(ERROR_CAPABILITY_DOMAIN_REQUIRED);
        }
        if (StringUtils.isBlank(draft.getSpecialistId())) {
            result.getErrors().add(ERROR_SPECIALIST_REQUIRED);
        }
        if (!result.getErrors().isEmpty()) {
            result.setValid(false).setStatus(VALIDATION_STATUS_INVALID);
        }
    }

    /**
     * 发布入口的第一期显式拦截。
     *
     * <p>当前只落地草稿与静态校验，未实现批准的服务端 binding 和 dry-run 证据，因此任何发布请求
     * 都必须明确失败，不能把页面按钮误表现为已经创建了可执行 Tool。
     */
    public CapabilityActionDraft publish(String operator, Map<String, String> params) {
        String draftId = required(params, PARAM_DRAFT_ID);
        assetAuthorizationService.requirePermission(
                operator, ReleaseAssetType.CAPABILITY_ACTION, draftId, AssetAction.PUBLISH);
        CapabilityActionValidationResult validation = validateDraft(detail(draftId));
        log.warn("能力中心发布被第一期门禁拦截, draftId:{}, revision:{}, valid:{}, blockers:{}",
                draftId, validation.getRevision(), validation.getValid(), validation.getPublishBlockers());
        throw new IllegalStateException(ERROR_PUBLISH_BLOCKED + ": " + PUBLISH_BLOCKER_DRY_RUN);
    }

    /**
     * 规范化模型生成的能力草稿快照，但不执行持久化。
     *
     * <p>上游是能力中心 Authoring Tool，下游是前端受控表单。该方法补齐固定协议字段和六个
     * 顶层 section，并复用持久化前的敏感信息脱敏规则；它不会绕过 revision，也不会把模型输出
     * 直接保存为 canonical draft。
     */
    public Map<String, Object> canonicalizeAuthoringDraft(Map<String, Object> proposedDraft) {
        Map<String, Object> sanitized = sanitizeDraft(proposedDraft == null ? Collections.emptyMap() : proposedDraft);
        Map<String, Object> canonical = initialDraft();
        canonical.put(FIELD_MODE, StringUtils.defaultIfBlank(stringValue(sanitized.get(FIELD_MODE)), MODE_CREATE));
        mergeSection(canonical, sanitized, FIELD_BASIC_INFO);
        mergeSection(canonical, sanitized, FIELD_GOVERNANCE);
        Map<String, Object> basicInfo = mapValue(canonical.get(FIELD_BASIC_INFO));
        basicInfo.remove(FIELD_LEGACY_TOOL_NAME);
        basicInfo.remove(FIELD_LEGACY_RELEASE_APPROVER);
        basicInfo.remove(FIELD_BUSINESS_OWNER);
        basicInfo.remove(FIELD_BUSINESS_DOMAIN);
        basicInfo.remove(FIELD_CAPABILITY_DOMAIN);
        basicInfo.remove(FIELD_SPECIALIST_IDS);
        canonical.put(FIELD_BASIC_INFO, basicInfo);
        canonicalizeClientVariants(canonical, sanitized);
        Map<String, Object> governance = mapValue(canonical.get(FIELD_GOVERNANCE));
        governance.remove(FIELD_REQUIRED_REVIEWS);
        canonical.put(FIELD_GOVERNANCE, governance);
        return canonical;
    }

    /**
     * 规范化端契约并执行旧草稿迁移。
     *
     * <p>旧草稿只有根级技术契约时，仅迁入 PC；新格式必须显式给出四种互斥模式之一，并让端契约键
     * 完全一致。该边界不复制 APP/COMMON、不跨端继承，也不解释历史不可变发布快照。
     */
    private void canonicalizeClientVariants(Map<String, Object> canonical, Map<String, Object> sanitized) {
        boolean hasNewContract = sanitized.containsKey(FIELD_SUPPORTED_CLIENTS)
                || sanitized.containsKey(FIELD_CLIENT_VARIANTS);
        boolean hasLegacyContract = Stream.of(
                FIELD_API_SOURCE, FIELD_MODEL_CONTRACT, FIELD_EXECUTION_BINDING, FIELD_RESULT_CONTRACT)
                .anyMatch(sanitized::containsKey);
        if (hasNewContract && hasLegacyContract) {
            throw new IllegalArgumentException(ERROR_MIXED_CLIENT_CONTRACT);
        }
        List<String> clients = hasNewContract
                ? canonicalSupportedClients(sanitized.get(FIELD_SUPPORTED_CLIENTS))
                : List.of(CLIENT_PC);
        Map<String, Object> proposedVariants = mapValue(sanitized.get(FIELD_CLIENT_VARIANTS));
        if (hasNewContract && (!(sanitized.get(FIELD_CLIENT_VARIANTS) instanceof Map)
                || !new ArrayList<>(proposedVariants.keySet()).equals(clients))) {
            throw new IllegalArgumentException(ERROR_CLIENT_VARIANTS_INVALID);
        }
        Map<String, Object> canonicalVariants = new LinkedHashMap<>();
        for (String client : clients) {
            Map<String, Object> source = hasNewContract
                    ? requireClientVariant(proposedVariants, client)
                    : legacyTechnicalVariant(sanitized);
            canonicalVariants.put(client, canonicalTechnicalVariant(source));
        }
        canonical.put(FIELD_SUPPORTED_CLIENTS, clients);
        canonical.put(FIELD_CLIENT_VARIANTS, canonicalVariants);
    }

    /** 严格识别四种互斥端模式，拒绝重排、重复和 COMMON 与具体端混合。 */
    private List<String> canonicalSupportedClients(Object value) {
        if (!(value instanceof List)) {
            throw new IllegalArgumentException(ERROR_SUPPORTED_CLIENTS_INVALID);
        }
        List<String> selected = new ArrayList<>();
        for (Object item : (List<?>) value) {
            String client = StringUtils.upperCase(StringUtils.trim(stringValue(item)), Locale.ROOT);
            selected.add(client);
        }
        if (CLIENT_MODES.contains(selected)) {
            return List.copyOf(selected);
        }
        throw new IllegalArgumentException(ERROR_SUPPORTED_CLIENTS_INVALID);
    }
    private Map<String, Object> requireClientVariant(Map<String, Object> variants, String client) {
        Object value = variants.get(client);
        if (!(value instanceof Map)) {
            throw new IllegalArgumentException(ERROR_CLIENT_VARIANTS_INVALID);
        }
        return mapValue(value);
    }
    private Map<String, Object> legacyTechnicalVariant(Map<String, Object> legacyDraft) {
        Map<String, Object> variant = new LinkedHashMap<>();
        Stream.of(FIELD_API_SOURCE, FIELD_MODEL_CONTRACT, FIELD_EXECUTION_BINDING, FIELD_RESULT_CONTRACT)
                .filter(legacyDraft::containsKey)
                .forEach(section -> variant.put(section, legacyDraft.get(section)));
        return variant;
    }
    private Map<String, Object> canonicalTechnicalVariant(Map<String, Object> source) {
        Map<String, Object> variant = initialTechnicalVariant();
        mergeSection(variant, source, FIELD_API_SOURCE);
        mergeSection(variant, source, FIELD_MODEL_CONTRACT);
        mergeSection(variant, source, FIELD_EXECUTION_BINDING);
        mergeSection(variant, source, FIELD_RESULT_CONTRACT);
        Map<String, Object> apiSource = mapValue(variant.get(FIELD_API_SOURCE));
        apiSource.remove(FIELD_SERVICE_DEFINITION_ID);
        apiSource.remove(FIELD_API_CENTER_ID);
        String sourceType = StringUtils.defaultIfBlank(
                stringValue(apiSource.get(FIELD_SOURCE_TYPE)), "GRPC").toUpperCase(Locale.ROOT);
        if (!ALLOWED_SOURCE_TYPES.contains(sourceType)) {
            throw new IllegalArgumentException(
                    "API来源.sourceType 只允许 GRPC。");
        }
        Object rawClusterCode = apiSource.get(FIELD_CLUSTER_CODE);
        if (rawClusterCode != null && !(rawClusterCode instanceof String)) {
            throw new IllegalArgumentException(ERROR_CLUSTER_SOURCE);
        }
        String clusterCode = StringUtils.trimToNull((String) rawClusterCode);
        if (clusterCode != null && !SOURCE_TYPE_API_CENTER.equals(sourceType)) {
            throw new IllegalArgumentException(ERROR_CLUSTER_SOURCE);
        }
        if (clusterCode == null) {
            apiSource.remove(FIELD_CLUSTER_CODE);
        } else {
            apiSource.put(FIELD_CLUSTER_CODE, clusterCode);
        }
        apiSource.put(FIELD_SOURCE_TYPE, sourceType);
        variant.put(FIELD_API_SOURCE, apiSource);
        Map<String, Object> modelContract = canonicalModelContract(mapValue(variant.get(FIELD_MODEL_CONTRACT)));
        variant.put(FIELD_MODEL_CONTRACT, modelContract);
        variant.put(FIELD_EXECUTION_BINDING, CapabilityActionExecutionBindingCanonicalizer.canonicalize(
                mapValue(variant.get(FIELD_EXECUTION_BINDING)), modelContract, sourceType));
        variant.put(FIELD_RESULT_CONTRACT,
                canonicalResultContract(mapValue(variant.get(FIELD_RESULT_CONTRACT))));
        return variant;
    }
    /**
     * 对模型 patch 中的单个 value 执行与草稿保存相同的递归脱敏。
     */
    public Object sanitizeAuthoringValue(Object value) {
        return sanitizeDraftValue(StringUtils.EMPTY, value);
    }

    /**
     * 对当前页面草稿执行只读静态校验，不写 Repository、不增加 revision。
     */
    public CapabilityActionValidationResult validateAuthoringDraft(String draftId, int revision,
            Map<String, Object> draft) {
        CapabilityActionDraft preview = new CapabilityActionDraft()
                .setDraftId(draftId)
                .setRevision(revision)
                .setStatus(STATUS_DRAFT)
                .setDraft(canonicalizeAuthoringDraft(draft));
        return validateDraft(preview);
    }

    private CapabilityActionValidationResult validateDraft(CapabilityActionDraft draft) {
        Map<String, Object> canonicalDraft = canonicalizeAuthoringDraft(draft.getDraft());
        List<String> errors = new ArrayList<>();
        List<String> warnings = new ArrayList<>();
        Map<String, Object> basicInfo = mapValue(canonicalDraft.get(FIELD_BASIC_INFO));
        Map<String, Object> governance = mapValue(canonicalDraft.get(FIELD_GOVERNANCE));

        if (!PAYLOAD_TYPE_SNAPSHOT.equals(stringValue(canonicalDraft.get(FIELD_PAYLOAD_TYPE)))) {
            errors.add("payloadType 必须为 " + PAYLOAD_TYPE_SNAPSHOT + "。");
        }
        requireValue(errors, basicInfo, FIELD_ACTION_CODE, "基础信息.actionCode");
        String actionCode = stringValue(basicInfo.get(FIELD_ACTION_CODE));
        if (StringUtils.isNotBlank(actionCode) && !ACTION_CODE_PATTERN.matcher(actionCode).matches()) {
            errors.add(ERROR_ACTION_CODE_INVALID);
        }
        requireValue(errors, basicInfo, FIELD_NAME_CN, "基础信息.nameCn");
        requireValue(errors, basicInfo, FIELD_DESCRIPTION, "基础信息.description");
        requireValue(errors, basicInfo, FIELD_TECHNICAL_OWNER, "基础信息.technicalOwner");
        for (String client : supportedClients(canonicalDraft)) {
            validateClientVariant(errors, client, clientVariant(canonicalDraft, client), governance);
        }
        validateGovernance(errors, governance);
        return new CapabilityActionValidationResult()
                .setDraftId(draft.getDraftId())
                .setRevision(draft.getRevision())
                .setValid(errors.isEmpty())
                .setStatus(errors.isEmpty() ? VALIDATION_STATUS_VALID : VALIDATION_STATUS_INVALID)
                .setErrors(errors)
                .setWarnings(warnings)
                .setPublishBlockers(List.of())
                .setValidatedAt(System.currentTimeMillis());
    }
    /** 对单端完整技术契约执行现有静态门禁，并为错误补充端标识。 */
    private void validateClientVariant(List<String> errors, String client,
            Map<String, Object> variant, Map<String, Object> governance) {
        int errorStart = errors.size();
        Map<String, Object> apiSource = mapValue(variant.get(FIELD_API_SOURCE));
        Map<String, Object> modelContract = mapValue(variant.get(FIELD_MODEL_CONTRACT));
        Map<String, Object> executionBinding = mapValue(variant.get(FIELD_EXECUTION_BINDING));
        Map<String, Object> resultContract = mapValue(variant.get(FIELD_RESULT_CONTRACT));
        requireValue(errors, apiSource, FIELD_SOURCE_TYPE, "API来源.sourceType");
        String sourceType = stringValue(apiSource.get(FIELD_SOURCE_TYPE));
        if (!ALLOWED_SOURCE_TYPES.contains(sourceType)) {
            errors.add("API来源.sourceType 只允许 GRPC。");
        }
        requireValue(errors, modelContract, FIELD_DESCRIPTION, "参数契约.description");
        validateInputFields(errors, modelContract.get(FIELD_INPUT_FIELDS));
        Object inputExample = validateContractExample(
                errors, modelContract, FIELD_INPUT_EXAMPLE_JSON, "参数契约.inputExampleJson");
        validateInputExampleTypes(errors, modelContract.get(FIELD_INPUT_FIELDS), inputExample);
        validateInputExampleAllowedValues(errors, modelContract.get(FIELD_INPUT_FIELDS), inputExample);
        validateKeyOutputFields(errors, resultContract);
        validatePresentationComponents(errors, resultContract);
        validateExecutionBinding(errors, executionBinding, sourceType);
        String sideEffectLevel = stringValue(governance.get(FIELD_SIDE_EFFECT_LEVEL));
        if (SIDE_EFFECT_WRITE.equals(sideEffectLevel) || SIDE_EFFECT_DESTRUCTIVE.equals(sideEffectLevel)) {
            requireValue(errors, executionBinding, FIELD_IDEMPOTENCY, "执行绑定.idempotency");
        }
        for (int index = errorStart; index < errors.size(); index++) {
            errors.set(index, client + "端." + errors.get(index));
        }
    }
    private List<String> supportedClients(Map<String, Object> canonicalDraft) {
        return canonicalSupportedClients(canonicalDraft.get(FIELD_SUPPORTED_CLIENTS));
    }
    private Map<String, Object> clientVariant(Map<String, Object> canonicalDraft, String client) {
        return requireClientVariant(mapValue(canonicalDraft.get(FIELD_CLIENT_VARIANTS)), client);
    }

    private String firstVariantSourceType(Map<String, Object> canonicalDraft) {
        List<String> clients = supportedClients(canonicalDraft);
        return nestedString(clientVariant(canonicalDraft, clients.get(0)), FIELD_API_SOURCE, FIELD_SOURCE_TYPE);
    }

    /**
     * 校验模型参数契约中的最小业务语义，避免只登记技术字段名后就进入发布流程。
     */
    private void validateInputFields(List<String> errors, Object inputFieldsValue) {
        if (!(inputFieldsValue instanceof List)) {
            errors.add("参数契约.inputFields 必须是数组。");
            return;
        }
        List<?> inputFields = (List<?>) inputFieldsValue;
        Set<String> fieldNames = new HashSet<>();
        for (int index = 0; index < inputFields.size(); index++) {
            Map<String, Object> field = mapValue(inputFields.get(index));
            String prefix = "参数契约.inputFields[" + index + "]";
            if (field.isEmpty()) {
                errors.add(prefix + " 必须是对象。");
                continue;
            }
            requireValue(errors, field, FIELD_TOOL_FIELD, prefix + ".toolField");
            String toolField = stringValue(field.get(FIELD_TOOL_FIELD));
            if (StringUtils.isNotBlank(toolField) && !fieldNames.add(toolField)) {
                errors.add(prefix + ".toolField 不能重复: " + toolField + "。");
            }
            requireValue(errors, field, FIELD_FIELD_TYPE, prefix + ".type");
            requireValue(errors, field, FIELD_FIELD_SOURCE, prefix + ".source");
            requireValue(errors, field, FIELD_BUSINESS_MEANING, prefix + ".businessMeaning");
            validateOptionalExample(errors, field, prefix);
            String type = stringValue(field.get(FIELD_FIELD_TYPE));
            if (!StringUtils.equalsAny(type, FIELD_TYPE_STRING, FIELD_TYPE_NUMBER, FIELD_TYPE_INTEGER,
                    FIELD_TYPE_BOOLEAN, FIELD_TYPE_ARRAY)) {
                errors.add(prefix + ".type 只允许 string、number、integer、boolean 或 array。");
            }
            if (FIELD_TYPE_ARRAY.equals(type)) {
                validateInputSchemaNode(errors, field.get(FIELD_ITEMS), prefix + ".items", 1);
            }
            String source = stringValue(field.get(FIELD_FIELD_SOURCE));
            if (!StringUtils.equalsAny(source, FIELD_SOURCE_MODEL_INPUT, FIELD_SOURCE_CONSTANT,
                    FIELD_SOURCE_SYSTEM_VARIABLE)) {
                errors.add(prefix + ".source 只允许 MODEL_INPUT、CONSTANT 或 SYSTEM_VARIABLE。");
            }
            if (FIELD_SOURCE_CONSTANT.equals(source)) {
                validateConstantValue(errors, field, type, prefix);
            } else if (FIELD_SOURCE_SYSTEM_VARIABLE.equals(source)) {
                validateSystemVariable(errors, field, type, prefix);
            } else if (FIELD_SOURCE_MODEL_INPUT.equals(source)) {
                validateAllowedValues(errors, field.get(FIELD_ALLOWED_VALUES), type, prefix);
            }
        }
    }

    /** 示例只表示一个典型入参；闭集候选必须进入 allowedValues，不能用数组复写枚举。 */
    private void validateOptionalExample(List<String> errors, Map<String, Object> field, String prefix) {
        Object examples = field.get(FIELD_EXAMPLES);
        if (examples != null && !(examples instanceof String)) {
            errors.add(prefix + ERROR_EXAMPLES_MUST_BE_SINGLE_STRING);
        }
    }

    /** 校验模型入参结构化枚举；单位字段不参与此约束。 */
    private void validateAllowedValues(List<String> errors, Object allowedValuesValue,
            String type, String prefix) {
        if (allowedValuesValue == null) {
            return;
        }
        if (!StringUtils.equalsAny(type, FIELD_TYPE_STRING, FIELD_TYPE_NUMBER, FIELD_TYPE_INTEGER)) {
            errors.add(prefix + ".allowedValues 只允许用于 string、number 或 integer 模型输入。");
            return;
        }
        if (!(allowedValuesValue instanceof List)) {
            errors.add(prefix + ".allowedValues 必须是数组。");
            return;
        }
        List<?> allowedValues = (List<?>) allowedValuesValue;
        if (allowedValues.isEmpty()) {
            errors.add(prefix + ".allowedValues 配置后至少需要一个可选值。");
            return;
        }
        Set<String> identities = new HashSet<>();
        for (int index = 0; index < allowedValues.size(); index++) {
            Map<String, Object> item = mapValue(allowedValues.get(index));
            String itemPrefix = prefix + ".allowedValues[" + index + "]";
            if (item.isEmpty()) {
                errors.add(itemPrefix + " 必须是对象。");
                continue;
            }
            Object value = item.get(FIELD_VALUE);
            if (!matchesFieldType(value, type)) {
                errors.add(itemPrefix + ".value 必须与字段 type 一致且不能为空。");
            } else if (!identities.add(typedValueIdentity(value, type))) {
                errors.add(itemPrefix + ".value 不能重复。");
            }
            requireValue(errors, item, FIELD_LABEL, itemPrefix + ".label");
            Object description = item.get(FIELD_DESCRIPTION);
            if (description != null && !(description instanceof String)) {
                errors.add(itemPrefix + ".description 必须是字符串。");
            }
        }
    }

    /** 入参 Demo 是 dry-run 的真实业务参数，受结构化枚举的同一闭集约束。 */
    private void validateInputExampleAllowedValues(List<String> errors, Object inputFieldsValue,
            Object inputExampleValue) {
        if (!(inputFieldsValue instanceof List) || !(inputExampleValue instanceof Map)) {
            return;
        }
        Map<String, Object> inputExample = mapValue(inputExampleValue);
        for (Object fieldValue : (List<?>) inputFieldsValue) {
            Map<String, Object> field = mapValue(fieldValue);
            if (!FIELD_SOURCE_MODEL_INPUT.equals(stringValue(field.get(FIELD_FIELD_SOURCE)))
                    || !(field.get(FIELD_ALLOWED_VALUES) instanceof List)) {
                continue;
            }
            String toolField = stringValue(field.get(FIELD_TOOL_FIELD));
            if (!inputExample.containsKey(toolField)) {
                continue;
            }
            String type = stringValue(field.get(FIELD_FIELD_TYPE));
            boolean matched = ((List<?>) field.get(FIELD_ALLOWED_VALUES)).stream()
                    .map(this::mapValue)
                    .map(item -> item.get(FIELD_VALUE))
                    .anyMatch(value -> typedValuesEqual(value, inputExample.get(toolField), type));
            if (!matched) {
                errors.add("参数契约.inputExampleJson." + toolField + " 必须命中 allowedValues 允许值。");
            }
        }
    }

    private boolean matchesFieldType(Object value, String type) {
        if (FIELD_TYPE_STRING.equals(type)) {
            return value instanceof String && StringUtils.isNotBlank((String) value);
        }
        if (FIELD_TYPE_INTEGER.equals(type)) {
            return CapabilityIntegerSupport.isInteger(value);
        }
        if (FIELD_TYPE_NUMBER.equals(type)) {
            return value instanceof Number;
        }
        if (FIELD_TYPE_BOOLEAN.equals(type)) {
            return value instanceof Boolean;
        }
        return FIELD_TYPE_ARRAY.equals(type) && value instanceof List;
    }

    private boolean typedValuesEqual(Object left, Object right, String type) {
        if (!matchesFieldType(left, type) || !matchesFieldType(right, type)) {
            return false;
        }
        return StringUtils.equalsAny(type, FIELD_TYPE_NUMBER, FIELD_TYPE_INTEGER)
                ? new BigDecimal(String.valueOf(left)).compareTo(new BigDecimal(String.valueOf(right))) == 0
                : left.equals(right);
    }

    private String typedValueIdentity(Object value, String type) {
        if (StringUtils.equalsAny(type, FIELD_TYPE_NUMBER, FIELD_TYPE_INTEGER)) {
            return "number:" + new BigDecimal(String.valueOf(value)).stripTrailingZeros().toPlainString();
        }
        return type + ":" + value;
    }

    /**
     * 校验 input Demo 中模型可见字段的真实 JSON 类型；数组元素按发布 Schema 递归检查。
     */
    private void validateInputExampleTypes(List<String> errors, Object inputFieldsValue,
            Object inputExampleValue) {
        if (!(inputFieldsValue instanceof List) || !(inputExampleValue instanceof Map)) {
            return;
        }
        Map<String, Object> inputExample = mapValue(inputExampleValue);
        for (Object fieldValue : (List<?>) inputFieldsValue) {
            Map<String, Object> field = mapValue(fieldValue);
            if (!FIELD_SOURCE_MODEL_INPUT.equals(stringValue(field.get(FIELD_FIELD_SOURCE)))) {
                continue;
            }
            String toolField = stringValue(field.get(FIELD_TOOL_FIELD));
            if (!inputExample.containsKey(toolField)) {
                continue;
            }
            validateInputSchemaValue(errors, inputExample.get(toolField), field,
                    "参数契约.inputExampleJson." + toolField, 0);
        }
    }

    /** 校验递归 items/properties 结构，阻止缺失元素 Schema 或未声明对象字段进入发布契约。 */
    private void validateInputSchemaNode(List<String> errors, Object schemaValue,
            String prefix, int depth) {
        if (depth > MAX_INPUT_SCHEMA_DEPTH) {
            errors.add(prefix + " 嵌套层级不能超过 " + MAX_INPUT_SCHEMA_DEPTH + " 层。");
            return;
        }
        Map<String, Object> schema = mapValue(schemaValue);
        if (schema.isEmpty()) {
            errors.add(prefix + " 必须是包含 type 的对象。");
            return;
        }
        String type = stringValue(schema.get(FIELD_FIELD_TYPE));
        if (!StringUtils.equalsAny(type, FIELD_TYPE_STRING, FIELD_TYPE_NUMBER, FIELD_TYPE_INTEGER,
                FIELD_TYPE_BOOLEAN, FIELD_TYPE_ARRAY, FIELD_TYPE_OBJECT)) {
            errors.add(prefix + ".type 只允许 string、number、integer、boolean、array 或 object。");
            return;
        }
        if (FIELD_TYPE_ARRAY.equals(type)) {
            validateInputSchemaNode(errors, schema.get(FIELD_ITEMS), prefix + ".items", depth + 1);
            return;
        }
        if (!FIELD_TYPE_OBJECT.equals(type)) {
            return;
        }
        Object propertiesValue = schema.get(FIELD_PROPERTIES);
        if (propertiesValue != null && !(propertiesValue instanceof Map)) {
            errors.add(prefix + ".properties 必须是字段名到 Schema 的对象。");
            return;
        }
        Map<String, Object> properties = mapValue(propertiesValue);
        properties.forEach((propertyName, propertySchema) -> {
            if (StringUtils.isBlank(propertyName)) {
                errors.add(prefix + ".properties 的字段名不能为空。");
                return;
            }
            validateInputSchemaNode(errors, propertySchema,
                    prefix + ".properties." + propertyName, depth + 1);
        });
        Object requiredValue = schema.get(FIELD_REQUIRED);
        if (requiredValue == null) {
            return;
        }
        if (!(requiredValue instanceof List)) {
            errors.add(prefix + ".required 必须是字段名数组。");
            return;
        }
        for (Object requiredField : (List<?>) requiredValue) {
            if (!(requiredField instanceof String)
                    || StringUtils.isBlank((String) requiredField)
                    || !properties.containsKey(requiredField)) {
                errors.add(prefix + ".required 只能引用 properties 中的非空字段名。");
                return;
            }
        }
    }

    /** 对示例值执行递归结构校验，并返回精确到数组下标/对象字段的错误路径。 */
    private void validateInputSchemaValue(List<String> errors, Object value,
            Map<String, Object> schema, String prefix, int depth) {
        if (value == null || depth > MAX_INPUT_SCHEMA_DEPTH) {
            return;
        }
        String type = stringValue(schema.get(FIELD_FIELD_TYPE));
        boolean matches = FIELD_TYPE_STRING.equals(type) ? value instanceof String
                : FIELD_TYPE_NUMBER.equals(type) ? value instanceof Number
                : FIELD_TYPE_INTEGER.equals(type) ? CapabilityIntegerSupport.isInteger(value)
                : FIELD_TYPE_BOOLEAN.equals(type) ? value instanceof Boolean
                : FIELD_TYPE_ARRAY.equals(type) ? value instanceof List
                : FIELD_TYPE_OBJECT.equals(type) && value instanceof Map;
        if (!matches) {
            errors.add(prefix + " 必须匹配声明类型 " + type + "。");
            return;
        }
        if (FIELD_TYPE_ARRAY.equals(type)) {
            Map<String, Object> items = mapValue(schema.get(FIELD_ITEMS));
            List<?> values = (List<?>) value;
            for (int index = 0; index < values.size(); index++) {
                validateInputSchemaValue(errors, values.get(index), items,
                        prefix + "[" + index + "]", depth + 1);
            }
            return;
        }
        if (!FIELD_TYPE_OBJECT.equals(type)) {
            return;
        }
        Map<String, Object> objectValue = mapValue(value);
        Map<String, Object> properties = mapValue(schema.get(FIELD_PROPERTIES));
        Object requiredValue = schema.get(FIELD_REQUIRED);
        if (requiredValue instanceof List) {
            for (Object requiredField : (List<?>) requiredValue) {
                if (requiredField instanceof String
                        && (!objectValue.containsKey(requiredField) || objectValue.get(requiredField) == null)) {
                    errors.add(prefix + "." + requiredField + " 是必填字段。");
                }
            }
        }
        objectValue.forEach((propertyName, propertyValue) -> {
            Map<String, Object> propertySchema = mapValue(properties.get(propertyName));
            if (propertySchema.isEmpty()) {
                errors.add(prefix + " 包含未声明字段 " + propertyName + "。");
                return;
            }
            validateInputSchemaValue(errors, propertyValue, propertySchema,
                    prefix + "." + propertyName, depth + 1);
        });
    }

    /** 校验作者可选的可信系统变量及 client 显式值映射。 */
    private void validateSystemVariable(List<String> errors, Map<String, Object> field,
            String type, String prefix) {
        String systemVariable = stringValue(field.get(FIELD_SYSTEM_VARIABLE));
        if (!StringUtils.equalsAny(systemVariable, SYSTEM_VARIABLE_USER_ID, SYSTEM_VARIABLE_CLIENT)) {
            errors.add(prefix + ".systemVariable 只允许 userId 或 client。");
            return;
        }
        if (SYSTEM_VARIABLE_USER_ID.equals(systemVariable) && !FIELD_TYPE_STRING.equals(type)) {
            errors.add(prefix + ".type 在 userId 系统变量下必须是 string（十进制用户 ID）。");
        }
        if (SYSTEM_VARIABLE_CLIENT.equals(systemVariable) && !FIELD_TYPE_STRING.equals(type)) {
            errors.add(prefix + ".type 在 client 系统变量下必须是 string。");
        }
        Object mappingValue = field.get(FIELD_VALUE_MAPPING);
        if (SYSTEM_VARIABLE_USER_ID.equals(systemVariable)
                && mappingValue instanceof Map<?, ?> && !((Map<?, ?>) mappingValue).isEmpty()) {
            errors.add(prefix + ".valueMapping 只允许用于 client 系统变量。");
            return;
        }
        if (mappingValue != null && !(mappingValue instanceof Map)) {
            errors.add(prefix + ".valueMapping 必须是字符串到字符串的对象。");
            return;
        }
        if (mappingValue instanceof Map<?, ?> mapping) {
            for (Map.Entry<?, ?> entry : mapping.entrySet()) {
                if (StringUtils.isBlank(String.valueOf(entry.getKey()))
                        || !(entry.getValue() instanceof String)
                        || StringUtils.isBlank((String) entry.getValue())) {
                    errors.add(prefix + ".valueMapping 只允许非空字符串到非空字符串的映射。");
                    return;
                }
            }
        }
    }

    /** 校验常量字段存在且与声明类型一致，避免把字符串常量误写进数字请求字段。 */
    private void validateConstantValue(List<String> errors, Map<String, Object> field,
            String type, String prefix) {
        Object value = field.get(FIELD_CONSTANT_VALUE);
        if (value == null || value instanceof String && StringUtils.isBlank((String) value)) {
            errors.add(prefix + ".constantValue 不能为空。");
            return;
        }
        if (FIELD_TYPE_INTEGER.equals(type) && !CapabilityIntegerSupport.isInteger(value)) {
            errors.add(prefix + ".constantValue 必须是整数，不能包含小数部分。");
        } else if (FIELD_TYPE_NUMBER.equals(type) && !(value instanceof Number)) {
            try {
                new BigDecimal(String.valueOf(value));
            } catch (NumberFormatException exception) {
                errors.add(prefix + ".constantValue 必须是数字。");
            }
        } else if (FIELD_TYPE_STRING.equals(type) && !(value instanceof String)) {
            errors.add(prefix + ".constantValue 必须是字符串。");
        } else if (FIELD_TYPE_BOOLEAN.equals(type) && !(value instanceof Boolean)) {
            errors.add(prefix + ".constantValue 必须是布尔值。");
        } else if (FIELD_TYPE_ARRAY.equals(type)) {
            if (!(value instanceof List)) {
                errors.add(prefix + ".constantValue 必须是数组。");
            } else {
                validateInputSchemaValue(errors, value, field, prefix + ".constantValue", 0);
            }
        }
    }

    /**
     * 校验关键出参字段能在脱敏响应 Demo 中真实命中，避免人工维护完整复杂出参表单。
     */
    private void validateKeyOutputFields(List<String> errors, Map<String, Object> resultContract) {
        Object responseDemo = parseJsonObject(errors, resultContract, FIELD_RESPONSE_DEMO_JSON,
                "结果契约.responseDemoJson");
        Object keyOutputFieldsValue = resultContract.get(FIELD_KEY_OUTPUT_FIELDS);
        if (!(keyOutputFieldsValue instanceof List)) {
            errors.add("结果契约.keyOutputFields 必须是数组。");
            return;
        }
        List<?> keyOutputFields = (List<?>) keyOutputFieldsValue;
        if (keyOutputFields.isEmpty()) {
            errors.add("结果契约.keyOutputFields 至少需要一个关键字段。");
        }
        for (int index = 0; index < keyOutputFields.size(); index++) {
            Map<String, Object> field = mapValue(keyOutputFields.get(index));
            String prefix = "结果契约.keyOutputFields[" + index + "]";
            if (field.isEmpty()) {
                errors.add(prefix + " 必须是对象。");
                continue;
            }
            requireValue(errors, field, FIELD_PATH, prefix + ".path");
            requireValue(errors, field, FIELD_DESCRIPTION, prefix + ".description");
            String path = stringValue(field.get(FIELD_PATH));
            if (responseDemo != null && StringUtils.isNotBlank(path)
                    && resolvePathValues(responseDemo, path).isEmpty()) {
                errors.add(prefix + ".path 未在 responseDemoJson 中命中: " + path + "。");
            }
        }
    }

    /**
     * 校验能力可选展示方案及其结果映射。
     *
     * <p>组件引用只描述能力能够如何展示，不代表 Skill 一定启用渲染。这里仅校验组件身份快照和
     * `组件参数路径 -> 能力结果路径` 映射；组件启用状态由组件中心及 Skill 渲染绑定门禁校验。
     */
    private void validatePresentationComponents(List<String> errors, Map<String, Object> resultContract) {
        Object componentsValue = resultContract.get(FIELD_PRESENTATION_COMPONENTS);
        if (componentsValue == null) {
            return;
        }
        if (!(componentsValue instanceof List)) {
            errors.add("结果契约.presentationComponents 必须是数组。");
            return;
        }
        Object responseDemo = parseJsonObject(stringValue(resultContract.get(FIELD_RESPONSE_DEMO_JSON)));
        Set<String> identities = new HashSet<>();
        List<?> components = (List<?>) componentsValue;
        for (int index = 0; index < components.size(); index++) {
            Map<String, Object> component = mapValue(components.get(index));
            String prefix = "结果契约.presentationComponents[" + index + "]";
            if (component.isEmpty()) {
                errors.add(prefix + " 必须是对象。");
                continue;
            }
            requirePositiveLong(errors, component, FIELD_ASSET_ID, prefix + ".assetId");
            requireValue(errors, component, FIELD_COMPONENT_NAME, prefix + ".componentName");
            requireValue(errors, component, FIELD_COMPONENT_VERSION, prefix + ".componentVersion");
            requireValue(errors, component, FIELD_USAGE, prefix + ".usage");
            String usage = stringValue(component.get(FIELD_USAGE));
            if (StringUtils.isNotBlank(usage) && !PRESENTATION_USAGES.contains(usage)) {
                errors.add(prefix + ".usage 不受支持: " + usage + "。");
            }
            String identity = stringValue(component.get(FIELD_COMPONENT_NAME)) + "::" + usage;
            if (!identities.add(identity)) {
                errors.add(prefix + " 与其他包装组件的 componentName + usage 重复。");
            }
            validatePresentationParamsMapping(errors, component.get(FIELD_PARAMS_MAPPING), responseDemo, prefix);
        }
    }

    private void validatePresentationParamsMapping(List<String> errors, Object mappingValue,
            Object responseDemo, String prefix) {
        if (!(mappingValue instanceof Map) || ((Map<?, ?>) mappingValue).isEmpty()) {
            errors.add(prefix + ".paramsMapping 至少需要一个组件参数到能力结果路径的映射。");
            return;
        }
        mapValue(mappingValue).forEach((componentParam, resultPathValue) -> {
            String resultPath = stringValue(resultPathValue);
            if (!COMPONENT_PARAM_PATH_PATTERN.matcher(componentParam).matches()) {
                errors.add(prefix + ".paramsMapping 组件参数路径不合法: " + componentParam + "。");
            }
            if (StringUtils.isBlank(resultPath)) {
                errors.add(prefix + ".paramsMapping[" + componentParam + "] 结果路径不能为空。");
            } else if (responseDemo != null && resolvePathValues(responseDemo, resultPath).isEmpty()) {
                errors.add(prefix + ".paramsMapping[" + componentParam
                        + "] 未在 responseDemoJson 中命中: " + resultPath + "。");
            }
        });
    }

    private void requirePositiveLong(List<String> errors, Map<String, Object> values,
            String field, String displayName) {
        String value = stringValue(values.get(field));
        try {
            if (StringUtils.isBlank(value) || Long.parseLong(value) <= 0L) {
                throw new NumberFormatException(value);
            }
        } catch (NumberFormatException e) {
            errors.add(displayName + " 必须是正整数。");
        }
    }

    /**
     * 校验入参/出参 Few-shot Demo 是合法 JSON，防止把不可解析文本注入模型契约。
     */
    private Object validateContractExample(List<String> errors, Map<String, Object> section, String field,
            String displayName) {
        return parseJsonObject(errors, section, field, displayName);
    }

    private Object parseJsonObject(List<String> errors, Map<String, Object> section, String field,
            String displayName) {
        String exampleJson = stringValue(section.get(field));
        if (StringUtils.isBlank(exampleJson)) {
            errors.add(displayName + " 不能为空。");
            return null;
        }
        try {
            Object example = JsonSupport.fromJSON(exampleJson, Object.class);
            if (!(example instanceof Map)) {
                errors.add(displayName + " 必须是 JSON 对象。");
                return null;
            }
            return example;
        } catch (Exception e) {
            errors.add(displayName + " 必须是合法 JSON。");
            return null;
        }
    }

    /**
     * 按绑定类型校验固定服务目标和请求映射；模型不能通过草稿提供任意 URL。
     */
    private void validateExecutionBinding(List<String> errors, Map<String, Object> executionBinding,
            String sourceType) {
        if (!"GRPC".equals(sourceType)) {
            errors.add("只允许 GRPC 执行绑定，不支持 HTTP 或本地方法兜底。");
            return;
        }
        try { dev.a2flow.management.capabilityrpc.GrpcCapabilityContract.validateBinding(executionBinding); }
        catch (IllegalArgumentException failure) { errors.add("GRPC执行绑定：" + failure.getMessage()); }
        validateJsonMap(errors, executionBinding, FIELD_REQUEST_MAPPINGS_JSON, "执行绑定.requestMappingsJson", true);
        validateJsonMap(errors, executionBinding, FIELD_CONTEXT_MAPPINGS_JSON, "执行绑定.contextMappingsJson", true);
    }

    private void validateJsonMap(List<String> errors, Map<String, Object> section, String field,
            String displayName, boolean allowEmpty) {
        String json = stringValue(section.get(field));
        if (StringUtils.isBlank(json)) {
            if (!allowEmpty) {
                errors.add(displayName + " 不能为空。");
            }
            return;
        }
        try {
            Object parsed = JsonSupport.fromJSON(json, Object.class);
            if (!(parsed instanceof Map)) {
                errors.add(displayName + " 必须是 JSON 对象。");
                return;
            }
            if (!allowEmpty && ((Map<?, ?>) parsed).isEmpty()) {
                errors.add(displayName + " 至少需要一个字段映射。");
                return;
            }
            if (FIELD_STATIC_HEADERS_JSON.equals(field)) {
                for (Object key : ((Map<?, ?>) parsed).keySet()) {
                    String normalized = StringUtils.lowerCase(String.valueOf(key), Locale.ROOT);
                    if (SENSITIVE_FIELD_NAMES.contains(normalized) || Set.of(
                            "host", "content-type", "content-length", "connection", "transfer-encoding")
                            .contains(normalized)) {
                        errors.add(displayName + " 不允许配置凭证或受控传输 Header。");
                        return;
                    }
                }
            }
        } catch (Exception e) {
            errors.add(displayName + " 必须是合法 JSON 对象。");
        }
    }

    /**
     * 校验副作用和审批策略，写操作不得配置为无需确认的自动执行。
     */
    private void validateGovernance(List<String> errors, Map<String, Object> governance) {
        requireValue(errors, governance, FIELD_SIDE_EFFECT_LEVEL, "治理.sideEffectLevel");
        requireValue(errors, governance, FIELD_APPROVAL_POLICY, "治理.approvalPolicy");
        String sideEffectLevel = stringValue(governance.get(FIELD_SIDE_EFFECT_LEVEL));
        String approvalPolicy = stringValue(governance.get(FIELD_APPROVAL_POLICY));
        if ((SIDE_EFFECT_WRITE.equals(sideEffectLevel) || SIDE_EFFECT_DESTRUCTIVE.equals(sideEffectLevel))
                && APPROVAL_AUTO_EXECUTE.equals(approvalPolicy)) {
            errors.add("WRITE/DESTRUCTIVE 能力不能使用 AUTO_EXECUTE 审批策略。");
        }
    }

    private Map<String, Object> initialDraft() {
        Map<String, Object> draft = new LinkedHashMap<>();
        draft.put(FIELD_PAYLOAD_TYPE, PAYLOAD_TYPE_SNAPSHOT);
        draft.put(FIELD_MODE, MODE_CREATE);
        draft.put(FIELD_BASIC_INFO, new LinkedHashMap<>());
        draft.put(FIELD_SUPPORTED_CLIENTS, List.of(CLIENT_PC));
        Map<String, Object> clientVariants = new LinkedHashMap<>();
        clientVariants.put(CLIENT_PC, initialTechnicalVariant());
        draft.put(FIELD_CLIENT_VARIANTS, clientVariants);
        Map<String, Object> governance = new LinkedHashMap<>();
        governance.put(FIELD_SIDE_EFFECT_LEVEL, SIDE_EFFECT_READ);
        governance.put(FIELD_APPROVAL_POLICY, APPROVAL_REQUEST);
        draft.put(FIELD_GOVERNANCE, governance);
        return draft;
    }

    /** 构造单端技术契约默认值；公共身份和治理字段不进入端内结构。 */
    private Map<String, Object> initialTechnicalVariant() {
        Map<String, Object> variant = new LinkedHashMap<>();
        Map<String, Object> apiSource = new LinkedHashMap<>();
        apiSource.put(FIELD_SOURCE_TYPE, "GRPC");
        variant.put(FIELD_API_SOURCE, apiSource);
        Map<String, Object> modelContract = new LinkedHashMap<>();
        modelContract.put(FIELD_INPUT_FIELDS, new ArrayList<>());
        modelContract.put(FIELD_INPUT_EXAMPLE_JSON, StringUtils.EMPTY);
        variant.put(FIELD_MODEL_CONTRACT, modelContract);
        Map<String, Object> executionBinding = new LinkedHashMap<>();
        executionBinding.put(FIELD_BINDING_TYPE, "GRPC");
        executionBinding.put(FIELD_TARGET, new LinkedHashMap<>());
        executionBinding.put(FIELD_REQUEST_MAPPINGS_JSON, emptyJsonObject());
        executionBinding.put(FIELD_CONTEXT_MAPPINGS_JSON, emptyJsonObject());
        executionBinding.put(FIELD_TIMEOUT_MS, DEFAULT_HTTP_TIMEOUT_MS);
        executionBinding.put(FIELD_MAX_RESPONSE_BYTES, DEFAULT_MAX_RESPONSE_BYTES);
        executionBinding.put(FIELD_IDEMPOTENCY, IDEMPOTENCY_NONE);
        executionBinding.put(FIELD_RESPONSE_POLICY, RESPONSE_POLICY_ORIGINAL);
        variant.put(FIELD_EXECUTION_BINDING, executionBinding);
        Map<String, Object> resultContract = new LinkedHashMap<>();
        resultContract.put(FIELD_KEY_OUTPUT_FIELDS, new ArrayList<>());
        resultContract.put(FIELD_RESPONSE_DEMO_JSON, StringUtils.EMPTY);
        variant.put(FIELD_RESULT_CONTRACT, resultContract);
        return variant;
    }

    /**
     * 重建模型入参契约，只保留当前开发协议允许的字段，避免旧策略字段继续影响 AI 和运行时。
     */
    private Map<String, Object> canonicalModelContract(Map<String, Object> source) {
        Map<String, Object> result = new LinkedHashMap<>();
        copyField(source, result, FIELD_DESCRIPTION);
        copyField(source, result, FIELD_INPUT_EXAMPLE_JSON);
        List<Map<String, Object>> inputFields = new ArrayList<>();
        Object fieldsValue = source.get(FIELD_INPUT_FIELDS);
        if (fieldsValue instanceof List) {
            for (Object item : (List<?>) fieldsValue) {
                Map<String, Object> sourceField = mapValue(item);
                Map<String, Object> field = new LinkedHashMap<>();
                copyField(sourceField, field, FIELD_TOOL_FIELD);
                copyField(sourceField, field, FIELD_FIELD_TYPE);
                if (FIELD_TYPE_ARRAY.equals(stringValue(sourceField.get(FIELD_FIELD_TYPE)))) {
                    field.put(FIELD_ITEMS, canonicalInputSchemaNode(sourceField.get(FIELD_ITEMS)));
                }
                copyField(sourceField, field, FIELD_BUSINESS_MEANING);
                copyField(sourceField, field, FIELD_UNIT);
                copyField(sourceField, field, FIELD_FIELD_SOURCE);
                copyField(sourceField, field, FIELD_EXAMPLES);
                if (FIELD_SOURCE_CONSTANT.equals(stringValue(sourceField.get(FIELD_FIELD_SOURCE)))) {
                    copyField(sourceField, field, FIELD_CONSTANT_VALUE);
                } else if (FIELD_SOURCE_SYSTEM_VARIABLE.equals(
                        stringValue(sourceField.get(FIELD_FIELD_SOURCE)))) {
                    copyField(sourceField, field, FIELD_SYSTEM_VARIABLE);
                    if (SYSTEM_VARIABLE_CLIENT.equals(stringValue(sourceField.get(FIELD_SYSTEM_VARIABLE)))) {
                        field.put(FIELD_VALUE_MAPPING,
                                canonicalSystemVariableMapping(sourceField.get(FIELD_VALUE_MAPPING)));
                    }
                } else {
                    copyField(sourceField, field, FIELD_REQUIRED);
                    if (FIELD_SOURCE_MODEL_INPUT.equals(
                            stringValue(sourceField.get(FIELD_FIELD_SOURCE)))
                            && sourceField.containsKey(FIELD_ALLOWED_VALUES)) {
                        field.put(FIELD_ALLOWED_VALUES,
                                canonicalAllowedValues(sourceField.get(FIELD_ALLOWED_VALUES)));
                    }
                }
                inputFields.add(field);
            }
        }
        result.put(FIELD_INPUT_FIELDS, inputFields);
        return result;
    }

    /** 递归保留标准 items/properties/required 结构，同时保留非法外形供静态校验明确报错。 */
    private Object canonicalInputSchemaNode(Object value) {
        if (!(value instanceof Map)) {
            return value;
        }
        Map<String, Object> source = mapValue(value);
        Map<String, Object> result = new LinkedHashMap<>();
        copyField(source, result, FIELD_FIELD_TYPE);
        copyField(source, result, FIELD_DESCRIPTION);
        if (source.containsKey(FIELD_ITEMS)) {
            result.put(FIELD_ITEMS, canonicalInputSchemaNode(source.get(FIELD_ITEMS)));
        }
        if (source.containsKey(FIELD_PROPERTIES)) {
            Object propertiesValue = source.get(FIELD_PROPERTIES);
            if (!(propertiesValue instanceof Map)) {
                result.put(FIELD_PROPERTIES, propertiesValue);
            } else {
                Map<String, Object> properties = new LinkedHashMap<>();
                mapValue(propertiesValue).forEach((name, schema) ->
                        properties.put(name, canonicalInputSchemaNode(schema)));
                result.put(FIELD_PROPERTIES, properties);
            }
        }
        copyField(source, result, FIELD_REQUIRED);
        return result;
    }

    /** 枚举只保留可审阅协议字段，同时保留非法外形供静态校验明确报错。 */
    private Object canonicalAllowedValues(Object value) {
        if (!(value instanceof List)) {
            return value;
        }
        List<Map<String, Object>> result = new ArrayList<>();
        for (Object itemValue : (List<?>) value) {
            Map<String, Object> source = mapValue(itemValue);
            Map<String, Object> item = new LinkedHashMap<>();
            copyField(source, item, FIELD_VALUE);
            copyField(source, item, FIELD_LABEL);
            copyField(source, item, FIELD_DESCRIPTION);
            result.add(item);
        }
        return result;
    }

    /** 保留非法映射值供静态校验明确报错，不能在规范化阶段悄悄丢弃。 */
    private Object canonicalSystemVariableMapping(Object value) {
        if (value == null) {
            return new LinkedHashMap<>();
        }
        if (!(value instanceof Map<?, ?>)) {
            return value;
        }
        Map<String, Object> result = new LinkedHashMap<>();
        ((Map<?, ?>) value).forEach((key, mappedValue) -> {
            String normalizedKey = StringUtils.trimToEmpty(String.valueOf(key));
            Object normalizedValue = mappedValue instanceof String
                    ? StringUtils.trimToEmpty((String) mappedValue) : mappedValue;
            result.put(normalizedKey, normalizedValue);
        });
        return result;
    }

    private String emptyJsonObject() {
        return JsonSupport.toJSON(Collections.emptyMap());
    }

    /**
     * 重建结果契约并覆盖所有系统推导字段。
     *
     * <p>用户只维护响应 Demo、关键字段路径和业务说明；技术 Schema 与识别类型必须由服务端根据
     * 同一份 Demo 生成，不能接受模型或前端传入的类型结论。
     */
    private Map<String, Object> canonicalResultContract(Map<String, Object> source) {
        Map<String, Object> result = new LinkedHashMap<>();
        String responseDemoJson = stringValue(source.get(FIELD_RESPONSE_DEMO_JSON));
        result.put(FIELD_RESPONSE_DEMO_JSON, responseDemoJson);
        Object responseDemo = parseJsonObject(responseDemoJson);

        List<Object> keyOutputFields = new ArrayList<>();
        Object fieldsValue = source.get(FIELD_KEY_OUTPUT_FIELDS);
        if (fieldsValue instanceof List) {
            for (Object item : (List<?>) fieldsValue) {
                Map<String, Object> sourceField = mapValue(item);
                Map<String, Object> field = new LinkedHashMap<>();
                copyField(sourceField, field, FIELD_PATH);
                copyField(sourceField, field, FIELD_DESCRIPTION);
                List<Object> resolvedValues = resolvePathValues(responseDemo,
                        stringValue(sourceField.get(FIELD_PATH)));
                if (!resolvedValues.isEmpty()) {
                    field.put(FIELD_OBSERVED_TYPE, observedType(resolvedValues));
                }
                keyOutputFields.add(field);
            }
        }
        result.put(FIELD_KEY_OUTPUT_FIELDS, keyOutputFields);
        if (responseDemo != null) {
            result.put(FIELD_TECHNICAL_OUTPUT_SCHEMA, JsonSupport.toJSON(buildTechnicalSchema(responseDemo)));
        }
        copyField(source, result, FIELD_ERROR_MAPPINGS);
        result.put(FIELD_PRESENTATION_COMPONENTS,
                canonicalPresentationComponents(source.get(FIELD_PRESENTATION_COMPONENTS)));
        return result;
    }

    /**
     * 规范化能力可选展示方案，只保留组件中心身份、版本、用途和结构化参数映射。
     */
    private List<Map<String, Object>> canonicalPresentationComponents(Object value) {
        if (!(value instanceof List)) {
            return new ArrayList<>();
        }
        List<Map<String, Object>> result = new ArrayList<>();
        for (Object item : (List<?>) value) {
            Map<String, Object> source = mapValue(item);
            if (source.isEmpty()) {
                continue;
            }
            Map<String, Object> component = new LinkedHashMap<>();
            copyField(source, component, FIELD_ASSET_ID);
            copyField(source, component, FIELD_COMPONENT_NAME);
            copyField(source, component, FIELD_COMPONENT_NAME_CN);
            copyField(source, component, FIELD_ASSET_TYPE);
            copyField(source, component, FIELD_RENDER_PROTOCOL);
            copyField(source, component, FIELD_COMPONENT_VERSION);
            copyField(source, component, FIELD_PROTOCOL_VERSION);
            copyField(source, component, FIELD_USAGE);
            component.put(FIELD_PARAMS_MAPPING, canonicalStringMap(source.get(FIELD_PARAMS_MAPPING)));
            result.add(component);
        }
        return result;
    }

    private Map<String, String> canonicalStringMap(Object value) {
        if (!(value instanceof Map)) {
            return new LinkedHashMap<>();
        }
        Map<String, String> result = new LinkedHashMap<>();
        mapValue(value).forEach((key, mapValue) -> {
            String normalizedKey = StringUtils.trimToEmpty(key);
            String normalizedValue = StringUtils.trimToEmpty(stringValue(mapValue));
            if (StringUtils.isNotBlank(normalizedKey) || StringUtils.isNotBlank(normalizedValue)) {
                result.put(normalizedKey, normalizedValue);
            }
        });
        return result;
    }

    private void copyField(Map<String, Object> source, Map<String, Object> target, String field) {
        if (source.containsKey(field)) {
            target.put(field, source.get(field));
        }
    }

    /**
     * 从脱敏响应 Demo 递归生成只读技术 Schema，供运行态编译和审阅使用。
     */
    private Map<String, Object> buildTechnicalSchema(Object value) {
        Map<String, Object> schema = new LinkedHashMap<>();
        if (value instanceof Map) {
            schema.put(FIELD_FIELD_TYPE, "object");
            Map<String, Object> properties = new LinkedHashMap<>();
            mapValue(value).forEach((key, childValue) -> properties.put(key, buildTechnicalSchema(childValue)));
            schema.put(FIELD_PROPERTIES, properties);
            return schema;
        }
        if (value instanceof List) {
            schema.put(FIELD_FIELD_TYPE, "array");
            Object sample = ((List<?>) value).stream().filter(item -> item != null).findFirst().orElse(null);
            schema.put(FIELD_ITEMS, sample == null ? new LinkedHashMap<>() : buildTechnicalSchema(sample));
            return schema;
        }
        schema.put(FIELD_FIELD_TYPE, scalarType(value));
        return schema;
    }

    /**
     * 解析点路径和数组路径。数组段使用 `[]`，例如 data.cards[].url。
     */
    private List<Object> resolvePathValues(Object root, String path) {
        if (root == null || StringUtils.isBlank(path)) {
            return Collections.emptyList();
        }
        List<Object> currentValues = new ArrayList<>();
        currentValues.add(root);
        for (String segment : path.split("\\.", -1)) {
            if (!KEY_OUTPUT_PATH_SEGMENT_PATTERN.matcher(segment).matches()) {
                return Collections.emptyList();
            }
            boolean arraySegment = segment.endsWith("[]");
            String key = arraySegment ? segment.substring(0, segment.length() - 2) : segment;
            List<Object> nextValues = new ArrayList<>();
            for (Object currentValue : currentValues) {
                if (!(currentValue instanceof Map)) {
                    continue;
                }
                Map<String, Object> currentMap = mapValue(currentValue);
                if (!currentMap.containsKey(key)) {
                    continue;
                }
                Object nextValue = currentMap.get(key);
                if (arraySegment) {
                    if (nextValue instanceof List) {
                        nextValues.addAll((List<?>) nextValue);
                    }
                } else {
                    nextValues.add(nextValue);
                }
            }
            if (nextValues.isEmpty()) {
                return Collections.emptyList();
            }
            currentValues = nextValues;
        }
        return currentValues;
    }

    private String observedType(List<Object> values) {
        Object sample = values.stream().filter(value -> value != null).findFirst().orElse(null);
        return scalarType(sample);
    }

    private String scalarType(Object value) {
        if (value == null) {
            return "null";
        }
        if (value instanceof Map) {
            return "object";
        }
        if (value instanceof List) {
            return "array";
        }
        if (value instanceof Boolean) {
            return "boolean";
        }
        if (value instanceof Byte || value instanceof Short || value instanceof Integer || value instanceof Long) {
            return "integer";
        }
        if (value instanceof Number) {
            return "number";
        }
        return "string";
    }

    private Object parseJsonObject(String json) {
        if (StringUtils.isBlank(json)) {
            return null;
        }
        try {
            Object parsed = JsonSupport.fromJSON(json, Object.class);
            return parsed instanceof Map ? parsed : null;
        } catch (Exception e) {
            return null;
        }
    }

    private void mergeSection(Map<String, Object> canonical, Map<String, Object> proposed, String sectionName) {
        Map<String, Object> merged = new LinkedHashMap<>(mapValue(canonical.get(sectionName)));
        merged.putAll(mapValue(proposed.get(sectionName)));
        canonical.put(sectionName, merged);
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> parseDraftJson(String draftJson) {
        if (StringUtils.isBlank(draftJson)) {
            throw new IllegalArgumentException(ERROR_DRAFT_JSON_REQUIRED);
        }
        try {
            Map<String, Object> draft = JsonSupport.fromJSON(draftJson, Map.class);
            if (draft == null) {
                throw new IllegalArgumentException(ERROR_DRAFT_JSON_INVALID);
            }
            return sanitizeDraft(draft);
        } catch (Exception e) {
            throw new IllegalArgumentException(ERROR_DRAFT_JSON_INVALID, e);
        }
    }

    /**
     * 在 canonical draft 持久化前递归移除敏感值。
     *
     * <p>字段语义和运行时凭证来源枚举可以保留，但 Cookie、Authorization、token、密码等具体值
     * 以及携带这些信息的原始 curl 文本只能保存脱敏标记，不能进入 mock、数据库或后续模型上下文。
     */
    private Map<String, Object> sanitizeDraft(Map<String, Object> source) {
        Map<String, Object> sanitized = new LinkedHashMap<>();
        source.forEach((key, value) -> sanitized.put(key, sanitizeDraftValue(key, value)));
        return sanitized;
    }

    private Object sanitizeDraftValue(String key, Object value) {
        String normalizedKey = StringUtils.defaultString(key)
                .replaceAll("[^a-zA-Z0-9]", StringUtils.EMPTY)
                .toLowerCase(Locale.ROOT);
        if (SENSITIVE_FIELD_NAMES.contains(normalizedKey) && value != null) {
            return REDACTED_VALUE;
        }
        if (value instanceof Map) {
            return sanitizeDraft(mapValue(value));
        }
        if (value instanceof List) {
            List<Object> sanitized = new ArrayList<>();
            for (Object item : (List<?>) value) {
                sanitized.add(sanitizeDraftValue(StringUtils.EMPTY, item));
            }
            return sanitized;
        }
        if (value instanceof String && SENSITIVE_REQUEST_TEXT_PATTERN.matcher((String) value).find()) {
            return REDACTED_REQUEST_VALUE;
        }
        return value;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> mapValue(Object value) {
        return value instanceof Map ? (Map<String, Object>) value : Collections.emptyMap();
    }

    private String nestedString(Map<String, Object> draft, String parent, String key) {
        return stringValue(mapValue(draft.get(parent)).get(key));
    }

    private CapabilityActionDraft publishedDraft(PublishedAssetSnapshot published) {
        if (published == null || published.getSnapshot() == null
                || StringUtils.isBlank(published.getSnapshot().getPayloadJson())) {
            throw new IllegalStateException("published capability snapshot is empty");
        }
        CapabilityActionDraft draft = JsonSupport.fromJSON(
                published.getSnapshot().getPayloadJson(), CapabilityActionDraft.class);
        if (draft == null) {
            throw new IllegalStateException("published capability snapshot is invalid");
        }
        return draft.setPublished(true).setPublishedVersion(published.getVersion());
    }

    private boolean matchesPublishedKeyword(CapabilityActionDraft draft, String keyword) {
        if (StringUtils.isBlank(keyword)) {
            return true;
        }
        return Stream.of(
                        draft.getDraftId(),
                        nestedString(draft.getDraft(), FIELD_BASIC_INFO, FIELD_ACTION_CODE),
                        nestedString(draft.getDraft(), FIELD_BASIC_INFO, FIELD_NAME_CN),
                        nestedString(draft.getDraft(), FIELD_BASIC_INFO, FIELD_DESCRIPTION))
                .filter(StringUtils::isNotBlank)
                .map(StringUtils::lowerCase)
                .anyMatch(value -> StringUtils.contains(value, keyword));
    }

    private void requireValue(List<String> errors, Map<String, Object> source, String key, String displayName) {
        if (StringUtils.isBlank(stringValue(source.get(key)))) {
            errors.add(displayName + " 不能为空。");
        }
    }

    private String required(Map<String, String> params, String key) {
        String value = value(params, key);
        if (StringUtils.isBlank(value)) {
            throw new IllegalArgumentException(key + " is required");
        }
        return value;
    }

    private String value(Map<String, String> params, String key) {
        return params == null ? StringUtils.EMPTY : StringUtils.defaultString(params.get(key));
    }

    private int integer(String value, String field) {
        try {
            return Integer.parseInt(value);
        } catch (NumberFormatException e) {
            throw new IllegalArgumentException(field + " must be an integer");
        }
    }

    private String stringValue(Object value) {
        return value == null ? StringUtils.EMPTY : String.valueOf(value);
    }
}
