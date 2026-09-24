package dev.a2flow.management.a2ui.application;

import static dev.a2flow.management.a2ui.application.A2uiApplicationErrorCode.CAPABILITY_REFERENCE_INVALID;
import static dev.a2flow.management.a2ui.application.A2uiApplicationErrorCode.CAPABILITY_SCHEMA_INCOMPATIBLE;

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

import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiCurrentCapabilityContract;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiCurrentCapabilityVariantContract;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiSideEffectLevel;
import dev.a2flow.management.model.CapabilityActionDraft;
import dev.a2flow.management.release.CapabilityReleasePayloadAdapter;
import dev.a2flow.management.release.ReleaseAssetType;
import dev.a2flow.management.release.ReleaseEnvironment;
import dev.a2flow.management.release.ReleaseModels.AssetReleaseState;
import dev.a2flow.management.release.dependency.AssetDependencyModels.AssetDependencyReference;
import dev.a2flow.management.release.dependency.AssetDependencyModels.AssetResolutionContext;
import dev.a2flow.management.release.dependency.AssetDependencyModels.ResolvedReleasedAsset;
import dev.a2flow.management.release.dependency.AssetDependencyResolutionException;
import dev.a2flow.management.release.dependency.AssetDependencyType;
import dev.a2flow.management.release.dependency.EnvironmentAwareAssetResolver;
import dev.a2flow.management.storage.db.repository.AssetReleaseStateRepository;

import lombok.extern.slf4j.Slf4j;

/**
 * A2UI Application 发布时的当前 CapabilityAction 解析器。
 *
 * <p>上游传入作者态 Binding 中的稳定 actionCode，本服务复用 Skill 绑定候选的共享环境解析器，
 * 按 PRT 请求选择当前 PRT Build；仅当 PRT 指针完全不存在时由共享解析器选择 ONLINE Version。
 * 下游 compiler 只用不可变发布快照做当次 schema 兼容性校验；本服务不读取能力草稿、不把 capability
 * version、releaseId、digest 或执行地址写进 Application Build，也不执行能力或提供 alternate fallback。
 */
@Service
@Slf4j
public class A2uiCurrentCapabilityResolver {

    private static final String FIELD_BASIC_INFO = "basicInfo";
    private static final String FIELD_ACTION_CODE = "actionCode";
    private static final String FIELD_SUPPORTED_CLIENTS = "supportedClients";
    private static final String FIELD_CLIENT_VARIANTS = "clientVariants";
    private static final String FIELD_MODEL_CONTRACT = "modelContract";
    private static final String FIELD_RESULT_CONTRACT = "resultContract";
    private static final String FIELD_GOVERNANCE = "governance";
    private static final String FIELD_SIDE_EFFECT_LEVEL = "sideEffectLevel";
    private static final String CLIENT_PC = "PC";
    private static final String CLIENT_APP = "APP";
    private static final String CLIENT_COMMON = "COMMON";
    private static final List<String> CLIENT_MODE_PC = List.of(CLIENT_PC);
    private static final List<String> CLIENT_MODE_APP = List.of(CLIENT_APP);
    private static final List<String> CLIENT_MODE_DIFFERENT = List.of(CLIENT_PC, CLIENT_APP);
    private static final List<String> CLIENT_MODE_COMMON = List.of(CLIENT_COMMON);
    private static final String SIDE_EFFECT_READ = "READ";
    private static final String SIDE_EFFECT_WRITE = "WRITE";
    private static final String SIDE_EFFECT_DESTRUCTIVE = "DESTRUCTIVE";

    @Resource
    private AssetReleaseStateRepository assetReleaseStateRepository;

    @Resource
    private EnvironmentAwareAssetResolver environmentAwareAssetResolver;

    @Resource
    private CapabilityReleasePayloadAdapter payloadAdapter;

    public A2uiCurrentCapabilityResolver() {
    }

    A2uiCurrentCapabilityResolver(AssetReleaseStateRepository assetReleaseStateRepository,
            EnvironmentAwareAssetResolver environmentAwareAssetResolver,
            CapabilityReleasePayloadAdapter payloadAdapter) {
        this.assetReleaseStateRepository = assetReleaseStateRepository;
        this.environmentAwareAssetResolver = environmentAwareAssetResolver;
        this.payloadAdapter = payloadAdapter;
    }

    /**
     * 按 actionCode 一次性解析当前 PRT 生效能力；缺失、停用、重复或 schema 不完整均
     * fail closed。
     */
    public Map<String, A2uiCurrentCapabilityContract> resolve(Set<String> requestedActionCodes) {
        Set<String> requested = normalizedActionCodes(requestedActionCodes);
        if (requested.isEmpty()) {
            return Collections.emptyMap();
        }
        if (assetReleaseStateRepository == null || environmentAwareAssetResolver == null
                || payloadAdapter == null) {
            throw failure(CAPABILITY_REFERENCE_INVALID);
        }
        Map<String, A2uiCurrentCapabilityContract> result = new LinkedHashMap<>();
        assetReleaseStateRepository.scanByAssetType(ReleaseAssetType.CAPABILITY_ACTION, state -> {
            ResolvedReleasedAsset resolved = resolveCurrentPreprod(state);
            if (resolved == null) {
                return;
            }
            CapabilityActionDraft draft;
            try {
                draft = payloadAdapter.requireDraft(
                        payloadAdapter.snapshot(resolved), resolved.getAssetKey());
            } catch (RuntimeException exception) {
                log.info("A2UI Application发布跳过无法识别的当前CapabilityAction, assetKey:{}, "
                                + "exceptionType:{}",
                        resolved.getAssetKey(), exception.getClass().getSimpleName());
                return;
            }
            String actionCode = nestedString(draft.getDraft(), FIELD_BASIC_INFO, FIELD_ACTION_CODE);
            if (!requested.contains(actionCode)) {
                return;
            }
            CapabilityActionDraft executable;
            try {
                executable = payloadAdapter.requireExecutableDraft(resolved);
            } catch (Exception exception) {
                log.warn("A2UI Application发布引用的当前CapabilityAction不可执行, actionCode:{}",
                        actionCode);
                throw failure(CAPABILITY_REFERENCE_INVALID);
            }
            A2uiCurrentCapabilityContract contract = contract(executable, actionCode);
            if (result.putIfAbsent(actionCode, contract) != null) {
                log.warn("A2UI Application发布发现重复当前CapabilityAction, actionCode:{}", actionCode);
                throw failure(CAPABILITY_REFERENCE_INVALID);
            }
        });
        if (!result.keySet().containsAll(requested)) {
            Set<String> missing = new LinkedHashSet<>(requested);
            missing.removeAll(result.keySet());
            log.warn("A2UI Application发布缺少当前CapabilityAction, actionCodes:{}", missing);
            throw failure(CAPABILITY_REFERENCE_INVALID);
        }
        log.info("A2UI Application发布完成当前CapabilityAction解析, actionCount:{}", result.size());
        return Collections.unmodifiableMap(result);
    }

    /**
     * 复用共享 PRT 环境矩阵解析单个稳定能力身份；未发布的无关能力不参与 actionCode 匹配。
     * 损坏或停用的目标能力最终表现为 requested actionCode 缺失并 fail closed，不读取草稿补值。
     */
    private ResolvedReleasedAsset resolveCurrentPreprod(AssetReleaseState state) {
        if (state == null || StringUtils.isBlank(state.getAssetKey())) {
            return null;
        }
        AssetDependencyReference dependency = new AssetDependencyReference()
                .setAssetType(AssetDependencyType.CAPABILITY_ACTION)
                .setAssetKey(state.getAssetKey());
        try {
            return environmentAwareAssetResolver.resolveFromState(dependency,
                    new AssetResolutionContext().setRequestedEnvironment(ReleaseEnvironment.PRT), state);
        } catch (AssetDependencyResolutionException exception) {
            log.info("A2UI Application发布跳过当前PRT不可用CapabilityAction, assetKey:{}, errorCode:{}",
                    state.getAssetKey(), exception.getErrorCode());
            return null;
        }
    }

    A2uiCurrentCapabilityContract contract(CapabilityActionDraft draft, String actionCode) {
        Map<String, Object> source = draft.getDraft();
        List<String> supportedClients = supportedClients(source.get(FIELD_SUPPORTED_CLIENTS));
        Map<String, Object> clientVariants = map(source.get(FIELD_CLIENT_VARIANTS));
        if (!clientVariants.keySet().equals(new LinkedHashSet<>(supportedClients))) {
            throw failure(CAPABILITY_SCHEMA_INCOMPATIBLE);
        }
        Map<String, A2uiCurrentCapabilityVariantContract> variants = new LinkedHashMap<>();
        for (String client : supportedClients) {
            Map<String, Object> variant = map(clientVariants.get(client));
            Map<String, Object> modelContract = map(variant.get(FIELD_MODEL_CONTRACT));
            Map<String, Object> resultContract = map(variant.get(FIELD_RESULT_CONTRACT));
            if (modelContract.isEmpty() || resultContract.isEmpty()) {
                throw failure(CAPABILITY_SCHEMA_INCOMPATIBLE);
            }
            variants.put(client, new A2uiCurrentCapabilityVariantContract(
                    client,
                    A2uiImmutableJsonSupport.immutableMap(modelContract),
                    A2uiImmutableJsonSupport.immutableMap(resultContract)));
        }
        Map<String, Object> governance = map(source.get(FIELD_GOVERNANCE));
        return new A2uiCurrentCapabilityContract(
                actionCode, variants, sideEffect(governance.get(FIELD_SIDE_EFFECT_LEVEL)));
    }

    private List<String> supportedClients(Object value) {
        if (!(value instanceof List)) {
            throw failure(CAPABILITY_SCHEMA_INCOMPATIBLE);
        }
        List<String> clients = new ArrayList<>();
        for (Object client : (List<?>) value) {
            if (!(client instanceof String)) {
                throw failure(CAPABILITY_SCHEMA_INCOMPATIBLE);
            }
            clients.add((String) client);
        }
        if (!CLIENT_MODE_PC.equals(clients) && !CLIENT_MODE_APP.equals(clients)
                && !CLIENT_MODE_DIFFERENT.equals(clients) && !CLIENT_MODE_COMMON.equals(clients)) {
            throw failure(CAPABILITY_SCHEMA_INCOMPATIBLE);
        }
        return clients;
    }

    private A2uiSideEffectLevel sideEffect(Object rawSideEffect) {
        String sideEffect = rawSideEffect == null ? null : String.valueOf(rawSideEffect);
        if (SIDE_EFFECT_READ.equals(sideEffect)) {
            return A2uiSideEffectLevel.READ_ONLY;
        }
        if (SIDE_EFFECT_WRITE.equals(sideEffect)) {
            return A2uiSideEffectLevel.WRITE;
        }
        if (SIDE_EFFECT_DESTRUCTIVE.equals(sideEffect)) {
            return A2uiSideEffectLevel.DESTRUCTIVE;
        }
        throw failure(CAPABILITY_SCHEMA_INCOMPATIBLE);
    }

    private Set<String> normalizedActionCodes(Set<String> actionCodes) {
        Set<String> result = new LinkedHashSet<>();
        if (actionCodes != null) {
            for (String actionCode : actionCodes) {
                if (StringUtils.isBlank(actionCode)) {
                    throw failure(CAPABILITY_REFERENCE_INVALID);
                }
                result.add(actionCode.trim());
            }
        }
        return result;
    }

    private String nestedString(Map<String, Object> source, String parent, String field) {
        Object value = map(source.get(parent)).get(field);
        return value == null ? StringUtils.EMPTY : String.valueOf(value);
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> map(Object value) {
        return value instanceof Map ? (Map<String, Object>) value : Collections.emptyMap();
    }

    private A2uiApplicationValidationException failure(A2uiApplicationErrorCode errorCode) {
        return new A2uiApplicationValidationException(errorCode);
    }
}
