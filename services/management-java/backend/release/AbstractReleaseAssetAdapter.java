package dev.a2flow.management.release;

import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import jakarta.annotation.Resource;

import org.apache.commons.lang3.StringUtils;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.release.ReleaseModels.AssetSnapshot;
import dev.a2flow.management.release.ReleaseModels.GateResult;
import dev.a2flow.management.release.ReleaseModels.PublishResult;
import dev.a2flow.management.release.diff.ReleaseDiffContentType;
import dev.a2flow.management.release.diff.ReleaseDiffDocument;
import dev.a2flow.management.release.diff.ReleaseDiffEngine;
import dev.a2flow.management.release.diff.ReleaseDiffQuery;
import dev.a2flow.management.release.diff.ReleaseDiffResource;

/**
 * 发布资产 Adapter 的公共辅助基类。
 *
 * <p>这里只提供稳定 JSON 摘要、通用 JSON Diff 和门禁构造方法，不包含任何资产类型分支或发布决策。
 */
public abstract class AbstractReleaseAssetAdapter implements ReleaseAssetAdapter {

    private static final String LABEL_CURRENT_CONTENT = "当前内容";
    private static final String LABEL_TARGET_VERSION = "目标版本";
    private static final String DEFAULT_JSON_DIFF_PATH = "asset.json";

    protected static final String GATE_PASSED = "PASSED";
    protected static final String GATE_FAILED = "FAILED";
    protected static final String DEPLOYMENT_SUCCEEDED = "SUCCEEDED";
    protected static final String DEPLOYMENT_PLATFORM_PENDING = "PLATFORM_PENDING";
    protected static final String DEPLOYMENT_FAILED = "FAILED";

    @Resource
    private ReleaseDiffEngine releaseDiffEngine;

    /** 把领域对象规范化为快照。 */
    protected AssetSnapshot snapshot(String assetKey, Object payload, Map<String, Object> summary,
            String preferredDigest, String artifactRef) {
        String payloadJson = JsonSupport.toJSON(payload);
        return new AssetSnapshot()
                .setAssetType(assetType().name())
                .setAssetKey(assetKey)
                .setDigest(StringUtils.defaultIfBlank(preferredDigest, ReleaseDigestUtils.sha256(payloadJson)))
                .setArtifactRef(StringUtils.defaultString(artifactRef))
                .setSummary(summary)
                .setPayloadJson(payloadJson);
    }

    /**
     * 默认把当前和目标 payload 映射为虚拟 JSON 文件，并交给共享引擎计算。
     *
     * <p>组件和业务能力只需要覆写 diffResourcePath 指定稳定文件名；不得在 Adapter 内再次实现
     * 行级算法或返回原始 JSON Map。
     */
    @Override
    public ReleaseDiffDocument diff(AssetSnapshot current, AssetSnapshot target, ReleaseDiffQuery query) {
        String resourcePath = diffResourcePath();
        return releaseDiffEngine.compare(LABEL_CURRENT_CONTENT, LABEL_TARGET_VERSION,
                List.of(jsonResource(resourcePath, current)),
                List.of(jsonResource(resourcePath, target)), query);
    }

    /** 返回当前领域在发布 Diff 中使用的虚拟 JSON 文件名。 */
    protected String diffResourcePath() {
        return DEFAULT_JSON_DIFF_PATH;
    }

    private ReleaseDiffResource jsonResource(String path, AssetSnapshot snapshot) {
        String content = StringUtils.defaultString(snapshot.getPayloadJson());
        return new ReleaseDiffResource()
                .setPath(path)
                .setContentType(ReleaseDiffContentType.JSON)
                .setLanguage("json")
                .setDigest(snapshot.getDigest())
                .setSize((long) content.getBytes(StandardCharsets.UTF_8).length)
                .setContent(content);
    }

    protected GateResult gate(String code, String label, boolean passed, boolean required, String message) {
        return new GateResult()
                .setCode(code)
                .setLabel(label)
                .setStatus(passed ? GATE_PASSED : GATE_FAILED)
                .setRequired(required)
                .setMessage(message);
    }

    protected PublishResult pending(String message, Map<String, Object> data) {
        return new PublishResult()
                .setStatus(DEPLOYMENT_PLATFORM_PENDING)
                .setMessage(message)
                .setData(data == null ? new LinkedHashMap<>() : data);
    }

    /** 构造领域发布已经完成的成功结果，由共享发布服务据此推进环境指针。 */
    protected PublishResult succeeded(String message, Map<String, Object> data) {
        return new PublishResult()
                .setStatus(DEPLOYMENT_SUCCEEDED)
                .setMessage(message)
                .setData(data == null ? new LinkedHashMap<>() : data);
    }

    protected PublishResult failed(String message) {
        return new PublishResult()
                .setStatus(DEPLOYMENT_FAILED)
                .setMessage(message);
    }

    protected Map<String, Object> summaryEntry(Object... values) {
        Map<String, Object> summary = new LinkedHashMap<>();
        for (int index = 0; index + 1 < values.length; index += 2) {
            summary.put(String.valueOf(values[index]), values[index + 1]);
        }
        return summary;
    }
}
