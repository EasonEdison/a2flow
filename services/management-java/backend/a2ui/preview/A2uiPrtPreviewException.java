package dev.a2flow.management.a2ui.preview;

/** Stable, payload-free management PRT preview failure. */
public final class A2uiPrtPreviewException extends RuntimeException {
    private final String errorCode;

    public A2uiPrtPreviewException(String errorCode) {
        super(errorCode);
        this.errorCode = errorCode;
    }

    public String getErrorCode() {
        return errorCode;
    }
}
