package dev.a2flow.management.storage.db;

import org.mybatis.spring.annotation.MapperScan;
import org.springframework.context.annotation.Configuration;

/**
 * SkillFactory 持久化 Mapper 扫描配置。
 *
 * <p>仅注册管理端资产、通用关系与事件仓储，不扫描其他服务的 Mapper。
 */
@Configuration
@MapperScan("dev.a2flow.management.storage.db.mapper")
public class SkillFactoryMapperScanConfig {
}
