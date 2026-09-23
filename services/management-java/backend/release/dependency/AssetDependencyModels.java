package dev.a2flow.management.release.dependency;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import dev.a2flow.management.release.GrayRouteReason;
import dev.a2flow.management.release.ReleaseEnvironment;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * 环境感知资产依赖的共享数据契约。
 *
 * <p>这些模型只承载稳定身份、不可变发布来源、依赖路径和准出结果。领域 Adapter 可以读取
 * payloadJson 并声明下游依赖，但共享模型不解释组件模板、能力 Host 或未来编排字段。
 */
public final class AssetDependencyModels {

    private AssetDependencyModels() {
    }

    /** 一个可由环境解析器解析的稳定依赖资产身份。 */
    @Data
    @Accessors(chain = true)
    public static class AssetDependencyReference {
        private AssetDependencyType assetType;
        private String assetKey;
    }

    /**
     * 运行时解析资产时由可信引擎注入的上下文。
     *
     * <p>userId 不从模型参数、Tool 参数或领域 payload 读取；缺失时灰度规则明确选择 stable。
     */
    @Data
    @Accessors(chain = true)
    public static class AssetResolutionContext {
        private ReleaseEnvironment requestedEnvironment;
        @com.fasterxml.jackson.databind.annotation.JsonSerialize(using = com.fasterxml.jackson.databind.ser.std.ToStringSerializer.class)
        private Long userId;
    }

    /** 依赖报告中的一段完整路径节点；root 节点允许使用 SKILL 等非依赖类型名称。 */
    @Data
    @Accessors(chain = true)
    public static class DependencyPathNode {
        private String assetType;
        private String assetKey;
    }

    /** 稳定资产身份在可信请求环境下命中的不可变发布源。 */
    @Data
    @Accessors(chain = true)
    public static class ResolvedReleasedAsset {
        private AssetDependencyType assetType;
        private String assetKey;
        private List<DependencyPathNode> path = new ArrayList<>();
        private ReleaseEnvironment requestedEnvironment;
        private ReleaseEnvironment resolvedEnvironment;
        private ReleasedAssetSourceType sourceType;
        private String sourceId;
        private Integer version;
        private String digest;
        private String artifactRef;
        private String payloadJson;
        private Map<String, Object> summary = new LinkedHashMap<>();
        private Boolean candidate;
        private GrayRouteReason routeReason;
    }

    /** 一次完整依赖图校验请求。 */
    @Data
    @Accessors(chain = true)
    public static class DependencyValidationRequest {
        private String rootAssetType;
        private String rootAssetKey;
        private ReleaseEnvironment requestedEnvironment;
        private List<AssetDependencyReference> dependencies = new ArrayList<>();
    }

    /** 一个依赖节点未能通过解析或图结构校验时的稳定失败结果。 */
    @Data
    @Accessors(chain = true)
    public static class DependencyReleaseFailure {
        private AssetDependencyErrorCode errorCode;
        private String message;
        private String causeType;
        private String causeCode;
        private String fieldPath;
        private List<DependencyPathNode> path = new ArrayList<>();
    }

    /**
     * 一次依赖准出的完整报告。
     *
     * <p>resolvedAssets 与 failures 均按稳定资产类型、assetKey 和深度优先顺序确定性输出，供发布
     * 门禁、页面展示和审计复用。
     */
    @Data
    @Accessors(chain = true)
    public static class DependencyReleaseReport {
        private Boolean passed;
        private String rootAssetType;
        private String rootAssetKey;
        private ReleaseEnvironment requestedEnvironment;
        private List<ResolvedReleasedAsset> resolvedAssets = new ArrayList<>();
        private List<DependencyReleaseFailure> failures = new ArrayList<>();
    }
}
