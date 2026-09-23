package dev.a2flow.management.agentcore.runtime.tool;

/**

 * Created on 2026-04-25
 */
public class ToolException extends RuntimeException {
    public enum ErrorCode {
        UNKNOWN_TOOL,
        INVALID_PARAMS,
        EXECUTION_ERROR,
        FILE_NOT_FOUND,
        PERMISSION_DENIED,
        TIMEOUT,
        PROCESS_ERROR,
        VALIDATION_ERROR
    }

    private final ErrorCode errorCode;

    public ToolException(String message) {
        super(message);
        this.errorCode = ErrorCode.EXECUTION_ERROR;
    }

    public ToolException(String message, ErrorCode errorCode) {
        super(message);
        this.errorCode = errorCode;
    }

    public ToolException(String message, Throwable cause, ErrorCode errorCode) {
        super(message, cause);
        this.errorCode = errorCode;
    }

}
