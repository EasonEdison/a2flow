package dev.a2flow.management.config;

import java.util.ArrayList;
import java.util.List;

import lombok.Data;

/**
 * SkillFactory 资产权限 KConf 配置。
 *
 * <p>该配置只保存平台管理员用户名白名单，不保存资产负责人。资产负责人统一存放在
 * {@code skill_asset_principal} 表中，避免 KConf 与数据库形成双事实源。
 */
@Data
public class SkillFactoryPermissionConfig {

    /** 允许跨资产执行编辑、发布、下线和负责人管理的平台管理员用户名。 */
    private List<String> adminOperators = new ArrayList<>();
}
