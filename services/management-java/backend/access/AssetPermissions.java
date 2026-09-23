package dev.a2flow.management.access;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * SkillFactory 前端可直接消费的资产动作权限集合。
 */
@Data
@Accessors(chain = true)
public class AssetPermissions {

    private boolean canView;
    private boolean canEdit;
    private boolean canPublish;
    private boolean canForcePublish;
    private boolean canOffline;
    private boolean canManageOwner;
}
