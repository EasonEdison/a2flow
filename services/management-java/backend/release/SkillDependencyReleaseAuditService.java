package dev.a2flow.management.release;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import jakarta.annotation.Resource;

import org.springframework.stereotype.Service;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.release.ReleaseModels.AssetSnapshot;
import dev.a2flow.management.release.dependency.AssetDependencyModels.AssetDependencyReference;
import dev.a2flow.management.release.dependency.AssetDependencyModels.DependencyPathNode;
import dev.a2flow.management.release.dependency.AssetDependencyModels.DependencyReleaseFailure;
import dev.a2flow.management.release.dependency.AssetDependencyModels.DependencyReleaseReport;
import dev.a2flow.management.release.dependency.AssetDependencyModels.DependencyValidationRequest;
import dev.a2flow.management.release.dependency.AssetDependencyModels.ResolvedReleasedAsset;
import dev.a2flow.management.release.dependency.AssetDependencyReleaseValidator;
import dev.a2flow.management.release.dependency.AssetDependencyType;
import dev.a2flow.management.release.dependency.ReleasedAssetSourceType;

import lombok.Data;
import lombok.experimental.Accessors;
import lombok.extern.slf4j.Slf4j;

/**
 * Skill 发布依赖解析审计服务。
 *
 * <p>上游在创建不可变 Skill Build 前传入当前内容快照，本服务复用公共依赖校验器分别解析
 * PRT 和 ONLINE，并把完整路径、环境和来源写入 Build 快照。审计结果参与 sourceDigest 和
 * 版本 Diff，但不负责运行态选源，也不提供消费方版本策略。
 */
@Service
@Slf4j
public class SkillDependencyReleaseAuditService {

    public static final String FIELD_INPUT_DIGEST = "inputDigest";
    public static final String FIELD_DEPENDENCY_RESOLUTIONS = "dependencyResolutions";
    public static final String FIELD_DEPENDENCY_RESOLUTION_FAILURES = "dependencyResolutionFailures";

    private static final String FIELD_ERROR_CODE = "errorCode";
    private static final String FIELD_PATH = "path";
    private static final String ROOT_ASSET_TYPE = "SKILL";
    private static final String ERROR_SNAPSHOT_PAYLOAD_INVALID = "Skill发布快照内容解析失败";

    @Resource
    private SkillReleaseBindingSnapshotReader bindingSnapshotReader;

    @Resource
    private AssetDependencyReleaseValidator assetDependencyReleaseValidator;

    /** 解析两个环境并生成只用于发布审计的不可变 Skill Build 快照。 */
    public AssetSnapshot freeze(String assetKey, AssetSnapshot currentSnapshot) {
        List<SkillReleaseBindingSnapshotReader.DirectDependency> directDependencies =
                bindingSnapshotReader.readDirectDependencies(currentSnapshot);
        DependencyReleaseReport preprod = validate(
                assetKey, ReleaseEnvironment.PRT, directDependencies);
        DependencyReleaseReport online = validate(
                assetKey, ReleaseEnvironment.ONLINE, directDependencies);
        Map<String, List<DependencyResolutionAuditEntry>> resolutions = new LinkedHashMap<>();
        Map<String, List<DependencyReleaseFailure>> failures = new LinkedHashMap<>();
        recordReport(preprod, resolutions, failures);
        recordReport(online, resolutions, failures);

        Map<String, Object> payload = payload(currentSnapshot);
        writeAudit(payload, currentSnapshot.getDigest(), resolutions, failures);
        Map<String, Object> summary = currentSnapshot.getSummary() == null
                ? new LinkedHashMap<>() : new LinkedHashMap<>(currentSnapshot.getSummary());
        writeAudit(summary, currentSnapshot.getDigest(), resolutions, failures);
        String releaseDigest = releaseDigest(currentSnapshot.getDigest(), resolutions, failures);
        log.info("Skill依赖发布审计冻结完成, skillCode:{}, inputDigest:{}, releaseDigest:{}, "
                        + "preprodResolutionCount:{}, onlineResolutionCount:{}, "
                        + "preprodFailureCount:{}, onlineFailureCount:{}",
                assetKey, currentSnapshot.getDigest(), releaseDigest,
                itemCount(resolutions, ReleaseEnvironment.PRT),
                itemCount(resolutions, ReleaseEnvironment.ONLINE),
                itemCount(failures, ReleaseEnvironment.PRT),
                itemCount(failures, ReleaseEnvironment.ONLINE));
        return new AssetSnapshot()
                .setAssetType(currentSnapshot.getAssetType())
                .setAssetKey(currentSnapshot.getAssetKey())
                .setDigest(releaseDigest)
                .setArtifactRef(currentSnapshot.getArtifactRef())
                .setSummary(summary)
                .setPayloadJson(JsonSupport.toJSON(payload));
    }

    private DependencyReleaseReport validate(String assetKey, ReleaseEnvironment environment,
            List<SkillReleaseBindingSnapshotReader.DirectDependency> directDependencies) {
        List<AssetDependencyReference> references = directDependencies.stream()
                .map(dependency -> new AssetDependencyReference()
                        .setAssetType(dependency.getAssetType())
                        .setAssetKey(dependency.getAssetKey()))
                .toList();
        return assetDependencyReleaseValidator.validate(new DependencyValidationRequest()
                .setRootAssetType(ROOT_ASSET_TYPE)
                .setRootAssetKey(assetKey)
                .setRequestedEnvironment(environment)
                .setDependencies(references));
    }

    private void recordReport(DependencyReleaseReport report,
            Map<String, List<DependencyResolutionAuditEntry>> resolutions,
            Map<String, List<DependencyReleaseFailure>> failures) {
        String environment = report.getRequestedEnvironment().name();
        List<DependencyResolutionAuditEntry> entries = new ArrayList<>();
        for (ResolvedReleasedAsset resolved : report.getResolvedAssets()) {
            entries.add(new DependencyResolutionAuditEntry()
                    .setPath(copyPath(resolved.getPath()))
                    .setAssetType(resolved.getAssetType())
                    .setAssetKey(resolved.getAssetKey())
                    .setRequestedEnvironment(resolved.getRequestedEnvironment())
                    .setResolvedEnvironment(resolved.getResolvedEnvironment())
                    .setSourceType(resolved.getSourceType())
                    .setSourceId(resolved.getSourceId())
                    .setVersion(resolved.getVersion())
                    .setDigest(resolved.getDigest()));
        }
        List<DependencyReleaseFailure> copiedFailures = new ArrayList<>();
        report.getFailures().forEach(failure -> copiedFailures.add(copyFailure(failure)));
        resolutions.put(environment, entries);
        failures.put(environment, copiedFailures);
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> payload(AssetSnapshot snapshot) {
        try {
            Object parsed = JsonSupport.fromJSON(snapshot.getPayloadJson(), Object.class);
            if (!(parsed instanceof Map)) {
                throw new IllegalStateException(ERROR_SNAPSHOT_PAYLOAD_INVALID);
            }
            return new LinkedHashMap<>((Map<String, Object>) parsed);
        } catch (RuntimeException exception) {
            throw new IllegalStateException(ERROR_SNAPSHOT_PAYLOAD_INVALID, exception);
        }
    }

    private void writeAudit(Map<String, Object> target, String inputDigest,
            Map<String, List<DependencyResolutionAuditEntry>> resolutions,
            Map<String, List<DependencyReleaseFailure>> failures) {
        target.put(FIELD_INPUT_DIGEST, inputDigest);
        target.put(FIELD_DEPENDENCY_RESOLUTIONS, resolutions);
        target.put(FIELD_DEPENDENCY_RESOLUTION_FAILURES, failures);
    }

    private String releaseDigest(String inputDigest,
            Map<String, List<DependencyResolutionAuditEntry>> resolutions,
            Map<String, List<DependencyReleaseFailure>> failures) {
        Map<String, Object> digestSource = new LinkedHashMap<>();
        digestSource.put(FIELD_INPUT_DIGEST, inputDigest);
        digestSource.put(FIELD_DEPENDENCY_RESOLUTIONS, resolutions);
        digestSource.put(FIELD_DEPENDENCY_RESOLUTION_FAILURES, digestFailures(failures));
        return ReleaseDigestUtils.sha256(JsonSupport.toJSON(digestSource));
    }

    private Map<String, List<Map<String, Object>>> digestFailures(
            Map<String, List<DependencyReleaseFailure>> failuresByEnvironment) {
        Map<String, List<Map<String, Object>>> result = new LinkedHashMap<>();
        failuresByEnvironment.forEach((environment, failures) -> {
            List<Map<String, Object>> entries = new ArrayList<>();
            for (DependencyReleaseFailure failure : failures) {
                Map<String, Object> entry = new LinkedHashMap<>();
                entry.put(FIELD_ERROR_CODE, failure.getErrorCode());
                entry.put(FIELD_PATH, copyPath(failure.getPath()));
                entries.add(entry);
            }
            result.put(environment, entries);
        });
        return result;
    }

    private DependencyReleaseFailure copyFailure(DependencyReleaseFailure failure) {
        return new DependencyReleaseFailure()
                .setErrorCode(failure.getErrorCode())
                .setMessage(failure.getMessage())
                .setPath(copyPath(failure.getPath()));
    }

    private List<DependencyPathNode> copyPath(List<DependencyPathNode> path) {
        if (path == null) {
            return new ArrayList<>();
        }
        List<DependencyPathNode> copied = new ArrayList<>();
        for (DependencyPathNode node : path) {
            copied.add(node == null ? new DependencyPathNode() : new DependencyPathNode()
                    .setAssetType(node.getAssetType())
                    .setAssetKey(node.getAssetKey()));
        }
        return copied;
    }

    private int itemCount(Map<String, ? extends List<?>> values,
            ReleaseEnvironment environment) {
        List<?> items = values.get(environment.name());
        return items == null ? 0 : items.size();
    }

    /** 单条完整依赖路径在 Build 创建时解析到的发布来源审计。 */
    @Data
    @Accessors(chain = true)
    public static class DependencyResolutionAuditEntry {
        private List<DependencyPathNode> path = new ArrayList<>();
        private AssetDependencyType assetType;
        private String assetKey;
        private ReleaseEnvironment requestedEnvironment;
        private ReleaseEnvironment resolvedEnvironment;
        private ReleasedAssetSourceType sourceType;
        private String sourceId;
        private Integer version;
        private String digest;
    }
}
