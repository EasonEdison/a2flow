package dev.a2flow.management.aicoding.tool.common;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.function.BooleanSupplier;

import org.apache.commons.lang3.StringUtils;
import org.springframework.ai.chat.model.ToolContext;
import org.springframework.ai.tool.ToolCallback;
import org.springframework.ai.tool.definition.ToolDefinition;

import com.google.common.collect.Lists;
import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.agentcore.runtime.tool.ToolException;
import dev.a2flow.management.aicoding.tool.common.SkillFactoryToolPathResolver.ResolvedPath;

import lombok.extern.slf4j.Slf4j;

/**
 * SkillFactory AI Coding 专用 Python 执行工具。
 *
 * <p>该工具只在 `AiCodingReActEngine` 内按 KConf 显式配置暴露，不注册为全局 Spring ToolCallback，
 * 避免影响普通数字员工 ReAct 工具。它支持执行 workspace 内脚本，也支持一次性 Python 代码片段，
 * 便于模型在受控工作目录中运行 Skill 脚本或做临时数据处理。外部 HTTP 调试统一由需要用户明确
 * 授权的 SkillFactory Curl Tool 承接，本工具不提供第二条 subprocess curl 传输路径。本工具不负责
 * patch 落盘，文件写入仍必须通过 `propose_patch` 和确认门禁完成。
 */
@Slf4j
public class SkillFactoryPythonToolCallback implements ToolCallback {

    public static final String TOOL_NAME = "python";

    private static final String FIELD_FILE = "file";
    private static final String FIELD_CODE = "code";
    private static final String FIELD_ARGS = "args";
    private static final String FIELD_TIMEOUT = "timeout";
    private static final int DEFAULT_TIMEOUT_SECONDS = 60;
    private static final int MAX_TIMEOUT_SECONDS = 180;
    private static final int MAX_OUTPUT_CHARS = 20000;
    private static final int PROCESS_POLL_INTERVAL_MILLIS = 200;
    private static final String TOOL_DESCRIPTION =
            "Execute Python in the current SkillFactory workspace or execute an exact absolute script path returned "
                    + "by use_skill. Provide either a script file or inline code for Skill scripts and data "
                    + "processing. External HTTP requests must use the consent-gated curl tool.";
    private static final String INPUT_SCHEMA = """
            {
                "type": "object",
                "properties": {
                    "file": {"type": "string", "description": "Workspace-relative path or exact absolute path from use_skill"},
                    "code": {"type": "string", "description": "Inline Python code to execute with python3 -c"},
                    "args": {"type": "array", "items": {"type": "string"}, "description": "Command line arguments"},
                    "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 60}
                }
            }
            """;

    @Override
    public ToolDefinition getToolDefinition() {
        return ToolDefinition.builder()
                .name(TOOL_NAME)
                .description(TOOL_DESCRIPTION)
                .inputSchema(INPUT_SCHEMA)
                .build();
    }

    @Override
    public String call(String toolInput) {
        return StringUtils.EMPTY;
    }

    /**
     * 执行 Python 脚本或代码片段。
     */
    @Override
    public String call(String toolInput, ToolContext toolContext) {
        if (StringUtils.isBlank(toolInput) || Objects.isNull(toolContext)) {
            throw new ToolException("python tool invalid params", ToolException.ErrorCode.INVALID_PARAMS);
        }
        Map<String, Object> input = JsonSupport.fromJson(toolInput);
        return execute(input, toolContext);
    }

    private String execute(Map<String, Object> input, ToolContext toolContext) {
        try {
            ExecutionCommand executionCommand = buildCommand(input, toolContext);
            int timeout = timeoutSeconds(input);
            String mode = StringUtils.isNotBlank(StringUtils.trimToEmpty((String) input.get(FIELD_CODE)))
                    ? FIELD_CODE : FIELD_FILE;
            log.info("SkillFactory Python工具开始执行, workspacePath={}, mode={}, timeout={}",
                    executionCommand.workingDirectory(), mode, timeout);
            ProcessBuilder processBuilder = new ProcessBuilder(executionCommand.command());
            processBuilder.directory(executionCommand.workingDirectory().toFile());
            processBuilder.redirectErrorStream(true);
            long startTime = System.currentTimeMillis();
            Process process = processBuilder.start();
            CompletableFuture<String> outputFuture = CompletableFuture.supplyAsync(() -> readOutputUnchecked(process));
            boolean finished = waitForProcess(process, timeout, toolContext);
            if (!finished) {
                process.destroyForcibly();
                process.waitFor(5, TimeUnit.SECONDS);
                throw new ToolException("Python execution timed out", ToolException.ErrorCode.TIMEOUT);
            }
            String output = outputFuture.get(5, TimeUnit.SECONDS);
            int exitCode = process.exitValue();
            log.info("SkillFactory Python工具执行完成, exitCode={}, costMs={}, outputLength={}",
                    exitCode, System.currentTimeMillis() - startTime, StringUtils.length(output));
            if (exitCode != 0) {
                throw new ToolException("Python execution exited with code " + exitCode + ": " + output,
                        ToolException.ErrorCode.EXECUTION_ERROR);
            }
            return StringUtils.defaultIfBlank(output, "Executed successfully");
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new ToolException("Python execution interrupted: " + e.getMessage(), e,
                    ToolException.ErrorCode.EXECUTION_ERROR);
        } catch (ExecutionException | TimeoutException e) {
            throw new ToolException("Python output collection failed: " + e.getMessage(), e,
                    ToolException.ErrorCode.EXECUTION_ERROR);
        } catch (IOException e) {
            throw new ToolException("Python execution failed: " + e.getMessage(), e,
                    ToolException.ErrorCode.EXECUTION_ERROR);
        }
    }

    private ExecutionCommand buildCommand(Map<String, Object> input, ToolContext toolContext) {
        List<String> command = Lists.newArrayList("python3");
        Path workspacePath = workspacePath(toolContext);
        Path workingDirectory = workspacePath;
        String file = StringUtils.trimToEmpty((String) input.get(FIELD_FILE));
        String code = StringUtils.trimToEmpty((String) input.get(FIELD_CODE));
        if (StringUtils.isNotBlank(code)) {
            command.add("-c");
            command.add(code);
        } else if (StringUtils.isNotBlank(file)) {
            ResolvedPath resolvedPath =
                    SkillFactoryToolPathResolver.resolve(file, toolContext);
            Path filePath = resolvedPath.path();
            if (!Files.exists(filePath)) {
                throw new ToolException("File not found: " + file, ToolException.ErrorCode.FILE_NOT_FOUND);
            }
            command.add(filePath.toString());
            workingDirectory = resolvedPath.workingDirectory();
        } else {
            throw new ToolException("Python tool requires either file or code",
                    ToolException.ErrorCode.INVALID_PARAMS);
        }
        appendArgs(command, input);
        return new ExecutionCommand(command, workingDirectory);
    }

    private void appendArgs(List<String> command, Map<String, Object> input) {
        Object argsObject = input.get(FIELD_ARGS);
        if (!(argsObject instanceof List<?> args)) {
            return;
        }
        args.forEach(arg -> command.add(String.valueOf(arg)));
    }

    private int timeoutSeconds(Map<String, Object> input) {
        Object timeoutObject = input.get(FIELD_TIMEOUT);
        if (!(timeoutObject instanceof Number timeoutNumber)) {
            return DEFAULT_TIMEOUT_SECONDS;
        }
        return Math.max(1, Math.min(timeoutNumber.intValue(), MAX_TIMEOUT_SECONDS));
    }

    private Path workspacePath(ToolContext toolContext) {
        Map<String, Object> toolContextMap = toolContext.getContext();
        Path workspacePath = (Path) toolContextMap.get("workspacePath");
        if (Objects.isNull(workspacePath)) {
            throw new ToolException("workspacePath not exists", ToolException.ErrorCode.PERMISSION_DENIED);
        }
        return workspacePath;
    }

    private String readOutput(Process process) throws IOException {
        StringBuilder output = new StringBuilder();
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(process.getInputStream(), StandardCharsets.UTF_8))) {
            String line;
            while ((line = reader.readLine()) != null) {
                if (output.length() < MAX_OUTPUT_CHARS) {
                    output.append(line).append('\n');
                }
            }
        }
        return StringUtils.abbreviate(output.toString(), MAX_OUTPUT_CHARS);
    }

    private String readOutputUnchecked(Process process) {
        try {
            return readOutput(process);
        } catch (IOException e) {
            throw new IllegalStateException(e);
        }
    }

    /** 等待 Python 进程结束，并在等待期间响应后端取消信号。 */
    private boolean waitForProcess(Process process, int timeoutSeconds, ToolContext toolContext)
            throws InterruptedException {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(timeoutSeconds);
        BooleanSupplier cancelChecker = cancelChecker(toolContext);
        while (System.nanoTime() < deadline) {
            if (cancelChecker.getAsBoolean()) {
                process.destroyForcibly();
                process.waitFor(5, TimeUnit.SECONDS);
                throw new ToolException("Python execution cancelled", ToolException.ErrorCode.EXECUTION_ERROR);
            }
            if (process.waitFor(PROCESS_POLL_INTERVAL_MILLIS, TimeUnit.MILLISECONDS)) {
                return true;
            }
        }
        return false;
    }

    private BooleanSupplier cancelChecker(ToolContext toolContext) {
        Object checker = toolContext.getContext().get(SkillFactoryToolPathResolver.CONTEXT_CANCEL_CHECKER);
        return checker instanceof BooleanSupplier supplier ? supplier : () -> false;
    }

    private record ExecutionCommand(List<String> command, Path workingDirectory) {
    }
}
