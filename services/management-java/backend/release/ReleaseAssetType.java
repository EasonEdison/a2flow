package dev.a2flow.management.release;

import java.util.Arrays;

/**
 * SkillFactory 发布控制面支持的资产类型。
 *
 * <p>该枚举只定义共享发布身份，不包含 Skill、组件或业务能力的领域字段。新增内部中心时，必须同时
 * 注册对应的 {@link ReleaseAssetAdapter}，不能只增加枚举后让共享 Service 猜测领域行为。
 */
public enum ReleaseAssetType {

    SKILL,
    COMPONENT,
    CAPABILITY_ACTION,
    ORCHESTRATION_CONFIG,
    A2UI_ATOM,
    A2UI_CATALOG,
    A2UI_APPLICATION;

    /**
     * 解析前端提交的资产类型，并对不支持的值返回明确错误。
     */
    public static ReleaseAssetType parse(String value) {
        return Arrays.stream(values())
                .filter(item -> item.name().equalsIgnoreCase(value))
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException("unsupported release assetType: " + value));
    }
}
