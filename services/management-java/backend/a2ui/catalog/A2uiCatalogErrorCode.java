package dev.a2flow.management.a2ui.catalog;

/**
 * A2UI Catalog 稳定错误码。
 *
 * <p>上游 M 端可按 code 定位发布门禁，下游不得依赖可变的中文错误文案。本枚举不定义 HTTP
 * 状态或 SSE 传输语义，物理 transport 仍由后续评审决定。
 */
public enum A2uiCatalogErrorCode {
    COMPONENT_CONTRACT_INVALID("A2UI_COMPONENT_CONTRACT_INVALID", "基础组件契约不完整"),
    COMPONENT_NOT_ATOMIC("A2UI_COMPONENT_NOT_ATOMIC", "基础 Catalog 只允许原子组件"),
    COMPONENT_LIFECYCLE_INVALID("A2UI_COMPONENT_LIFECYCLE_INVALID", "组件生命周期迁移不合法"),
    FRONTEND_SUPPORT_REQUIRED("A2UI_FRONTEND_SUPPORT_REQUIRED", "AVAILABLE 必须由前端支持声明确认"),
    FRONTEND_SUPPORT_UNTRUSTED("A2UI_FRONTEND_SUPPORT_UNTRUSTED", "前端支持声明不可信"),
    FRONTEND_SUPPORT_MISMATCH("A2UI_FRONTEND_SUPPORT_MISMATCH", "前端支持声明与组件契约不匹配"),
    CATALOG_SUPPORT_AUTHORITY_REQUIRED("A2UI_CATALOG_SUPPORT_AUTHORITY_REQUIRED", "Catalog 支持证据必须由受信主体写入"),
    CATALOG_SUPPORT_DIGEST_MISMATCH("A2UI_CATALOG_SUPPORT_DIGEST_MISMATCH", "Catalog 支持证据摘要不匹配"),
    CATALOG_SUPPORT_COMPONENT_SUBSET_INVALID("A2UI_CATALOG_SUPPORT_COMPONENT_SUBSET_INVALID", "Catalog 支持组件集合不是 Catalog 子集"),
    CATALOG_SUPPORT_CLOSURE_REQUIRED("A2UI_CATALOG_SUPPORT_CLOSURE_REQUIRED", "Catalog 支持证据闭合信息不完整");

    private final String code;
    private final String message;

    A2uiCatalogErrorCode(String code, String message) {
        this.code = code;
        this.message = message;
    }

    public String getCode() {
        return code;
    }

    public String getMessage() {
        return message;
    }
}
