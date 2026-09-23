package dev.a2flow.management.release;

import java.util.List;
import java.util.Map;

import jakarta.annotation.Resource;

import org.springframework.stereotype.Component;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.lifecycle.SkillFactoryComponentRegistryService;
import dev.a2flow.management.model.SkillFactoryComponentAsset;
import dev.a2flow.management.release.ReleaseModels.AssetSnapshot;
import dev.a2flow.management.release.ReleaseModels.GateResult;
import dev.a2flow.management.release.ReleaseModels.PublishResult;
import dev.a2flow.management.release.ReleaseModels.ReleasePublishContext;

import lombok.extern.slf4j.Slf4j;

/**
 * 组件中心发布适配器。
 *
 * <p>上游由共享发布控制面传入组件资产 ID 和目标环境，本类从组件注册 Repository 边界读取当前组件，
 * 校验启用状态与协议版本，并把共享控制面冻结的快照登记为环境生效版本。组件 Registry 就是
 * 数据库/Repository 持久化边界，不依赖额外外部 Registry；历史重发只切换公共 ONLINE 版本，
 * 不覆盖 `skill_component_registry` 当前可编辑内容。本类不负责前端 bundle 上传、adviser 运行态加载
 * 或跨系统发布。
 */
@Component
@Slf4j
public class ComponentReleaseAssetAdapter extends AbstractReleaseAssetAdapter {

    private static final String DIFF_RESOURCE_PATH = "component.json";
    private static final String SUMMARY_COMPONENT_NAME = "componentName";
    private static final String SUMMARY_COMPONENT_NAME_CN = "componentNameCn";
    private static final String SUMMARY_ASSET_TYPE = "assetType";
    private static final String SUMMARY_PROTOCOL_VERSION = "protocolVersion";
    private static final String SUMMARY_DSL_TYPE = "dslType";
    private static final String SUMMARY_ASSET_KEY = "assetKey";
    private static final String SUMMARY_ENVIRONMENT = "environment";
    private static final String SUMMARY_SOURCE_TYPE = "sourceType";
    private static final String SUMMARY_SOURCE_VERSION = "sourceVersion";
    private static final String SUMMARY_DIGEST = "digest";
    private static final String GATE_COMPONENT_ENABLED = "COMPONENT_ENABLED";
    private static final String GATE_COMPONENT_PROTOCOL_VERSION = "COMPONENT_PROTOCOL_VERSION";
    private static final String LABEL_COMPONENT_ENABLED = "组件已启用";
    private static final String LABEL_PROTOCOL_VERSION = "协议版本";
    private static final String MESSAGE_COMPONENT_ENABLED = "组件可被引用";
    private static final String MESSAGE_COMPONENT_DISABLED = "组件未启用";
    private static final String MESSAGE_PROTOCOL_READY = "协议版本已配置";
    private static final String MESSAGE_PROTOCOL_MISSING = "协议版本为空";
    private static final String MESSAGE_COMPONENT_PUBLISHED = "组件 Registry 数据库发布完成";
    private static final String ERROR_SNAPSHOT_REQUIRED = "组件发布快照为空";
    private static final String ERROR_SNAPSHOT_INVALID = "组件发布快照无法解析";
    private static final String A2UI_APPLICATION_ASSET_TYPE = "A2UI_APPLICATION";
    private static final String ERROR_A2UI_APPLICATION_WRONG_ADAPTER = "A2UI_APPLICATION 必须使用独立发布适配器";

    @Resource
    private SkillFactoryComponentRegistryService componentRegistryService;

    @Override
    public ReleaseAssetType assetType() {
        return ReleaseAssetType.COMPONENT;
    }

    /** 组件运行态支持按可信 userId 的比例和白名单灰度。 */
    @Override
    public GrayReleasePolicy grayReleasePolicy() {
        return GrayReleasePolicy.PERCENTAGE_AND_WHITELIST;
    }

    /** 组件结构化快照统一映射成 component.json 参与共享行级 Diff。 */
    @Override
    protected String diffResourcePath() {
        return DIFF_RESOURCE_PATH;
    }

    @Override
    public AssetSnapshot currentSnapshot(String assetKey, Map<String, String> params) {
        SkillFactoryComponentAsset asset = componentRegistryService.detail(assetKey);
        rejectApplicationAsset(asset);
        return snapshot(assetKey, asset, summaryEntry(
                SUMMARY_COMPONENT_NAME, asset.getComponentName(),
                SUMMARY_COMPONENT_NAME_CN, asset.getComponentNameCn(),
                SUMMARY_ASSET_TYPE, asset.getAssetType(),
                SUMMARY_PROTOCOL_VERSION, asset.getProtocolVersion(),
                SUMMARY_DSL_TYPE, asset.getDslType()), null, asset.getBundleUrl());
    }

    @Override
    public List<GateResult> evaluateGates(String assetKey, ReleaseEnvironment environment,
            AssetSnapshot snapshot, Map<String, String> params) {
        SkillFactoryComponentAsset asset = componentFromSnapshot(snapshot);
        boolean enabled = Boolean.TRUE.equals(asset.getEnabled());
        boolean protocolReady = asset.getProtocolVersion() != null && asset.getProtocolVersion() > 0;
        return List.of(
                gate(GATE_COMPONENT_ENABLED, LABEL_COMPONENT_ENABLED, enabled, true,
                        enabled ? MESSAGE_COMPONENT_ENABLED : MESSAGE_COMPONENT_DISABLED),
                gate(GATE_COMPONENT_PROTOCOL_VERSION, LABEL_PROTOCOL_VERSION, protocolReady, true,
                        protocolReady ? MESSAGE_PROTOCOL_READY : MESSAGE_PROTOCOL_MISSING));
    }

    @Override
    public void restore(String userName, String assetKey, AssetSnapshot snapshot, Map<String, String> params) {
        SkillFactoryComponentAsset asset = componentFromSnapshot(snapshot);
        log.info("组件从正式版本创建变更前恢复Registry内容, assetKey:{}, componentName:{}, operator:{}",
                assetKey, asset.getComponentName(), userName);
        componentRegistryService.restoreReleasedSnapshot(userName, assetKey, asset);
    }

    /**
     * 发布共享控制面选中的不可变组件快照，并把成功结果交给共享服务保存环境生效版本。
     */
    @Override
    public PublishResult deploy(ReleasePublishContext context) {
        AssetSnapshot snapshot = context.getSnapshot();
        SkillFactoryComponentAsset asset = componentFromSnapshot(snapshot);
        log.info("组件Registry数据库版本生效完成, assetKey:{}, componentName:{}, environment:{}, "
                        + "sourceType:{}, sourceVersion:{}, requestId:{}, operator:{}",
                context.getAssetKey(), asset.getComponentName(), context.getEnvironment(), context.getSourceType(),
                context.getSourceVersion(), context.getRequestId(), context.getUserName());
        return succeeded(MESSAGE_COMPONENT_PUBLISHED, summaryEntry(
                SUMMARY_ASSET_KEY, context.getAssetKey(),
                SUMMARY_COMPONENT_NAME, asset.getComponentName(),
                SUMMARY_ENVIRONMENT, context.getEnvironment().name(),
                SUMMARY_SOURCE_TYPE, context.getSourceType(),
                SUMMARY_SOURCE_VERSION, context.getSourceVersion(),
                SUMMARY_DIGEST, snapshot.getDigest()));
    }

    /** 从公共版本快照解析组件，禁止历史重发回读当前 Registry 草稿。 */
    private SkillFactoryComponentAsset componentFromSnapshot(AssetSnapshot snapshot) {
        if (snapshot == null || snapshot.getPayloadJson() == null || snapshot.getPayloadJson().isEmpty()) {
            throw new IllegalStateException(ERROR_SNAPSHOT_REQUIRED);
        }
        SkillFactoryComponentAsset asset = JsonSupport.fromJSON(
                snapshot.getPayloadJson(), SkillFactoryComponentAsset.class);
        if (asset == null) {
            throw new IllegalStateException(ERROR_SNAPSHOT_INVALID);
        }
        rejectApplicationAsset(asset);
        return asset;
    }

    private void rejectApplicationAsset(SkillFactoryComponentAsset asset) {
        if (asset != null && A2UI_APPLICATION_ASSET_TYPE.equals(asset.getAssetType())) {
            throw new IllegalStateException(ERROR_A2UI_APPLICATION_WRONG_ADAPTER);
        }
    }
}
