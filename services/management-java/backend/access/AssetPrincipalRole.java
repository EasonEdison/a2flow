package dev.a2flow.management.access;

/**
 * SkillFactory 资产成员关系角色。
 *
 * <p>一期只持久化 OWNER；ADMIN 来自 KConf，VIEWER 由“非 OWNER 且非 ADMIN”实时推导。
 */
public enum AssetPrincipalRole {

    OWNER
}
