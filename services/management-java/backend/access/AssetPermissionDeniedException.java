package dev.a2flow.management.access;

/**
 * SkillFactory 资产权限不足异常。
 *
 * <p>统一错误前缀便于前端识别并刷新权限，但不返回管理员白名单等敏感策略详情。
 */
public class AssetPermissionDeniedException extends IllegalStateException {

    private final String errorCode;
    private final String assetType;
    private final String assetCode;
    private final String operation;
    private final String fieldPath;

    public AssetPermissionDeniedException(String message) {
        this(message, null, null, null, null, null);
    }

    public AssetPermissionDeniedException(String message, String errorCode,
            String assetType, String assetCode, String operation) {
        this(message, errorCode, assetType, assetCode, operation, null);
    }

    public AssetPermissionDeniedException(String message, String errorCode,
            String assetType, String assetCode, String operation, String fieldPath) {
        super(message);
        this.errorCode = errorCode;
        this.assetType = assetType;
        this.assetCode = assetCode;
        this.operation = operation;
        this.fieldPath = fieldPath;
    }

    public String getErrorCode() {
        return errorCode;
    }

    public String getAssetType() {
        return assetType;
    }

    public String getAssetCode() {
        return assetCode;
    }

    public String getOperation() {
        return operation;
    }

    public String getFieldPath() {
        return fieldPath;
    }
}
