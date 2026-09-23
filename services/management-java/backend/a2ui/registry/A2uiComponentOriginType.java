package dev.a2flow.management.a2ui.registry;

import java.util.Arrays;

/**
 * A2UI 原子组件的受控来源类型。
 *
 * <p>该枚举只描述 atom contract 来源，与所属 Catalog 的来源分离。一个 PLATFORM_MANAGED
 * Catalog 可以同时引用两种来源的 atom，调用方不得据 Catalog 来源反推组件来源。
 */
public enum A2uiComponentOriginType {

    A2UI_OFFICIAL,
    PLATFORM_CUSTOM;

    /** 按精确编码解析来源，未知值直接失败关闭。 */
    public static A2uiComponentOriginType parse(String code) {
        return Arrays.stream(values())
                .filter(value -> value.name().equals(code))
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException("A2UI_COMPONENT_ORIGIN_INVALID"));
    }
}
