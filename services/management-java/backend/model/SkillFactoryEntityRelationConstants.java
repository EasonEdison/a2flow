package dev.a2flow.management.model;

/**
 * SkillFactory 通用实体关系协议常量。
 *
 * <p>该类定义工作台、AI Coding 依赖读取和关系 Repository 共同使用的稳定关系标识。上游业务
 * Service 使用这些标识组装关系，下游 Repository 只按字段持久化和查询；这里不负责关系校验、
 * 目标实体解析或版本状态流转，避免数据协议与业务流程相互耦合。
 */
public final class SkillFactoryEntityRelationConstants {

    public static final String NAMESPACE_SKILL_FACTORY = "SKILL_FACTORY";
    public static final String ENTITY_TYPE_SKILL = "SKILL";
    public static final String ENTITY_TYPE_CAPABILITY_ACTION = "CAPABILITY_ACTION";
    public static final String ENTITY_TYPE_COMPONENT_ASSET = "COMPONENT_ASSET";
    public static final String ENTITY_TYPE_BUSINESS_DOMAIN = "BUSINESS_DOMAIN";
    public static final String ENTITY_TYPE_CAPABILITY_DOMAIN = "CAPABILITY_DOMAIN";
    public static final String ENTITY_TYPE_SPECIALIST = "SPECIALIST";
    public static final String RELATION_TYPE_SKILL_USES_CAPABILITY = "SKILL_USES_CAPABILITY";
    public static final String RELATION_TYPE_SKILL_USES_COMPONENT = "SKILL_USES_COMPONENT";
    public static final String RELATION_TYPE_SKILL_BELONGS_TO_SPECIALIST =
            "SKILL_BELONGS_TO_SPECIALIST";
    public static final String RELATION_TYPE_CAPABILITY_BELONGS_TO_BUSINESS_DOMAIN =
            "CAPABILITY_ACTION_BELONGS_TO_BUSINESS_DOMAIN";
    public static final String RELATION_TYPE_CAPABILITY_BELONGS_TO_CAPABILITY_DOMAIN =
            "CAPABILITY_ACTION_BELONGS_TO_CAPABILITY_DOMAIN";
    public static final String RELATION_TYPE_CAPABILITY_BELONGS_TO_SPECIALIST =
            "CAPABILITY_ACTION_BELONGS_TO_SPECIALIST";
    public static final String RELATION_MODE_DIRECT = "DIRECT";
    public static final String RELATION_MODE_ASSIGNED = "ASSIGNED";

    private SkillFactoryEntityRelationConstants() {
    }
}
