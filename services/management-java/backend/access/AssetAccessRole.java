package dev.a2flow.management.access;

/**
 * 当前操作者相对某个 SkillFactory 资产的权限角色。
 */
public enum AssetAccessRole {

    /** 资产负责人。 */
    OWNER,

    /** KConf 管理员。 */
    ADMIN,

    /** 已登录但不具备修改权限的只读访问者。 */
    VIEWER
}
