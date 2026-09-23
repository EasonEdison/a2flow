package dev.a2flow.management.agentcore.runtime.tool;

import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

import jakarta.annotation.Resource;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Component;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.model.CapabilityActionDraft;
import dev.a2flow.management.model.CapabilityActionExecutionPlan;
import dev.a2flow.management.model.CapabilityToolErrorCode;
import dev.a2flow.management.release.CapabilityReleasePayloadAdapter;
import dev.a2flow.management.release.ReleaseAssetType;
import dev.a2flow.management.release.ReleaseEnvironment;
import dev.a2flow.management.release.ReleaseModels.AssetReleaseState;
import dev.a2flow.management.release.dependency.AssetDependencyModels.AssetDependencyReference;
import dev.a2flow.management.release.dependency.AssetDependencyModels.AssetResolutionContext;
import dev.a2flow.management.release.dependency.AssetDependencyModels.ResolvedReleasedAsset;
import dev.a2flow.management.release.dependency.AssetDependencyType;
import dev.a2flow.management.release.dependency.EnvironmentAwareAssetResolver;
import dev.a2flow.management.storage.db.repository.AssetReleaseStateRepository;

import lombok.extern.slf4j.Slf4j;

/**
 * 环境感知业务能力目录。
 *
 * <p>目录只枚举共享发布状态中的稳定能力身份，并按可信环境和 userId 解析不可变发布源。模型可见
 * 查询结果不包含 assetKey、URL、Header、凭证、环境指针或版本来源；草稿和解析失败的发布源不会进入目录。
 */
@Component
@Slf4j
public class CapabilityCatalogQueryService {

    private static final String FIELD_BASIC_INFO = "basicInfo";
    private static final String FIELD_CLIENT_VARIANTS = "clientVariants";
    private static final String FIELD_MODEL_CONTRACT = "modelContract";
    private static final String FIELD_GOVERNANCE = "governance";
    private static final String FIELD_ACTION_CODE = "actionCode";
    private static final String FIELD_NAME_CN = "nameCn";
    private static final String FIELD_BUSINESS_DOMAIN = "businessDomain";
    private static final String FIELD_DESCRIPTION = "description";
    private static final String FIELD_INPUT_EXAMPLE_JSON = "inputExampleJson";
    private static final String FIELD_APPROVAL_POLICY = "approvalPolicy";
    private static final String FIELD_STATUS = "status";
    private static final String FIELD_MODEL_DESCRIPTION = "modelDescription";
    private static final String FIELD_INPUT_SCHEMA = "inputSchema";
    private static final String FIELD_INPUT_EXAMPLE = "inputExample";
    private static final String FIELD_KEY_OUTPUT_FIELDS = "keyOutputFields";
    private static final String FIELD_SIDE_EFFECT_LEVEL = "sideEffectLevel";
    private static final String FIELD_ERROR_CODE = "errorCode";
    private static final String STATUS_AVAILABLE = "AVAILABLE";
    private static final String STATUS_UNAVAILABLE = "UNAVAILABLE";
    private static final String CLIENT_PC = "PC";
    private static final String CLIENT_APP = "APP";
    private static final String ERROR_TRUSTED_CLIENT_TYPE = "trusted clientType must be PC or APP";
    private static final String MESSAGE_CLIENT_NOT_SUPPORTED =
            "business capability does not support trusted clientType";
    private static final String MESSAGE_RELEASE_NOT_AVAILABLE =
            "business capability release is not available in trusted environment";

    @Resource
    private AssetReleaseStateRepository assetReleaseStateRepository;

    @Resource
    private EnvironmentAwareAssetResolver environmentAwareAssetResolver;

    @Resource
    private CapabilityReleasePayloadAdapter capabilityReleasePayloadAdapter;

    @Resource
    private CapabilityActionToolProvider capabilityActionToolProvider;

    public CapabilityCatalogQueryService() {
    }

    /** 显式依赖构造仅用于聚焦回归，生产环境仍由 Spring 注入同一组组件。 */
    public CapabilityCatalogQueryService(AssetReleaseStateRepository assetReleaseStateRepository,
            EnvironmentAwareAssetResolver environmentAwareAssetResolver,
            CapabilityReleasePayloadAdapter capabilityReleasePayloadAdapter,
            CapabilityActionToolProvider capabilityActionToolProvider) {
        this.assetReleaseStateRepository = assetReleaseStateRepository;
        this.environmentAwareAssetResolver = environmentAwareAssetResolver;
        this.capabilityReleasePayloadAdapter = capabilityReleasePayloadAdapter;
        this.capabilityActionToolProvider = capabilityActionToolProvider;
    }

    /** 按业务域返回当前可信环境下可用能力的精简摘要。 */
    public List<Map<String, Object>> queryByBusinessDomain(String businessDomain,
            ReleaseEnvironment requestedEnvironment, Long userId, String clientType) {
        if (StringUtils.isBlank(businessDomain)) {
            throw new CapabilityCatalogException(CapabilityToolErrorCode.ARGUMENT_INVALID,
                    "businessDomain is required");
        }
        CatalogSnapshot catalog = loadCatalog(requestedEnvironment, userId, clientType);
        return catalog.entries.values().stream()
                .filter(entry -> StringUtils.equals(businessDomain, entry.businessDomain))
                .sorted(Comparator.comparing(entry -> entry.actionCode))
                .map(this::compactView)
                .toList();
    }

    /** 按 actionCode 批量返回模型选择和执行需要的契约，缺失项显式返回 UNAVAILABLE。 */
    public List<Map<String, Object>> queryByActionCodes(List<String> actionCodes,
            ReleaseEnvironment requestedEnvironment, Long userId, String clientType) {
        Set<String> normalizedActionCodes = normalizeActionCodes(actionCodes);
        CatalogSnapshot catalog = loadCatalog(requestedEnvironment, userId, clientType);
        List<Map<String, Object>> result = new ArrayList<>();
        for (String actionCode : normalizedActionCodes) {
            CatalogEntry entry = catalog.entries.get(actionCode);
            result.add(entry == null
                    ? unavailableView(actionCode, catalog.clientUnsupportedActionCodes.contains(actionCode)
                            ? CapabilityToolErrorCode.CAPABILITY_CLIENT_NOT_SUPPORTED
                            : CapabilityToolErrorCode.CAPABILITY_RELEASE_NOT_AVAILABLE)
                    : fullView(entry));
        }
        return result;
    }

    /**
     * 按 actionCode 批量返回可安全编译进 SKILL.md 的稳定使用提示字段。
     *
     * <p>该投影不包含参数 Schema、示例、关键出参、transport 或发布来源；调用方只能把它作为
     * 作者态提示，运行前仍须重新查询完整契约。缺失项保持显式 UNAVAILABLE，避免编译端保留旧内容。
     */
    public List<Map<String, Object>> queryGuidanceByActionCodes(List<String> actionCodes,
            ReleaseEnvironment requestedEnvironment, Long userId) {
        Set<String> normalizedActionCodes = normalizeActionCodes(actionCodes);
        Map<String, CatalogEntry> catalog = loadGuidanceCatalog(requestedEnvironment, userId);
        List<Map<String, Object>> result = new ArrayList<>();
        for (String actionCode : normalizedActionCodes) {
            CatalogEntry entry = catalog.get(actionCode);
            result.add(entry == null ? unavailableView(actionCode) : guidanceView(entry));
        }
        return result;
    }

    /**
     * 创建期 SKILL.md 指引只读取公共业务语义和治理，不选端、不泄露端内技术契约。
     */
    private Map<String, CatalogEntry> loadGuidanceCatalog(
            ReleaseEnvironment requestedEnvironment, Long userId) {
        if (requestedEnvironment == null) {
            throw new CapabilityCatalogException(CapabilityToolErrorCode.RELEASE_ENVIRONMENT_REQUIRED,
                    "trusted releaseEnvironment is required");
        }
        Map<String, CatalogEntry> catalog = new LinkedHashMap<>();
        for (AssetReleaseState state : assetReleaseStateRepository.listByAssetType(
                ReleaseAssetType.CAPABILITY_ACTION)) {
            CatalogEntry entry = resolveGuidanceEntry(state, requestedEnvironment, userId);
            if (entry == null) {
                continue;
            }
            CatalogEntry previous = catalog.putIfAbsent(entry.actionCode, entry);
            if (previous != null && !StringUtils.equals(previous.assetKey, entry.assetKey)) {
                throw new CapabilityCatalogException(CapabilityToolErrorCode.CAPABILITY_ACTION_CODE_CONFLICT,
                        "released business capability actionCode is duplicated");
            }
        }
        return catalog;
    }

    private CatalogEntry resolveGuidanceEntry(AssetReleaseState state,
            ReleaseEnvironment requestedEnvironment, Long userId) {
        String assetKey = state == null ? StringUtils.EMPTY : StringUtils.trimToEmpty(state.getAssetKey());
        if (StringUtils.isBlank(assetKey)) {
            return null;
        }
        try {
            ResolvedReleasedAsset resolvedAsset = environmentAwareAssetResolver.resolve(
                    new AssetDependencyReference()
                            .setAssetType(AssetDependencyType.CAPABILITY_ACTION)
                            .setAssetKey(assetKey),
                    new AssetResolutionContext()
                            .setRequestedEnvironment(requestedEnvironment)
                            .setUserId(userId));
            if (resolvedAsset.getResolvedEnvironment() != requestedEnvironment) return null;
            CapabilityActionDraft draft = capabilityReleasePayloadAdapter.requireExecutableDraft(resolvedAsset);
            return guidanceEntry(assetKey, draft);
        } catch (Exception exception) {
            log.warn("业务能力创建期指引跳过不可用发布源, assetKey:{}, requestedEnvironment:{}, errorType:{}",
                    assetKey, requestedEnvironment, exception.getClass().getSimpleName());
            return null;
        }
    }

    private CatalogEntry guidanceEntry(String assetKey, CapabilityActionDraft draft) {
        Map<String, Object> root = draft.getDraft();
        Map<String, Object> basicInfo = map(root.get(FIELD_BASIC_INFO));
        Map<String, Object> governance = map(root.get(FIELD_GOVERNANCE));
        CatalogEntry result = new CatalogEntry();
        result.assetKey = assetKey;
        result.actionCode = required(basicInfo, FIELD_ACTION_CODE);
        result.nameCn = required(basicInfo, FIELD_NAME_CN);
        result.businessDomain = required(basicInfo, FIELD_BUSINESS_DOMAIN);
        result.description = required(basicInfo, FIELD_DESCRIPTION);
        result.modelDescription = result.description;
        result.sideEffectLevel = required(governance, FIELD_SIDE_EFFECT_LEVEL);
        result.approvalPolicy = required(governance, FIELD_APPROVAL_POLICY);
        return result;
    }

    /** 为固定执行 Tool 将模型 actionCode 映射为当前可信环境下唯一稳定资产身份。 */
    public String requireAssetKey(String actionCode, ReleaseEnvironment requestedEnvironment,
            Long userId, String clientType) {
        if (StringUtils.isBlank(actionCode)) {
            throw new CapabilityCatalogException(CapabilityToolErrorCode.ARGUMENT_INVALID,
                    "actionCode is required");
        }
        CatalogSnapshot catalog = loadCatalog(requestedEnvironment, userId, clientType);
        CatalogEntry entry = catalog.entries.get(actionCode);
        if (entry == null) {
            CapabilityToolErrorCode errorCode = catalog.clientUnsupportedActionCodes.contains(actionCode)
                    ? CapabilityToolErrorCode.CAPABILITY_CLIENT_NOT_SUPPORTED
                    : CapabilityToolErrorCode.CAPABILITY_RELEASE_NOT_AVAILABLE;
            throw new CapabilityCatalogException(errorCode, errorCode
                    == CapabilityToolErrorCode.CAPABILITY_CLIENT_NOT_SUPPORTED
                    ? MESSAGE_CLIENT_NOT_SUPPORTED : MESSAGE_RELEASE_NOT_AVAILABLE);
        }
        return entry.assetKey;
    }

    /** 枚举稳定发布聚合并按可信环境解析，任何 actionCode 冲突都关闭整个目录。 */
    private CatalogSnapshot loadCatalog(ReleaseEnvironment requestedEnvironment,
            Long userId, String requestedClientType) {
        if (requestedEnvironment == null) {
            throw new CapabilityCatalogException(CapabilityToolErrorCode.RELEASE_ENVIRONMENT_REQUIRED,
                    "trusted releaseEnvironment is required");
        }
        String clientType = requireClientType(requestedClientType);
        Map<String, CatalogEntry> catalog = new LinkedHashMap<>();
        Set<String> clientUnsupportedActionCodes = new LinkedHashSet<>();
        for (AssetReleaseState state : assetReleaseStateRepository.listByAssetType(
                ReleaseAssetType.CAPABILITY_ACTION)) {
            CatalogEntry entry = resolveEntry(state, requestedEnvironment, userId,
                    clientType, clientUnsupportedActionCodes);
            if (entry == null) {
                continue;
            }
            CatalogEntry previous = catalog.putIfAbsent(entry.actionCode, entry);
            if (previous != null && !StringUtils.equals(previous.assetKey, entry.assetKey)) {
                log.error("业务能力目录发现重复actionCode, actionCode:{}, firstAssetKey:{}, secondAssetKey:{}",
                        entry.actionCode, previous.assetKey, entry.assetKey);
                throw new CapabilityCatalogException(CapabilityToolErrorCode.CAPABILITY_ACTION_CODE_CONFLICT,
                        "released business capability actionCode is duplicated");
            }
        }
        return new CatalogSnapshot(catalog, clientUnsupportedActionCodes);
    }

    /** 解析单项不可变发布源；不可用项跳过且不读取草稿、最大版本或替代来源。 */
    private CatalogEntry resolveEntry(AssetReleaseState state, ReleaseEnvironment requestedEnvironment,
            Long userId, String clientType, Set<String> clientUnsupportedActionCodes) {
        String assetKey = state == null ? StringUtils.EMPTY : StringUtils.trimToEmpty(state.getAssetKey());
        if (StringUtils.isBlank(assetKey)) {
            return null;
        }
        CapabilityActionDraft draft = null;
        try {
            ResolvedReleasedAsset resolvedAsset = environmentAwareAssetResolver.resolve(
                    new AssetDependencyReference()
                            .setAssetType(AssetDependencyType.CAPABILITY_ACTION)
                            .setAssetKey(assetKey),
                    new AssetResolutionContext()
                            .setRequestedEnvironment(requestedEnvironment)
                            .setUserId(userId));
            if (resolvedAsset.getResolvedEnvironment() != requestedEnvironment) return null;
            draft = capabilityReleasePayloadAdapter.requireExecutableDraft(resolvedAsset);
            CapabilityActionExecutionPlan plan = capabilityActionToolProvider.compile(draft, clientType);
            return entry(assetKey, draft, plan);
        } catch (CapabilityActionToolProvider.CapabilityClientNotSupportedException exception) {
            String actionCode = draft == null ? StringUtils.EMPTY
                    : string(map(draft.getDraft().get(FIELD_BASIC_INFO)).get(FIELD_ACTION_CODE));
            if (StringUtils.isNotBlank(actionCode)) {
                clientUnsupportedActionCodes.add(actionCode);
            }
            log.info("业务能力目录端契约不可用, assetKey:{}, actionCode:{}, clientType:{}",
                    assetKey, actionCode, exception.getClientType());
            return null;
        } catch (CapabilityCatalogException exception) {
            throw exception;
        } catch (Exception exception) {
            log.warn("业务能力目录跳过不可用发布源, assetKey:{}, requestedEnvironment:{}, clientType:{}, "
                            + "errorType:{}",
                    assetKey, requestedEnvironment, clientType, exception.getClass().getSimpleName());
            return null;
        }
    }

    private CatalogEntry entry(String assetKey, CapabilityActionDraft draft,
            CapabilityActionExecutionPlan plan) {
        Map<String, Object> root = draft.getDraft();
        Map<String, Object> basicInfo = map(root.get(FIELD_BASIC_INFO));
        Map<String, Object> variant = map(map(root.get(FIELD_CLIENT_VARIANTS))
                .get(plan.getContractClientType()));
        Map<String, Object> modelContract = map(variant.get(FIELD_MODEL_CONTRACT));
        Map<String, Object> governance = map(root.get(FIELD_GOVERNANCE));
        String inputExampleJson = string(modelContract.get(FIELD_INPUT_EXAMPLE_JSON));
        Object inputExample = StringUtils.isBlank(inputExampleJson)
                ? Collections.emptyMap() : JsonSupport.fromJSON(inputExampleJson, Object.class);
        if (!(inputExample instanceof Map)) {
            throw new IllegalStateException("capability inputExampleJson must be object");
        }
        CatalogEntry result = new CatalogEntry();
        result.assetKey = assetKey;
        result.actionCode = required(basicInfo, FIELD_ACTION_CODE);
        result.nameCn = required(basicInfo, FIELD_NAME_CN);
        result.businessDomain = required(basicInfo, FIELD_BUSINESS_DOMAIN);
        result.description = required(basicInfo, FIELD_DESCRIPTION);
        result.modelDescription = plan.getToolDescription();
        result.inputSchema = JsonSupport.fromJSON(plan.getInputSchema(), Object.class);
        result.inputExample = inputExample;
        result.keyOutputFields = plan.getKeyOutputFields();
        result.sideEffectLevel = plan.getSideEffectLevel();
        result.approvalPolicy = required(governance, FIELD_APPROVAL_POLICY);
        return result;
    }

    private String requireClientType(String value) {
        String clientType = StringUtils.upperCase(StringUtils.trimToEmpty(value), Locale.ROOT);
        if (!StringUtils.equalsAny(clientType, CLIENT_PC, CLIENT_APP)) {
            throw new CapabilityCatalogException(CapabilityToolErrorCode.CAPABILITY_CLIENT_NOT_SUPPORTED,
                    ERROR_TRUSTED_CLIENT_TYPE);
        }
        return clientType;
    }

    private Map<String, Object> compactView(CatalogEntry entry) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put(FIELD_STATUS, STATUS_AVAILABLE);
        result.put(FIELD_ACTION_CODE, entry.actionCode);
        result.put(FIELD_NAME_CN, entry.nameCn);
        result.put(FIELD_BUSINESS_DOMAIN, entry.businessDomain);
        result.put(FIELD_DESCRIPTION, entry.description);
        return result;
    }

    private Map<String, Object> fullView(CatalogEntry entry) {
        Map<String, Object> result = compactView(entry);
        result.put(FIELD_MODEL_DESCRIPTION, entry.modelDescription);
        result.put(FIELD_INPUT_SCHEMA, entry.inputSchema);
        result.put(FIELD_INPUT_EXAMPLE, entry.inputExample);
        result.put(FIELD_KEY_OUTPUT_FIELDS, entry.keyOutputFields);
        result.put(FIELD_SIDE_EFFECT_LEVEL, entry.sideEffectLevel);
        result.put(FIELD_APPROVAL_POLICY, entry.approvalPolicy);
        return result;
    }

    private Map<String, Object> guidanceView(CatalogEntry entry) {
        Map<String, Object> result = compactView(entry);
        result.put(FIELD_MODEL_DESCRIPTION, entry.modelDescription);
        result.put(FIELD_SIDE_EFFECT_LEVEL, entry.sideEffectLevel);
        result.put(FIELD_APPROVAL_POLICY, entry.approvalPolicy);
        return result;
    }

    private Map<String, Object> unavailableView(String actionCode) {
        return unavailableView(actionCode, CapabilityToolErrorCode.CAPABILITY_RELEASE_NOT_AVAILABLE);
    }

    private Map<String, Object> unavailableView(String actionCode, CapabilityToolErrorCode errorCode) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put(FIELD_STATUS, STATUS_UNAVAILABLE);
        result.put(FIELD_ACTION_CODE, actionCode);
        result.put(FIELD_ERROR_CODE, errorCode);
        return result;
    }

    private Set<String> normalizeActionCodes(List<String> actionCodes) {
        if (actionCodes == null || actionCodes.isEmpty()) {
            throw new CapabilityCatalogException(CapabilityToolErrorCode.ARGUMENT_INVALID,
                    "actionCodeList must not be empty");
        }
        Set<String> result = new LinkedHashSet<>();
        for (String actionCode : actionCodes) {
            String normalized = StringUtils.trimToEmpty(actionCode);
            if (StringUtils.isBlank(normalized)) {
                throw new CapabilityCatalogException(CapabilityToolErrorCode.ARGUMENT_INVALID,
                        "actionCodeList contains blank actionCode");
            }
            result.add(normalized);
        }
        return result;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> map(Object value) {
        return value instanceof Map ? (Map<String, Object>) value : Collections.emptyMap();
    }

    private String required(Map<String, Object> source, String field) {
        String value = string(source.get(field));
        if (StringUtils.isBlank(value)) {
            throw new IllegalStateException("capability release payload missing field: " + field);
        }
        return value;
    }

    private String string(Object value) {
        return value == null ? StringUtils.EMPTY : String.valueOf(value);
    }

    private static final class CatalogEntry {
        private String assetKey;
        private String actionCode;
        private String nameCn;
        private String businessDomain;
        private String description;
        private String modelDescription;
        private Object inputSchema;
        private Object inputExample;
        private List<Map<String, Object>> keyOutputFields;
        private String sideEffectLevel;
        private String approvalPolicy;
    }

    private static final class CatalogSnapshot {
        private final Map<String, CatalogEntry> entries;
        private final Set<String> clientUnsupportedActionCodes;

        private CatalogSnapshot(Map<String, CatalogEntry> entries,
                Set<String> clientUnsupportedActionCodes) {
            this.entries = entries;
            this.clientUnsupportedActionCodes = clientUnsupportedActionCodes;
        }
    }

    /** 目录解析失败的稳定错误。 */
    public static class CapabilityCatalogException extends RuntimeException {

        private final CapabilityToolErrorCode errorCode;

        public CapabilityCatalogException(CapabilityToolErrorCode errorCode, String message) {
            super(message);
            this.errorCode = errorCode;
        }

        public CapabilityToolErrorCode getErrorCode() {
            return errorCode;
        }
    }
}
