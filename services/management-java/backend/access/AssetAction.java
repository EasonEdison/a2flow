package dev.a2flow.management.access;

/**
 * SkillFactory 通用资产动作。
 *
 * <p>公开 method 和关键领域 Service 应先映射到这里，再由
 * {@link AssetAuthorizationService} 按 OWNER/ADMIN/VIEWER 策略判断，避免每个中心自行解析负责人。
 */
public enum AssetAction {

    VIEW,
    EDIT,
    PUBLISH,
    FORCE_PUBLISH,
    OFFLINE,
    MANAGE_OWNER
}
