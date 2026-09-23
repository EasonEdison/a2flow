package dev.a2flow.management.agentcore.runtime.tool.model;

import org.apache.commons.lang3.StringUtils;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

/**

 * Created on 2026-04-25
 */
@Data
@AllArgsConstructor
@NoArgsConstructor
public class ToolResult {
    private boolean success;
    private Object output;
    private String error;
    private long executionTimeMs;
    private long resultLength;
    public static ToolResult success(Object output) {
        return new ToolResult(true, output, null, 0, 0);
    }

    public static ToolResult success(Object output, long executionTimeMs) {
        return new ToolResult(true, output, null, executionTimeMs, 0);
    }

    public static ToolResult success(Object output, long executionTimeMs, long resultLength) {
        return new ToolResult(true, output, null, executionTimeMs, resultLength);
    }

    public static ToolResult failure(String error) {
        return new ToolResult(false, null, error, 0, 0);
    }

    public static ToolResult failure(Throwable error) {
        return new ToolResult(false, null, error.getMessage(), 0, 0);
    }

    public String getOutputAsString() {
        if (output == null) {
            return StringUtils.EMPTY;
        }
        return output.toString();
    }
}
