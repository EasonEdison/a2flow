package dev.a2flow.management.release;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * 发布控制面共享模型集合。
 *
 * <p>这些模型只承载 Change、Build、Version、Deployment 和环境指针等治理状态；领域正文以
 * {@link AssetSnapshot} 的 JSON 快照保存，共享层不会解析 Skill 文件、组件 schema 或能力草稿字段。
 */
public final class ReleaseModels {

    private ReleaseModels() {
    }

    /** 当前领域事实源的不可变读取快照。 */
    @Data
    @Accessors(chain = true)
    public static class AssetSnapshot {
        private String assetType;
        private String assetKey;
        private String digest;
        private String artifactRef;
        /** A2UI immutable manifest 的存储策略，例如首版 INLINE_V1。 */
        private String storagePolicy;
        private Map<String, Object> summary = new LinkedHashMap<>();
        private String payloadJson;
        /** payloadJson 按 UTF-8 编码后的字节数，用于 immutable manifest readback 校验。 */
        private Long payloadBytes;
    }

    /** 某资产当前 ONLINE 指针对应的唯一正式版本快照。 */
    @Data
    @Accessors(chain = true)
    public static class PublishedAssetSnapshot {
        private String assetKey;
        private Integer version;
        private String versionId;
        /** 当前发布产物的原始 Build 身份，用于校验同一 Build 晋升正式版本。 */
        private String sourceBuildId;
        /** 产物构建时的源内容摘要；与编译产物摘要分开用于管理页比较。 */
        private String inputDigest;
        private AssetSnapshot snapshot;
    }

    /**
     * 一次构建或正式版本对应的结构化产物。
     *
     * <p>对象存储 key 是发布读取的规范身份，URL 只用于展示或临时下载。没有二进制产物的组件和能力
     * 保持该对象为空，不需要创建领域专属版本表。
     */
    @Data
    @Accessors(chain = true)
    public static class ReleaseArtifact {
        private String artifactType;
        private String storageProvider;
        private String bucket;
        private String objectKey;
        private String packageUrl;
        private String packageDigest;
        private String fileTreeDigest;
        private Long size;
        private String buildSummary;
    }

    /** 单项发布门禁结果。 */
    @Data
    @Accessors(chain = true)
    public static class GateResult {
        private String code;
        private String label;
        private String status;
        private Boolean required;
        private String message;
        private String errorCode;
        private String causeCode;
        private String fieldPath;
        private List<String> dependencyPath = new ArrayList<>();
        private Integer dependencyDetailsContractVersion;
        private List<DependencyGateDetail> dependencyDetails = new ArrayList<>();
    }

    /**
     * 递归依赖门禁中的单条已解析发布事实或失败事实。
     *
     * <p>resolved 条目只携带不可变 Build/Version 身份与摘要；failure 条目只携带稳定错误定位。
     * 两者都保留从根资产到当前资产的完整路径，不承载冻结 payload、内部异常消息或堆栈。
     */
    @Data
    @Accessors(chain = true)
    public static class DependencyGateDetail {
        private String status;
        private String assetType;
        private String assetKey;
        private String requestedEnvironment;
        private String resolvedEnvironment;
        private String sourceType;
        private String sourceId;
        private Integer version;
        private String digest;
        private Boolean candidate;
        private String routeReason;
        private String errorCode;
        private String causeType;
        private String causeCode;
        private String fieldPath;
        private String message;
        private List<String> dependencyPath = new ArrayList<>();
    }

    /**
     * 领域声明的摘要绑定发布准出要求。
     *
     * <p>expectedRuleVersion 是可选的当前内容规则约束；未声明时共享控制面保持原有证据判断。
     * 历史正式版本重发使用版本冻结证据，不应用该当前规则约束。
     */
    @Data
    @Accessors(chain = true)
    public static class ReleaseValidationRequirement {
        private String code;
        private String label;
        private String expectedRuleVersion;
    }

    /**
     * Skill 综合准出中的单项检查结果。
     *
     * <p>后端确定性检查和模型语义检查使用同一结构，但通过 source 区分事实来源。findings 只保存
     * 结构化定位和修复提示；敏感凭证检查不得把命中的真实值写入这里。
     */
    @Data
    @Accessors(chain = true)
    public static class ReleaseReadinessCheck {
        private String code;
        private String status;
        private Boolean required;
        private String source;
        private String summary;
        private List<Map<String, Object>> findings = new ArrayList<>();
    }

    /**
     * Skill 综合准出中的人工豁免审计。
     *
     * <p>当前只允许豁免预发调试记录缺失。可信 messageId、runId、operator 和时间由后端运行上下文
     * 写入，模型只能提交用户明确表达的原因。
     */
    @Data
    @Accessors(chain = true)
    public static class ReleaseValidationWaiver {
        private String checkCode;
        private String reason;
        private String messageId;
        private String runId;
        private String operator;
        private Long waivedAt;
    }

    /**
     * 只读 Skill 综合准出巡检快照。
     *
     * <p>该对象绑定当前 workspace 摘要，向 mounted Skill 提供确定性事实和最小同行元数据；
     * 它不保存模型语义结论，不修改文件，也不触发发布。
     */
    @Data
    @Accessors(chain = true)
    public static class ReleaseReadinessInspection {
        private String skillCode;
        private String workspaceDigest;
        private String ruleVersion;
        private Long inspectedAt;
        private List<String> workspaceFiles = new ArrayList<>();
        private List<String> pythonFiles = new ArrayList<>();
        private Map<String, Object> currentSkill = new LinkedHashMap<>();
        private List<Map<String, Object>> specialists = new ArrayList<>();
        private List<Map<String, Object>> peerSkills = new ArrayList<>();
        private List<Map<String, Object>> debugRuns = new ArrayList<>();
        private List<ReleaseReadinessCheck> deterministicChecks = new ArrayList<>();
    }

    /**
     * 模型或自动检查器写入的发布准出证据。
     *
     * <p>证据必须绑定领域事实源摘要。共享发布控制面只信任与待发布摘要一致且状态为 PASSED 的证据；
     * 文件或表单内容变化后，旧证据会因摘要不一致自动过期。Tool 是否暴露给某个 Agent/Skill 由运行配置
     * 控制，本模型不保存或校验调用来源 Skill 身份。
     */
    @Data
    @Accessors(chain = true)
    public static class ReleaseValidationEvidence {
        private String checkCode;
        private String status;
        private String boundDigest;
        private String ruleVersion;
        private String checkRunId;
        private String summary;
        private List<Map<String, Object>> findings = new ArrayList<>();
        private List<ReleaseReadinessCheck> checks = new ArrayList<>();
        private List<ReleaseValidationWaiver> waivers = new ArrayList<>();
        private String operator;
        private Long checkedAt;
    }

    /** 可编辑变更。一个资产同时最多只有一个 ACTIVE 变更。 */
    @Data
    @Accessors(chain = true)
    public static class ReleaseChange {
        private String changeId;
        private String requestId;
        private String changeName;
        private Integer targetVersion;
        private Integer baseVersion;
        private String status;
        private String sourceDigest;
        private String operator;
        private Long createTime;
        private Long updateTime;
    }

    /**
     * Build 冻结的单条 Skill 通用实体关系。
     *
     * <p>这里只保存恢复所需的业务字段，不保存旧关系主键、来源版本、操作人和时间戳；恢复时由当前
     * Skill 身份和当前数字版本重新生成这些字段，避免把历史数据库身份写回编辑态。
     */
    @Data
    @Accessors(chain = true)
    public static class ReleaseRelationEntry {
        private String relationType;
        private String targetEntityType;
        private String targetEntityId;
        private String targetEntityCode;
        private String targetVersion;
        private String relationMode;
        private String snapshotJson;
        private Integer sortNo;
        private String attribute;
    }

    /** Skill Build 的完整通用实体关系恢复快照。 */
    @Data
    @Accessors(chain = true)
    public static class ReleaseRelationSnapshot {
        public static final int CURRENT_CONTRACT_VERSION = 1;

        private Integer contractVersion;
        private Boolean complete;
        private List<ReleaseRelationEntry> relations = new ArrayList<>();
    }

    /** 一次不可变预发构建。 */
    @Data
    @Accessors(chain = true)
    public static class ReleaseBuild {
        private String buildId;
        private String changeId;
        private Integer targetVersion;
        private Integer buildNumber;
        private String inputDigest;
        private String sourceDigest;
        private String status;
        private AssetSnapshot snapshot;
        private ReleaseArtifact artifact;
        /** Skill 使用的完整关系恢复快照；非 Skill 资产和旧 Build 允许为空但不可用于 Skill 重置。 */
        private ReleaseRelationSnapshot relationSnapshot;
        private List<GateResult> gates = new ArrayList<>();
        private String operator;
        private Long createTime;
    }

    /** 已封板的不可变正式版本。 */
    @Data
    @Accessors(chain = true)
    public static class ReleaseVersion {
        private Integer version;
        private String versionId;
        private String sourceBuildId;
        private String inputDigest;
        private String sourceDigest;
        private AssetSnapshot snapshot;
        private ReleaseArtifact artifact;
        private Map<String, ReleaseValidationEvidence> validations = new LinkedHashMap<>();
        private String operator;
        private Long createTime;
    }

    /** 一次环境部署流水。 */
    @Data
    @Accessors(chain = true)
    public static class ReleaseDeployment {
        private String deploymentId;
        private String requestId;
        private String environment;
        private String sourceType;
        private String sourceId;
        private Integer sourceVersion;
        private String sourceDigest;
        private String status;
        private String currentStage;
        private Boolean retryable;
        private String errorCode;
        private String message;
        private Boolean forced;
        private String forceReason;

        private String publishMode;
        private ReleaseArtifact artifact;
        private Map<String, Object> domainResult = new LinkedHashMap<>();
        private List<GateResult> gates = new ArrayList<>();
        private String operator;
        private Long createTime;
        private Long updateTime;
    }

    /** 某环境当前实际生效或最后成功的发布指针。 */
    @Data
    @Accessors(chain = true)
    public static class EnvironmentState {
        private String environment;
        private String sourceType;
        private String sourceId;
        private Integer version;
        private String digest;
        private String deploymentId;
        private Long updateTime;
        private ReleasePointer candidate;
        private GrayReleaseRule grayRule;
        private String grayStatus;
    }

    /** 灰度环境中的不可变候选指针。 */
    @Data
    @Accessors(chain = true)
    public static class ReleasePointer {
        private String sourceType;
        private String sourceId;
        private Integer version;
        private String digest;
        private String deploymentId;
        private Long updateTime;
    }

    /** userId 尾号比例与白名单组合灰度规则。 */
    @Data
    @Accessors(chain = true)
    public static class GrayReleaseRule {
        private Integer percentage;
        @com.fasterxml.jackson.databind.annotation.JsonSerialize(contentUsing = com.fasterxml.jackson.databind.ser.std.ToStringSerializer.class)
        private List<Long> userIdWhitelist = new ArrayList<>();
    }

    /**
     * 领域 Adapter 一次发布需要的完整上下文。
     *
     * <p>共享控制面在调用 Adapter 前明确冻结来源类型、来源版本和快照，避免领域实现通过页面参数
     * 猜测当前发布还是历史重发。Adapter 只能发布这里携带的不可变快照，不得重新读取当前草稿
     * 作为发布载荷。
     */
    @Data
    @Accessors(chain = true)
    public static class ReleasePublishContext {
        private String userName;
        private String assetKey;
        private ReleaseEnvironment environment;
        private String sourceType;
        private String sourceId;
        private Integer sourceVersion;
        private String requestId;
        private AssetSnapshot snapshot;
        private ReleaseArtifact artifact;
        private ReleaseDeployment previousDeployment;
        private Map<String, String> params = new LinkedHashMap<>();
    }

    /** Repository 按资产保存的完整发布聚合。 */
    @Data
    @Accessors(chain = true)
    public static class AssetReleaseState {
        private String assetType;
        private String assetKey;
        private Integer revision = 0;
        private ReleaseChange activeChange;
        private List<ReleaseBuild> builds = new ArrayList<>();
        private List<ReleaseVersion> versions = new ArrayList<>();
        private List<ReleaseDeployment> deployments = new ArrayList<>();
        private Map<String, EnvironmentState> environments = new LinkedHashMap<>();
        private Map<String, ReleaseValidationEvidence> validations = new LinkedHashMap<>();
    }

    /** Adapter 执行真实领域发布后的结果。 */
    @Data
    @Accessors(chain = true)
    public static class PublishResult {
        private String status;
        private String currentStage;
        private Boolean retryable;
        private String errorCode;
        private String message;
        private ReleaseArtifact artifact;
        private Map<String, Object> data = new LinkedHashMap<>();
    }

    /**
     * 一次共享发布状态变更的最小响应。
     *
     * <p>上游是 Change 或 Deployment 的持久化结果，下游是管理接口与共享发布页。
     * 该模型只回答本次操作身份、状态和可读消息，不承载 Overview、领域快照或历史流水。
     */
    @Data
    @Accessors(chain = true)
    public static class ReleaseOperationResult {
        private String operationId;
        private String status;
        private String message;
    }

    /**
     * 资产列表需要的轻量公共发布事实投影。
     *
     * <p>status 仅从共享 Change/Build/Version/环境指针推导，environmentPointers 仅复制真实存在的
     * PRT/ONLINE 指针。该模型不承载领域草稿，也不形成独立发布状态机。
     */
    @Data
    @Accessors(chain = true)
    public static class AssetReleaseProjection {
        private String status;
        private Map<String, EnvironmentState> environmentPointers = new LinkedHashMap<>();
    }

    /** 发布详情页一次查询需要的完整视图。 */
    @Data
    @Accessors(chain = true)
    public static class ReleaseOverview {

        private Boolean grayReleaseSupported;
        private String grayReleasePolicy;
        private Integer nextVersion;
        private AssetSnapshot currentSnapshot;
        private ReleaseChange activeChange;
        private List<ReleaseBuild> builds = new ArrayList<>();
        private List<ReleaseVersion> versions = new ArrayList<>();
        private List<ReleaseDeployment> deployments = new ArrayList<>();

        private Map<String, EnvironmentState> environments = new LinkedHashMap<>();
        private List<GateResult> gates = new ArrayList<>();
        // 分环境返回检查结果，避免预发通过掩盖线上失败。
        private Map<String, List<GateResult>> environmentGates = new LinkedHashMap<>();
        private List<String> allowedActions = new ArrayList<>();
        private List<String> blockedReasons = new ArrayList<>();
    }
}
