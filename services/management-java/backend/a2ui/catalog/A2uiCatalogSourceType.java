package dev.a2flow.management.a2ui.catalog;

import java.util.Arrays;

/**
 * A2UI Catalog 的受控来源类型。
 *
 * <p>该枚举只表达 Catalog 资产来源，不表达组件来源、前端支持状态或编辑权限。上游 canonical
 * source 和下游 immutable release 都必须使用这里的精确值，禁止按 catalogId 或展示名称猜测。
 */
public enum A2uiCatalogSourceType {

    A2UI_OFFICIAL,
    PLATFORM_MANAGED;

    /** 按精确编码解析来源，未知值直接失败关闭。 */
    public static A2uiCatalogSourceType parse(String code) {
        return Arrays.stream(values())
                .filter(value -> value.name().equals(code))
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException("A2UI_CATALOG_SOURCE_INVALID"));
    }
}
