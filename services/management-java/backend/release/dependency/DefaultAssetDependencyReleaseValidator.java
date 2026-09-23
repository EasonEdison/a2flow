package dev.a2flow.management.release.dependency;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;

import dev.a2flow.management.release.WorkflowReleasePayloadValidationException;
import dev.a2flow.management.release.dependency.AssetDependencyModels.AssetDependencyReference;
import dev.a2flow.management.release.dependency.AssetDependencyModels.DependencyPathNode;
import dev.a2flow.management.release.dependency.AssetDependencyModels.DependencyReleaseFailure;
import dev.a2flow.management.release.dependency.AssetDependencyModels.DependencyReleaseReport;
import dev.a2flow.management.release.dependency.AssetDependencyModels.DependencyValidationRequest;
import dev.a2flow.management.release.dependency.AssetDependencyModels.ResolvedReleasedAsset;

import lombok.extern.slf4j.Slf4j;

/**
 * 环境资产依赖图的默认准出校验器。
 *
 * <p>上游提供 Skill 等根资产及其直接依赖，本类按资产类型和 assetKey 排序执行深度优先遍历，
 * 每个节点复用 {@link EnvironmentAwareAssetResolver}，再由领域 Adapter 提取下一层依赖。它只生成
 * 报告，不执行发布、不移动环境指针，也不解释领域 payload。
 */
@Service
@Slf4j
public class DefaultAssetDependencyReleaseValidator implements AssetDependencyReleaseValidator {

    private static final int MAX_DEPENDENCY_DEPTH = 16;
    private static final String IDENTITY_SEPARATOR = "::";
    private static final String DEFAULT_ROOT_ASSET_TYPE = "ASSET";
    private static final String MESSAGE_REQUEST_INVALID = "依赖校验请求缺少根资产或目标环境";
    private static final String MESSAGE_REFERENCE_INVALID = "依赖资产类型或assetKey为空";
    private static final String MESSAGE_CYCLE = "依赖图存在循环引用";
    private static final String MESSAGE_DEPTH = "依赖图深度超过16层";
    private static final String MESSAGE_ADAPTER_MISSING = "依赖资产类型尚未注册领域Adapter";
    private static final String MESSAGE_EXPANSION_FAILED = "领域Adapter展开下游依赖失败";

    private static final Comparator<AssetDependencyReference> DEPENDENCY_COMPARATOR = Comparator.nullsFirst(
            Comparator.comparing((AssetDependencyReference reference) ->
                            reference.getAssetType() == null ? "" : reference.getAssetType().name())
                    .thenComparing(reference -> StringUtils.defaultString(reference.getAssetKey())));

    private final EnvironmentAwareAssetResolver assetResolver;
    private final AssetDependencyAdapterRegistry adapterRegistry;

    public DefaultAssetDependencyReleaseValidator(EnvironmentAwareAssetResolver assetResolver,
            AssetDependencyAdapterRegistry adapterRegistry) {
        this.assetResolver = assetResolver;
        this.adapterRegistry = adapterRegistry;
    }

    /**
     * 校验完整依赖图并返回所有确定性失败。
     *
     * <p>同一资产通过多个路径出现时保留每条结构化路径，但只展开第一次命中的节点；当前递归栈仍
     * 单独参与环检测，因此不会因全局去重漏报循环引用，也不会丢失多路径审计事实。
     */
    @Override
    public DependencyReleaseReport validate(DependencyValidationRequest request) {
        DependencyReleaseReport report = baseReport(request);
        List<DependencyPathNode> rootPath = rootPath(request);
        if (!validRoot(request)) {
            report.getFailures().add(failure(AssetDependencyErrorCode.ASSET_REFERENCE_INVALID,
                    MESSAGE_REQUEST_INVALID, rootPath));
            return report.setPassed(false);
        }
        if (request.getRequestedEnvironment() == null) {
            report.getFailures().add(failure(AssetDependencyErrorCode.RELEASE_ENVIRONMENT_REQUIRED,
                    MESSAGE_REQUEST_INVALID, rootPath));
            return report.setPassed(false);
        }
        log.info("资产依赖准出校验开始, rootAssetType:{}, rootAssetKey:{}, requestedEnvironment:{}, "
                        + "directDependencyCount:{}",
                request.getRootAssetType(), request.getRootAssetKey(), request.getRequestedEnvironment(),
                request.getDependencies() == null ? 0 : request.getDependencies().size());
        TraversalContext context = new TraversalContext(report);
        for (AssetDependencyReference dependency : ordered(request.getDependencies())) {
            traverse(dependency, 1, rootPath, context);
        }
        report.setPassed(report.getFailures().isEmpty());
        log.info("资产依赖准出校验结束, rootAssetType:{}, rootAssetKey:{}, requestedEnvironment:{}, "
                        + "passed:{}, resolvedCount:{}, failureCount:{}",
                request.getRootAssetType(), request.getRootAssetKey(), request.getRequestedEnvironment(),
                report.getPassed(), report.getResolvedAssets().size(), report.getFailures().size());
        return report;
    }

    private void traverse(AssetDependencyReference dependency, int depth, List<DependencyPathNode> parentPath,
            TraversalContext context) {
        if (!validReference(dependency)) {
            context.report.getFailures().add(failure(AssetDependencyErrorCode.ASSET_REFERENCE_INVALID,
                    MESSAGE_REFERENCE_INVALID, appendReference(parentPath, dependency)));
            return;
        }
        String identity = identity(dependency);
        List<DependencyPathNode> currentPath = append(parentPath, dependency);
        if (context.activeIdentities.contains(identity)) {
            addFailure(context, AssetDependencyErrorCode.DEPENDENCY_CYCLE, MESSAGE_CYCLE, currentPath);
            return;
        }
        if (depth > MAX_DEPENDENCY_DEPTH) {
            addFailure(context, AssetDependencyErrorCode.DEPENDENCY_DEPTH_EXCEEDED, MESSAGE_DEPTH, currentPath);
            return;
        }
        if (context.expandedIdentities.contains(identity)) {
            ResolvedReleasedAsset expanded = context.resolvedAssetsByIdentity.get(identity);
            if (expanded != null) {
                context.report.getResolvedAssets().add(copyResolvedAsset(expanded, currentPath));
            }
            return;
        }

        ResolvedReleasedAsset resolvedAsset;
        try {
            resolvedAsset = assetResolver.resolve(dependency, context.report.getRequestedEnvironment());
        } catch (AssetDependencyResolutionException exception) {
            addResolutionFailure(context, exception, currentPath);
            return;
        }
        resolvedAsset.setPath(new ArrayList<>(currentPath));
        context.report.getResolvedAssets().add(resolvedAsset);
        context.resolvedAssetsByIdentity.put(identity, resolvedAsset);
        AssetDependencyAdapter adapter = adapterRegistry.find(dependency.getAssetType()).orElse(null);
        if (adapter == null) {
            addFailure(context, AssetDependencyErrorCode.ASSET_TYPE_UNSUPPORTED,
                    MESSAGE_ADAPTER_MISSING, currentPath);
            return;
        }

        List<AssetDependencyReference> children;
        try {
            children = adapter.dependencies(resolvedAsset);
            if (children == null) {
                throw new IllegalStateException(MESSAGE_EXPANSION_FAILED);
            }
        } catch (AssetDependencyResolutionException exception) {
            logExpansionFailure(dependency, exception);
            addResolutionFailure(context, exception, currentPath);
            return;
        } catch (WorkflowReleasePayloadValidationException exception) {
            logExpansionFailure(dependency, exception);
            addFailure(context, AssetDependencyErrorCode.DEPENDENCY_EXPANSION_FAILED,
                    MESSAGE_EXPANSION_FAILED, currentPath,
                    exception.getClass().getSimpleName(), exception.getErrorCode(),
                    exception.getFieldPath());
            return;
        } catch (RuntimeException exception) {
            logExpansionFailure(dependency, exception);
            addFailure(context, AssetDependencyErrorCode.DEPENDENCY_EXPANSION_FAILED,
                    MESSAGE_EXPANSION_FAILED, currentPath,
                    exception.getClass().getSimpleName(), null, null);
            return;
        }

        context.activeIdentities.add(identity);
        for (AssetDependencyReference child : ordered(children)) {
            traverse(child, depth + 1, currentPath, context);
        }
        context.activeIdentities.remove(identity);
        context.expandedIdentities.add(identity);
    }

    private DependencyReleaseReport baseReport(DependencyValidationRequest request) {
        return new DependencyReleaseReport()
                .setPassed(false)
                .setRootAssetType(request == null ? null : request.getRootAssetType())
                .setRootAssetKey(request == null ? null : request.getRootAssetKey())
                .setRequestedEnvironment(request == null ? null : request.getRequestedEnvironment());
    }

    private boolean validRoot(DependencyValidationRequest request) {
        return request != null
                && StringUtils.isNotBlank(request.getRootAssetType())
                && StringUtils.isNotBlank(request.getRootAssetKey());
    }

    private boolean validReference(AssetDependencyReference dependency) {
        return dependency != null && dependency.getAssetType() != null
                && StringUtils.isNotBlank(dependency.getAssetKey());
    }

    private List<AssetDependencyReference> ordered(List<AssetDependencyReference> dependencies) {
        if (dependencies == null || dependencies.isEmpty()) {
            return List.of();
        }
        Map<String, AssetDependencyReference> uniqueDependencies = new TreeMap<>();
        for (AssetDependencyReference dependency : dependencies) {
            String key = validReference(dependency) ? identity(dependency)
                    : "INVALID::" + uniqueDependencies.size();
            uniqueDependencies.putIfAbsent(key, dependency);
        }
        return uniqueDependencies.values().stream().sorted(DEPENDENCY_COMPARATOR).toList();
    }

    private List<DependencyPathNode> rootPath(DependencyValidationRequest request) {
        if (request == null) {
            return List.of();
        }
        return List.of(new DependencyPathNode()
                .setAssetType(StringUtils.defaultIfBlank(request.getRootAssetType(), DEFAULT_ROOT_ASSET_TYPE))
                .setAssetKey(request.getRootAssetKey()));
    }

    private List<DependencyPathNode> append(List<DependencyPathNode> path,
            AssetDependencyReference dependency) {
        List<DependencyPathNode> appended = new ArrayList<>(path);
        appended.add(new DependencyPathNode()
                .setAssetType(dependency.getAssetType().name())
                .setAssetKey(dependency.getAssetKey()));
        return appended;
    }

    private List<DependencyPathNode> appendReference(List<DependencyPathNode> path,
            AssetDependencyReference dependency) {
        List<DependencyPathNode> appended = new ArrayList<>(path);
        appended.add(new DependencyPathNode()
                .setAssetType(dependency == null || dependency.getAssetType() == null
                        ? null : dependency.getAssetType().name())
                .setAssetKey(dependency == null ? null : dependency.getAssetKey()));
        return appended;
    }

    private void addFailure(TraversalContext context, AssetDependencyErrorCode errorCode,
            String message, List<DependencyPathNode> path) {
        addFailure(context, errorCode, message, path, null, null, null);
    }

    private void addFailure(TraversalContext context, AssetDependencyErrorCode errorCode,
            String message, List<DependencyPathNode> path, String causeType, String causeCode,
            String fieldPath) {
        context.report.getFailures().add(failure(errorCode, message, path)
                .setCauseType(causeType)
                .setCauseCode(causeCode)
                .setFieldPath(fieldPath));
        log.warn("资产依赖准出失败, errorCode:{}, dependencyPath:{}", errorCode, pathText(path));
    }

    private void addResolutionFailure(TraversalContext context,
            AssetDependencyResolutionException exception, List<DependencyPathNode> path) {
        Throwable safeCause = safeCause(exception);
        addFailure(context, exception.getErrorCode(), exception.getMessage(), path,
                safeCause.getClass().getSimpleName(),
                StringUtils.defaultIfBlank(exception.getCauseCode(), causeCode(safeCause)),
                StringUtils.defaultIfBlank(exception.getFieldPath(), fieldPath(safeCause)));
    }

    private Throwable safeCause(AssetDependencyResolutionException exception) {
        Throwable cause = exception;
        while (cause != null) {
            if (cause instanceof WorkflowReleasePayloadValidationException) {
                return cause;
            }
            cause = cause.getCause();
        }
        return exception;
    }

    private String causeCode(Throwable cause) {
        if (cause instanceof WorkflowReleasePayloadValidationException) {
            return ((WorkflowReleasePayloadValidationException) cause).getErrorCode();
        }
        return ((AssetDependencyResolutionException) cause).getErrorCode().name();
    }

    private String fieldPath(Throwable cause) {
        if (cause instanceof WorkflowReleasePayloadValidationException) {
            return ((WorkflowReleasePayloadValidationException) cause).getFieldPath();
        }
        return ((AssetDependencyResolutionException) cause).getFieldPath();
    }

    private void logExpansionFailure(AssetDependencyReference dependency, RuntimeException exception) {
        log.warn("领域Adapter展开依赖失败, assetType:{}, assetKey:{}, errorType:{}",
                dependency.getAssetType(), dependency.getAssetKey(), exception.getClass().getSimpleName());
    }

    private DependencyReleaseFailure failure(AssetDependencyErrorCode errorCode,
            String message, List<DependencyPathNode> path) {
        return new DependencyReleaseFailure()
                .setErrorCode(errorCode)
                .setMessage(message)
                .setPath(new ArrayList<>(path));
    }

    private String identity(AssetDependencyReference dependency) {
        return dependency.getAssetType().name() + IDENTITY_SEPARATOR + dependency.getAssetKey();
    }

    private String pathText(List<DependencyPathNode> path) {
        return path.stream()
                .map(node -> node.getAssetType() + "/" + StringUtils.defaultString(node.getAssetKey()))
                .reduce((left, right) -> left + " -> " + right)
                .orElse("");
    }

    private ResolvedReleasedAsset copyResolvedAsset(
            ResolvedReleasedAsset source, List<DependencyPathNode> path) {
        return new ResolvedReleasedAsset()
                .setAssetType(source.getAssetType())
                .setAssetKey(source.getAssetKey())
                .setPath(new ArrayList<>(path))
                .setRequestedEnvironment(source.getRequestedEnvironment())
                .setResolvedEnvironment(source.getResolvedEnvironment())
                .setSourceType(source.getSourceType())
                .setSourceId(source.getSourceId())
                .setVersion(source.getVersion())
                .setDigest(source.getDigest())
                .setArtifactRef(source.getArtifactRef())
                .setPayloadJson(source.getPayloadJson())
                .setCandidate(source.getCandidate())
                .setRouteReason(source.getRouteReason())
                .setSummary(source.getSummary() == null
                        ? new LinkedHashMap<>() : new LinkedHashMap<>(source.getSummary()));
    }

    private static final class TraversalContext {
        private final DependencyReleaseReport report;
        private final Set<String> activeIdentities = new LinkedHashSet<>();
        private final Set<String> expandedIdentities = new LinkedHashSet<>();
        private final Map<String, ResolvedReleasedAsset> resolvedAssetsByIdentity =
                new LinkedHashMap<>();

        private TraversalContext(DependencyReleaseReport report) {
            this.report = report;
        }
    }
}
