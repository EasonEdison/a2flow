package dev.a2flow.management.release.dependency;

/**
 * 环境资产解析和依赖准出的稳定错误码。
 *
 * <p>调用方应按错误码做状态展示或发布阻断，不应依赖中文 message 文案。错误码覆盖环境输入、
 * 发布指针完整性、资产启用状态以及依赖图结构错误。
 */
public enum AssetDependencyErrorCode {
    RELEASE_ENVIRONMENT_REQUIRED,
    RELEASE_ENVIRONMENT_INVALID,
    ASSET_REFERENCE_INVALID,
    ASSET_TYPE_UNSUPPORTED,
    ASSET_RELEASE_NOT_AVAILABLE,
    PREPROD_POINTER_INVALID,
    ONLINE_POINTER_REQUIRED,
    ONLINE_POINTER_INVALID,
    ASSET_DISABLED,
    DEPENDENCY_EXPANSION_FAILED,
    DEPENDENCY_CYCLE,
    DEPENDENCY_DEPTH_EXCEEDED
}
