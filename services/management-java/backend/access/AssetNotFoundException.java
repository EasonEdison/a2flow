package dev.a2flow.management.access;

import dev.a2flow.management.release.ReleaseAssetType;

/**
 * SkillFactory 稳定资产不存在异常。
 *
 * <p>上游由统一资产访问层在权限判断前确认稳定资产身份；下游分发器把该异常映射为可识别的
 * ASSET_NOT_FOUND 业务结果。该异常不代表权限不足，不创建资产，也不允许调用方提供 fallback 身份。
 */
public class AssetNotFoundException extends IllegalArgumentException {

    private static final String ERROR_CODE = "ASSET_NOT_FOUND";
    private static final String ERROR_MESSAGE = "asset not found";

    private final String assetType;
    private final String assetCode;

    public AssetNotFoundException(ReleaseAssetType assetType, String assetCode) {
        super(ERROR_MESSAGE);
        this.assetType = assetType == null ? null : assetType.name();
        this.assetCode = assetCode;
    }

    public String getErrorCode() {
        return ERROR_CODE;
    }

    public String getAssetType() {
        return assetType;
    }

    public String getAssetCode() {
        return assetCode;
    }
}
