package dev.a2flow.management.release.dependency;

import dev.a2flow.management.release.ReleaseEnvironment;

import lombok.Getter;

/**
 * 单个依赖资产解析失败异常。
 *
 * <p>resolver 用它向上游暴露稳定错误码和最小资产定位信息，不携带完整 payload、路由配置或其他
 * 敏感内容。依赖 validator 会把这些字段转换成带完整路径的失败报告。
 */
@Getter
public class AssetDependencyResolutionException extends IllegalStateException {

    private final AssetDependencyErrorCode errorCode;
    private final AssetDependencyType assetType;
    private final String assetKey;
    private final ReleaseEnvironment requestedEnvironment;
    private final String causeCode;
    private final String fieldPath;

    public AssetDependencyResolutionException(AssetDependencyErrorCode errorCode,
            AssetDependencyType assetType, String assetKey, ReleaseEnvironment requestedEnvironment,
            String message) {
        this(errorCode, assetType, assetKey, requestedEnvironment, message, null, null);
    }

    public AssetDependencyResolutionException(AssetDependencyErrorCode errorCode,
            AssetDependencyType assetType, String assetKey, ReleaseEnvironment requestedEnvironment,
            String message, Throwable cause) {
        this(errorCode, assetType, assetKey, requestedEnvironment, message, null, cause);
    }

    public AssetDependencyResolutionException(AssetDependencyErrorCode errorCode,
            AssetDependencyType assetType, String assetKey, ReleaseEnvironment requestedEnvironment,
            String message, ResolutionCause resolutionCause, Throwable cause) {
        super(message, cause);
        this.errorCode = errorCode;
        this.assetType = assetType;
        this.assetKey = assetKey;
        this.requestedEnvironment = requestedEnvironment;
        this.causeCode = resolutionCause == null ? null : resolutionCause.causeCode();
        this.fieldPath = resolutionCause == null ? null : resolutionCause.fieldPath();
    }

    /** 依赖解析失败的稳定原因定位。 */
    public record ResolutionCause(String causeCode, String fieldPath) {
    }
}
