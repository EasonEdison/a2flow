package dev.a2flow.management.access;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * 返回给管理端的资产负责人摘要。
 *
 * <p>该对象只暴露当前资产的 ACTIVE OWNER，不暴露平台管理员白名单和数据库内部主键。
 */
@Data
@Accessors(chain = true)
public class AssetPrincipal {

    private String principalType;
    private String principalId;
    private String roleType;
}
