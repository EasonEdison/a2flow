package dev.a2flow.management.a2ui.application;

import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Map;

import jakarta.annotation.Resource;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiApplicationActionScanResult;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiInteractionMode;
import dev.a2flow.management.a2ui.registry.A2uiRegistryValidationException;
import dev.a2flow.management.access.AssetAuthorizationService;
import dev.a2flow.management.lifecycle.domain.ComponentAsset;
import dev.a2flow.management.release.ReleaseAssetType;
import dev.a2flow.management.storage.db.repository.SkillFactoryComponentAssetRepository;

/**
 * A2UI_APPLICATION 当前 source 到共享 Registry 的转换服务。
 *
 * <p>上游是 M 端 Application authoring payload，下游是 `skill_component_registry` 当前行。
 * 完整编辑态只落 `runtime_config_json`；Catalog、Host Profile、support evidence 和 immutable
 * release snapshot 不在本服务中伪造或从客户端输入推导。成功分支先按原始类型校验，再随完整 source 保存。
 */
@Service
public class A2uiApplicationRegistryService {

    private static final String ASSET_TYPE_A2UI_APPLICATION = "A2UI_APPLICATION";
    private static final String ERROR_PAYLOAD_REQUIRED = "A2UI_APPLICATION_PAYLOAD_REQUIRED";
    private static final String ERROR_REQUIRED_FIELD = "A2UI_APPLICATION_REQUIRED_FIELD_MISSING";
    private static final String ERROR_AUTHORITY_FORBIDDEN = "A2UI_APPLICATION_AUTHORITY_INPUT_FORBIDDEN";
    private static final String ERROR_ID_INVALID = "A2UI_APPLICATION_ID_INVALID";
    private static final String ERROR_NOT_FOUND = "A2UI_APPLICATION_NOT_FOUND";
    private static final String ERROR_DUPLICATE = "A2UI_APPLICATION_DUPLICATE";
    private static final String ERROR_ACTION_CODE_RESERVED = "A2UI_ACTION_CODE_RESERVED";
    private static final String ERROR_DRAFT_INVALID = "A2UI_APPLICATION_DRAFT_INVALID";
    private static final String ERROR_INTERACTION_MODE_INVALID =
            "A2UI_APPLICATION_INTERACTION_MODE_INVALID";
    private static final String FIELD_ACTION_BINDINGS = "actionBindings";
    private static final String FIELD_SUCCESS_BRANCHES = "successBranches";
    private static final String FIELD_COMPLETE_WORKFLOW_INTERACTION_ON_SUCCESS =
            "completeWorkflowInteractionOnSuccess";
    private static final String FIELD_INTERACTION_MODE = "interactionMode";
    private static final String PARAM_KEYWORD = "keyword";
    private static final List<String> AUTHORITY_FIELDS = Arrays.asList(
            "catalog", "catalogRevision", "catalogDigest", "catalogSourceType",
            "componentOriginType", "componentOrigins", "frontendSupport",
            "hostProfile", "release", "support", "rendererArtifactDigest", "appBuildId",
            "publicationEnvironment",
            "protocolVersion", "protocolStatus", "protocolSourceCommit", "protocolSchemaDigests",
            "clientDataModel",
            "rawMessages", "capabilityEndpoint", "resultAdapter", "identity", "environment",
            "credential", "script");

    private final A2uiApplicationActionScanService actionScanService =
            new A2uiApplicationActionScanService();

    @Resource
    private SkillFactoryComponentAssetRepository assetRepository;

    @Resource
    private AssetAuthorizationService assetAuthorizationService;

    /**
     * 将仅含 authoring source 的 payload 写入共享 Registry 当前态。
     */
    public ComponentAsset toRegistryAsset(Map<String, Object> payload, String operator) {
        validateAuthority(payload);
        // 在 JSON 复制和持久化前拒绝非法转换，保留原始字符串类型与全部空白。
        try {
            A2uiRequestTransformValidator.validate(payload);
            A2uiSuccessBranchValidator.validate(payload);
        } catch (A2uiApplicationValidationException exception) {
            throw new A2uiRegistryValidationException(ERROR_DRAFT_INVALID);
        }
        Map<String, Object> canonicalPayload = canonicalAuthoringPayload(payload);
        String appCode = text(canonicalPayload, "appCode");
        String nameCn = text(canonicalPayload, "nameCn");
        String catalogId = text(canonicalPayload, "catalogId");
        if (StringUtils.isAnyBlank(appCode, nameCn, catalogId)) {
            throw new A2uiRegistryValidationException(ERROR_REQUIRED_FIELD);
        }
        validateReservedActionCodes(canonicalPayload);
        String canonicalSource = JsonSupport.toJSON(
                A2uiImmutableJsonSupport.canonicalize(canonicalPayload));
        return new ComponentAsset()
                .setAssetType(ASSET_TYPE_A2UI_APPLICATION)
                .setComponentName(appCode)
                .setComponentNameCn(nameCn)
                .setRuntimeConfigJson(canonicalSource)
                .setEnabled(Boolean.TRUE)
                .setOperator(StringUtils.trimToNull(operator));
    }

    /** 显式补齐 Workflow 交互缺省值；非法作者态输入保持 fail closed。 */
    @SuppressWarnings("unchecked")
    private Map<String, Object> canonicalAuthoringPayload(Map<String, Object> payload) {
        Map<String, Object> canonicalPayload = JsonSupport.fromJSON(
                JsonSupport.toJSON(payload), Map.class);
        String interactionMode = text(canonicalPayload, FIELD_INTERACTION_MODE);
        if (interactionMode == null) {
            canonicalPayload.put(FIELD_INTERACTION_MODE, A2uiInteractionMode.DISPLAY_ONLY.name());
        } else {
            try {
                canonicalPayload.put(FIELD_INTERACTION_MODE,
                        A2uiInteractionMode.valueOf(interactionMode).name());
            } catch (IllegalArgumentException exception) {
                throw new A2uiRegistryValidationException(ERROR_INTERACTION_MODE_INVALID);
            }
        }
        for (Object rawBinding : list(canonicalPayload.get(FIELD_ACTION_BINDINGS))) {
            if (!(rawBinding instanceof Map)) {
                throw new A2uiRegistryValidationException(ERROR_DRAFT_INVALID);
            }
            Map<String, Object> binding = (Map<String, Object>) rawBinding;
            canonicalCompletion(binding);
            for (Object rawBranch : list(binding.get(FIELD_SUCCESS_BRANCHES))) {
                canonicalCompletion((Map<String, Object>) rawBranch);
            }
        }
        return canonicalPayload;
    }

    /** 根与分支共用完成标记缺省规则；结构已由原始形态校验器检查。 */
    private void canonicalCompletion(Map<String, Object> source) {
        Object completion = source.get(FIELD_COMPLETE_WORKFLOW_INTERACTION_ON_SUCCESS);
        if (completion == null) {
            source.put(FIELD_COMPLETE_WORKFLOW_INTERACTION_ON_SUCCESS, Boolean.FALSE);
        } else if (!(completion instanceof Boolean)) {
            throw new A2uiRegistryValidationException(ERROR_DRAFT_INVALID);
        }
    }

    /**
     * 从共享 Registry 读取 A2UI_APPLICATION 当前 source；不存在时返回空，禁止读取其他资产类型。
     */
    public ComponentAsset current(String appCode) {
        if (assetRepository == null || StringUtils.isBlank(appCode)) {
            return null;
        }
        return assetRepository.findByAssetTypeAndName(ASSET_TYPE_A2UI_APPLICATION, appCode);
    }

    /** 查询 A2UI_APPLICATION 当前 Registry 行。 */
    public List<ComponentAsset> list(Map<String, String> params) {
        String keyword = params == null ? null : params.get(PARAM_KEYWORD);
        return assetRepository.list(new SkillFactoryComponentAssetRepository.ComponentAssetQuery()
                .setAssetType(ASSET_TYPE_A2UI_APPLICATION)
                .setKeyword(keyword), false);
    }

    /** 按 Registry 主键读取 A2UI_APPLICATION。 */
    public ComponentAsset detail(String id) {
        return assetRepository.get(parseId(id));
    }

    /** 创建 Application 当前 source；不创建独立 draft 表。 */
    public ComponentAsset create(String operator, Map<String, Object> payload) {
        ComponentAsset next = toRegistryAsset(payload, operator);
        if (assetRepository.existsComponentIdentity(null, ASSET_TYPE_A2UI_APPLICATION,
                next.getComponentName())) {
            throw new A2uiRegistryValidationException(ERROR_DUPLICATE);
        }
        ComponentAsset saved = assetRepository.save(next);
        if (assetAuthorizationService != null) {
            assetAuthorizationService.initializeOwners(operator, ReleaseAssetType.A2UI_APPLICATION,
                    next.getComponentName(), null);
        }
        return saved;
    }

    /** 更新 Application 当前 source；Catalog/Profile/support 继续由服务端只读 projection 提供。 */
    public ComponentAsset update(String operator, String id, Map<String, Object> payload) {
        Long assetId = parseId(id);
        ComponentAsset current = assetRepository.get(assetId);
        if (current == null || !ASSET_TYPE_A2UI_APPLICATION.equals(current.getAssetType())) {
            throw new A2uiRegistryValidationException(ERROR_NOT_FOUND);
        }
        ComponentAsset next = toRegistryAsset(payload, operator).setId(assetId);
        if (assetRepository.existsComponentIdentity(assetId, ASSET_TYPE_A2UI_APPLICATION,
                next.getComponentName())) {
            throw new A2uiRegistryValidationException(ERROR_DUPLICATE);
        }
        return assetRepository.update(next);
    }

    /** 保存成功后只从 Registry canonical source 重新扫描，拒绝浏览器旧状态污染返回结果。 */
    @SuppressWarnings("unchecked")
    public A2uiApplicationActionScanResult scanCanonicalSource(ComponentAsset saved) {
        if (saved == null || StringUtils.isBlank(saved.getRuntimeConfigJson())) {
            throw new A2uiRegistryValidationException(ERROR_PAYLOAD_REQUIRED);
        }
        Map<String, Object> source = JsonSupport.fromJSON(
                saved.getRuntimeConfigJson(), Map.class);
        if (source == null) {
            throw new A2uiRegistryValidationException(ERROR_PAYLOAD_REQUIRED);
        }
        return actionScanService.scan(source);
    }

    private void validateAuthority(Map<String, Object> payload) {
        if (payload == null) {
            throw new A2uiRegistryValidationException(ERROR_PAYLOAD_REQUIRED);
        }
        for (String authorityField : AUTHORITY_FIELDS) {
            if (payload.containsKey(authorityField)) {
                throw new A2uiRegistryValidationException(ERROR_AUTHORITY_FORBIDDEN);
            }
        }
    }

    /**
     * 只识别作者态明确声明的 ActionCode 保留边界，不要求尚未完成的草稿通过完整 Show/Build 校验。
     */
    private void validateReservedActionCodes(Map<String, Object> payload) {
        for (Object rawBinding : list(payload.get("loadBindings"))) {
            rejectReservedActionCode(text(map(map(rawBinding).get("capability")), "actionCode"));
        }
        for (Object rawBinding : list(payload.get("actionBindings"))) {
            Map<String, Object> binding = map(rawBinding);
            rejectReservedActionCode(text(binding, "actionCode"));
            rejectReservedActionCode(text(map(binding.get("capability")), "actionCode"));
        }
        Map<String, Object> showTemplate = map(payload.get("showTemplate"));
        for (Object rawMessage : list(showTemplate.get("messageTemplates"))) {
            Map<String, Object> updateComponents = map(map(rawMessage).get("updateComponents"));
            for (Object rawComponent : list(updateComponents.get("components"))) {
                Map<String, Object> action = map(map(rawComponent).get("action"));
                rejectReservedActionCode(text(map(action.get("event")), "name"));
            }
        }
    }

    private void rejectReservedActionCode(String actionCode) {
        if (A2uiReservedActionCode.isReserved(actionCode)) {
            throw new A2uiRegistryValidationException(ERROR_ACTION_CODE_RESERVED);
        }
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> map(Object value) {
        return value instanceof Map ? (Map<String, Object>) value : Collections.emptyMap();
    }

    private List<?> list(Object value) {
        return value instanceof List ? (List<?>) value : Collections.emptyList();
    }

    private String text(Map<String, Object> payload, String fieldName) {
        Object value = payload.get(fieldName);
        return value == null ? null : StringUtils.trimToNull(String.valueOf(value));
    }

    private Long parseId(String id) {
        try {
            return Long.valueOf(id);
        } catch (Exception exception) {
            throw new A2uiRegistryValidationException(ERROR_ID_INVALID);
        }
    }
}
