package dev.a2flow.management.release.dependency;

/**
 * 共享发布控制面可解析的依赖资产类型。
 *
 * <p>该枚举描述依赖图中的稳定资产身份，不等同于领域草稿类型。Skill、组件、业务能力分别通过
 * {@link AssetDependencyAdapter} 映射到已有发布聚合；编排配置仅预留扩展身份，本期不注册实现。
 */
public enum AssetDependencyType {

    SKILL,
    COMPONENT_ASSET,
    A2UI_APPLICATION,
    CAPABILITY_ACTION,
    ORCHESTRATION_CONFIG
}
