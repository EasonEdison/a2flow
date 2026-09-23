package dev.a2flow.management.storage.db;

/**
 * SkillFactory 存储层常量。
 *
 * <p>该类只为 `runtime/skillfactory` 内的 DB Mapper 提供数据源名等固定值，避免存储细节散落在
 * Mapper 注解中。它不承载业务方法编码、审批状态或 workspace 路径规则。
 */
public final class SkillFactoryStorageConstants {

    public static final String SELLER_DATA_MANAGER_DATA_SOURCE = "management";

    private SkillFactoryStorageConstants() {
    }
}
