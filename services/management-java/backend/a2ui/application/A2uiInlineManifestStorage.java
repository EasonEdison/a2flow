package dev.a2flow.management.a2ui.application;

import java.nio.charset.StandardCharsets;

import org.apache.commons.lang3.StringUtils;

import dev.a2flow.management.a2ui.registry.A2uiRegistryValidationException;
import dev.a2flow.management.release.ReleaseDigestUtils;
import dev.a2flow.management.release.ReleaseModels.AssetSnapshot;

/**
 * A2UI Application 首版 immutable manifest 的 INLINE_V1 存储边界。
 *
 * <p>策略上限由调用方注入，未配置时正式路径 fail closed。该类只保存完整 canonical JSON、
 * SHA-256 和 UTF-8 字节数，不自动切换对象存储，也不从 Registry current source 重建快照。
 */
public class A2uiInlineManifestStorage {

    private static final String STORAGE_POLICY_INLINE_V1 = "INLINE_V1";
    private static final String ASSET_TYPE_A2UI_APPLICATION = "A2UI_APPLICATION";
    private static final String DIGEST_PREFIX = "sha256:";
    private static final String ERROR_POLICY_UNCONFIGURED = "A2UI_MANIFEST_POLICY_UNCONFIGURED";
    private static final String ERROR_TOO_LARGE = "A2UI_MANIFEST_TOO_LARGE";
    private static final String ERROR_READBACK_INVALID = "A2UI_MANIFEST_READBACK_INVALID";

    private final Integer maxManifestBytes;

    public A2uiInlineManifestStorage(Integer maxManifestBytes) {
        this.maxManifestBytes = maxManifestBytes;
    }

    /**
     * 保存完整 inline manifest；策略缺失或超限均直接失败。
     */
    public AssetSnapshot store(String assetKey, String canonicalJson) {
        requirePolicy();
        if (StringUtils.isBlank(assetKey) || canonicalJson == null) {
            throw new A2uiRegistryValidationException(ERROR_READBACK_INVALID);
        }
        byte[] payload = canonicalJson.getBytes(StandardCharsets.UTF_8);
        if (payload.length > maxManifestBytes) {
            throw new A2uiRegistryValidationException(ERROR_TOO_LARGE);
        }
        return new AssetSnapshot()
                .setAssetType(ASSET_TYPE_A2UI_APPLICATION)
                .setAssetKey(assetKey)
                .setStoragePolicy(STORAGE_POLICY_INLINE_V1)
                .setPayloadJson(canonicalJson)
                .setPayloadBytes((long) payload.length)
                .setDigest(digest(canonicalJson));
    }

    /**
     * 验证发布读回的 immutable inline manifest 没有被截断、替换或重新编码。
     */
    public String verifyReadback(AssetSnapshot snapshot) {
        requirePolicy();
        if (snapshot == null || !STORAGE_POLICY_INLINE_V1.equals(snapshot.getStoragePolicy())
                || snapshot.getPayloadJson() == null || snapshot.getPayloadBytes() == null
                || snapshot.getDigest() == null) {
            throw new A2uiRegistryValidationException(ERROR_READBACK_INVALID);
        }
        byte[] payload = snapshot.getPayloadJson().getBytes(StandardCharsets.UTF_8);
        if (payload.length > maxManifestBytes || payload.length != snapshot.getPayloadBytes()
                || !snapshot.getDigest().equals(digest(snapshot.getPayloadJson()))) {
            throw new A2uiRegistryValidationException(ERROR_READBACK_INVALID);
        }
        return snapshot.getDigest();
    }

    private void requirePolicy() {
        if (maxManifestBytes == null || maxManifestBytes <= 0) {
            throw new A2uiRegistryValidationException(ERROR_POLICY_UNCONFIGURED);
        }
    }

    private String digest(String canonicalJson) {
        return DIGEST_PREFIX + ReleaseDigestUtils.sha256(canonicalJson);
    }
}
