package dev.a2flow.management.agentcore.exception;

import lombok.Getter;

/**
 * 业务自定义异常
 *

 * Created on 2021-02-09
 */
@Getter
public class AgentServiceException extends RuntimeException {
    private int code;
    private String message;

    public AgentServiceException(int code, String message) {
        this.code = code;
        this.message = message;
    }

    public AgentServiceException(ResultCode codeEnum) {
        this.code = codeEnum.getCode();
        this.message = codeEnum.getMessage();
    }

    public AgentServiceException(ResultCode codeEnum, Throwable cause) {
        if (cause instanceof AgentServiceException) {
            this.code = ((AgentServiceException) cause).getCode();
            this.message = cause.getMessage();
            if (cause.getCause() != null) {
                this.initCause(cause.getCause());
            }
            return;
        }

        this.code = codeEnum.getCode();
        this.message = codeEnum.getMessage();
        this.initCause(cause);
    }

    public AgentServiceException(ResultCode codeEnum, String extraMessage) {
        this.code = codeEnum.getCode();
        this.message = extraMessage;
    }

    public static AgentServiceException of(int code, String message) {
        return new AgentServiceException(code, message);
    }
}
