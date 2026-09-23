package dev.a2flow.management.release;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Component;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.model.CapabilityActionDraft;
import dev.a2flow.management.release.ReleaseModels.AssetSnapshot;
import dev.a2flow.management.release.dependency.AssetDependencyModels.ResolvedReleasedAsset;

/**
 * 业务能力发布快照的领域解析适配器。
 *
 * <p>共享发布层只负责选择 PRT Build 或 ONLINE Version，本类负责校验能力 payload 的稳定身份和
 * 可执行字段，并从能力结果契约提取包装组件引用。包装组件只作为间接依赖返回，不写回 Skill 的
 * componentBindings。
 */
@Component
public class CapabilityReleasePayloadAdapter {

    private static final String FIELD_BASIC_INFO = "basicInfo";
    private static final String FIELD_ACTION_CODE = "actionCode";
    private static final String FIELD_SUPPORTED_CLIENTS = "supportedClients";
    private static final String FIELD_CLIENT_VARIANTS = "clientVariants";
    private static final String FIELD_GOVERNANCE = "governance";
    private static final String FIELD_ENABLED = "enabled";
    private static final String FIELD_EMERGENCY_DISABLED = "emergencyDisabled";
    private static final String FIELD_RESULT_CONTRACT = "resultContract";
    private static final String FIELD_PRESENTATION_COMPONENTS = "presentationComponents";
    private static final String FIELD_ASSET_ID = "assetId";
    private static final String CLIENT_PC = "PC";
    private static final String CLIENT_APP = "APP";
    private static final String CLIENT_COMMON = "COMMON";
    private static final List<String> CLIENT_MODE_PC = List.of(CLIENT_PC);
    private static final List<String> CLIENT_MODE_APP = List.of(CLIENT_APP);
    private static final List<String> CLIENT_MODE_DIFFERENT = List.of(CLIENT_PC, CLIENT_APP);
    private static final List<String> CLIENT_MODE_COMMON = List.of(CLIENT_COMMON);
    private static final String STATUS_DISABLED = "DISABLED";
    private static final String ERROR_CLIENT_VARIANTS_MISSING =
            "业务能力发布快照缺少 clientVariants，请重新发布";
    private static final String ERROR_CLIENT_VARIANTS_MISMATCH =
            "业务能力发布快照 supportedClients 与 clientVariants 不一致";
    private static final String ERROR_SUPPORTED_CLIENTS_INVALID =
            "业务能力发布快照 supportedClients 非法";
    private static final String ERROR_SUPPORTED_CLIENTS_MISSING =
            "业务能力发布快照缺少 supportedClients，请重新发布";
    private static final String ERROR_CLIENT_VARIANT_MISSING_PREFIX =
            "业务能力发布快照缺少 ";

    /**
     * 解析作者编辑态能力 payload，只校验发布快照身份，不把未完成字段误判成系统异常。
     */
    public CapabilityActionDraft requireAuthoringDraft(AssetSnapshot snapshot, String expectedAssetKey) {
        if (snapshot == null || StringUtils.isBlank(snapshot.getPayloadJson())) {
            throw new IllegalStateException("业务能力发布快照为空");
        }
        validateSnapshotIdentity(snapshot, expectedAssetKey);
        CapabilityActionDraft draft = JsonSupport.fromJSON(
                snapshot.getPayloadJson(), CapabilityActionDraft.class);
        if (draft == null || draft.getDraft() == null || draft.getDraft().isEmpty()) {
            throw new IllegalStateException("业务能力发布快照无法解析");
        }
        if (StringUtils.isNotBlank(expectedAssetKey)
                && !StringUtils.equals(expectedAssetKey, draft.getDraftId())) {
            throw new IllegalStateException("业务能力发布快照稳定身份不一致");
        }
        return draft;
    }

    /**
     * 解析并校验公共发布源中的能力 payload 身份与必要执行字段。
     */
    public CapabilityActionDraft requireDraft(AssetSnapshot snapshot, String expectedAssetKey) {
        CapabilityActionDraft draft = requireAuthoringDraft(snapshot, expectedAssetKey);
        if (StringUtils.isBlank(nestedString(draft.getDraft(), FIELD_BASIC_INFO, FIELD_ACTION_CODE))) {
            throw new IllegalStateException("业务能力发布快照缺少 actionCode");
        }
        return draft;
    }

    /**
     * 判断不可变能力 payload 是否允许在发布依赖和运行时被引用。
     */
    public boolean isEnabled(AssetSnapshot snapshot, String expectedAssetKey) {
        CapabilityActionDraft draft = requireDraft(snapshot, expectedAssetKey);
        return isDraftEnabled(draft);
    }

    private boolean isDraftEnabled(CapabilityActionDraft draft) {
        Map<String, Object> governance = map(draft.getDraft().get(FIELD_GOVERNANCE));
        return !Boolean.FALSE.equals(governance.get(FIELD_ENABLED))
                && !Boolean.TRUE.equals(governance.get(FIELD_EMERGENCY_DISABLED))
                && !StringUtils.equalsIgnoreCase(STATUS_DISABLED, draft.getStatus());
    }

    /**
     * 解析当前可执行的能力 payload；停用状态必须显式失败。
     */
    public CapabilityActionDraft requireExecutableDraft(AssetSnapshot snapshot, String expectedAssetKey) {
        CapabilityActionDraft draft = requireDraft(snapshot, expectedAssetKey);
        if (!isDraftEnabled(draft)) {
            throw new IllegalStateException("业务能力已停用");
        }
        return draft;
    }

    /**
     * 将公共环境解析结果转换成能力领域快照并校验为可执行 payload。
     */
    public CapabilityActionDraft requireExecutableDraft(ResolvedReleasedAsset resolvedAsset) {
        return requireExecutableDraft(snapshot(resolvedAsset), resolvedAsset.getAssetKey());
    }

    /**
     * 将公共环境解析结果转换成能力领域快照。
     */
    public AssetSnapshot snapshot(ResolvedReleasedAsset resolvedAsset) {
        if (resolvedAsset == null) {
            throw new IllegalStateException("业务能力环境解析结果为空");
        }
        return new AssetSnapshot()
                .setAssetType(ReleaseAssetType.CAPABILITY_ACTION.name())
                .setAssetKey(resolvedAsset.getAssetKey())
                .setDigest(resolvedAsset.getDigest())
                .setArtifactRef(resolvedAsset.getArtifactRef())
                .setSummary(resolvedAsset.getSummary())
                .setPayloadJson(resolvedAsset.getPayloadJson());
    }

    /** 按支持端和端内声明顺序提取并去重包装组件资产 ID。 */
    public List<String> presentationComponentAssetKeys(AssetSnapshot snapshot, String expectedAssetKey) {
        CapabilityActionDraft draft = requireExecutableDraft(snapshot, expectedAssetKey);
        Set<String> assetKeys = new LinkedHashSet<>();
        Map<String, Object> variants = requireClientVariants(draft.getDraft());
        for (String client : supportedClients(draft.getDraft())) {
            Map<String, Object> resultContract = map(requireClientVariant(variants, client)
                    .get(FIELD_RESULT_CONTRACT));
            for (Object value : list(resultContract.get(FIELD_PRESENTATION_COMPONENTS))) {
                assetKeys.add(requirePositiveAssetKey(map(value).get(FIELD_ASSET_ID)));
            }
        }
        return new ArrayList<>(assetKeys);
    }

    /** 从不可变发布快照读取精确支持端，不从当前草稿或调用上下文补值。 */
    public List<String> supportedClients(AssetSnapshot snapshot, String expectedAssetKey) {
        return supportedClients(requireDraft(snapshot, expectedAssetKey).getDraft());
    }

    /** 作者编辑态只校验端契约本身，不把尚未填写 actionCode 误判为发布快照损坏。 */
    public List<String> supportedClientsForAuthoring(AssetSnapshot snapshot, String expectedAssetKey) {
        return supportedClients(requireAuthoringDraft(snapshot, expectedAssetKey).getDraft());
    }

    /**
     * 发布依赖不解释历史单契约，也不跨端回退；旧快照必须重新发布为端契约后才能进入新链路。
     */
    private Map<String, Object> requireClientVariants(Map<String, Object> draft) {
        Object value = draft.get(FIELD_CLIENT_VARIANTS);
        if (!(value instanceof Map)) {
            throw new IllegalStateException(ERROR_CLIENT_VARIANTS_MISSING);
        }
        Map<String, Object> variants = map(value);
        List<String> supported = supportedClients(draft);
        if (!new ArrayList<>(variants.keySet()).equals(supported)) {
            throw new IllegalStateException(ERROR_CLIENT_VARIANTS_MISMATCH);
        }
        return variants;
    }

    private List<String> supportedClients(Map<String, Object> draft) {
        List<?> rawClients = list(draft.get(FIELD_SUPPORTED_CLIENTS));
        List<String> clients = new ArrayList<>();
        for (Object value : rawClients) {
            clients.add(String.valueOf(value));
        }
        if (clients.isEmpty()) {
            throw new IllegalStateException(ERROR_SUPPORTED_CLIENTS_MISSING);
        }
        if (CLIENT_MODE_PC.equals(clients) || CLIENT_MODE_APP.equals(clients)
                || CLIENT_MODE_DIFFERENT.equals(clients) || CLIENT_MODE_COMMON.equals(clients)) {
            return List.copyOf(clients);
        }
        throw new IllegalStateException(ERROR_SUPPORTED_CLIENTS_INVALID);
    }

    private Map<String, Object> requireClientVariant(Map<String, Object> variants, String client) {
        Object value = variants.get(client);
        if (!(value instanceof Map)) {
            throw new IllegalStateException(ERROR_CLIENT_VARIANT_MISSING_PREFIX + client + " 端契约");
        }
        return map(value);
    }

    private void validateSnapshotIdentity(AssetSnapshot snapshot, String expectedAssetKey) {
        if (StringUtils.isNotBlank(snapshot.getAssetType())
                && !StringUtils.equals(ReleaseAssetType.CAPABILITY_ACTION.name(), snapshot.getAssetType())) {
            throw new IllegalStateException("业务能力发布快照资产类型不一致");
        }
        if (StringUtils.isNotBlank(expectedAssetKey) && StringUtils.isNotBlank(snapshot.getAssetKey())
                && !StringUtils.equals(expectedAssetKey, snapshot.getAssetKey())) {
            throw new IllegalStateException("业务能力发布快照资产标识不一致");
        }
    }

    private String nestedString(Map<String, Object> source, String parent, String field) {
        Object value = map(source.get(parent)).get(field);
        return value == null ? StringUtils.EMPTY : String.valueOf(value);
    }

    private String requirePositiveAssetKey(Object value) {
        try {
            long parsed = value instanceof Number
                    ? ((Number) value).longValue() : Long.parseLong(String.valueOf(value));
            if (parsed <= 0) {
                throw new IllegalArgumentException("assetId must be positive");
            }
            return String.valueOf(parsed);
        } catch (Exception e) {
            throw new IllegalStateException("业务能力包装组件缺少合法 assetId", e);
        }
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> map(Object value) {
        return value instanceof Map ? (Map<String, Object>) value : Collections.emptyMap();
    }

    private List<?> list(Object value) {
        return value instanceof List ? (List<?>) value : Collections.emptyList();
    }
}
