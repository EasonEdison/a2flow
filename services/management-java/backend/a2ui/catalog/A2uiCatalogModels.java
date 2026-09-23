package dev.a2flow.management.a2ui.catalog;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import dev.a2flow.management.a2ui.registry.A2uiComponentOriginType;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * 快手 A2UI 基础 Catalog 的领域模型集合。
 *
 * <p>上游是 M 端维护的组件协议契约，下游是 Catalog 发布门禁和 Application Build compiler。
 * 本模型只描述协议和 Catalog 快照成员，不承载 React Renderer、支持声明、运行时身份、
 * 凭证或环境 authority。
 */
public final class A2uiCatalogModels {

    private A2uiCatalogModels() {
    }

    /** 基础组件只能是不可再拆的原子渲染能力；组合卡片和表单属于 Application/ShowTemplate。 */
    public enum A2uiCompositionKind {
        ATOMIC,
        COMPOSED
    }

    /** 子节点/插槽约束；首版保留结构化扩展字段，具体模式由 Catalog revision 冻结。 */
    @Data
    @Accessors(chain = true)
    public static class A2uiChildrenConstraint {
        private String mode;
        private List<String> allowedComponentTypes = new ArrayList<>();
        private Integer minChildren;
        private Integer maxChildren;
    }

    /**
     * 一个快手基础组件的完整协议契约。
     *
     * <p>componentCode 是 M 端稳定资产标识，type 是 A2UI 消息中由 B Renderer 解析的类型。
     * Catalog revision/digest 与 Application Build 精确绑定；是否可发布由共享环境指针判定。
     */
    @Data
    @Accessors(chain = true)
    public static class A2uiCatalogComponentContract {
        private String componentCode;
        private String type;
        private A2uiComponentOriginType componentOriginType;
        private String nameCn;
        private String category;
        private A2uiCompositionKind compositionKind;
        private Map<String, Object> propsSchema = new LinkedHashMap<>();
        private Map<String, Object> eventSchema = new LinkedHashMap<>();
        private A2uiChildrenConstraint childrenConstraint;
        private Map<String, Object> validMessageExample = new LinkedHashMap<>();
        private Map<String, Object> invalidMessageExample = new LinkedHashMap<>();
        private String catalogId;
        private String catalogRevision;
        private String catalogDigest;
    }
}
