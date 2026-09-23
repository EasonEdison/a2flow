package dev.a2flow.management.release;

import java.util.List;

import jakarta.annotation.Resource;

import org.springframework.stereotype.Component;

import dev.a2flow.management.release.dependency.AssetDependencyAdapter;
import dev.a2flow.management.release.dependency.AssetDependencyErrorCode;
import dev.a2flow.management.release.dependency.AssetDependencyModels.AssetDependencyReference;
import dev.a2flow.management.release.dependency.AssetDependencyModels.ResolvedReleasedAsset;
import dev.a2flow.management.release.dependency.AssetDependencyResolutionException;
import dev.a2flow.management.release.dependency.AssetDependencyType;

/**
 * Workflow 不可变发布快照接入公共依赖图的领域 Adapter。
 *
 * <p>上游公共环境解析器负责选择 PRT Build 或 ONLINE Version，本类只校验 Workflow frozen
 * payload，并从其中已经重新编译验证的 compiledPlan 提取稳定 Skill 身份。下游继续由公共
 * AssetDependencyReleaseValidator 展开 Skill→Capability/Component；本类不读 Workflow/Skill 草稿、
 * latest 版本或私有发布状态，也不选择 PINNED/TRACK 策略。
 */
@Component
public class WorkflowAssetDependencyAdapter implements AssetDependencyAdapter {

    private static final String ERROR_WORKFLOW_DEPENDENCY_NOT_READY =
            "Workflow冻结发布快照未通过依赖准出";

    @Resource
    private WorkflowReleasePayloadAdapter payloadAdapter;

    @Override
    public AssetDependencyType assetType() {
        return AssetDependencyType.ORCHESTRATION_CONFIG;
    }

    @Override
    public ReleaseAssetType releaseAssetType() {
        return ReleaseAssetType.ORCHESTRATION_CONFIG;
    }

    /** 只有完整通过 frozen payload 校验的 Workflow 才允许被依赖。 */
    @Override
    public boolean isEnabled(ResolvedReleasedAsset resolvedAsset) {
        try {
            payloadAdapter.requirePayload(resolvedAsset);
            return true;
        } catch (WorkflowReleasePayloadValidationException exception) {
            throw dependencyNotReady(resolvedAsset, exception);
        }
    }

    private AssetDependencyResolutionException dependencyNotReady(
            ResolvedReleasedAsset resolvedAsset, WorkflowReleasePayloadValidationException cause) {
        return new AssetDependencyResolutionException(
                AssetDependencyErrorCode.DEPENDENCY_EXPANSION_FAILED,
                AssetDependencyType.ORCHESTRATION_CONFIG,
                resolvedAsset == null ? null : resolvedAsset.getAssetKey(),
                resolvedAsset == null ? null : resolvedAsset.getRequestedEnvironment(),
                ERROR_WORKFLOW_DEPENDENCY_NOT_READY,
                cause);
    }

    /** 从 validated compiledPlan 提取去重排序后的 Skill 直接依赖。 */
    @Override
    public List<AssetDependencyReference> dependencies(ResolvedReleasedAsset resolvedAsset) {
        try {
            WorkflowReleasePayload payload = payloadAdapter.requirePayload(resolvedAsset);
            return payloadAdapter.skillCodes(payload).stream()
                    .map(skillCode -> new AssetDependencyReference()
                            .setAssetType(AssetDependencyType.SKILL)
                            .setAssetKey(skillCode))
                    .toList();
        } catch (WorkflowReleasePayloadValidationException exception) {
            throw dependencyNotReady(resolvedAsset, exception);
        }
    }
}
