package dev.a2flow.management.release;

import java.util.List;
import java.util.Map;

import dev.a2flow.management.release.ReleaseModels.AssetSnapshot;
import dev.a2flow.management.release.ReleaseModels.GateResult;
import dev.a2flow.management.release.ReleaseModels.PublishResult;
import dev.a2flow.management.release.ReleaseModels.ReleaseArtifact;
import dev.a2flow.management.release.ReleaseModels.ReleasePublishContext;
import dev.a2flow.management.release.ReleaseModels.ReleaseRelationSnapshot;
import dev.a2flow.management.release.ReleaseModels.ReleaseValidationRequirement;
import dev.a2flow.management.release.diff.ReleaseDiffDocument;
import dev.a2flow.management.release.diff.ReleaseDiffQuery;

/**
 * SkillFactory 内部资产接入共享发布控制面的领域适配器。
 *
 * <p>共享 Service 只依赖本接口，不直接访问 Skill workspace、组件注册表或能力草稿。实现类必须提供
 * 稳定摘要、领域门禁、Diff、历史内容恢复和真实发布结果；未接通的发布器必须返回明确的
 * PLATFORM_PENDING/FAILED，不能伪造成功。
 */
public interface ReleaseAssetAdapter {

    /** 返回该适配器负责的资产类型。 */
    ReleaseAssetType assetType();

    /** 从当前领域事实源读取快照。 */
    AssetSnapshot currentSnapshot(String assetKey, Map<String, String> params);

    /**
     * 使用服务端可信操作上下文读取当前领域事实快照。
     *
     * <p>默认委托既有入口，确保无需身份上下文的 Adapter 保持原行为；需要按当前操作人校验的领域必须
     * 显式覆写本方法，禁止从 params、变更创建人或默认系统身份推断 operator。
     */
    default AssetSnapshot currentSnapshot(ReleaseOperationContext operationContext,
            String assetKey, Map<String, String> params) {
        return currentSnapshot(assetKey, params);
    }

    /**
     * 使用服务端可信操作上下文读取真实发布所需当前快照。
     *
     * <p>默认复用当前快照以保持既有 Adapter 行为；需要在读取发布源前强校验 PUBLISH 的领域必须覆写。
     */
    default AssetSnapshot currentPublishSnapshot(ReleaseOperationContext operationContext,
            String assetKey, Map<String, String> params) {
        return currentSnapshot(operationContext, assetKey, params);
    }

    /**
     * 判断当前领域快照是否天然代表新资产的首个可编辑变更。
     *
     * <p>默认返回 false，表示该领域必须显式调用 RELEASE_CHANGE_CREATE。只有领域事实源在实体创建后
     * 已经形成可编辑草稿时才应覆写为 true；共享状态机还会额外校验不存在历史正式版本，避免线上封板后
     * 绕过新建变更流程。
     */
    default boolean isInitialEditableChange(AssetSnapshot snapshot) {
        return false;
    }

    /**
     * 声明该资产是否接入共享灰度发布。
     *
     * <p>默认禁用，确保新增资产不会因为遗漏领域评审而自动暴露灰度入口。支持的领域必须显式覆写。
     */
    default GrayReleasePolicy grayReleasePolicy() {
        return GrayReleasePolicy.DISABLED;
    }

    /**
     * 在创建不可变 Build 前冻结领域发布快照。
     *
     * <p>默认资产直接使用当前快照。Skill 可在这里把公共 dependency report 写入发布快照并生成
     * 新 sourceDigest；该方法不得修改当前领域草稿。
     */
    default AssetSnapshot freezeBuildSnapshot(
            String assetKey, AssetSnapshot current, Map<String, String> params) {
        return current;
    }

    /**
     * 使用服务端可信操作上下文冻结 Build 快照。
     *
     * <p>默认委托既有入口；需要身份校验的领域必须显式覆写，并且只能信任 operationContext。
     */
    default AssetSnapshot freezeBuildSnapshot(ReleaseOperationContext operationContext,
            String assetKey, AssetSnapshot current, Map<String, String> params) {
        return freezeBuildSnapshot(assetKey, current, params);
    }

    /**
     * 按服务端可信目标环境冻结 Build 快照。
     *
     * <p>默认委托既有可信上下文入口，避免影响不依赖环境的资产；需要冻结同环境依赖的 Adapter
     * 必须覆写本方法，禁止从 params 或当前 ONLINE 指针猜测目标环境。
     */
    default AssetSnapshot freezeBuildSnapshot(ReleaseOperationContext operationContext,
            String assetKey, ReleaseEnvironment environment, AssetSnapshot current,
            Map<String, String> params) {
        return freezeBuildSnapshot(operationContext, assetKey, current, params);
    }

    /** 从已验证的冻结 Build 派生线上快照；不得修改原 Build 或读取可变草稿，默认沿用原快照。 */
    default AssetSnapshot prepareOnlineSnapshot(String assetKey, AssetSnapshot verifiedBuild) {
        return verifiedBuild;
    }

    /**
     * 冻结 Build 恢复所需的完整关系快照。
     *
     * <p>默认返回 null，表示该资产没有关系恢复契约。Skill 必须显式覆写；共享发布状态只负责持久化，
     * 不读取领域关系表或猜测旧 Build 是否完整。
     */
    default ReleaseRelationSnapshot freezeBuildRelationSnapshot(
            String assetKey, AssetSnapshot snapshot, Map<String, String> params) {
        return null;
    }

    /**
     * 计算当前快照和目标快照之间的统一发布 Diff。
     *
     * <p>实现必须返回强类型 ReleaseDiffDocument。列表查询和指定 entryPath 的详情查询共用本入口，
     * 禁止继续返回领域自定义 Map 或原始 payload JSON。
     */
    ReleaseDiffDocument diff(AssetSnapshot current, AssetSnapshot target, ReleaseDiffQuery query);

    /** 计算指定环境的领域发布门禁。 */
    List<GateResult> evaluateGates(String assetKey, ReleaseEnvironment environment,
            AssetSnapshot snapshot, Map<String, String> params);

    /**
     * 使用服务端可信操作上下文计算快照门禁。
     *
     * <p>默认委托既有入口，保持现有 Adapter 行为不变。
     */
    default List<GateResult> evaluateGates(ReleaseOperationContext operationContext,
            String assetKey, ReleaseEnvironment environment, AssetSnapshot snapshot,
            Map<String, String> params) {
        return evaluateGates(assetKey, environment, snapshot, params);
    }

    /**
     * 计算带结构化产物的领域发布门禁。
     *
     * <p>没有二进制产物的领域沿用快照门禁；Skill 等产物型领域可覆写本方法校验 ZIP 摘要和对象身份。
     */
    default List<GateResult> evaluateGates(String assetKey, ReleaseEnvironment environment,
            AssetSnapshot snapshot, ReleaseArtifact artifact, Map<String, String> params) {
        return evaluateGates(assetKey, environment, snapshot, params);
    }

    /**
     * 使用服务端可信操作上下文计算带结构化产物的领域门禁。
     *
     * <p>默认委托既有带产物入口，避免改变现有 Adapter 的门禁分派语义。
     */
    default List<GateResult> evaluateGates(ReleaseOperationContext operationContext,
            String assetKey, ReleaseEnvironment environment, AssetSnapshot snapshot,
            ReleaseArtifact artifact, Map<String, String> params) {
        return evaluateGates(assetKey, environment, snapshot, artifact, params);
    }

    /**
     * 计算编辑期只读展示的门禁预览。
     *
     * <p>默认复用既有门禁以保持非 Workflow Adapter 行为；需要区分编辑预览和真实发布权限的领域必须
     * 覆写该入口，并且不得创建 Build、Version 或环境指针。
     */
    default List<GateResult> evaluatePreviewGates(ReleaseOperationContext operationContext,
            String assetKey, ReleaseEnvironment environment, AssetSnapshot snapshot,
            ReleaseArtifact artifact, Map<String, String> params) {
        return evaluateGates(operationContext, assetKey, environment, snapshot, artifact, params);
    }

    /**
     * 声明指定环境需要的摘要绑定准出证据。
     *
     * <p>默认没有额外要求。共享控制面负责读取和校验证据，领域 Adapter 只声明编码和展示名称，
     * 避免 Skill、组件和业务能力各自复制证据状态机。
     */
    default List<ReleaseValidationRequirement> validationRequirements(ReleaseEnvironment environment) {
        return List.of();
    }

    /**
     * 根据不可变资产快照声明准出证据；默认保持现有资产的环境级要求。
     *
     * <p>只有证据维度取决于 payload 的领域（例如业务能力支持端）才需要覆写。实现不得从当前草稿、
     * 请求参数或运行态身份推断要求，避免历史版本重发被当前内容污染。
     */
    default List<ReleaseValidationRequirement> validationRequirements(
            ReleaseEnvironment environment, AssetSnapshot snapshot) {
        return validationRequirements(environment);
    }

    /** 把历史版本内容恢复到领域可编辑事实源。 */
    void restore(String userName, String assetKey, AssetSnapshot snapshot, Map<String, String> params);

    /** 使用服务端可信操作上下文恢复历史内容，默认兼容既有 Adapter。 */
    default void restore(ReleaseOperationContext operationContext,
            String assetKey, AssetSnapshot snapshot, Map<String, String> params) {
        restore(operationContext.getOperator(), assetKey, snapshot, params);
    }

    /**
     * 声明领域发布器能否安全恢复同 requestId 的 PUBLISHING 流水。
     *
     * <p>默认拒绝，避免重复调用具有外部副作用的发布器。只有发布动作由冻结快照确定、重复执行不会
     * 产生额外外部状态的领域才能显式返回 true；共享控制面仍复用原 Build 和 Deployment。
     */
    default boolean supportsPublishingRecovery() {
        return false;
    }

    /**
     * 发布共享控制面已经冻结的来源快照并返回真实结果。
     *
     * <p>历史重发必须使用上下文中的历史版本和快照，禁止回读当前草稿替代发布内容。
     */
    PublishResult deploy(ReleasePublishContext context);

    /** 使用服务端可信操作上下文发布，默认兼容既有 Adapter。 */
    default PublishResult deploy(
            ReleaseOperationContext operationContext, ReleasePublishContext context) {
        return deploy(context);
    }
}
