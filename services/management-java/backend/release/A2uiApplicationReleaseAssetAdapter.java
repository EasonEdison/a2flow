package dev.a2flow.management.release;

import static dev.a2flow.management.a2ui.application.A2uiApplicationErrorCode.CATALOG_ENVIRONMENT_MISMATCH;
import static dev.a2flow.management.a2ui.application.A2uiApplicationErrorCode.HISTORY_SNAPSHOT_INVALID;
import static dev.a2flow.management.a2ui.application.A2uiApplicationErrorCode.SOURCE_STALE;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import jakarta.annotation.Resource;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Component;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.a2ui.application.A2uiApplicationHistoryRestoreSupport;
import dev.a2flow.management.a2ui.application.A2uiApplicationManifestCompilerService;
import dev.a2flow.management.a2ui.application.A2uiApplicationModels.A2uiApplicationBuild;
import dev.a2flow.management.a2ui.application.A2uiApplicationRegistryService;
import dev.a2flow.management.a2ui.application.A2uiApplicationValidationException;
import dev.a2flow.management.a2ui.application.A2uiImmutableJsonSupport;
import dev.a2flow.management.a2ui.application.A2uiInlineManifestStorage;
import dev.a2flow.management.lifecycle.domain.ComponentAsset;
import dev.a2flow.management.release.ReleaseModels.AssetSnapshot;
import dev.a2flow.management.release.ReleaseModels.GateResult;
import dev.a2flow.management.release.ReleaseModels.PublishResult;
import dev.a2flow.management.release.ReleaseModels.ReleaseArtifact;
import dev.a2flow.management.release.ReleaseModels.ReleasePublishContext;
import dev.a2flow.management.release.ReleaseModels.ReleaseValidationRequirement;

import lombok.extern.slf4j.Slf4j;

/**
 * A2UI_APPLICATION 独立发布适配器。
 *
 * <p>上游是共享 release control plane，下游是 A2UI Application Registry current source 和
 * INLINE_V1 immutable manifest。该适配器不复用 COMPONENT adapter，不创建私有 Build/History/rollback
 * API，也不在缺少 manifest policy 时降级为 Registry current source 发布。
 */
@Component
@Slf4j
public class A2uiApplicationReleaseAssetAdapter extends AbstractReleaseAssetAdapter {

    private static final String ASSET_TYPE = "A2UI_APPLICATION";
    private static final String MANIFEST_POLICY = "INLINE_V1";
    private static final int MAX_MANIFEST_BYTES = 1024 * 1024;
    private static final String SOURCE_DIGEST_PARAM = "sourceDigest";
    private static final String GATE_SOURCE = "A2UI_APPLICATION_SOURCE_DIGEST";
    private static final String GATE_MANIFEST = "A2UI_APPLICATION_INLINE_MANIFEST";
    private static final String GATE_CATALOG_ENVIRONMENT = "A2UI_APPLICATION_CATALOG_ENVIRONMENT";
    private static final String LABEL_SOURCE = "Application source 摘要";
    private static final String LABEL_MANIFEST = "INLINE_V1 immutable manifest";
    private static final String LABEL_CATALOG_ENVIRONMENT = "目标环境 Catalog 精确版本";
    private static final String MESSAGE_SOURCE_READY = "Application source 摘要已冻结";
    private static final String MESSAGE_SOURCE_MISSING = "Application source 不存在";
    private static final String MESSAGE_MANIFEST_READY = "INLINE_V1 manifest 已冻结";
    private static final String MESSAGE_MANIFEST_MISSING = "INLINE_V1 manifest 尚未冻结";
    private static final String MESSAGE_MANIFEST_COMPILE_FAILED = "INLINE_V1 manifest 编译失败";
    private static final String MESSAGE_CATALOG_CHECK_SKIPPED =
            "INLINE_V1 manifest 编译失败，未执行目标环境 Catalog 校验";
    private static final String MESSAGE_CATALOG_READY = "Build 固定的 Catalog 已在目标环境精确发布";
    private static final String MESSAGE_CATALOG_MISMATCH = "Build 固定的 Catalog 未在目标环境精确发布";
    private static final String ERROR_SOURCE_REQUIRED = "A2UI_APPLICATION_SOURCE_REQUIRED";
    private static final String ERROR_COMPILER_REQUIRED = "A2UI_APPLICATION_COMPILER_REQUIRED";
    private static final String ERROR_ENVIRONMENT_REQUIRED = "A2UI_APPLICATION_ENVIRONMENT_REQUIRED";
    private static final String ERROR_ONLINE_SOURCE_INVALID = "A2UI_APPLICATION_ONLINE_SOURCE_INVALID";
    private static final String ERROR_MANIFEST_COMPILE_FAILED =
            "A2UI_APPLICATION_MANIFEST_COMPILE_FAILED";
    private static final String FIELD_APP_CODE = "appCode";
    private static final String FIELD_DESCRIPTION = "description";
    private static final String FIELD_APP_BUILD_ID = "appBuildId";
    private static final String FIELD_PUBLICATION_ENVIRONMENT = "publicationEnvironment";
    private static final String BUILD_ID_PREFIX = "a2ui_build_";
    private static final String DIGEST_PREFIX = "sha256:";

    @Resource
    private A2uiApplicationRegistryService registryService;

    @Resource
    private dev.a2flow.management.lifecycle.publish.RuntimeAssetPublisher runtimeAssetPublisher;

    @Resource
    private A2uiApplicationManifestCompilerService manifestCompilerService;

    private final A2uiInlineManifestStorage manifestStorage;

    public A2uiApplicationReleaseAssetAdapter() {
        this(MAX_MANIFEST_BYTES);
    }

    public A2uiApplicationReleaseAssetAdapter(Integer maxManifestBytes) {
        this(maxManifestBytes, null);
    }

    public A2uiApplicationReleaseAssetAdapter(Integer maxManifestBytes,
            A2uiApplicationManifestCompilerService manifestCompilerService) {
        this.manifestStorage = new A2uiInlineManifestStorage(maxManifestBytes);
        this.manifestCompilerService = manifestCompilerService;
    }

    @Override
    public ReleaseAssetType assetType() {
        return ReleaseAssetType.A2UI_APPLICATION;
    }

    @Override
    @SuppressWarnings("unchecked")
    public AssetSnapshot currentSnapshot(String assetKey, Map<String, String> params) {
        ComponentAsset asset = registryService == null ? null : registryService.current(assetKey);
        if (asset == null || StringUtils.isBlank(asset.getRuntimeConfigJson())) {
            throw new IllegalStateException(ERROR_SOURCE_REQUIRED);
        }
        Map<String, Object> source = JsonSupport.fromJSON(asset.getRuntimeConfigJson(), Map.class);
        String sourceDigest = A2uiImmutableJsonSupport.digest(source);
        return snapshot(assetKey, source, summaryEntry(
                "appCode", asset.getComponentName(),
                "nameCn", asset.getComponentNameCn(),
                "sourceDigest", sourceDigest), sourceDigest, null);
    }

    @Override
    public AssetSnapshot freezeBuildSnapshot(String assetKey, AssetSnapshot current,
            Map<String, String> params) {
        throw new IllegalStateException(ERROR_ENVIRONMENT_REQUIRED);
    }

    @Override
    public AssetSnapshot freezeBuildSnapshot(ReleaseOperationContext operationContext,
            String assetKey, ReleaseEnvironment environment, AssetSnapshot current,
            Map<String, String> params) {
        String expectedDigest = params == null ? null : params.get(SOURCE_DIGEST_PARAM);
        if (StringUtils.isNotBlank(expectedDigest)
                && !StringUtils.equals(expectedDigest, current == null ? null : current.getDigest())) {
            throw new A2uiApplicationValidationException(SOURCE_STALE);
        }
        if (current == null || StringUtils.isBlank(current.getPayloadJson())) {
            throw new IllegalStateException(ERROR_SOURCE_REQUIRED);
        }
        if (manifestCompilerService == null) {
            throw new IllegalStateException(ERROR_COMPILER_REQUIRED);
        }
        if (environment == null) {
            throw new IllegalStateException(ERROR_ENVIRONMENT_REQUIRED);
        }
        A2uiApplicationBuild build = manifestCompilerService.compile(
                assetKey, current.getPayloadJson(), environment);
        return manifestStorage.store(assetKey, JsonSupport.toJSON(build));
    }

    /** 只从冻结预发产物生成独立线上身份；组件、绑定和精确 Catalog 引用均保留原文语义。 */
    @Override
    @SuppressWarnings("unchecked")
    public AssetSnapshot prepareOnlineSnapshot(String assetKey, AssetSnapshot verifiedBuild) {
        manifestStorage.verifyReadback(verifiedBuild);
        Map<String, Object> manifest = JsonSupport.fromJSON(verifiedBuild.getPayloadJson(), Map.class);
        if (!ASSET_TYPE.equals(verifiedBuild.getAssetType())
                || !StringUtils.equals(assetKey, verifiedBuild.getAssetKey())
                || manifest == null || !assetKey.equals(manifest.get(FIELD_APP_CODE))
                || !ReleaseEnvironment.PRT.name().equals(manifest.get(FIELD_PUBLICATION_ENVIRONMENT))
                || !(manifest.get(SOURCE_DIGEST_PARAM) instanceof String)
                || !(manifest.get(FIELD_APP_BUILD_ID) instanceof String)
                || StringUtils.isAnyBlank((String) manifest.get(SOURCE_DIGEST_PARAM),
                        (String) manifest.get(FIELD_APP_BUILD_ID))) {
            throw new IllegalStateException(ERROR_ONLINE_SOURCE_INVALID);
        }
        if (!GATE_PASSED.equals(catalogEnvironmentGate(
                ReleaseEnvironment.ONLINE, verifiedBuild, true).getStatus())) {
            throw new A2uiApplicationValidationException(CATALOG_ENVIRONMENT_MISMATCH);
        }
        // JSON 深拷贝切断原 Build 引用；目标内容先排除旧身份，再计算确定性的线上身份。
        manifest.put(FIELD_PUBLICATION_ENVIRONMENT, ReleaseEnvironment.ONLINE.name());
        manifest.remove(FIELD_APP_BUILD_ID);
        manifest.remove(SOURCE_DIGEST_PARAM);
        String sourceDigest = A2uiImmutableJsonSupport.digest(manifest);
        manifest.put(SOURCE_DIGEST_PARAM, sourceDigest);
        manifest.put(FIELD_APP_BUILD_ID, BUILD_ID_PREFIX + sourceDigest.substring(DIGEST_PREFIX.length()));
        AssetSnapshot online = manifestStorage.store(assetKey,
                JsonSupport.toJSON(A2uiImmutableJsonSupport.canonicalize(manifest)));
        log.info("A2UI Application线上快照已派生, assetKey:{}, buildDigest:{}, onlineDigest:{}",
                assetKey, verifiedBuild.getDigest(), online.getDigest());
        return online;
    }

    @Override
    public List<GateResult> evaluateGates(String assetKey, ReleaseEnvironment environment,
            AssetSnapshot snapshot, Map<String, String> params) {
        boolean sourceReady = snapshot != null && StringUtils.isNotBlank(snapshot.getDigest());
        boolean manifestReady = snapshot != null && MANIFEST_POLICY.equals(snapshot.getStoragePolicy())
                && snapshot.getPayloadBytes() != null;
        GateResult catalogGate = catalogEnvironmentGate(environment, snapshot, manifestReady);
        return List.of(
                gate(GATE_SOURCE, LABEL_SOURCE, sourceReady, true,
                        sourceReady ? MESSAGE_SOURCE_READY : MESSAGE_SOURCE_MISSING),
                gate(GATE_MANIFEST, LABEL_MANIFEST, manifestReady, true,
                        manifestReady ? MESSAGE_MANIFEST_READY : MESSAGE_MANIFEST_MISSING),
                catalogGate);
    }

    /** 发布页预览在内存编译同一 immutable manifest，不写入 Build、Version 或环境指针。 */
    @Override
    public List<GateResult> evaluatePreviewGates(
            ReleaseOperationContext operationContext, String assetKey,
            ReleaseEnvironment environment, AssetSnapshot snapshot,
            ReleaseArtifact artifact, Map<String, String> params) {
        try {
            // 线上检查使用冻结预发产物，不能把 manifest 当作作者态草稿重新编译。
            AssetSnapshot preview = environment == ReleaseEnvironment.ONLINE
                    ? prepareOnlineSnapshot(assetKey, snapshot)
                    : freezeBuildSnapshot(operationContext, assetKey, environment, snapshot, params);
            return evaluateGates(
                    operationContext, assetKey, environment, preview, artifact, params);
        } catch (RuntimeException exception) {
            String errorCode = previewCompileErrorCode(exception);
            if (exception instanceof A2uiApplicationValidationException) {
                log.warn("A2UI Application发布预览manifest编译失败, assetKey:{}, environment:{}, "
                                + "errorCode:{}, exceptionType:{}",
                        assetKey, environment, errorCode, exception.getClass().getSimpleName());
            } else {
                log.error("A2UI Application发布预览manifest发生未预期编译异常, assetKey:{}, "
                                + "environment:{}, errorCode:{}",
                        assetKey, environment, errorCode, exception);
            }
            return previewCompileFailureGates(snapshot, exception, errorCode);
        }
    }

    private List<GateResult> previewCompileFailureGates(
            AssetSnapshot snapshot, RuntimeException exception, String errorCode) {
        boolean sourceReady = snapshot != null && StringUtils.isNotBlank(snapshot.getDigest());
        String manifestMessage = exception instanceof A2uiApplicationValidationException
                ? exception.getMessage() : MESSAGE_MANIFEST_COMPILE_FAILED;
        return List.of(
                gate(GATE_SOURCE, LABEL_SOURCE, sourceReady, true,
                        sourceReady ? MESSAGE_SOURCE_READY : MESSAGE_SOURCE_MISSING),
                gate(GATE_MANIFEST, LABEL_MANIFEST, false, true, manifestMessage)
                        .setErrorCode(errorCode),
                gate(GATE_CATALOG_ENVIRONMENT, LABEL_CATALOG_ENVIRONMENT, false, true,
                        MESSAGE_CATALOG_CHECK_SKIPPED).setCauseCode(errorCode));
    }

    private String previewCompileErrorCode(RuntimeException exception) {
        if (exception instanceof A2uiApplicationValidationException validation) {
            return validation.getErrorCode();
        }
        return ERROR_MANIFEST_COMPILE_FAILED;
    }

    private GateResult catalogEnvironmentGate(
            ReleaseEnvironment environment, AssetSnapshot snapshot, boolean manifestReady) {
        if (!manifestReady || manifestCompilerService == null || environment == null) {
            return gate(GATE_CATALOG_ENVIRONMENT, LABEL_CATALOG_ENVIRONMENT, false, true,
                    MESSAGE_CATALOG_MISMATCH).setErrorCode(CATALOG_ENVIRONMENT_MISMATCH.getCode());
        }
        try {
            @SuppressWarnings("unchecked")
            Map<String, Object> build = JsonSupport.fromJSON(
                    snapshot.getPayloadJson(), Map.class);
            @SuppressWarnings("unchecked")
            Map<String, Object> catalog = build == null ? null
                    : (Map<String, Object>) build.get("catalog");
            manifestCompilerService.verifyCatalogPublication(
                    catalog == null ? null : String.valueOf(catalog.get("catalogId")),
                    catalog == null ? null : String.valueOf(catalog.get("revision")),
                    catalog == null ? null : String.valueOf(catalog.get("digest")), environment);
            return gate(GATE_CATALOG_ENVIRONMENT, LABEL_CATALOG_ENVIRONMENT, true, true,
                    MESSAGE_CATALOG_READY);
        } catch (RuntimeException exception) {
            log.warn("A2UI Application目标环境Catalog校验失败, assetKey:{}, environment:{}, errorCode:{}",
                    snapshot.getAssetKey(), environment, CATALOG_ENVIRONMENT_MISMATCH.getCode());
            return gate(GATE_CATALOG_ENVIRONMENT, LABEL_CATALOG_ENVIRONMENT, false, true,
                    MESSAGE_CATALOG_MISMATCH).setErrorCode(CATALOG_ENVIRONMENT_MISMATCH.getCode());
        }
    }

    @Override
    public List<ReleaseValidationRequirement> validationRequirements(ReleaseEnvironment environment) {
        return Collections.emptyList();
    }

    /** 从已校验的历史产物恢复编排；只更新当前作者态，不重新发布或覆盖历史环境指针。 */
    @Override
    @SuppressWarnings("unchecked")
    public void restore(String userName, String assetKey, AssetSnapshot snapshot,
            Map<String, String> params) {
        manifestStorage.verifyReadback(snapshot);
        if (!ASSET_TYPE.equals(snapshot.getAssetType())
                || !StringUtils.equals(assetKey, snapshot.getAssetKey())) {
            throw new A2uiApplicationValidationException(HISTORY_SNAPSHOT_INVALID);
        }
        ComponentAsset current = registryService.current(assetKey);
        if (current == null || current.getId() == null) {
            throw new A2uiApplicationValidationException(HISTORY_SNAPSHOT_INVALID);
        }
        Map<String, Object> currentSource = JsonSupport.fromJSON(current.getRuntimeConfigJson(), Map.class);
        Map<String, Object> source = A2uiApplicationHistoryRestoreSupport.restore(
                snapshot.getPayloadJson(), assetKey, current.getComponentNameCn(),
                currentSource == null ? null : currentSource.get(FIELD_DESCRIPTION));
        registryService.update(userName, String.valueOf(current.getId()), source);
        log.info("A2UI Application历史编排已恢复, assetKey:{}, snapshotDigest:{}, operator:{}",
                assetKey, snapshot.getDigest(), userName);
    }

    @Override
    public PublishResult deploy(ReleasePublishContext context) {
        AssetSnapshot snapshot = context == null ? null : context.getSnapshot();
        if (snapshot == null || !MANIFEST_POLICY.equals(snapshot.getStoragePolicy())) {
            return failed("A2UI Application immutable manifest is required");
        }
        manifestStorage.verifyReadback(snapshot);
        com.fasterxml.jackson.databind.JsonNode published = JsonSupport.fromJSON(
                snapshot.getPayloadJson(), com.fasterxml.jackson.databind.JsonNode.class);
        if (published == null || !published.path("appCode").isTextual()) {
            throw new IllegalStateException("A2UI_APPLICATION_CODE_REQUIRED");
        }
        runtimeAssetPublisher.publish("APPLICATION", published.get("appCode").asText(), context);
        log.info("A2UI Application immutable manifest 发布完成, assetKey:{}, environment:{}, operator:{}",
                context.getAssetKey(), context.getEnvironment(), context.getUserName());
        return succeeded("A2UI Application immutable manifest 发布完成", new LinkedHashMap<>());
    }
}
