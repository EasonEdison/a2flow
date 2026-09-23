package dev.a2flow.management.storage.db.mapper;

/**
 * SkillFactory Mapper 层常量。
 *
 * <p>这个类只服务 SkillFactory 内部各业务子包的 MyBatis-Plus Mapper 注解，避免数据源名这类固定字符串
 * 散落在多个 Mapper 接口中。业务 Service 不应依赖这里的常量，避免把 DB 访问细节向上泄露。
 */
public final class SkillFactoryMapperConstants {

    public static final String SELLER_DATA_MANAGER_DATA_SOURCE = "management";

    private SkillFactoryMapperConstants() {
    }
}
