package dev.a2flow.management.release;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import jakarta.annotation.Resource;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Component;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.lifecycle.CapabilityActionDraftService;
import dev.a2flow.management.model.CapabilityActionDraft;
import dev.a2flow.management.release.ReleaseModels.AssetSnapshot;
import dev.a2flow.management.release.ReleaseModels.GateResult;
import dev.a2flow.management.release.ReleaseModels.PublishResult;
import dev.a2flow.management.release.ReleaseModels.ReleasePublishContext;
import dev.a2flow.management.release.ReleaseModels.ReleaseValidationRequirement;

import lombok.extern.slf4j.Slf4j;

/**
 * 业务能力注册中心发布适配器。
 *
 * <p>快照来自 canonical draft，静态校验与 binding/dry-run 门禁基于不可变快照执行。发布成功边界是
 * 共享发布状态 Repository 将 PRT/ONLINE 生效版本写入数据库；历史重发只切换公共 ONLINE 版本，
 * 不覆盖当前能力草稿。本类不负责修改能力字段，也不把当前 draft 偷换成历史发布载荷。
 */
@Component
@Slf4j
public class CapabilityReleaseAssetAdapter extends AbstractReleaseAssetAdapter {

    private static final String DIFF_RESOURCE_PATH = "capability.json";
    private static final String STATUS_DRAFT = "DRAFT";
    private static final String VALIDATION_INVALID = "INVALID";
    private static final String CHECK_CAPABILITY_DRY_RUN_PC = "CAPABILITY_DRY_RUN_PC";
    private static final String CHECK_CAPABILITY_DRY_RUN_APP = "CAPABILITY_DRY_RUN_APP";
    private static final String CHECK_CAPABILITY_DRY_RUN_COMMON = "CAPABILITY_DRY_RUN_COMMON";
    private static final String CHECK_CAPABILITY_DRY_RUN_ONLINE_PC = "CAPABILITY_DRY_RUN_ONLINE_PC";
    private static final String CHECK_CAPABILITY_DRY_RUN_ONLINE_APP = "CAPABILITY_DRY_RUN_ONLINE_APP";
    private static final String CHECK_CAPABILITY_DRY_RUN_ONLINE_COMMON =
            "CAPABILITY_DRY_RUN_ONLINE_COMMON";
    private static final String LABEL_CAPABILITY_DRY_RUN_PC = "验证 PRT（PC）";
    private static final String LABEL_CAPABILITY_DRY_RUN_APP = "验证 PRT（APP）";
    private static final String LABEL_CAPABILITY_DRY_RUN_COMMON = "验证 PRT（PC/APP 通用）";
    private static final String LABEL_CAPABILITY_DRY_RUN_ONLINE_PC = "验证线上（PC）";
    private static final String LABEL_CAPABILITY_DRY_RUN_ONLINE_APP = "验证线上（APP）";
    private static final String LABEL_CAPABILITY_DRY_RUN_ONLINE_COMMON =
            "验证线上（PC/APP 通用）";
    private static final String RULE_CAPABILITY_DRY_RUN = "capability-dry-run-client-v1";
    private static final String RULE_CAPABILITY_DRY_RUN_ONLINE = "capability-dry-run-online-client-v1";
    private static final String CLIENT_PC = "PC";
    private static final String CLIENT_APP = "APP";
    private static final String CLIENT_COMMON = "COMMON";
    private static final String SUMMARY_ASSET_KEY = "assetKey";
    private static final String SUMMARY_STATUS = "status";
    private static final String SUMMARY_ENVIRONMENT = "environment";
    private static final String SUMMARY_SOURCE_TYPE = "sourceType";
    private static final String SUMMARY_SOURCE_VERSION = "sourceVersion";
    private static final String SUMMARY_DIGEST = "digest";
    private static final String MESSAGE_VERSION_EFFECTIVE = "业务能力数据库生效版本更新完成";
    private static final String FIELD_BASIC_INFO = "basicInfo";
    private static final String FIELD_BUSINESS_DOMAIN = "businessDomain";
    private static final String FIELD_CAPABILITY_DOMAIN = "capabilityDomain";
    private static final String FIELD_SUPPORTED_CLIENTS = "supportedClients";
    private static final String FIELD_CLIENT_VARIANTS = "clientVariants";
    private static final String FIELD_API_SOURCE = "apiSource";
    private static final String FIELD_SOURCE_TYPE = "sourceType";
    private static final String FIELD_EXECUTION_BINDING = "executionBinding";
    private static final String FIELD_BINDING_TYPE = "bindingType";
    private static final String SOURCE_TYPE_LOCAL_METHOD = "LOCAL_METHOD";
    private static final String BINDING_TYPE_LOCAL_METHOD = "LOCAL_METHOD";
    private static final String DIGEST_DRAFT = "draft";
    private static final String DIGEST_BUSINESS_DOMAIN = "businessDomain";
    private static final String DIGEST_CAPABILITY_DOMAIN = "capabilityDomain";
    private static final String DIGEST_SPECIALIST_IDS = "specialistIds";
    private static final String CHECK_CLASSIFICATION_COMPLETE = "CAPABILITY_CLASSIFICATION_COMPLETE";
    private static final String LABEL_CLASSIFICATION_COMPLETE = "分类关系完整性";
    private static final String MESSAGE_CLASSIFICATION_COMPLETE = "业务域、能力域和所属专员已完整配置";
    private static final String MESSAGE_CLASSIFICATION_INCOMPLETE =
            "请补齐业务域、能力域和所属专员";
    private static final String CHECK_CLIENT_CONTRACT_COMPLETE = "CAPABILITY_CLIENT_CONTRACT_COMPLETE";
    private static final String LABEL_CLIENT_CONTRACT_COMPLETE = "支持端契约完整性";
    private static final String MESSAGE_CLIENT_CONTRACT_COMPLETE = "支持端契约已完整配置";
    private static final String MESSAGE_CLIENT_CONTRACT_INCOMPLETE =
            "请选择支持端并补齐对应端契约";
    private static final String ERROR_DRAFT_MISSING = "业务能力草稿不存在，不能生成发布快照";
    private static final String ERROR_VALIDATION_CLIENT_UNSUPPORTED = "业务能力验证端类型不支持: ";
    @Resource
    private CapabilityActionDraftService capabilityActionDraftService;

    @Resource
    private CapabilityReleasePayloadAdapter capabilityReleasePayloadAdapter;

    @Resource
    private dev.a2flow.management.lifecycle.publish.RuntimeAssetPublisher runtimeAssetPublisher;

    @Override
    public ReleaseAssetType assetType() {
        return ReleaseAssetType.CAPABILITY_ACTION;
    }

    /** 新注册能力的 DRAFT 事实就是首个可编辑变更；初版仍须通过共享静态校验和 PRT dry-run 门禁。 */
    @Override
    public boolean isInitialEditableChange(AssetSnapshot snapshot) {
        Object status = snapshot.getSummary() == null ? null : snapshot.getSummary().get(SUMMARY_STATUS);
        return StringUtils.equalsIgnoreCase(STATUS_DRAFT, String.valueOf(status));
    }

    /** 业务能力运行态支持按可信 userId 的比例和白名单灰度。 */
    @Override
    public GrayReleasePolicy grayReleasePolicy() {
        return GrayReleasePolicy.PERCENTAGE_AND_WHITELIST;
    }

    /** 数据库版本生效由冻结快照确定且无外部副作用，允许同 requestId 恢复原 PUBLISHING 流水。 */
    @Override
    public boolean supportsPublishingRecovery() {
        return true;
    }

    /** 业务能力 canonical draft 统一映射成 capability.json 参与共享行级 Diff。 */
    @Override
    protected String diffResourcePath() {
        return DIFF_RESOURCE_PATH;
    }

    @Override
    public AssetSnapshot currentSnapshot(String assetKey, Map<String, String> params) {
        CapabilityActionDraft managementDraft = capabilityActionDraftService.detail(assetKey);
        CapabilityActionDraft frozenDraft = freezeClassificationProjection(managementDraft);
        Map<String, Object> digestSource = new LinkedHashMap<>();
        digestSource.put(DIGEST_DRAFT, frozenDraft.getDraft());
        digestSource.put(DIGEST_BUSINESS_DOMAIN, frozenDraft.getBusinessDomain());
        digestSource.put(DIGEST_CAPABILITY_DOMAIN, frozenDraft.getCapabilityDomain());
        digestSource.put(DIGEST_SPECIALIST_IDS, frozenDraft.getSpecialistId());
        String canonicalDigest = ReleaseDigestUtils.sha256(JsonSupport.toJSON(digestSource));
        return snapshot(assetKey, frozenDraft, summaryEntry(
                "draftId", frozenDraft.getDraftId(),
                "revision", frozenDraft.getRevision(),
                "status", frozenDraft.getStatus(),
                "validationStatus", frozenDraft.getValidationStatus()), canonicalDigest, frozenDraft.getDraftId());
    }

    /**
     * 深拷贝管理草稿并把当前 revision 的关系投影冻结进发布 payload。
     *
     * <p>分类关系不完整是合法的待编辑状态，因此仍可生成 overview 快照并开放新建变更；发布由
     * 必选门禁阻断。这里会移除 canonical JSON 中没有对应关系投影的旧分类值，禁止把旧字段当作
     * relation 事实的兼容回退。
     */
    @SuppressWarnings("unchecked")
    private CapabilityActionDraft freezeClassificationProjection(CapabilityActionDraft source) {
        if (source == null) {
            throw new IllegalStateException(ERROR_DRAFT_MISSING);
        }
        CapabilityActionDraft frozen = JsonSupport.fromJSON(
                JsonSupport.toJSON(source), CapabilityActionDraft.class);
        Map<String, Object> canonical = new LinkedHashMap<>(frozen.getDraft());
        Object basicValue = canonical.get(FIELD_BASIC_INFO);
        Map<String, Object> basicInfo = basicValue instanceof Map
                ? new LinkedHashMap<>((Map<String, Object>) basicValue) : new LinkedHashMap<>();
        if (StringUtils.isNotBlank(frozen.getBusinessDomain())) {
            basicInfo.put(FIELD_BUSINESS_DOMAIN, frozen.getBusinessDomain());
        } else {
            basicInfo.remove(FIELD_BUSINESS_DOMAIN);
        }
        if (StringUtils.isNotBlank(frozen.getCapabilityDomain())) {
            basicInfo.put(FIELD_CAPABILITY_DOMAIN, frozen.getCapabilityDomain());
        } else {
            basicInfo.remove(FIELD_CAPABILITY_DOMAIN);
        }
        canonical.put(FIELD_BASIC_INFO, basicInfo);
        frozen.setDraft(canonical);
        return frozen;
    }

    @Override
    public List<GateResult> evaluateGates(String assetKey, ReleaseEnvironment environment,
            AssetSnapshot snapshot, Map<String, String> params) {
        CapabilityActionDraft draft = authoringDraftFromSnapshot(snapshot, assetKey);
        boolean classificationComplete = !StringUtils.isAnyBlank(draft.getBusinessDomain(),
                draft.getCapabilityDomain(), draft.getSpecialistId());
        boolean clientContractComplete = hasSupportedClientDeclaration(draft);
        boolean staticValid = !StringUtils.equals(draft.getValidationStatus(), VALIDATION_INVALID)
                && StringUtils.isNotBlank(draft.getValidationStatus());
        return List.of(
                gate(CHECK_CLASSIFICATION_COMPLETE, LABEL_CLASSIFICATION_COMPLETE,
                        classificationComplete, true, classificationComplete
                                ? MESSAGE_CLASSIFICATION_COMPLETE : MESSAGE_CLASSIFICATION_INCOMPLETE),
                gate(CHECK_CLIENT_CONTRACT_COMPLETE, LABEL_CLIENT_CONTRACT_COMPLETE,
                        clientContractComplete, true, clientContractComplete
                                ? MESSAGE_CLIENT_CONTRACT_COMPLETE : MESSAGE_CLIENT_CONTRACT_INCOMPLETE),
                gate("CAPABILITY_STATIC_VALIDATION", "静态校验", staticValid, true,
                        staticValid ? "静态校验已执行" : "请先完成静态校验"));
    }

    /** 预发和线上都只接受与当前 canonical draft 摘要一致的真实 API 验证证据。 */
    @Override
    public List<ReleaseValidationRequirement> validationRequirements(ReleaseEnvironment environment) {
        return List.of(validationRequirement(environment, CLIENT_PC),
                validationRequirement(environment, CLIENT_APP),
                validationRequirement(environment, CLIENT_COMMON));
    }

    /**
     * 只要求不可变快照实际声明且支持直接验证的端证据。
     *
     * <p>LOCAL_METHOD 当前不进入直接 dry-run；只有 sourceType/bindingType 严格成对时才豁免。缺字段或混合
     * pair 继续保留原证据要求并由静态校验阻断，避免作者恢复页抛异常，也不把畸形绑定误判为已准出。
     */
    @Override
    public List<ReleaseValidationRequirement> validationRequirements(
            ReleaseEnvironment environment, AssetSnapshot snapshot) {
        CapabilityActionDraft draft = authoringDraftFromSnapshot(snapshot, snapshot.getAssetKey());
        if (!hasSupportedClientDeclaration(draft)) {
            log.warn("业务能力发布概览缺少支持端声明，由必选门禁阻断发布, assetKey:{}, environment:{}",
                    snapshot.getAssetKey(), environment);
            return List.of();
        }
        return capabilityReleasePayloadAdapter
                .supportedClientsForAuthoring(snapshot, snapshot.getAssetKey()).stream()
                .filter(client -> requiresDirectDryRun(draft, client))
                .map(client -> validationRequirement(environment, client))
                .toList();
    }

    /** 从 canonical 端契约判断当前端是否仍需 HTTP 直接验证，不解释旧字段或跨端回退。 */
    private boolean requiresDirectDryRun(CapabilityActionDraft draft, String client) {
        Object variantsValue = draft.getDraft().get(FIELD_CLIENT_VARIANTS);
        if (!(variantsValue instanceof Map)) {
            return true;
        }
        Object variantValue = ((Map<?, ?>) variantsValue).get(client);
        if (!(variantValue instanceof Map)) {
            return true;
        }
        Map<?, ?> variant = (Map<?, ?>) variantValue;
        Object apiSourceValue = variant.get(FIELD_API_SOURCE);
        Object executionBindingValue = variant.get(FIELD_EXECUTION_BINDING);
        if (!(apiSourceValue instanceof Map) || !(executionBindingValue instanceof Map)) {
            return true;
        }
        String sourceType = String.valueOf(((Map<?, ?>) apiSourceValue).get(FIELD_SOURCE_TYPE));
        String bindingType = String.valueOf(
                ((Map<?, ?>) executionBindingValue).get(FIELD_BINDING_TYPE));
        return !SOURCE_TYPE_LOCAL_METHOD.equals(sourceType)
                || !BINDING_TYPE_LOCAL_METHOD.equals(bindingType);
    }

    /** 历史快照缺少支持端时保留作者恢复入口，但不推断任何 PC、APP 或通用端默认值。 */
    private boolean hasSupportedClientDeclaration(CapabilityActionDraft draft) {
        Object supportedClients = draft.getDraft().get(FIELD_SUPPORTED_CLIENTS);
        return supportedClients instanceof List && !((List<?>) supportedClients).isEmpty();
    }

    private ReleaseValidationRequirement validationRequirement(
            ReleaseEnvironment environment, String client) {
        return new ReleaseValidationRequirement()
                .setCode(validationCheckCode(environment, client))
                .setLabel(validationLabel(environment, client))
                .setExpectedRuleVersion(environment == ReleaseEnvironment.ONLINE
                        ? RULE_CAPABILITY_DRY_RUN_ONLINE : RULE_CAPABILITY_DRY_RUN);
    }

    private String validationCheckCode(ReleaseEnvironment environment, String client) {
        if (environment == ReleaseEnvironment.ONLINE) {
            if (CLIENT_PC.equals(client)) {
                return CHECK_CAPABILITY_DRY_RUN_ONLINE_PC;
            }
            if (CLIENT_APP.equals(client)) {
                return CHECK_CAPABILITY_DRY_RUN_ONLINE_APP;
            }
            if (CLIENT_COMMON.equals(client)) {
                return CHECK_CAPABILITY_DRY_RUN_ONLINE_COMMON;
            }
            throw new IllegalArgumentException(ERROR_VALIDATION_CLIENT_UNSUPPORTED + client);
        }
        if (CLIENT_PC.equals(client)) {
            return CHECK_CAPABILITY_DRY_RUN_PC;
        }
        if (CLIENT_APP.equals(client)) {
            return CHECK_CAPABILITY_DRY_RUN_APP;
        }
        if (CLIENT_COMMON.equals(client)) {
            return CHECK_CAPABILITY_DRY_RUN_COMMON;
        }
        throw new IllegalArgumentException(ERROR_VALIDATION_CLIENT_UNSUPPORTED + client);
    }

    private String validationLabel(ReleaseEnvironment environment, String client) {
        if (environment == ReleaseEnvironment.ONLINE) {
            if (CLIENT_PC.equals(client)) {
                return LABEL_CAPABILITY_DRY_RUN_ONLINE_PC;
            }
            if (CLIENT_APP.equals(client)) {
                return LABEL_CAPABILITY_DRY_RUN_ONLINE_APP;
            }
            if (CLIENT_COMMON.equals(client)) {
                return LABEL_CAPABILITY_DRY_RUN_ONLINE_COMMON;
            }
            throw new IllegalArgumentException(ERROR_VALIDATION_CLIENT_UNSUPPORTED + client);
        }
        if (CLIENT_PC.equals(client)) {
            return LABEL_CAPABILITY_DRY_RUN_PC;
        }
        if (CLIENT_APP.equals(client)) {
            return LABEL_CAPABILITY_DRY_RUN_APP;
        }
        if (CLIENT_COMMON.equals(client)) {
            return LABEL_CAPABILITY_DRY_RUN_COMMON;
        }
        throw new IllegalArgumentException(ERROR_VALIDATION_CLIENT_UNSUPPORTED + client);
    }

    @Override
    public void restore(String userName, String assetKey, AssetSnapshot snapshot, Map<String, String> params) {
        throw new IllegalStateException("capability historical restore publisher is not connected");
    }

    @Override
    public PublishResult deploy(ReleasePublishContext context) {
        AssetSnapshot snapshot = context.getSnapshot();
        CapabilityActionDraft draft = draftFromSnapshot(snapshot, context.getAssetKey());
        Object basic = draft.getDraft().get("basicInfo");
        if (!(basic instanceof Map<?, ?> basicInfo) || !(basicInfo.get("actionCode") instanceof String actionCode)) {
            throw new IllegalStateException("CAPABILITY_ACTION_CODE_REQUIRED");
        }
        runtimeAssetPublisher.publish("ABILITY", actionCode, context);
        log.info("业务能力数据库版本生效完成, assetKey:{}, draftId:{}, environment:{}, sourceType:{}, "
                        + "sourceVersion:{}, requestId:{}, operator:{}",
                context.getAssetKey(), draft.getDraftId(), context.getEnvironment(), context.getSourceType(),
                context.getSourceVersion(), context.getRequestId(), context.getUserName());
        return succeeded(MESSAGE_VERSION_EFFECTIVE, summaryEntry(
                SUMMARY_ASSET_KEY, context.getAssetKey(),
                SUMMARY_ENVIRONMENT, context.getEnvironment().name(),
                SUMMARY_SOURCE_TYPE, context.getSourceType(),
                SUMMARY_SOURCE_VERSION, context.getSourceVersion(),
                SUMMARY_DIGEST, snapshot.getDigest()));
    }

    /** 从公共版本快照解析能力草稿，避免历史重发依赖当前可编辑事实源。 */
    private CapabilityActionDraft draftFromSnapshot(AssetSnapshot snapshot, String expectedAssetKey) {
        return capabilityReleasePayloadAdapter.requireExecutableDraft(snapshot, expectedAssetKey);
    }

    /** 发布概览读取可恢复的未完成草稿；严格发布和运行入口不得调用此方法。 */
    private CapabilityActionDraft authoringDraftFromSnapshot(
            AssetSnapshot snapshot, String expectedAssetKey) {
        return capabilityReleasePayloadAdapter.requireAuthoringDraft(snapshot, expectedAssetKey);
    }
}
