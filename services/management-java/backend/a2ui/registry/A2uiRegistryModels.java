package dev.a2flow.management.a2ui.registry;

import java.util.Map;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * A2UI Registry 的最小领域输入模型。
 *
 * <p>模型只描述 A2UI_ATOM 的 canonical contract，不承载 Catalog revision、renderer digest、
 * frontend support 或生命周期字段；这些事实由共享发布域和受信证据流维护。
 */
public final class A2uiRegistryModels {

    private A2uiRegistryModels() {
    }

    @Data
    @Accessors(chain = true)
    public static class A2uiAtomPayload {

        private String componentCode;
        private String type;
        private A2uiComponentOriginType componentOriginType;
        private String nameCn;
        private String category;
        private String compositionKind;
        private Map<String, Object> propsSchema;
        private Map<String, Object> eventSchema;
        private Map<String, Object> childrenConstraint;
        private Map<String, Object> validMessageExample;
        private Map<String, Object> invalidMessageExample;
    }
}
