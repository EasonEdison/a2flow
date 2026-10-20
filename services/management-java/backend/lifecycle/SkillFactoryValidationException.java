package dev.a2flow.management.lifecycle;

import lombok.Getter;

/**
 * SkillFactory 基础信息的稳定业务校验异常。
 *
 * <p>上游生命周期 Service 在确认用户输入不满足 Skill 业务约束时构造本异常；下游统一 Dispatcher
 * 使用 {@code errorCode} 和 {@code fieldPath} 返回可读、可定位的业务失败。该异常不改变校验规则，
 * 不负责权限、发布状态、数据库异常或未知系统异常的兜底。
 */
@Getter
public class SkillFactoryValidationException extends IllegalArgumentException {

    private static final long serialVersionUID = 1L;
    private static final String ERROR_CODE_SKILL_NAME_CN_ALREADY_EXISTS =
            "SKILL_NAME_CN_ALREADY_EXISTS";
    private static final String FIELD_PATH_SKILL_NAME_CN = "skillNameCn";
    private static final String ERROR_MESSAGE_SKILL_NAME_CN_PREFIX = "Skill 中文名\u201c";
    private static final String ERROR_MESSAGE_SKILL_NAME_CN_SUFFIX = "\u201d已存在，请更换后重试";

    private final String errorCode;
    private final String fieldPath;

    private SkillFactoryValidationException(
            String errorCode, String message, String fieldPath) {
        super(message);
        this.errorCode = errorCode;
        this.fieldPath = fieldPath;
    }

    /** 构造中文名重复错误，仅回显已通过基础参数校验的中文名。 */
    public static SkillFactoryValidationException duplicateSkillNameCn(String skillNameCn) {
        return new SkillFactoryValidationException(
                ERROR_CODE_SKILL_NAME_CN_ALREADY_EXISTS,
                ERROR_MESSAGE_SKILL_NAME_CN_PREFIX + skillNameCn + ERROR_MESSAGE_SKILL_NAME_CN_SUFFIX,
                FIELD_PATH_SKILL_NAME_CN);
    }
    /** Binding resolution rejects before replacing any relations. */
    public static SkillFactoryValidationException capabilityPresentationRequired() {
        return new SkillFactoryValidationException("SKILL_CAPABILITY_PRESENTATION_REQUIRED",
                "EXECUTION_AND_RENDER requires capability presentation components", "capabilityBindings.bindMode");
    }

    /** Workspace files use relative paths from the actual workspace tree. */
    public static SkillFactoryValidationException invalidWorkspaceFilePath() {
        return new SkillFactoryValidationException("SKILL_WORKSPACE_FILE_PATH_INVALID",
                "filePath must be a relative path inside the workspace", "filePath");
    }

    /** Reject an identity that the existing Runtime publication contract cannot accept. */
    public static SkillFactoryValidationException invalidSkillKey() {
        return new SkillFactoryValidationException("INVALID_ASSET_KEY",
                "Skill code must use lowercase letters, digits and hyphens; slash-separated namespaces are allowed; maximum 128 characters",
                "skillCode");
    }

    /** Legacy URL/file recovery does not establish immutable artifact identity. */
    public static SkillFactoryValidationException packageRestoreSourceRequired() {
        return new SkillFactoryValidationException("PACKAGE_RESTORE_SOURCE_REQUIRED",
                "请通过已发布的 PRT Build 或正式版本重置工作区；不支持 URL 或本地文件恢复。", "sourceId");
    }

    /** Closed ZIP budget errors; never include source URLs or archive content. */
    public static SkillFactoryValidationException packageLimitExceeded(String code) {
        String message = switch (code) {
            case "PACKAGE_ENTRY_COUNT_EXCEEDED" -> "ZIP 条目数量超过限制，请减少文件和目录数量。";
            case "PACKAGE_ENTRY_BYTES_EXCEEDED" -> "ZIP 单个条目展开后超过大小限制。";
            case "PACKAGE_EXPANDED_BYTES_EXCEEDED" -> "ZIP 展开后的总大小超过限制。";
            default -> throw new IllegalArgumentException("UNKNOWN_PACKAGE_LIMIT_CODE");
        };
        return new SkillFactoryValidationException(code, message, "package");
    }

}
