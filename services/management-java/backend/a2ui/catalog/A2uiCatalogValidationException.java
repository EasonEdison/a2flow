package dev.a2flow.management.a2ui.catalog;

/**
 * A2UI Catalog 领域校验异常。
 *
 * <p>上游通过稳定 errorCode 向 M 端呈现可定位失败；本异常不负责映射外部 HTTP/SSE envelope，
 * 也不通过降级或默认值放行非法契约。
 */
public class A2uiCatalogValidationException extends RuntimeException {

    private static final long serialVersionUID = 1L;

    private final String errorCode;

    public A2uiCatalogValidationException(A2uiCatalogErrorCode errorCode) {
        super(errorCode.getMessage());
        this.errorCode = errorCode.getCode();
    }

    public String getErrorCode() {
        return errorCode;
    }
}
