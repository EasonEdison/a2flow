package dev.a2flow.management.lifecycle;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Collectors;
import java.util.stream.Stream;

import jakarta.annotation.Resource;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.access.AssetAction;
import dev.a2flow.management.access.AssetAuthorizationService;
import dev.a2flow.management.access.AssetCreationTransactionService;
import dev.a2flow.management.lifecycle.domain.ComponentAsset;
import dev.a2flow.management.model.SkillFactoryComponentAsset;
import dev.a2flow.management.model.SkillFactoryComponentPreviewResult;
import dev.a2flow.management.model.SkillFactoryRenderPreviewResult;
import dev.a2flow.management.release.AssetReleaseEditGuard;
import dev.a2flow.management.release.PublishedAssetQueryService;
import dev.a2flow.management.release.ReleaseAssetType;
import dev.a2flow.management.release.ReleaseModels.PublishedAssetSnapshot;
import dev.a2flow.management.storage.db.repository.SkillFactoryComponentAssetRepository;

import lombok.extern.slf4j.Slf4j;

/**
 * SkillFactory 组件中心 Service。
 *
 * <p>该类承接 sellerdata SkillFactory 组件中心 method 的业务语义：组件资产注册、查询、
 * 编辑、下线、enabled 列表和官方 demo / 自定义 JSON 校验。它不负责 M 端鉴权、
 * 不实现 adviser SSE/controller，也不执行真实 B 端 A2UI action；这些边界分别由
 * M 端入口、adviser 编排和业务运行时负责。
 */
@SuppressWarnings("checkstyle:LineLength")
@Service
@Slf4j
public class SkillFactoryComponentRegistryService {

    private static final String EMPTY = "";
    private static final String VALUE_ALL = "ALL";
    private static final String JSON_ARRAY_PREFIX = "[";
    private static final String JSON_FIELD_TYPE = "type";
    private static final String JSON_FIELD_DSL_TYPE = "dslType";
    private static final String JSON_FIELD_AGENT_UI_DSL = "agentUiDsl";
    private static final String JSON_FIELD_PARAMS = "params";
    private static final String JSON_FIELD_DATA = "data";
    private static final String JSON_FIELD_CARD_TYPE = "cardType";
    private static final String JSON_FIELD_BIZ_TYPE = "bizType";
    private static final String JSON_FIELD_REQUIRED = "required";
    private static final String JSON_FIELD_PROPERTIES = "properties";

    private static final String PARAM_ID = "id";
    private static final String PARAM_KEYWORD = "keyword";
    private static final String PARAM_ASSET_TYPE = "assetType";
    private static final String PARAM_COMPONENT_NAME = "componentName";
    private static final String PARAM_COMPONENT_NAME_CN = "componentNameCn";
    private static final String PARAM_DSL_TYPE = "dslType";
    private static final String PARAM_AGENT_UI_DSL = "agentUiDsl";
    private static final String PARAM_PROTOCOL_VERSION = "protocolVersion";
    private static final String PARAM_INTERACTION_MODE = "interactionMode";
    private static final String PARAM_BUNDLE_URL = "bundleUrl";
    private static final String PARAM_APP_BUNDLE_URL = "appBundleUrl";
    private static final String PARAM_OWNER = "owner";
    private static final String PARAM_SCENE = "scene";
    private static final String PARAM_PARAMS_SCHEMA_JSON = "paramsSchemaJson";
    private static final String PARAM_RENDER_TEMPLATE_JSON = "renderTemplateJson";
    private static final String PARAM_OFFICIAL_DEMO_JSON = "officialDemoJson";
    private static final String PARAM_MESSAGE_DEMO_JSON = "messageDemoJson";
    private static final String PARAM_INTEGRATION_PROMPT = "integrationPrompt";
    private static final String PARAM_ALLOWED_ACTIONS_JSON = "allowedActionsJson";
    private static final String PARAM_RUNTIME_CONFIG_JSON = "runtimeConfigJson";
    private static final String PARAM_SUPPORT_CLIENTS = "supportClients";
    private static final String PARAM_ATTRIBUTE = "attribute";
    private static final String PARAM_ENABLED = "enabled";
    private static final String PARAM_OWNERS_JSON = "ownersJson";
    private static final String PARAM_ENABLED_ONLY = "enabledOnly";
    private static final String PARAM_PREVIEW_JSON = "previewJson";
    private static final String PARAM_ASSETS_JSON = "assetsJson";
    private static final String PARAM_INPUT_MODE = "inputMode";
    private static final String PARAM_RENDER_TEXT = "renderText";
    private static final String PARAM_SOURCE = "source";
    private static final String PARAM_CLIENT_TYPE = "clientType";
    private static final String PARAM_PARAMS = "params";
    private static final String PARAM_DATA = "data";
    private static final String ACTION_UPDATE_COMPONENT = "更新渲染组件";
    private static final String ACTION_UPDATE_COMPONENT_BASIC_INFO = "更新渲染组件基础信息";

    private static final String INPUT_MODE_BUSINESS_DSL = "BUSINESS_DSL";
    private static final String INPUT_MODE_CARD_CONTAINER = "CARD_CONTAINER";
    private static final String INPUT_MODE_RAW_TEXT = "RAW_TEXT";
    private static final String RENDER_MARKER_START = "@@KS_COMPONENT_START@@";
    private static final String RENDER_MARKER_END = "@@KS_COMPONENT_END@@";
    private static final String DEFAULT_CLIENT_TYPE_PC = "PC";
    private static final int DEFAULT_PROTOCOL_VERSION = 1;
    private static final String ASSET_TYPE_CARD_COMPONENT = "CARD_COMPONENT";
    private static final String ASSET_TYPE_BUSINESS_DSL = "BUSINESS_DSL";
    private static final String ASSET_TYPE_A2UI_ATOM = "A2UI_ATOM";
    private static final String PROTOCOL_CARD_CONTAINER = "CARD_CONTAINER";
    private static final String PROTOCOL_A2UI = "A2UI";
    private static final String DSL_TYPE_CARD_CONTAINER = "CARD_CONTAINER";
    private static final String DSL_TYPE_BUSINESS_DSL = "BUSINESS_DSL";
    private static final String INTERACTION_MODE_DISPLAY_ONLY = "DISPLAY_ONLY";
    private static final String INTERACTION_MODE_INTERACTIVE = "INTERACTIVE";

    private static final String ERROR_REQUIRED_SUFFIX = " is required";
    private static final String ERROR_ID_INVALID = "id is invalid";
    private static final String ERROR_ASSET_NOT_FOUND = "component asset not found";
    private static final String ERROR_DUPLICATE_COMPONENT_IDENTITY =
            "component asset already exists with same assetType/componentName";
    private static final String ERROR_DUPLICATE_BUSINESS_DSL_IDENTITY =
            "component asset already exists with same dslType/agentUiDsl";
    private static final String ERROR_RELEASE_SNAPSHOT_IDENTITY_MISMATCH =
            "component release snapshot identity does not match current asset";
    private static final String ERROR_UNSUPPORTED_ASSET_TYPE = "assetType is unsupported";
    private static final String ERROR_UNSUPPORTED_DSL_TYPE = "dslType is unsupported";
    private static final String ERROR_PROTOCOL_VERSION_INVALID = "protocolVersion must be a positive integer";
    private static final String ERROR_INTERACTION_MODE_INVALID =
            "interactionMode must be DISPLAY_ONLY or INTERACTIVE";
    private static final String ERROR_JSON_INVALID_PREFIX = " is not valid JSON: ";
    private static final String ERROR_PREVIEW_JSON_INVALID = "previewJson is not valid JSON";
    private static final String ERROR_PREVIEW_A2UI_TYPE = "A2UI previewJson must contain message type";
    private static final String ERROR_PREVIEW_DSL_TYPE =
            "BUSINESS_DSL previewJson must contain matching dslType and agentUiDsl";
    private static final String ERROR_PREVIEW_PARAMS_OBJECT = "BUSINESS_DSL previewJson params must be JSON object";
    private static final String ERROR_PREVIEW_DSL_OBJECT = "BUSINESS_DSL previewJson must be JSON object";
    private static final String ERROR_RUNTIME_ASSET_NOT_FOUND = "component runtime asset not found or disabled";
    private static final String ERROR_RUNTIME_CLIENT_UNSUPPORTED = "component runtime client is unsupported";
    private static final String ERROR_RUNTIME_DSL_TYPE_UNSUPPORTED = "runtime dslType is unsupported";
    private static final String ERROR_RENDER_INPUT_INVALID = "render input is not valid JSON";
    private static final String ERROR_RENDER_ASSET_REQUIRED =
            "dslType and its runtime lookup key are required";
    private static final String ERROR_CARD_CONTAINER_PREVIEW_ADVISER_REQUIRED =
            "CARD_CONTAINER preview must use adviser bizrender with dslType=CARD_CONTAINER";
    private static final String ERROR_EXECUTABLE_CODE_UPLOAD = "executable code upload is not allowed";
    private static final String ERROR_JSON_OBJECT_REQUIRED_SUFFIX = " must be JSON object";
    private static final String ERROR_JSON_ARRAY_REQUIRED_SUFFIX = " must be JSON array";
    private static final String ERROR_CARD_DATA_ONLY_PREFIX =
            " must contain only card data; envelope field is not allowed: ";
    private static final String ERROR_CARD_TYPE_REQUIRED_SUFFIX = " cardType is required";
    private static final String ERROR_CARD_TYPE_MISMATCH_SUFFIX = " cardType must equal componentName";
    private static final String ERROR_CARD_BASIC_INFO_CARD_ONLY =
            "component basic info update only supports CARD_COMPONENT";
    private static final String ERROR_PARAM_REQUIRED_SUFFIX = " param is required";
    private static final String ERROR_PARAM_TYPE_PREFIX = " param type must be ";

    private static final Set<String> ASSET_TYPES = Set.of(
            ASSET_TYPE_CARD_COMPONENT, ASSET_TYPE_BUSINESS_DSL, ASSET_TYPE_A2UI_ATOM);
    private static final Set<String> DSL_TYPES = Set.of(
            DSL_TYPE_CARD_CONTAINER, DSL_TYPE_BUSINESS_DSL);
    private static final Set<String> INTERACTION_MODES = Set.of(
            INTERACTION_MODE_DISPLAY_ONLY, INTERACTION_MODE_INTERACTIVE);
    private static final Set<String> CARD_CONTAINER_ENVELOPE_FIELDS = Set.of(
            JSON_FIELD_DATA, PARAM_BUNDLE_URL, PARAM_APP_BUNDLE_URL, JSON_FIELD_BIZ_TYPE,
            PARAM_COMPONENT_NAME, JSON_FIELD_TYPE);
    private static final Set<String> EXECUTABLE_CODE_PARAM_KEYS = Set.of(
            "javacode", "groovycode", "javascriptcode", "jscode", "sourcecode", "runtimecode",
            "executablecode", "codefilebase64", "frontendcode", "backendcode", "script",
            "scriptbody", "scriptcontent", "scripttext");
    private static final Pattern TEMPLATE_PLACEHOLDER_PATTERN = Pattern.compile("\\{\\{\\s*([^}]+?)\\s*}}");

    @Resource
    private SkillFactoryComponentAssetRepository componentAssetRepository;

    @Resource
    private PublishedAssetQueryService publishedAssetQueryService;

    @Resource
    private AssetReleaseEditGuard assetReleaseEditGuard;

    @Resource
    private AssetAuthorizationService assetAuthorizationService;

    @Resource
    private AssetCreationTransactionService assetCreationTransactionService;

    /**
     * 查询组件资产列表，支持关键字、资产类型、协议族和 enabledOnly 筛选。
     */
    public List<SkillFactoryComponentAsset> list(Map<String, String> params) {
        boolean enabledOnly = booleanValue(params.get(PARAM_ENABLED_ONLY), false);
        SkillFactoryComponentAssetRepository.ComponentAssetQuery query = buildQuery(params);
        log.info("SkillFactory组件中心查询列表, keyword:{}, assetType:{}, dslType:{}, enabledOnly:{}",
                query.getKeyword(), query.getAssetType(), query.getDslType(), enabledOnly);
        return componentAssetRepository.list(query, enabledOnly).stream()
                .map(this::toApiAsset)
                .toList();
    }

    /**
     * 查询可被 Skill 创建和渲染验收引用的 enabled 组件资产。
     */
    public List<SkillFactoryComponentAsset> listEnabled(Map<String, String> params) {
        SkillFactoryComponentAssetRepository.ComponentAssetQuery query = buildQuery(params);
        log.info("SkillFactory组件中心查询可用资产, keyword:{}, assetType:{}, dslType:{}",
                query.getKeyword(), query.getAssetType(), query.getDslType());
        return componentAssetRepository.list(query, true).stream()
                .map(this::toApiAsset)
                .toList();
    }

    /**
     * 查询当前 ONLINE 指针命中的正式组件版本。
     *
     * <p>该列表供 Skill 工作台选择绑定使用。组件内容只解析共享发布状态冻结的正式快照，
     * 但可用状态必须服从当前 Registry 的 enabled 开关；已下线资产不会继续暴露给新 Skill。
     * PRT 或仅启用但未正式发布的组件同样不会返回。
     */
    public List<SkillFactoryComponentAsset> listPublished(Map<String, String> params) {
        SkillFactoryComponentAssetRepository.ComponentAssetQuery query = buildQuery(params);
        List<SkillFactoryComponentAsset> result = publishedAssetQueryService.listOnline(ReleaseAssetType.COMPONENT)
                .stream()
                .map(this::publishedAsset)
                .filter(asset -> matchesPublishedQuery(asset, query))
                .toList();
        log.info("SkillFactory组件中心查询正式资产, keyword:{}, assetType:{}, dslType:{}, count:{}",
                query.getKeyword(), query.getAssetType(), query.getDslType(), result.size());
        return result;
    }

    /**
     * 按组件资产 ID 读取当前 ONLINE 正式快照，并叠加当前 Registry 的 enabled 开关。
     */
    public SkillFactoryComponentAsset publishedDetail(String id) {
        Long assetId = parseId(id);
        return publishedAsset(publishedAssetQueryService.requireOnline(
                ReleaseAssetType.COMPONENT, String.valueOf(assetId)));
    }

    /**
     * 读取组件资产详情。
     */
    public SkillFactoryComponentAsset detail(String id) {
        Long assetId = parseId(id);
        log.info("SkillFactory组件中心读取详情, id:{}", assetId);
        ComponentAsset asset = componentAssetRepository.get(assetId);
        if (asset == null) {
            log.warn("SkillFactory组件中心详情不存在, id:{}", assetId);
            throw new IllegalArgumentException(ERROR_ASSET_NOT_FOUND);
        }
        return toApiAsset(asset);
    }

    /**
     * 注册组件资产。注册只写组件元数据，不上传可执行代码，不修改 adviser。
     */
    public SkillFactoryComponentAsset register(String userName, Map<String, String> params) {
        validateNoExecutableCodeParams(params);
        SkillFactoryComponentAsset asset = assetFromParams(params, null, true)
                .setOperator(userName);
        validateForSave(asset);
        ensureUnique(asset, null);
        assetAuthorizationService.validateCreationOwners(
                userName, ReleaseAssetType.COMPONENT, asset.getComponentName(), params.get(PARAM_OWNERS_JSON));
        log.info("SkillFactory组件中心注册资产, userName:{}, assetType:{}, componentName:{}, dslType:{}",
                userName, asset.getAssetType(), asset.getComponentName(), asset.getDslType());
        return toApiAsset(assetCreationTransactionService.createComponent(
                userName, toDomainAsset(asset), params.get(PARAM_OWNERS_JSON)));
    }

    /**
     * 更新组件资产。推荐前端提交详情页完整 payload；缺省字段会沿用当前值，
     * 避免稀疏更新误清空。
     */
    public SkillFactoryComponentAsset update(String userName, Map<String, String> params) {
        validateNoExecutableCodeParams(params);
        SkillFactoryComponentAsset current = detail(params.get(PARAM_ID));
        assetAuthorizationService.requirePermission(
                userName, ReleaseAssetType.COMPONENT,
                String.valueOf(current.getId()), AssetAction.EDIT);
        assetReleaseEditGuard.requireEditableChange(ReleaseAssetType.COMPONENT,
                String.valueOf(current.getId()), ACTION_UPDATE_COMPONENT, userName);
        SkillFactoryComponentAsset asset = assetFromParams(params, current, false)
                .setAssetType(current.getAssetType())
                .setComponentName(current.getComponentName())
                .setDslType(current.getDslType())
                .setAgentUiDsl(current.getAgentUiDsl())
                .setOperator(userName)
                .setCreateTime(current.getCreateTime());
        validateForSave(asset);
        ensureUnique(asset, asset.getId());
        log.info("SkillFactory组件中心更新资产, userName:{}, id:{}, componentName:{}, enabled:{}",
                userName, asset.getId(), asset.getComponentName(), asset.getEnabled());
        ComponentAsset updated = componentAssetRepository.update(toDomainAsset(asset));
        if (updated == null) {
            throw new IllegalArgumentException(ERROR_ASSET_NOT_FOUND);
        }
        return toApiAsset(updated);
    }

    /**
     * 独立更新 CARD_COMPONENT 基础信息。
     *
     * <p>该入口只读取基础信息字段，不读取或改写 Schema、模板、示例和运行配置，也不执行复杂配置校验。
     * 完整组件保存仍由 {@link #update(String, Map)} 承担并执行全部协议校验，避免基础信息维护与模板
     * 修复互相阻断。
     */
    public SkillFactoryComponentAsset updateCardBasicInfo(String userName, Map<String, String> params) {
        SkillFactoryComponentAsset current = detail(params.get(PARAM_ID));
        assetAuthorizationService.requirePermission(
                userName, ReleaseAssetType.COMPONENT,
                String.valueOf(current.getId()), AssetAction.EDIT);
        assetReleaseEditGuard.requireEditableChange(ReleaseAssetType.COMPONENT,
                String.valueOf(current.getId()), ACTION_UPDATE_COMPONENT_BASIC_INFO, userName);
        if (!StringUtils.equals(current.getAssetType(), ASSET_TYPE_CARD_COMPONENT)) {
            throw new IllegalArgumentException(ERROR_CARD_BASIC_INFO_CARD_ONLY);
        }
        SkillFactoryComponentAsset asset = copy(current)
                .setComponentNameCn(value(params, PARAM_COMPONENT_NAME_CN,
                        current.getComponentNameCn(), false))
                .setInteractionMode(value(params, PARAM_INTERACTION_MODE,
                        current.getInteractionMode(), false))
                .setBundleUrl(value(params, PARAM_BUNDLE_URL, current.getBundleUrl(), false))
                .setAppBundleUrl(value(params, PARAM_APP_BUNDLE_URL,
                        current.getAppBundleUrl(), false))
                .setScene(value(params, PARAM_SCENE, current.getScene(), false))
                .setOperator(userName);
        normalizeCardContainerIdentity(asset);
        validateCardBasicInfo(asset);
        log.info("SkillFactory组件中心更新基础信息, userName:{}, id:{}, componentName:{}, interactionMode:{}",
                userName, asset.getId(), asset.getComponentName(), asset.getInteractionMode());
        ComponentAsset updated = componentAssetRepository.updateCardBasicInfo(toDomainAsset(asset));
        if (updated == null) {
            throw new IllegalArgumentException(ERROR_ASSET_NOT_FOUND);
        }
        return toApiAsset(updated);
    }

    /**
     * 从不可变正式版本快照恢复组件的可编辑内容，作为共享发布控制面创建新变更的基线。
     *
     * <p>上游已经在发布状态锁内解析并校验 baseVersion。本方法再次校验 EDIT 权限和稳定资产身份，
     * 但不要求 ACTIVE 变更，因为恢复动作发生在新变更记录创建之前。组件 ID、协议身份、创建时间以及
     * 当前 Registry 的 enabled 紧急开关保持不变；其余版本化配置以历史快照为准。本方法不切换
     * PRT/ONLINE 指针，也不修改不可变发布版本。
     */
    public SkillFactoryComponentAsset restoreReleasedSnapshot(String userName, String id,
            SkillFactoryComponentAsset releasedAsset) {
        SkillFactoryComponentAsset current = detail(id);
        assetAuthorizationService.requirePermission(
                userName, ReleaseAssetType.COMPONENT, String.valueOf(current.getId()), AssetAction.EDIT);
        requireSameReleaseIdentity(current, releasedAsset);
        SkillFactoryComponentAsset restored = copy(releasedAsset)
                .setId(current.getId())
                .setAssetType(current.getAssetType())
                .setComponentName(current.getComponentName())
                .setDslType(current.getDslType())
                .setAgentUiDsl(current.getAgentUiDsl())
                .setEnabled(current.getEnabled())
                .setOperator(userName)
                .setCreateTime(current.getCreateTime());
        if (StringUtils.isBlank(restored.getInteractionMode())) {
            restored.setInteractionMode(current.getInteractionMode());
        }
        if (StringUtils.isBlank(restored.getInteractionMode())) {
            log.warn("SkillFactory组件历史快照缺少交互类型，临时允许创建变更后补齐, id:{}, "
                            + "componentName:{}, operator:{}",
                    restored.getId(), restored.getComponentName(), userName);
        }
        validateForHistoricalRestore(restored);
        ensureUnique(restored, restored.getId());
        log.info("SkillFactory组件中心从正式版本恢复可编辑内容, id:{}, componentName:{}, "
                        + "interactionMode:{}, enabled:{}, operator:{}",
                restored.getId(), restored.getComponentName(), restored.getInteractionMode(),
                restored.getEnabled(), userName);
        ComponentAsset updated = componentAssetRepository.update(toDomainAsset(restored));
        if (updated == null) {
            throw new IllegalArgumentException(ERROR_ASSET_NOT_FOUND);
        }
        return toApiAsset(updated);
    }

    /**
     * 下线组件资产。下线后 enabled=false，后续 enabled 列表不会再返回它。
     */
    public SkillFactoryComponentAsset offline(String userName, String id) {
        Long assetId = parseId(id);
        assetAuthorizationService.requirePermission(
                userName, ReleaseAssetType.COMPONENT,
                String.valueOf(assetId), AssetAction.OFFLINE);
        log.info("SkillFactory组件中心下线资产, userName:{}, id:{}", userName, assetId);
        ComponentAsset asset = componentAssetRepository.offline(assetId, userName);
        if (asset == null) {
            log.warn("SkillFactory组件中心下线失败，资产不存在, userName:{}, id:{}", userName, assetId);
            throw new IllegalArgumentException(ERROR_ASSET_NOT_FOUND);
        }
        return toApiAsset(asset);
    }

    /**
     * 校验官方 demo 或临时 JSON 是否满足登记协议。校验失败返回 valid=false，
     * 不写回注册表。
     */
    public SkillFactoryComponentPreviewResult preview(String id, String previewJson) {
        SkillFactoryComponentAsset asset = detail(id);
        String payload = StringUtils.defaultIfBlank(previewJson, asset.getOfficialDemoJson());
        if (StringUtils.equals(asset.getAssetType(), ASSET_TYPE_BUSINESS_DSL)) {
            SkillFactoryComponentPreviewResult result = buildBusinessDslPreviewResult(asset, payload);
            log.info("SkillFactory组件中心BUSINESS_DSL预览校验完成, id:{}, agentUiDsl:{}, valid:{}",
                    asset.getId(), asset.getAgentUiDsl(), result.getValid());
            return result;
        }
        List<String> errors = validatePreviewPayload(asset, payload);
        log.info("SkillFactory组件中心预览校验完成, id:{}, componentName:{}, dslType:{}, valid:{}",
                asset.getId(), asset.getComponentName(), asset.getDslType(), errors.isEmpty());
        return new SkillFactoryComponentPreviewResult()
                .setValid(errors.isEmpty())
                .setAssetId(asset.getId())
                .setComponentName(asset.getComponentName())
                .setAssetType(asset.getAssetType())
                .setDslType(asset.getDslType())
                .setPreviewJson(payload)
                .setErrors(errors);
    }

    /**
     * 查询 adviser 运行态可消费的单个组件资产。
     *
     * <p>该方法只返回 enabled 资产，并按 clientType 做端支持校验。它是 adviser
     * 渲染执行器和 action bridge 获取组件协议事实源的入口，
     * 不负责执行渲染或写入运行态状态。
     */
    public SkillFactoryComponentAsset runtimeDetail(Map<String, String> params) {
        Map<String, String> safeParams = params == null ? Collections.emptyMap() : params;
        SkillFactoryComponentAsset asset = findRuntimeAsset(safeParams);
        String clientType = upper(StringUtils.defaultIfBlank(
                safeParams.get(PARAM_CLIENT_TYPE), DEFAULT_CLIENT_TYPE_PC));
        ensureRuntimeAssetUsable(asset, clientType);
        log.info("SkillFactory组件中心运行态详情查询完成, assetType:{}, dslType:{}, componentName:{}, "
                        + "agentUiDsl:{}, "
                        + "clientType:{}",
                asset.getAssetType(), asset.getDslType(), asset.getComponentName(), asset.getAgentUiDsl(), clientType);
        return asset;
    }

    /**
     * 批量查询 adviser 运行态可消费资产。
     *
     * <p>assetsJson 为空时按查询条件返回 ONLINE 正式列表；不为空时逐个执行 runtimeDetail，
     * 保证 disabled/offline 资产不会被静默带入运行态。
     */
    public List<SkillFactoryComponentAsset> runtimeBatchGet(String assetsJson, Map<String, String> params) {
        if (StringUtils.isBlank(assetsJson)) {
            log.info("SkillFactory组件中心运行态批量查询使用ONLINE列表, keyword:{}, assetType:{}",
                    params == null ? EMPTY : params.get(PARAM_KEYWORD),
                    params == null ? EMPTY : params.get(PARAM_ASSET_TYPE));
            return listPublished(params == null ? Collections.emptyMap() : params);
        }
        com.alibaba.fastjson2.JSONArray assets = parseAssetsJson(assetsJson);
        List<SkillFactoryComponentAsset> result = new ArrayList<>();
        for (Object item : assets) {
            if (!(item instanceof com.alibaba.fastjson2.JSONObject)) {
                throw new IllegalArgumentException(PARAM_ASSETS_JSON + ERROR_JSON_ARRAY_REQUIRED_SUFFIX);
            }
            result.add(runtimeDetail(toStringParams((com.alibaba.fastjson2.JSONObject) item)));
        }
        log.info("SkillFactory组件中心运行态批量查询完成, requestCount:{}, resultCount:{}",
                assets.size(), result.size());
        return result;
    }

    /**
     * M 端显式渲染预览。
     *
     * <p>Sellerdata 只保留 BUSINESS_DSL 配置预览。CARD_CONTAINER 的模板解释必须走 Adviser bizrender，
     * 与真实 Chat stream 共用同一个执行器，避免管理面和运行态维护两套模板语义。
     */
    public SkillFactoryRenderPreviewResult renderPreview(Map<String, String> params) {
        Map<String, String> safeParams = params == null ? Collections.emptyMap() : params;
        String inputMode = upper(safeParams.get(PARAM_INPUT_MODE));
        String source = trim(safeParams.get(PARAM_SOURCE));
        log.info("SkillFactory组件中心开始运行态预览, source:{}, inputMode:{}, dslType:{}, "
                        + "componentName:{}, agentUiDsl:{}",
                source, inputMode, safeParams.get(PARAM_DSL_TYPE),
                safeParams.get(PARAM_COMPONENT_NAME), safeParams.get(PARAM_AGENT_UI_DSL));
        List<String> errors = new ArrayList<>();
        com.alibaba.fastjson2.JSONObject renderObject = parseRenderTextObject(safeParams.get(PARAM_RENDER_TEXT), errors);
        if (shouldPreviewCardContainer(inputMode, safeParams, renderObject)) {
            errors.add(ERROR_CARD_CONTAINER_PREVIEW_ADVISER_REQUIRED);
            return failedRenderPreview(PROTOCOL_CARD_CONTAINER, errors);
        }
        if (shouldPreviewBusinessDsl(inputMode, safeParams, renderObject)) {
            return renderBusinessDslPreview(safeParams, renderObject, errors);
        }
        if (StringUtils.equals(inputMode, INPUT_MODE_RAW_TEXT)
                || StringUtils.isNotBlank(safeParams.get(PARAM_COMPONENT_NAME))) {
            errors.add(ERROR_CARD_CONTAINER_PREVIEW_ADVISER_REQUIRED);
            return failedRenderPreview(PROTOCOL_CARD_CONTAINER, errors);
        }
        errors.add(ERROR_RENDER_ASSET_REQUIRED);
        return new SkillFactoryRenderPreviewResult()
                .setValid(false)
                .setRenderProtocol(inputMode)
                .setErrors(errors);
    }

    private SkillFactoryComponentAssetRepository.ComponentAssetQuery buildQuery(Map<String, String> params) {
        return new SkillFactoryComponentAssetRepository.ComponentAssetQuery()
                .setKeyword(trim(params.get(PARAM_KEYWORD)))
                .setAssetType(upper(params.get(PARAM_ASSET_TYPE)))
                .setDslType(upper(params.get(PARAM_DSL_TYPE)));
    }

    private SkillFactoryComponentAsset publishedAsset(PublishedAssetSnapshot published) {
        if (published == null || published.getSnapshot() == null
                || StringUtils.isBlank(published.getSnapshot().getPayloadJson())) {
            throw new IllegalStateException("published component snapshot is empty");
        }
        SkillFactoryComponentAsset asset = JsonSupport.fromJSON(
                published.getSnapshot().getPayloadJson(), SkillFactoryComponentAsset.class);
        if (asset == null) {
            throw new IllegalStateException("published component snapshot is invalid");
        }
        ComponentAsset currentAsset = componentAssetRepository.get(asset.getId());
        boolean enabled = currentAsset != null && Boolean.TRUE.equals(currentAsset.getEnabled());
        if (!enabled) {
            log.info("SkillFactory正式组件快照被Registry禁用, assetId:{}, componentName:{}, version:{}",
                    asset.getId(), asset.getComponentName(), published.getVersion());
        }
        return asset.setEnabled(enabled)
                .setPublished(true)
                .setPublishedVersion(published.getVersion());
    }

    private boolean matchesPublishedQuery(SkillFactoryComponentAsset asset,
            SkillFactoryComponentAssetRepository.ComponentAssetQuery query) {
        if (asset == null || !Boolean.TRUE.equals(asset.getEnabled())) {
            return false;
        }
        if (specified(query.getAssetType())
                && !StringUtils.equalsIgnoreCase(query.getAssetType(), asset.getAssetType())) {
            return false;
        }
        if (specified(query.getDslType())
                && !StringUtils.equalsIgnoreCase(query.getDslType(), asset.getDslType())) {
            return false;
        }
        String keyword = StringUtils.lowerCase(query.getKeyword());
        if (StringUtils.isBlank(keyword)) {
            return true;
        }
        return Stream.of(asset.getComponentName(), asset.getComponentNameCn(), asset.getDslType(),
                        asset.getAgentUiDsl(), asset.getAssetType())
                .filter(StringUtils::isNotBlank)
                .map(StringUtils::lowerCase)
                .anyMatch(value -> StringUtils.contains(value, keyword));
    }

    private SkillFactoryComponentAsset findRuntimeAsset(Map<String, String> params) {
        String dslType = upper(params.get(PARAM_DSL_TYPE));
        String componentName = trim(params.get(PARAM_COMPONENT_NAME));
        String agentUiDsl = trim(params.get(PARAM_AGENT_UI_DSL));
        String assetType;
        if (StringUtils.equals(dslType, DSL_TYPE_CARD_CONTAINER)) {
            requiredRuntimeKey(PARAM_COMPONENT_NAME, componentName);
            assetType = ASSET_TYPE_CARD_COMPONENT;
            agentUiDsl = EMPTY;
        } else if (StringUtils.equals(dslType, DSL_TYPE_BUSINESS_DSL)) {
            requiredRuntimeKey(PARAM_AGENT_UI_DSL, agentUiDsl);
            assetType = ASSET_TYPE_BUSINESS_DSL;
            componentName = EMPTY;
        } else {
            throw new IllegalArgumentException(ERROR_RUNTIME_DSL_TYPE_UNSUPPORTED);
        }
        String expectedComponentName = componentName;
        String expectedAgentUiDsl = agentUiDsl;
        SkillFactoryComponentAsset asset = publishedAssetQueryService.listOnline(ReleaseAssetType.COMPONENT)
                .stream()
                .map(this::publishedAsset)
                .filter(item -> Boolean.TRUE.equals(item.getEnabled()))
                .filter(item -> StringUtils.equals(item.getAssetType(), assetType))
                .filter(item -> StringUtils.equals(item.getDslType(), dslType))
                .filter(item -> StringUtils.isBlank(expectedComponentName)
                        || StringUtils.equals(item.getComponentName(), expectedComponentName))
                .filter(item -> StringUtils.isBlank(expectedAgentUiDsl)
                        || StringUtils.equals(item.getAgentUiDsl(), expectedAgentUiDsl))
                .findFirst()
                .orElse(null);
        if (asset == null) {
            log.warn("SkillFactory组件中心运行态资产不存在或不可用, assetType:{}, dslType:{}, "
                            + "componentName:{}, agentUiDsl:{}",
                    assetType, dslType, componentName, agentUiDsl);
            throw new IllegalArgumentException(ERROR_RUNTIME_ASSET_NOT_FOUND);
        }
        return asset;
    }

    private void requiredRuntimeKey(String fieldName, String value) {
        if (StringUtils.isBlank(value)) {
            throw new IllegalArgumentException(fieldName + ERROR_REQUIRED_SUFFIX);
        }
    }

    private void ensureRuntimeAssetUsable(SkillFactoryComponentAsset asset, String clientType) {
        if (asset == null || !Boolean.TRUE.equals(asset.getEnabled())) {
            throw new IllegalArgumentException(ERROR_RUNTIME_ASSET_NOT_FOUND);
        }
        if (StringUtils.isNotBlank(clientType) && !asset.getSupportClients().isEmpty()
                && asset.getSupportClients().stream().noneMatch(client -> StringUtils.equalsIgnoreCase(client,
                clientType))) {
            log.warn("SkillFactory组件中心运行态资产不支持当前端, componentName:{}, agentUiDsl:{}, "
                            + "clientType:{}, supportClients:{}",
                    asset.getComponentName(), asset.getAgentUiDsl(), clientType, asset.getSupportClients());
            throw new IllegalArgumentException(ERROR_RUNTIME_CLIENT_UNSUPPORTED);
        }
    }

    private com.alibaba.fastjson2.JSONArray parseAssetsJson(String assetsJson) {
        try {
            return com.alibaba.fastjson2.JSON.parseArray(assetsJson);
        } catch (Exception e) {
            log.warn("SkillFactory组件中心运行态批量查询assetsJson解析失败, error:{}", e.getMessage());
            throw new IllegalArgumentException(PARAM_ASSETS_JSON + ERROR_JSON_INVALID_PREFIX + e.getMessage());
        }
    }

    private Map<String, String> toStringParams(com.alibaba.fastjson2.JSONObject object) {
        Map<String, String> params = new LinkedHashMap<>();
        for (Map.Entry<String, Object> entry : object.entrySet()) {
            params.put(entry.getKey(), entry.getValue() == null ? EMPTY : String.valueOf(entry.getValue()));
        }
        return params;
    }

    private boolean shouldPreviewBusinessDsl(String inputMode, Map<String, String> params, com.alibaba.fastjson2.JSONObject renderObject) {
        String dslType = upper(firstNotBlank(params.get(PARAM_DSL_TYPE),
                renderObject == null ? EMPTY : renderObject.getString(JSON_FIELD_DSL_TYPE)));
        return StringUtils.equals(inputMode, INPUT_MODE_BUSINESS_DSL)
                || StringUtils.equals(dslType, DSL_TYPE_BUSINESS_DSL);
    }

    private boolean shouldPreviewCardContainer(String inputMode, Map<String, String> params, com.alibaba.fastjson2.JSONObject renderObject) {
        String dslType = upper(firstNotBlank(params.get(PARAM_DSL_TYPE),
                renderObject == null ? EMPTY : renderObject.getString(JSON_FIELD_DSL_TYPE)));
        return StringUtils.equals(inputMode, INPUT_MODE_CARD_CONTAINER)
                || StringUtils.equals(upper(params.get(PARAM_ASSET_TYPE)), ASSET_TYPE_CARD_COMPONENT)
                || StringUtils.equals(dslType, DSL_TYPE_CARD_CONTAINER)
                || StringUtils.isNotBlank(params.get(PARAM_RENDER_TEMPLATE_JSON));
    }

    private SkillFactoryRenderPreviewResult renderBusinessDslPreview(Map<String, String> params,
            com.alibaba.fastjson2.JSONObject renderObject, List<String> errors) {
        String agentUiDsl = firstNotBlank(params.get(PARAM_AGENT_UI_DSL),
                renderObject == null ? EMPTY : renderObject.getString(JSON_FIELD_AGENT_UI_DSL));
        if (StringUtils.isBlank(agentUiDsl)) {
            errors.add(ERROR_RENDER_ASSET_REQUIRED);
            return failedRenderPreview(PROTOCOL_A2UI, errors);
        }
        Map<String, String> runtimeParams = new LinkedHashMap<>(params);
        runtimeParams.put(PARAM_ASSET_TYPE, ASSET_TYPE_BUSINESS_DSL);
        runtimeParams.put(PARAM_DSL_TYPE, DSL_TYPE_BUSINESS_DSL);
        runtimeParams.put(PARAM_AGENT_UI_DSL, agentUiDsl);
        SkillFactoryComponentAsset asset = null;
        try {
            asset = runtimeDetail(runtimeParams);
        } catch (IllegalArgumentException e) {
            errors.add(e.getMessage());
        }
        com.alibaba.fastjson2.JSONObject businessParams = businessDslParams(params, renderObject, asset, errors);
        boolean paramsValid = asset != null && businessParams != null
                && validateParamsAgainstSchema(asset.getParamsSchemaJson(), businessParams, errors);
        com.alibaba.fastjson2.JSONObject renderTemplate = asset == null ? null : parseJsonObjectConfig(errors, PARAM_RENDER_TEMPLATE_JSON,
                asset.getRenderTemplateJson(), true);
        Object a2uiPayload = renderTemplate == null ? new LinkedHashMap<>()
                : applyRenderTemplate(renderTemplate, businessParams, agentUiDsl);
        return new SkillFactoryRenderPreviewResult()
                .setValid(errors.isEmpty())
                .setAssetId(asset == null ? null : asset.getId())
                .setAssetType(ASSET_TYPE_BUSINESS_DSL)
                .setComponentName(asset == null ? EMPTY : asset.getComponentName())
                .setComponentNameCn(asset == null ? EMPTY : asset.getComponentNameCn())
                .setRenderProtocol(asset == null ? PROTOCOL_A2UI : asset.getDslType())
                .setProtocolVersion(asset == null ? DEFAULT_PROTOCOL_VERSION : asset.getProtocolVersion())
                .setBundleUrl(asset == null ? EMPTY : asset.getBundleUrl())
                .setDslType(DSL_TYPE_BUSINESS_DSL)
                .setAgentUiDsl(agentUiDsl)
                .setParamsValid(paramsValid)
                .setData(a2uiPayload)
                .setErrors(errors);
    }

    private com.alibaba.fastjson2.JSONObject cardPayloadData(SkillFactoryComponentAsset asset, Map<String, String> params,
            com.alibaba.fastjson2.JSONObject renderObject, List<String> errors) {
        Object data = null;
        if (StringUtils.isNotBlank(params.get(PARAM_DATA))) {
            data = parseJsonObjectField(params.get(PARAM_DATA), PARAM_DATA, errors);
        } else if (renderObject != null) {
            data = renderObject.get(JSON_FIELD_DATA);
        }
        if (data instanceof com.alibaba.fastjson2.JSONObject) {
            return (com.alibaba.fastjson2.JSONObject) data;
        }
        if (data != null) {
            errors.add(PARAM_DATA + ERROR_JSON_OBJECT_REQUIRED_SUFFIX);
            return new com.alibaba.fastjson2.JSONObject();
        }
        if (asset == null) {
            return new com.alibaba.fastjson2.JSONObject();
        }
        com.alibaba.fastjson2.JSONObject officialDemo = parseJsonObjectField(asset.getOfficialDemoJson(), PARAM_OFFICIAL_DEMO_JSON, errors);
        Object demoData = officialDemo == null ? null : officialDemo.get(JSON_FIELD_DATA);
        return demoData instanceof com.alibaba.fastjson2.JSONObject ? (com.alibaba.fastjson2.JSONObject) demoData : new com.alibaba.fastjson2.JSONObject();
    }

    private com.alibaba.fastjson2.JSONObject businessDslParams(Map<String, String> params, com.alibaba.fastjson2.JSONObject renderObject,
            SkillFactoryComponentAsset asset, List<String> errors) {
        if (StringUtils.isNotBlank(params.get(PARAM_PARAMS))) {
            return parseJsonObjectField(params.get(PARAM_PARAMS), PARAM_PARAMS, errors);
        }
        if (renderObject != null && renderObject.get(JSON_FIELD_PARAMS) instanceof com.alibaba.fastjson2.JSONObject) {
            return renderObject.getJSONObject(JSON_FIELD_PARAMS);
        }
        if (asset == null) {
            errors.add(ERROR_PREVIEW_PARAMS_OBJECT);
            return null;
        }
        com.alibaba.fastjson2.JSONObject officialDemo = parseJsonObjectField(asset.getOfficialDemoJson(), PARAM_OFFICIAL_DEMO_JSON, errors);
        if (officialDemo != null && officialDemo.get(JSON_FIELD_PARAMS) instanceof com.alibaba.fastjson2.JSONObject) {
            return officialDemo.getJSONObject(JSON_FIELD_PARAMS);
        }
        errors.add(ERROR_PREVIEW_PARAMS_OBJECT);
        return null;
    }

    private Object applyRenderTemplate(Object templateValue, com.alibaba.fastjson2.JSONObject params,
            String agentUiDsl) {
        if (templateValue instanceof com.alibaba.fastjson2.JSONObject) {
            com.alibaba.fastjson2.JSONObject result = new com.alibaba.fastjson2.JSONObject();
            com.alibaba.fastjson2.JSONObject object = (com.alibaba.fastjson2.JSONObject) templateValue;
            for (Map.Entry<String, Object> entry : object.entrySet()) {
                result.put(entry.getKey(), applyRenderTemplate(entry.getValue(), params, agentUiDsl));
            }
            return result;
        }
        if (templateValue instanceof com.alibaba.fastjson2.JSONArray) {
            com.alibaba.fastjson2.JSONArray result = new com.alibaba.fastjson2.JSONArray();
            for (Object item : (com.alibaba.fastjson2.JSONArray) templateValue) {
                result.add(applyRenderTemplate(item, params, agentUiDsl));
            }
            return result;
        }
        if (templateValue instanceof String) {
            return applyTemplateString((String) templateValue, params, agentUiDsl);
        }
        return templateValue;
    }

    private Object applyTemplateString(String template, com.alibaba.fastjson2.JSONObject params, String agentUiDsl) {
        Matcher exactMatcher = TEMPLATE_PLACEHOLDER_PATTERN.matcher(template);
        if (exactMatcher.matches()) {
            Object value = resolveTemplateValue(exactMatcher.group(1), params, agentUiDsl);
            return value == null ? EMPTY : value;
        }
        Matcher matcher = TEMPLATE_PLACEHOLDER_PATTERN.matcher(template);
        StringBuffer buffer = new StringBuffer();
        while (matcher.find()) {
            Object value = resolveTemplateValue(matcher.group(1), params, agentUiDsl);
            matcher.appendReplacement(buffer, Matcher.quoteReplacement(stringifyTemplateValue(value)));
        }
        matcher.appendTail(buffer);
        return buffer.toString();
    }

    private Object resolveTemplateValue(String expression, com.alibaba.fastjson2.JSONObject params,
            String agentUiDsl) {
        String keyPath = trim(expression);
        if (StringUtils.equals(keyPath, JSON_FIELD_AGENT_UI_DSL)) {
            return agentUiDsl;
        }
        if (StringUtils.equals(keyPath, JSON_FIELD_DSL_TYPE)) {
            return DSL_TYPE_BUSINESS_DSL;
        }
        if (StringUtils.equals(keyPath, JSON_FIELD_PARAMS)) {
            return params == null ? new com.alibaba.fastjson2.JSONObject() : params;
        }
        keyPath = StringUtils.removeStart(keyPath, "$.");
        keyPath = StringUtils.removeStart(keyPath, JSON_FIELD_PARAMS + ".");
        if (params == null || StringUtils.isBlank(keyPath)) {
            return null;
        }
        Object current = params;
        for (String part : StringUtils.split(keyPath, '.')) {
            if (!(current instanceof com.alibaba.fastjson2.JSONObject)) {
                return null;
            }
            current = ((com.alibaba.fastjson2.JSONObject) current).get(part);
        }
        return current;
    }

    private String stringifyTemplateValue(Object value) {
        if (value == null) {
            return EMPTY;
        }
        if (value instanceof com.alibaba.fastjson2.JSONObject || value instanceof com.alibaba.fastjson2.JSONArray) {
            return com.alibaba.fastjson2.JSON.toJSONString(value);
        }
        return String.valueOf(value);
    }

    private com.alibaba.fastjson2.JSONObject parseRenderTextObject(String renderText, List<String> errors) {
        String stripped = stripRenderMarkers(renderText);
        if (StringUtils.isBlank(stripped)) {
            return null;
        }
        return parseJsonObjectField(stripped, PARAM_RENDER_TEXT, errors);
    }

    private String stripRenderMarkers(String renderText) {
        String text = trim(renderText);
        if (StringUtils.isBlank(text) || !StringUtils.contains(text, RENDER_MARKER_START)) {
            return text;
        }
        int start = StringUtils.indexOf(text, RENDER_MARKER_START) + RENDER_MARKER_START.length();
        int end = StringUtils.indexOf(text, RENDER_MARKER_END, start);
        if (end < 0) {
            return StringUtils.substring(text, start);
        }
        return StringUtils.substring(text, start, end);
    }

    private com.alibaba.fastjson2.JSONObject parseJsonObjectField(String value, String field, List<String> errors) {
        try {
            Object json = com.alibaba.fastjson2.JSON.parse(value);
            if (!(json instanceof com.alibaba.fastjson2.JSONObject)) {
                errors.add(field + ERROR_JSON_OBJECT_REQUIRED_SUFFIX);
                return null;
            }
            return (com.alibaba.fastjson2.JSONObject) json;
        } catch (Exception e) {
            log.warn("SkillFactory组件中心JSON对象解析失败, field:{}, error:{}", field, e.getMessage());
            errors.add(StringUtils.equals(field, PARAM_RENDER_TEXT) ? ERROR_RENDER_INPUT_INVALID
                    : field + ERROR_JSON_INVALID_PREFIX + e.getMessage());
            return null;
        }
    }

    private SkillFactoryRenderPreviewResult failedRenderPreview(String renderProtocol, List<String> errors) {
        return new SkillFactoryRenderPreviewResult()
                .setValid(false)
                .setRenderProtocol(renderProtocol)
                .setErrors(errors);
    }

    private String firstNotBlank(String... values) {
        for (String value : values) {
            if (StringUtils.isNotBlank(value)) {
                return trim(value);
            }
        }
        return EMPTY;
    }

    private boolean specified(String value) {
        return StringUtils.isNotBlank(value) && !StringUtils.equalsIgnoreCase(value, VALUE_ALL);
    }

    private SkillFactoryComponentAsset assetFromParams(Map<String, String> params,
            SkillFactoryComponentAsset current, boolean create) {
        SkillFactoryComponentAsset asset = current == null ? new SkillFactoryComponentAsset() : copy(current);
        asset.setId(create ? null : current.getId())
                .setAssetType(value(params, PARAM_ASSET_TYPE, asset.getAssetType(), true))
                .setComponentName(value(params, PARAM_COMPONENT_NAME, asset.getComponentName(), false))
                .setComponentNameCn(value(params, PARAM_COMPONENT_NAME_CN, asset.getComponentNameCn(), false))
                .setDslType(value(params, PARAM_DSL_TYPE, asset.getDslType(), false))
                .setAgentUiDsl(value(params, PARAM_AGENT_UI_DSL, asset.getAgentUiDsl(), false))
                .setProtocolVersion(integerValue(params, PARAM_PROTOCOL_VERSION,
                        asset.getProtocolVersion(), DEFAULT_PROTOCOL_VERSION))
                .setInteractionMode(value(params, PARAM_INTERACTION_MODE,
                        asset.getInteractionMode(), false))
                .setBundleUrl(value(params, PARAM_BUNDLE_URL, asset.getBundleUrl(), false))
                .setAppBundleUrl(value(params, PARAM_APP_BUNDLE_URL, asset.getAppBundleUrl(), false))
                .setOwner(value(params, PARAM_OWNER, asset.getOwner(), false))
                .setScene(value(params, PARAM_SCENE, asset.getScene(), false))
                .setParamsSchemaJson(value(params, PARAM_PARAMS_SCHEMA_JSON, asset.getParamsSchemaJson(), false))
                .setRenderTemplateJson(value(params, PARAM_RENDER_TEMPLATE_JSON,
                        asset.getRenderTemplateJson(), false))
                .setOfficialDemoJson(value(params, PARAM_OFFICIAL_DEMO_JSON, asset.getOfficialDemoJson(), false))
                .setMessageDemoJson(value(params, PARAM_MESSAGE_DEMO_JSON, asset.getMessageDemoJson(), false))
                .setIntegrationPrompt(value(params, PARAM_INTEGRATION_PROMPT, asset.getIntegrationPrompt(), false))
                .setAllowedActionsJson(value(params, PARAM_ALLOWED_ACTIONS_JSON, asset.getAllowedActionsJson(), false))
                .setRuntimeConfigJson(value(params, PARAM_RUNTIME_CONFIG_JSON, asset.getRuntimeConfigJson(), false))
                .setAttribute(value(params, PARAM_ATTRIBUTE, asset.getAttribute(), false));
        if (params.containsKey(PARAM_SUPPORT_CLIENTS) || create) {
            asset.setSupportClients(parseSupportClients(params.get(PARAM_SUPPORT_CLIENTS)));
        }
        if (params.containsKey(PARAM_ENABLED) || create) {
            asset.setEnabled(booleanValue(params.get(PARAM_ENABLED), false));
        }
        if (asset.getEnabled() == null) {
            asset.setEnabled(Boolean.FALSE);
        }
        normalizeCardContainerIdentity(asset);
        normalizeBusinessDslIdentity(asset);
        return asset;
    }

    /**
     * CARD_CONTAINER 资产统一使用协议族，并以 componentName 作为运行态查找键。
     */
    private void normalizeCardContainerIdentity(SkillFactoryComponentAsset asset) {
        if (StringUtils.equals(asset.getAssetType(), ASSET_TYPE_CARD_COMPONENT)) {
            asset.setDslType(DSL_TYPE_CARD_CONTAINER);
            asset.setAgentUiDsl(EMPTY);
            asset.setInteractionMode(upper(asset.getInteractionMode()));
        }
    }

    private void normalizeBusinessDslIdentity(SkillFactoryComponentAsset asset) {
        if (StringUtils.equals(asset.getAssetType(), ASSET_TYPE_BUSINESS_DSL)) {
            asset.setDslType(DSL_TYPE_BUSINESS_DSL);
            asset.setInteractionMode(EMPTY);
            return;
        }
        if (StringUtils.equals(asset.getAssetType(), ASSET_TYPE_A2UI_ATOM)) {
            asset.setDslType(EMPTY);
            asset.setAgentUiDsl(EMPTY);
            asset.setInteractionMode(EMPTY);
        }
    }

    private void validateForSave(SkillFactoryComponentAsset asset) {
        validateForSave(asset, false);
    }

    /**
     * 仅校验基础信息页可编辑字段，不让尚未修复的复杂配置阻断基础信息保存。
     */
    private void validateCardBasicInfo(SkillFactoryComponentAsset asset) {
        List<String> errors = new ArrayList<>();
        required(errors, PARAM_COMPONENT_NAME_CN, asset.getComponentNameCn());
        required(errors, PARAM_BUNDLE_URL, asset.getBundleUrl());
        required(errors, PARAM_APP_BUNDLE_URL, asset.getAppBundleUrl());
        required(errors, PARAM_SCENE, asset.getScene());
        if (!isInteractionModeValid(asset.getInteractionMode(), false)) {
            errors.add(ERROR_INTERACTION_MODE_INVALID);
        }
        if (!errors.isEmpty()) {
            log.warn("SkillFactory组件中心基础信息校验失败, componentName:{}, errors:{}",
                    asset.getComponentName(), errors);
            throw new IllegalArgumentException(StringUtils.join(errors, "; "));
        }
    }

    /**
     * 校验从不可变历史快照恢复的组件内容。
     *
     * <p>交互类型字段上线前封板的快照可能没有 interactionMode。该兼容仅允许先创建 ACTIVE 变更，
     * 普通组件保存仍要求显式选择有效交互类型，后续构建和发布不会绕过正常保存校验。
     */
    private void validateForHistoricalRestore(SkillFactoryComponentAsset asset) {
        validateForSave(asset, true);
    }

    private void validateForSave(SkillFactoryComponentAsset asset, boolean allowMissingInteractionMode) {
        List<String> errors = new ArrayList<>();
        required(errors, PARAM_ASSET_TYPE, asset.getAssetType());
        required(errors, PARAM_COMPONENT_NAME, asset.getComponentName());
        required(errors, "operator", asset.getOperator());
        if (asset.getProtocolVersion() == null || asset.getProtocolVersion() <= 0) {
            errors.add(ERROR_PROTOCOL_VERSION_INVALID);
        }
        validateEnums(asset, errors, allowMissingInteractionMode);
        validateJsonField(errors, PARAM_PARAMS_SCHEMA_JSON, asset.getParamsSchemaJson(), false);
        validateJsonField(errors, PARAM_OFFICIAL_DEMO_JSON, asset.getOfficialDemoJson(), false);
        validateJsonField(errors, PARAM_MESSAGE_DEMO_JSON, asset.getMessageDemoJson(), false);
        validateJsonField(errors, PARAM_ALLOWED_ACTIONS_JSON, asset.getAllowedActionsJson(), false);
        validateJsonField(errors, PARAM_RUNTIME_CONFIG_JSON, asset.getRuntimeConfigJson(), false);
        validateJsonField(errors, PARAM_ATTRIBUTE, asset.getAttribute(), false);
        validateProtocolSpecificFields(asset, errors);
        validateNoExecutableCodeAsset(asset, errors);
        if (!errors.isEmpty()) {
            log.warn("SkillFactory组件中心资产校验失败, componentName:{}, errors:{}",
                    asset.getComponentName(), errors);
            throw new IllegalArgumentException(StringUtils.join(errors, "; "));
        }
    }

    private void validateEnums(SkillFactoryComponentAsset asset, List<String> errors,
            boolean allowMissingInteractionMode) {
        if (StringUtils.isNotBlank(asset.getAssetType()) && !ASSET_TYPES.contains(asset.getAssetType())) {
            errors.add(ERROR_UNSUPPORTED_ASSET_TYPE);
        }
        if (StringUtils.isNotBlank(asset.getDslType()) && !DSL_TYPES.contains(asset.getDslType())) {
            errors.add(ERROR_UNSUPPORTED_DSL_TYPE);
        }
        if (StringUtils.equals(asset.getAssetType(), ASSET_TYPE_CARD_COMPONENT)
                && !isInteractionModeValid(asset.getInteractionMode(), allowMissingInteractionMode)) {
            errors.add(ERROR_INTERACTION_MODE_INVALID);
        }
    }

    private boolean isInteractionModeValid(String interactionMode, boolean allowMissingInteractionMode) {
        if (StringUtils.isBlank(interactionMode)) {
            return allowMissingInteractionMode;
        }
        return INTERACTION_MODES.contains(interactionMode);
    }

    private void validateProtocolSpecificFields(SkillFactoryComponentAsset asset, List<String> errors) {
        if (StringUtils.equals(asset.getAssetType(), ASSET_TYPE_CARD_COMPONENT)) {
            if (!StringUtils.equals(asset.getDslType(), DSL_TYPE_CARD_CONTAINER)) {
                errors.add(ERROR_UNSUPPORTED_DSL_TYPE);
            }
            required(errors, PARAM_BUNDLE_URL, asset.getBundleUrl());
            required(errors, PARAM_APP_BUNDLE_URL, asset.getAppBundleUrl());
            required(errors, PARAM_PARAMS_SCHEMA_JSON, asset.getParamsSchemaJson());
            required(errors, PARAM_RENDER_TEMPLATE_JSON, asset.getRenderTemplateJson());
            validateCardDataJson(asset.getOfficialDemoJson(), PARAM_OFFICIAL_DEMO_JSON,
                    asset.getComponentName(), false, errors);
            validateCardDataJson(asset.getRenderTemplateJson(), PARAM_RENDER_TEMPLATE_JSON,
                    asset.getComponentName(), true, errors);
        }
        if (StringUtils.equals(asset.getAssetType(), ASSET_TYPE_BUSINESS_DSL)) {
            if (!StringUtils.equals(asset.getDslType(), DSL_TYPE_BUSINESS_DSL)) {
                errors.add(ERROR_UNSUPPORTED_DSL_TYPE);
            }
            required(errors, PARAM_AGENT_UI_DSL, asset.getAgentUiDsl());
            required(errors, PARAM_PARAMS_SCHEMA_JSON, asset.getParamsSchemaJson());
            required(errors, PARAM_RENDER_TEMPLATE_JSON, asset.getRenderTemplateJson());
        }
    }

    /**
     * 校验 CARD_CONTAINER 组件只维护最终 payload 的 data 对象。
     *
     * <p>公共外壳由 Adviser 运行态使用可信资产元数据统一构建，组件配置不得重复声明或覆盖。
     */
    private void validateCardDataJson(String jsonText, String field, String componentName,
            boolean template, List<String> errors) {
        if (StringUtils.isBlank(jsonText)) {
            return;
        }
        if (template) {
            validateCardDataTemplate(jsonText, field, errors);
            return;
        }
        Object parsed;
        try {
            parsed = com.alibaba.fastjson2.JSON.parse(jsonText);
        } catch (Exception e) {
            return;
        }
        if (!(parsed instanceof com.alibaba.fastjson2.JSONObject)) {
            errors.add(field + ERROR_JSON_OBJECT_REQUIRED_SUFFIX);
            return;
        }
        com.alibaba.fastjson2.JSONObject data = (com.alibaba.fastjson2.JSONObject) parsed;
        for (String envelopeField : CARD_CONTAINER_ENVELOPE_FIELDS) {
            if (data.containsKey(envelopeField)) {
                errors.add(field + ERROR_CARD_DATA_ONLY_PREFIX + envelopeField);
            }
        }
        String cardType = trim(data.getString(JSON_FIELD_CARD_TYPE));
        if (StringUtils.isBlank(cardType)) {
            errors.add(field + ERROR_CARD_TYPE_REQUIRED_SUFFIX);
            return;
        }
        if (!StringUtils.equals(cardType, componentName)) {
            errors.add(field + ERROR_CARD_TYPE_MISMATCH_SUFFIX);
        }
    }

    private void validateCardDataTemplate(String templateJson, String field, List<String> errors) {
        String template = trim(templateJson);
        if (!StringUtils.startsWith(template, "{") || !StringUtils.endsWith(template, "}")) {
            errors.add(field + ERROR_JSON_OBJECT_REQUIRED_SUFFIX);
            return;
        }
        Set<String> rootFields = extractTemplateRootFields(template);
        for (String envelopeField : CARD_CONTAINER_ENVELOPE_FIELDS) {
            if (rootFields.contains(envelopeField)) {
                errors.add(field + ERROR_CARD_DATA_ONLY_PREFIX + envelopeField);
            }
        }
        if (!rootFields.contains(JSON_FIELD_CARD_TYPE)) {
            errors.add(field + ERROR_CARD_TYPE_REQUIRED_SUFFIX);
        }
    }

    /**
     * 提取受限 Handlebars JSON 模板的一级字段。
     *
     * <p>模板循环标签不是合法 JSON，不能在保存阶段直接反序列化；这里只扫描一级字符串 key，
     * 完整模板语法和渲染后 JSON 仍由 Adviser 的同一模板执行器校验。
     */
    private Set<String> extractTemplateRootFields(String template) {
        Set<String> fields = new LinkedHashSet<>();
        int depth = 0;
        for (int index = 0; index < template.length(); index++) {
            char current = template.charAt(index);
            if (current == '"') {
                int end = findJsonStringEnd(template, index + 1);
                if (end < 0) {
                    return Collections.emptySet();
                }
                if (depth == 1) {
                    int next = end + 1;
                    while (next < template.length() && Character.isWhitespace(template.charAt(next))) {
                        next++;
                    }
                    if (next < template.length() && template.charAt(next) == ':') {
                        fields.add(template.substring(index + 1, end));
                    }
                }
                index = end;
                continue;
            }
            if (current == '{' || current == '[') {
                depth++;
            } else if (current == '}' || current == ']') {
                depth--;
            }
        }
        return fields;
    }

    private int findJsonStringEnd(String text, int start) {
        boolean escaped = false;
        for (int index = start; index < text.length(); index++) {
            char current = text.charAt(index);
            if (escaped) {
                escaped = false;
            } else if (current == '\\') {
                escaped = true;
            } else if (current == '"') {
                return index;
            }
        }
        return -1;
    }

    private List<String> validatePreviewPayload(SkillFactoryComponentAsset asset, String payload) {
        if (StringUtils.isBlank(payload)) {
            return Collections.singletonList(PARAM_PREVIEW_JSON + ERROR_REQUIRED_SUFFIX);
        }
        Object json;
        try {
            json = com.alibaba.fastjson2.JSON.parse(payload);
        } catch (Exception e) {
            log.warn("SkillFactory组件中心预览JSON解析失败, id:{}, componentName:{}, error:{}",
                    asset.getId(), asset.getComponentName(), e.getMessage());
            return Collections.singletonList(ERROR_PREVIEW_JSON_INVALID);
        }
        List<String> errors = new ArrayList<>();
        if (StringUtils.equals(asset.getAssetType(), ASSET_TYPE_A2UI_ATOM)
                && !containsNonBlankField(json, JSON_FIELD_TYPE)) {
            errors.add(ERROR_PREVIEW_A2UI_TYPE);
        }
        return errors;
    }

    private SkillFactoryComponentPreviewResult buildBusinessDslPreviewResult(SkillFactoryComponentAsset asset,
            String payload) {
        List<String> errors = new ArrayList<>();
        com.alibaba.fastjson2.JSONObject preview = parseBusinessDslPreviewJson(asset, payload, errors);
        com.alibaba.fastjson2.JSONObject params = parseBusinessDslParams(preview, errors);
        boolean paramsValid = preview != null && params != null
                && validateParamsAgainstSchema(asset.getParamsSchemaJson(), params, errors);
        com.alibaba.fastjson2.JSONObject renderTemplate = parseJsonObjectConfig(errors, PARAM_RENDER_TEMPLATE_JSON,
                asset.getRenderTemplateJson(), true);
        boolean renderTemplateValid = renderTemplate != null;
        Object a2uiPayload = renderTemplate == null ? new LinkedHashMap<>()
                : applyRenderTemplate(renderTemplate, params, asset.getAgentUiDsl());

        return new SkillFactoryComponentPreviewResult()
                .setValid(errors.isEmpty())
                .setAssetId(asset.getId())
                .setComponentName(asset.getComponentName())
                .setAssetType(asset.getAssetType())
                .setDslType(asset.getDslType())
                .setPreviewJson(payload)
                .setParamsValid(paramsValid)
                .setRenderTemplateValid(renderTemplateValid)
                .setActionValid(Boolean.TRUE)
                .setA2uiMessagesPreview(buildBusinessDslCardPreview(a2uiPayload))
                .setContextSummaryPreview("dslType=" + asset.getDslType() + ", agentUiDsl="
                        + asset.getAgentUiDsl())
                .setErrors(errors);
    }

    private com.alibaba.fastjson2.JSONObject parseBusinessDslPreviewJson(SkillFactoryComponentAsset asset, String payload,
            List<String> errors) {
        if (StringUtils.isBlank(payload)) {
            errors.add(PARAM_PREVIEW_JSON + ERROR_REQUIRED_SUFFIX);
            return null;
        }
        Object json;
        try {
            json = com.alibaba.fastjson2.JSON.parse(stripRenderMarkers(payload));
        } catch (Exception e) {
            log.warn("SkillFactory组件中心BUSINESS_DSL预览JSON解析失败, id:{}, agentUiDsl:{}, error:{}",
                    asset.getId(), asset.getAgentUiDsl(), e.getMessage());
            errors.add(ERROR_PREVIEW_JSON_INVALID);
            return null;
        }
        if (!(json instanceof com.alibaba.fastjson2.JSONObject)) {
            errors.add(ERROR_PREVIEW_DSL_OBJECT);
            return null;
        }
        com.alibaba.fastjson2.JSONObject object = (com.alibaba.fastjson2.JSONObject) json;
        String dslType = upper(object.getString(JSON_FIELD_DSL_TYPE));
        String agentUiDsl = trim(object.getString(JSON_FIELD_AGENT_UI_DSL));
        if (!StringUtils.equals(dslType, DSL_TYPE_BUSINESS_DSL)
                || !StringUtils.equals(agentUiDsl, asset.getAgentUiDsl())) {
            errors.add(ERROR_PREVIEW_DSL_TYPE);
        }
        return object;
    }

    private com.alibaba.fastjson2.JSONObject parseBusinessDslParams(com.alibaba.fastjson2.JSONObject preview, List<String> errors) {
        if (preview == null) {
            return null;
        }
        Object params = preview.get(JSON_FIELD_PARAMS);
        if (!(params instanceof com.alibaba.fastjson2.JSONObject)) {
            errors.add(ERROR_PREVIEW_PARAMS_OBJECT);
            return null;
        }
        return (com.alibaba.fastjson2.JSONObject) params;
    }

    private boolean validateParamsAgainstSchema(String schemaJson, com.alibaba.fastjson2.JSONObject params, List<String> errors) {
        com.alibaba.fastjson2.JSONObject schema = parseJsonObjectConfig(errors, PARAM_PARAMS_SCHEMA_JSON, schemaJson, true);
        if (schema == null || params == null) {
            return false;
        }
        List<String> paramErrors = new ArrayList<>();
        Object required = schema.get(JSON_FIELD_REQUIRED);
        if (required instanceof com.alibaba.fastjson2.JSONArray) {
            for (Object item : (com.alibaba.fastjson2.JSONArray) required) {
                String field = trim(String.valueOf(item));
                if (StringUtils.isNotBlank(field)
                        && (!params.containsKey(field) || StringUtils.isBlank(String.valueOf(params.get(field))))) {
                    paramErrors.add(field + ERROR_PARAM_REQUIRED_SUFFIX);
                }
            }
        }
        Object properties = schema.get(JSON_FIELD_PROPERTIES);
        if (properties instanceof com.alibaba.fastjson2.JSONObject) {
            validateParamTypes(params, (com.alibaba.fastjson2.JSONObject) properties, paramErrors);
        }
        errors.addAll(paramErrors);
        return paramErrors.isEmpty();
    }

    private void validateParamTypes(com.alibaba.fastjson2.JSONObject params, com.alibaba.fastjson2.JSONObject properties, List<String> errors) {
        for (Map.Entry<String, Object> entry : properties.entrySet()) {
            String field = entry.getKey();
            Object value = params.get(field);
            if (value == null || !(entry.getValue() instanceof com.alibaba.fastjson2.JSONObject)) {
                continue;
            }
            String type = trim(((com.alibaba.fastjson2.JSONObject) entry.getValue()).getString(JSON_FIELD_TYPE));
            if (StringUtils.isBlank(type) || matchesJsonType(value, type)) {
                continue;
            }
            errors.add(field + ERROR_PARAM_TYPE_PREFIX + type);
        }
    }

    private boolean matchesJsonType(Object value, String type) {
        if (StringUtils.equals(type, "string")) {
            return value instanceof String;
        }
        if (StringUtils.equals(type, "number") || StringUtils.equals(type, "integer")) {
            return value instanceof Number;
        }
        if (StringUtils.equals(type, "boolean")) {
            return value instanceof Boolean;
        }
        if (StringUtils.equals(type, "object")) {
            return value instanceof com.alibaba.fastjson2.JSONObject;
        }
        if (StringUtils.equals(type, "array")) {
            return value instanceof com.alibaba.fastjson2.JSONArray;
        }
        return true;
    }

    private Object parseJsonConfig(List<String> errors, String field, String value, boolean required) {
        if (StringUtils.isBlank(value)) {
            if (required) {
                errors.add(field + ERROR_REQUIRED_SUFFIX);
            }
            return null;
        }
        try {
            return com.alibaba.fastjson2.JSON.parse(value);
        } catch (Exception e) {
            errors.add(field + ERROR_JSON_INVALID_PREFIX + e.getMessage());
            return null;
        }
    }

    private com.alibaba.fastjson2.JSONObject parseJsonObjectConfig(List<String> errors, String field, String value, boolean required) {
        Object json = parseJsonConfig(errors, field, value, required);
        if (json == null) {
            return null;
        }
        if (!(json instanceof com.alibaba.fastjson2.JSONObject)) {
            errors.add(field + ERROR_JSON_OBJECT_REQUIRED_SUFFIX);
            return null;
        }
        return (com.alibaba.fastjson2.JSONObject) json;
    }

    private List<Map<String, Object>> buildBusinessDslCardPreview(Object cardPayload) {
        if (!(cardPayload instanceof com.alibaba.fastjson2.JSONObject)) {
            return Collections.emptyList();
        }
        Map<String, Object> preview = new LinkedHashMap<>();
        preview.putAll((com.alibaba.fastjson2.JSONObject) cardPayload);
        return List.of(preview);
    }

    private void ensureUnique(SkillFactoryComponentAsset asset, Long excludeId) {
        if (componentAssetRepository.existsComponentIdentity(
                excludeId, asset.getAssetType(), asset.getComponentName())) {
            log.warn("SkillFactory组件中心管理身份冲突, assetType:{}, componentName:{}",
                    asset.getAssetType(), asset.getComponentName());
            throw new IllegalArgumentException(ERROR_DUPLICATE_COMPONENT_IDENTITY);
        }
        if (StringUtils.equals(asset.getDslType(), DSL_TYPE_BUSINESS_DSL)
                && componentAssetRepository.existsBusinessDslIdentity(
                excludeId, asset.getDslType(), asset.getAgentUiDsl())) {
            log.warn("SkillFactory组件中心BUSINESS_DSL身份冲突, dslType:{}, agentUiDsl:{}",
                    asset.getDslType(), asset.getAgentUiDsl());
            throw new IllegalArgumentException(ERROR_DUPLICATE_BUSINESS_DSL_IDENTITY);
        }
    }

    private void requireSameReleaseIdentity(SkillFactoryComponentAsset current,
            SkillFactoryComponentAsset releasedAsset) {
        boolean sameIdentity = releasedAsset != null
                && java.util.Objects.equals(current.getId(), releasedAsset.getId())
                && StringUtils.equals(current.getAssetType(), releasedAsset.getAssetType())
                && StringUtils.equals(current.getComponentName(), releasedAsset.getComponentName())
                && StringUtils.equals(current.getDslType(), releasedAsset.getDslType())
                && StringUtils.equals(current.getAgentUiDsl(), releasedAsset.getAgentUiDsl());
        if (!sameIdentity) {
            log.warn("SkillFactory组件正式版本身份不匹配, currentId:{}, releasedId:{}, "
                            + "currentComponentName:{}, releasedComponentName:{}",
                    current.getId(), releasedAsset == null ? null : releasedAsset.getId(),
                    current.getComponentName(), releasedAsset == null ? null : releasedAsset.getComponentName());
            throw new IllegalArgumentException(ERROR_RELEASE_SNAPSHOT_IDENTITY_MISMATCH);
        }
    }

    private void validateJsonField(List<String> errors, String field, String value, boolean required) {
        if (StringUtils.isBlank(value)) {
            if (required) {
                errors.add(field + ERROR_REQUIRED_SUFFIX);
            }
            return;
        }
        try {
            com.alibaba.fastjson2.JSON.parse(value);
        } catch (Exception e) {
            errors.add(field + ERROR_JSON_INVALID_PREFIX + e.getMessage());
        }
    }

    private boolean containsFieldValue(Object value, String field, String expected) {
        if (value instanceof com.alibaba.fastjson2.JSONObject) {
            com.alibaba.fastjson2.JSONObject object = (com.alibaba.fastjson2.JSONObject) value;
            if (StringUtils.equals(String.valueOf(object.get(field)), expected)) {
                return true;
            }
            return object.values().stream().anyMatch(item -> containsFieldValue(item, field, expected));
        }
        if (value instanceof com.alibaba.fastjson2.JSONArray) {
            com.alibaba.fastjson2.JSONArray array = (com.alibaba.fastjson2.JSONArray) value;
            return array.stream().anyMatch(item -> containsFieldValue(item, field, expected));
        }
        return false;
    }

    private boolean containsNonBlankField(Object value, String field) {
        if (value instanceof com.alibaba.fastjson2.JSONObject) {
            com.alibaba.fastjson2.JSONObject object = (com.alibaba.fastjson2.JSONObject) value;
            Object fieldValue = object.get(field);
            if (fieldValue != null && StringUtils.isNotBlank(String.valueOf(fieldValue))) {
                return true;
            }
            return object.values().stream().anyMatch(item -> containsNonBlankField(item, field));
        }
        if (value instanceof com.alibaba.fastjson2.JSONArray) {
            com.alibaba.fastjson2.JSONArray array = (com.alibaba.fastjson2.JSONArray) value;
            return array.stream().anyMatch(item -> containsNonBlankField(item, field));
        }
        return false;
    }

    private void required(List<String> errors, String field, String value) {
        if (StringUtils.isBlank(value)) {
            errors.add(field + ERROR_REQUIRED_SUFFIX);
        }
    }

    private void validateNoExecutableCodeParams(Map<String, String> params) {
        if (params == null || params.isEmpty()) {
            return;
        }
        List<String> errors = new ArrayList<>();
        params.forEach((key, value) -> {
            if (isExecutableCodeKey(key) && StringUtils.isNotBlank(value)) {
                errors.add(ERROR_EXECUTABLE_CODE_UPLOAD);
            }
            appendExecutableCodeJsonError(errors, key, value);
        });
        if (!errors.isEmpty()) {
            log.warn("SkillFactory组件中心拒绝可执行代码上传字段, keys:{}",
                    params.keySet());
            throw new IllegalArgumentException(StringUtils.join(errors, "; "));
        }
    }

    private void validateNoExecutableCodeAsset(SkillFactoryComponentAsset asset, List<String> errors) {
        appendExecutableCodeJsonError(errors, PARAM_PARAMS_SCHEMA_JSON, asset.getParamsSchemaJson());
        appendExecutableCodeJsonError(errors, PARAM_RENDER_TEMPLATE_JSON, asset.getRenderTemplateJson());
        appendExecutableCodeJsonError(errors, PARAM_OFFICIAL_DEMO_JSON, asset.getOfficialDemoJson());
        appendExecutableCodeJsonError(errors, PARAM_MESSAGE_DEMO_JSON, asset.getMessageDemoJson());
        appendExecutableCodeJsonError(errors, PARAM_ALLOWED_ACTIONS_JSON, asset.getAllowedActionsJson());
        appendExecutableCodeJsonError(errors, PARAM_RUNTIME_CONFIG_JSON, asset.getRuntimeConfigJson());
        appendExecutableCodeJsonError(errors, PARAM_ATTRIBUTE, asset.getAttribute());
    }

    private void appendExecutableCodeJsonError(List<String> errors, String field, String value) {
        if (StringUtils.isBlank(value) || !(StringUtils.startsWith(StringUtils.trim(value), "{")
                || StringUtils.startsWith(StringUtils.trim(value), JSON_ARRAY_PREFIX))) {
            return;
        }
        try {
            Object json = com.alibaba.fastjson2.JSON.parse(value);
            if (containsExecutableCodeKey(json)) {
                errors.add(field + ": " + ERROR_EXECUTABLE_CODE_UPLOAD);
            }
        } catch (Exception ignored) {
            // JSON 格式错误由 validateJsonField / parseJsonConfig 统一返回，避免重复噪音。
        }
    }

    private boolean containsExecutableCodeKey(Object value) {
        if (value instanceof com.alibaba.fastjson2.JSONObject) {
            com.alibaba.fastjson2.JSONObject object = (com.alibaba.fastjson2.JSONObject) value;
            for (Map.Entry<String, Object> entry : object.entrySet()) {
                if (isExecutableCodeKey(entry.getKey()) || containsExecutableCodeKey(entry.getValue())) {
                    return true;
                }
            }
            return false;
        }
        if (value instanceof com.alibaba.fastjson2.JSONArray) {
            com.alibaba.fastjson2.JSONArray array = (com.alibaba.fastjson2.JSONArray) value;
            return array.stream().anyMatch(this::containsExecutableCodeKey);
        }
        return false;
    }

    private boolean isExecutableCodeKey(String key) {
        String normalized = StringUtils.lowerCase(StringUtils.deleteWhitespace(
                StringUtils.replaceChars(StringUtils.defaultString(key), "_-", EMPTY)));
        return EXECUTABLE_CODE_PARAM_KEYS.contains(normalized);
    }

    private Long parseId(String id) {
        if (StringUtils.isBlank(id)) {
            throw new IllegalArgumentException(PARAM_ID + ERROR_REQUIRED_SUFFIX);
        }
        try {
            long value = Long.parseLong(id);
            if (value <= 0) {
                throw new NumberFormatException(ERROR_ID_INVALID);
            }
            return value;
        } catch (NumberFormatException e) {
            throw new IllegalArgumentException(ERROR_ID_INVALID);
        }
    }

    private List<String> parseSupportClients(String value) {
        if (StringUtils.isBlank(value)) {
            return new ArrayList<>();
        }
        try {
            return com.alibaba.fastjson2.JSON.parseArray(value, String.class).stream()
                    .map(StringUtils::trimToEmpty)
                    .filter(StringUtils::isNotBlank)
                    .collect(Collectors.toList());
        } catch (Exception e) {
            log.warn("SkillFactory组件中心supportClients解析失败, error:{}", e.getMessage());
            throw new IllegalArgumentException(PARAM_SUPPORT_CLIENTS + ERROR_JSON_ARRAY_REQUIRED_SUFFIX);
        }
    }

    private String value(Map<String, String> params, String key, String current, boolean upper) {
        if (!params.containsKey(key)) {
            return StringUtils.defaultString(current);
        }
        return upper ? upper(params.get(key)) : trim(params.get(key));
    }

    private boolean booleanValue(String value, boolean defaultValue) {
        if (StringUtils.isBlank(value)) {
            return defaultValue;
        }
        return StringUtils.equalsIgnoreCase(value, "true") || StringUtils.equals(value, "1");
    }

    private Integer integerValue(Map<String, String> params, String key, Integer current, int defaultValue) {
        if (!params.containsKey(key)) {
            return current == null ? defaultValue : current;
        }
        try {
            int parsed = Integer.parseInt(trim(params.get(key)));
            if (parsed <= 0) {
                throw new NumberFormatException(ERROR_PROTOCOL_VERSION_INVALID);
            }
            return parsed;
        } catch (NumberFormatException exception) {
            throw new IllegalArgumentException(ERROR_PROTOCOL_VERSION_INVALID);
        }
    }

    private String upper(String value) {
        return StringUtils.upperCase(trim(value));
    }

    private String trim(String value) {
        return StringUtils.trimToEmpty(value);
    }

    private SkillFactoryComponentAsset copy(SkillFactoryComponentAsset source) {
        return new SkillFactoryComponentAsset()
                .setId(source.getId())
                .setAssetType(source.getAssetType())
                .setComponentName(source.getComponentName())
                .setComponentNameCn(source.getComponentNameCn())
                .setDslType(source.getDslType())
                .setAgentUiDsl(source.getAgentUiDsl())
                .setProtocolVersion(source.getProtocolVersion())
                .setInteractionMode(source.getInteractionMode())
                .setBundleUrl(source.getBundleUrl())
                .setAppBundleUrl(source.getAppBundleUrl())
                .setOwner(source.getOwner())
                .setScene(source.getScene())
                .setParamsSchemaJson(source.getParamsSchemaJson())
                .setRenderTemplateJson(source.getRenderTemplateJson())
                .setOfficialDemoJson(source.getOfficialDemoJson())
                .setMessageDemoJson(source.getMessageDemoJson())
                .setIntegrationPrompt(source.getIntegrationPrompt())
                .setAllowedActionsJson(source.getAllowedActionsJson())
                .setRuntimeConfigJson(source.getRuntimeConfigJson())
                .setSupportClients(copySupportClients(source.getSupportClients()))
                .setEnabled(source.getEnabled())
                .setAttribute(source.getAttribute())
                .setPublished(source.getPublished())
                .setPublishedVersion(source.getPublishedVersion())
                .setOperator(source.getOperator())
                .setCreateTime(source.getCreateTime())
                .setUpdateTime(source.getUpdateTime());
    }

    /**
     * 把 Registry 领域对象映射为稳定 API DTO。
     */
    private SkillFactoryComponentAsset toApiAsset(ComponentAsset source) {
        return new SkillFactoryComponentAsset()
                .setId(source.getId())
                .setAssetType(source.getAssetType())
                .setComponentName(source.getComponentName())
                .setComponentNameCn(source.getComponentNameCn())
                .setDslType(source.getDslType())
                .setAgentUiDsl(source.getAgentUiDsl())
                .setProtocolVersion(source.getProtocolVersion())
                .setInteractionMode(source.getInteractionMode())
                .setBundleUrl(source.getBundleUrl())
                .setAppBundleUrl(source.getAppBundleUrl())
                .setOwner(source.getOwner())
                .setScene(source.getScene())
                .setParamsSchemaJson(source.getParamsSchemaJson())
                .setRenderTemplateJson(source.getRenderTemplateJson())
                .setOfficialDemoJson(source.getOfficialDemoJson())
                .setMessageDemoJson(source.getMessageDemoJson())
                .setAllowedActionsJson(source.getAllowedActionsJson())
                .setRuntimeConfigJson(source.getRuntimeConfigJson())
                .setIntegrationPrompt(source.getIntegrationPrompt())
                .setSupportClients(copySupportClients(source.getSupportClients()))
                .setEnabled(source.getEnabled())
                .setAttribute(source.getAttribute())
                .setOperator(source.getOperator())
                .setCreateTime(source.getCreateTime())
                .setUpdateTime(source.getUpdateTime());
    }

    /**
     * 把 API DTO 映射为 Registry 领域对象，DO 转换仍由 Repository 独占。
     */
    private ComponentAsset toDomainAsset(SkillFactoryComponentAsset source) {
        return new ComponentAsset()
                .setId(source.getId())
                .setAssetType(source.getAssetType())
                .setComponentName(source.getComponentName())
                .setComponentNameCn(source.getComponentNameCn())
                .setDslType(source.getDslType())
                .setAgentUiDsl(source.getAgentUiDsl())
                .setProtocolVersion(source.getProtocolVersion())
                .setInteractionMode(source.getInteractionMode())
                .setBundleUrl(source.getBundleUrl())
                .setAppBundleUrl(source.getAppBundleUrl())
                .setOwner(source.getOwner())
                .setScene(source.getScene())
                .setParamsSchemaJson(source.getParamsSchemaJson())
                .setRenderTemplateJson(source.getRenderTemplateJson())
                .setOfficialDemoJson(source.getOfficialDemoJson())
                .setMessageDemoJson(source.getMessageDemoJson())
                .setAllowedActionsJson(source.getAllowedActionsJson())
                .setRuntimeConfigJson(source.getRuntimeConfigJson())
                .setIntegrationPrompt(source.getIntegrationPrompt())
                .setSupportClients(copySupportClients(source.getSupportClients()))
                .setEnabled(source.getEnabled())
                .setAttribute(source.getAttribute())
                .setOperator(source.getOperator())
                .setCreateTime(source.getCreateTime())
                .setUpdateTime(source.getUpdateTime());
    }

    private List<String> copySupportClients(List<String> supportClients) {
        return supportClients == null ? new ArrayList<>() : new ArrayList<>(supportClients);
    }

}
