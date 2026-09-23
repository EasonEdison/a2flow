package dev.a2flow.management.aicoding.tool.common;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.function.BooleanSupplier;

import org.apache.commons.collections4.MapUtils;
import org.apache.commons.lang3.StringUtils;
import org.springframework.ai.chat.model.ToolContext;
import org.springframework.ai.tool.ToolCallback;
import org.springframework.ai.tool.definition.ToolDefinition;

import com.google.common.collect.Lists;
import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.agentcore.runtime.tool.ToolException;
import dev.a2flow.management.config.SkillFactoryHttpDebugConfig;

import lombok.extern.slf4j.Slf4j;

/**
 * SkillFactory AI Coding 专用外部 HTTP 调试工具。
 *
 * <p>上游模型从完整会话历史理解用户是否已经授权，并解析环境、path、method、header、body 和用户
 * curl Cookie；本工具不重复解释自然语言授权，只从可信 ToolContext 读取目标环境配置并校验结构边界。
 * 下游通过不带 shell 的 curl 进程发起请求并返回结构化结果。该工具只负责受控传输，不读取或写入
 * Skill 文件工作区，也不依赖 {@code workspacePath}。该类不解析浏览器 curl 文本、不允许任意 URL、
 * 不自动重试，也不承担 Skill 脚本内的长期 HTTP 客户端实现。
 */
@Slf4j
public class SkillFactoryCurlToolCallback implements ToolCallback {

    public static final String TOOL_NAME = "curl";
    public static final String CONTEXT_HTTP_DEBUG_CONFIG = "httpDebugConfig";

    private static final String FIELD_ENVIRONMENT = "environment";
    private static final String FIELD_SOURCE_TYPE = "sourceType";
    private static final String FIELD_PROTOCOL = "protocol";
    private static final String FIELD_HOST = "host";
    private static final String FIELD_PORT = "port";
    private static final String FIELD_PATH = "path";
    private static final String FIELD_METHOD = "method";
    private static final String FIELD_HEADERS = "headers";
    private static final String FIELD_BODY = "body";
    private static final String FIELD_COOKIE = "cookie";
    private static final String FIELD_TIMEOUT = "timeout";
    private static final String FIELD_MAX_OUTPUT_CHARS = "maxOutputChars";
    private static final String ENVIRONMENT_PRE_RELEASE = "PRE_RELEASE";
    private static final String ENVIRONMENT_PRODUCTION = "PRODUCTION";
    private static final String SOURCE_TYPE_API_CENTER = "API_CENTER";
    private static final String SOURCE_TYPE_HTTP_REQUEST = "HTTP_REQUEST";
    private static final String PROTOCOL_HTTP = "http";
    private static final String PROTOCOL_HTTPS = "https";
    private static final String DEFAULT_METHOD = "GET";
    private static final int DEFAULT_TIMEOUT_SECONDS = 30;
    private static final int MAX_TIMEOUT_SECONDS = 120;
    private static final int DEFAULT_MAX_OUTPUT_CHARS = 20000;
    private static final int HARD_MAX_OUTPUT_CHARS = 60000;
    private static final int PROCESS_POLL_INTERVAL_MILLIS = 200;
    private static final int OUTPUT_WAIT_SECONDS = 5;
    private static final int OUTPUT_TAIL_CHARS = 256;
    private static final int OUTPUT_BUFFER_CHARS = 2048;
    private static final String HTTP_STATUS_MARKER = "__SKILL_FACTORY_HTTP_STATUS__:";
    private static final Set<String> ALLOWED_METHODS = Set.of(
            "GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS");
    private static final Set<String> ALLOWED_ENVIRONMENTS = Set.of(
            ENVIRONMENT_PRE_RELEASE, ENVIRONMENT_PRODUCTION);
    private static final Set<String> ALLOWED_SOURCE_TYPES = Set.of(
            SOURCE_TYPE_API_CENTER, SOURCE_TYPE_HTTP_REQUEST);
    private static final Set<String> FORBIDDEN_HEADER_NAMES = Set.of(
            "cookie", "host", "proxy", "proxyconnection", "contentlength", "transferencoding");
    private static final List<String> FORBIDDEN_CREDENTIAL_HEADER_PARTS = List.of(
            "authorization", "token", "apikey", "accesskey", "secret", "signature");
    private static final String TOOL_DESCRIPTION =
            "Execute a bounded SkillFactory HTTP debugging request. You must decide from the conversation whether "
                    + "the user has authorized execution; if not, ask before calling this tool. One clear natural "
                    + "affirmative reply is sufficient, with no fixed phrase or second confirmation. Use environment "
                    + "PRE_RELEASE by default and choose PRODUCTION only when you understand explicit production "
                    + "intent. For API_CENTER, supply path/query, method, non-sensitive headers, body and the exact "
                    + "Cookie parsed from the user's latest applicable pasted curl; the backend chooses the configured "
                    + "origin. For HTTP_REQUEST, also supply protocol, host and optional port for the selected "
                    + "environment. Do not put Host or Cookie in headers, and do not automatically retry after a "
                    + "result or failure.";
    private static final String INPUT_SCHEMA = """
            {
                "type": "object",
                "properties": {
                    "sourceType": {
                        "type": "string",
                        "enum": ["API_CENTER", "HTTP_REQUEST"],
                        "default": "API_CENTER"
                    },
                    "environment": {
                        "type": "string",
                        "enum": ["PRE_RELEASE", "PRODUCTION"],
                        "default": "PRE_RELEASE"
                    },
                    "protocol": {
                        "type": "string",
                        "enum": ["http", "https"],
                        "description": "Required for HTTP_REQUEST; protocol for this one request"
                    },
                    "host": {
                        "type": "string",
                        "description": "Required for HTTP_REQUEST; domain for this one request, without scheme or path"
                    },
                    "port": {
                        "type": "integer",
                        "description": "Optional for HTTP_REQUEST; TCP port from 1 to 65535"
                    },
                    "path": {
                        "type": "string",
                        "description": "Request path beginning with /; may include query but never scheme or host"
                    },
                    "method": {"type": "string", "description": "HTTP method", "default": "GET"},
                    "headers": {
                        "type": "object",
                        "description": "Non-sensitive headers only",
                        "additionalProperties": {"type": "string"}
                    },
                    "body": {"type": "string", "description": "Exact request body"},
                    "cookie": {
                        "type": "string",
                        "description": "Exact Cookie value parsed from the user's most recent pasted curl"
                    },
                    "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 30},
                    "maxOutputChars": {"type": "integer", "description": "Maximum response chars to return"}
                },
                "required": ["path"]
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
     * 校验环境配置和请求结构后执行一次 HTTP 调试请求。
     */
    @Override
    public String call(String toolInput, ToolContext toolContext) {
        if (StringUtils.isBlank(toolInput) || Objects.isNull(toolContext)) {
            throw new ToolException("curl tool invalid params", ToolException.ErrorCode.INVALID_PARAMS);
        }
        Map<String, Object> input = JsonSupport.fromJson(toolInput);
        String sourceType = validateSourceType(MapUtils.getString(input, FIELD_SOURCE_TYPE, SOURCE_TYPE_API_CENTER));
        String environment = validateEnvironment(MapUtils.getString(
                input, FIELD_ENVIRONMENT, ENVIRONMENT_PRE_RELEASE));
        String path = validatePath(MapUtils.getString(input, FIELD_PATH));
        String origin = SOURCE_TYPE_HTTP_REQUEST.equals(sourceType)
                ? directOrigin(input) : resolveOrigin(httpDebugConfig(toolContext), environment);
        String targetUrl = origin + path;
        String method = validateMethod(MapUtils.getString(input, FIELD_METHOD, DEFAULT_METHOD));
        String cookie = validateCookie(MapUtils.getString(input, FIELD_COOKIE));
        CurlTarget target = new CurlTarget(sourceType, environment, origin, path, targetUrl, method, cookie);
        CurlExecutionRequest request = new CurlExecutionRequest(input, target);
        return execute(request, toolContext);
    }

    private String execute(CurlExecutionRequest request, ToolContext toolContext) {
        Process process = null;
        CompletableFuture<ProcessOutput> outputFuture = null;
        long startTime = System.currentTimeMillis();
        try {
            int timeout = timeoutSeconds(request.input());
            int maxOutputChars = maxOutputChars(request.input());
            List<String> command = buildCommand(
                    request.input(), request.target().targetUrl(), request.target().method(), timeout,
                    request.target().cookie());
            log.info("SkillFactory Curl工具开始执行, sourceType={}, environment={}, method={}, path={}, "
                            + "cookieProvided={}, "
                            + "timeout={}",
                    request.target().sourceType(), request.target().environment(), request.target().method(),
                    request.target().path(),
                    StringUtils.isNotBlank(request.target().cookie()), timeout);
            ProcessBuilder processBuilder = new ProcessBuilder(command);
            processBuilder.redirectErrorStream(true);
            process = processBuilder.start();
            outputFuture = drainOutput(process, maxOutputChars);
            writeBody(process, request.input());
            boolean finished = waitForProcess(process, timeout, toolContext);
            if (!finished) {
                terminateProcess(process);
                throw new ToolException("curl execution timed out", ToolException.ErrorCode.TIMEOUT);
            }
            ProcessOutput processOutput = outputFuture.get(OUTPUT_WAIT_SECONDS, TimeUnit.SECONDS);
            int exitCode = process.exitValue();
            long costMs = System.currentTimeMillis() - startTime;
            log.info("SkillFactory Curl工具执行完成, sourceType={}, environment={}, method={}, path={}, "
                            + "exitCode={}, costMs={}, "
                            + "outputLength={}, outputTruncated={}",
                    request.target().sourceType(), request.target().environment(), request.target().method(),
                    request.target().path(), exitCode, costMs,
                    StringUtils.length(processOutput.text()), processOutput.truncated());
            if (exitCode != 0) {
                throw new ToolException("curl exited with code " + exitCode + ": " + processOutput.text(),
                        ToolException.ErrorCode.EXECUTION_ERROR);
            }
            return structuredResult(
                    request.target().environment(), request.target().origin(), request.target().path(),
                    request.target().method(), costMs, processOutput);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            terminateProcess(process);
            throw new ToolException("curl execution interrupted", e, ToolException.ErrorCode.EXECUTION_ERROR);
        } catch (ExecutionException | TimeoutException e) {
            terminateProcess(process);
            throw new ToolException("curl output collection failed: " + e.getMessage(), e,
                    ToolException.ErrorCode.EXECUTION_ERROR);
        } catch (IOException e) {
            terminateProcess(process);
            throw new ToolException("curl execution failed: " + e.getMessage(), e,
                    ToolException.ErrorCode.EXECUTION_ERROR);
        } finally {
            if (outputFuture != null && !outputFuture.isDone()) {
                outputFuture.cancel(true);
            }
        }
    }

    private List<String> buildCommand(Map<String, Object> input, String targetUrl, String method, int timeout,
            String cookie) {
        List<String> command = Lists.newArrayList(
                "curl", "-sS", "--show-error",
                "--max-time", String.valueOf(timeout),
                "--request", method,
                "--write-out", "\n" + HTTP_STATUS_MARKER + "%{http_code}\n");
        appendHeaders(command, input);
        if (StringUtils.isNotBlank(cookie)) {
            command.add("--header");
            command.add("Cookie: " + cookie);
        }
        if (input.containsKey(FIELD_BODY) && input.get(FIELD_BODY) != null) {
            command.add("--data-binary");
            command.add("@-");
        }
        command.add(targetUrl);
        return command;
    }

    private void appendHeaders(List<String> command, Map<String, Object> input) {
        Object headersObject = input.get(FIELD_HEADERS);
        if (!(headersObject instanceof Map<?, ?> headers)) {
            return;
        }
        for (Map.Entry<?, ?> entry : headers.entrySet()) {
            String headerName = StringUtils.trimToEmpty(String.valueOf(entry.getKey()));
            if (StringUtils.isBlank(headerName)) {
                continue;
            }
            String normalizedHeaderName = normalizeHeaderName(headerName);
            if (isForbiddenHeaderName(normalizedHeaderName)) {
                throw new ToolException("curl header is controlled by backend: " + headerName,
                        ToolException.ErrorCode.PERMISSION_DENIED);
            }
            String headerValue = StringUtils.defaultString(String.valueOf(entry.getValue()));
            if (StringUtils.containsAny(headerName, "\r", "\n")
                    || StringUtils.containsAny(headerValue, "\r", "\n")) {
                throw new ToolException("curl header contains invalid newline",
                        ToolException.ErrorCode.INVALID_PARAMS);
            }
            command.add("--header");
            command.add(headerName + ": " + headerValue);
        }
    }

    private void writeBody(Process process, Map<String, Object> input) throws IOException {
        try (OutputStream stdin = process.getOutputStream()) {
            if (input.containsKey(FIELD_BODY) && input.get(FIELD_BODY) != null) {
                stdin.write(String.valueOf(input.get(FIELD_BODY)).getBytes(StandardCharsets.UTF_8));
            }
        }
    }

    private CompletableFuture<ProcessOutput> drainOutput(Process process, int maxOutputChars) {
        return CompletableFuture.supplyAsync(() -> {
            try {
                return readOutput(process, maxOutputChars);
            } catch (IOException e) {
                throw new IllegalStateException(e);
            }
        });
    }

    private ProcessOutput readOutput(Process process, int maxOutputChars) throws IOException {
        StringBuilder output = new StringBuilder();
        StringBuilder outputTail = new StringBuilder();
        boolean truncated = false;
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(process.getInputStream(), StandardCharsets.UTF_8))) {
            char[] buffer = new char[OUTPUT_BUFFER_CHARS];
            int count;
            while ((count = reader.read(buffer)) >= 0) {
                appendOutputTail(outputTail, buffer, count);
                int remaining = maxOutputChars - output.length();
                if (remaining > 0) {
                    output.append(buffer, 0, Math.min(remaining, count));
                }
                if (count > remaining) {
                    truncated = true;
                }
            }
        }
        if (truncated) {
            output.append("\n...[RESPONSE_TRUNCATED]...\n").append(outputTail);
        }
        return new ProcessOutput(output.toString(), truncated);
    }

    private void appendOutputTail(StringBuilder outputTail, char[] buffer, int count) {
        outputTail.append(buffer, 0, count);
        if (outputTail.length() > OUTPUT_TAIL_CHARS) {
            outputTail.delete(0, outputTail.length() - OUTPUT_TAIL_CHARS);
        }
    }

    private boolean waitForProcess(Process process, int timeoutSeconds, ToolContext toolContext)
            throws InterruptedException {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(timeoutSeconds);
        BooleanSupplier cancelChecker = cancelChecker(toolContext);
        while (System.nanoTime() < deadline) {
            if (cancelChecker.getAsBoolean()) {
                terminateProcess(process);
                throw new ToolException("curl execution cancelled", ToolException.ErrorCode.EXECUTION_ERROR);
            }
            if (process.waitFor(PROCESS_POLL_INTERVAL_MILLIS, TimeUnit.MILLISECONDS)) {
                return true;
            }
        }
        return false;
    }

    private String structuredResult(String environment, String origin, String path, String method, long costMs,
            ProcessOutput processOutput) {
        String output = processOutput.text();
        int markerIndex = output.lastIndexOf(HTTP_STATUS_MARKER);
        if (markerIndex < 0) {
            throw new ToolException("curl response missing HTTP status marker",
                    ToolException.ErrorCode.EXECUTION_ERROR);
        }
        String responseBody = StringUtils.removeEnd(output.substring(0, markerIndex), "\n");
        String statusText = StringUtils.substringBefore(
                output.substring(markerIndex + HTTP_STATUS_MARKER.length()), "\n").trim();
        int httpStatus;
        try {
            httpStatus = Integer.parseInt(statusText);
        } catch (NumberFormatException e) {
            throw new ToolException("curl returned invalid HTTP status: " + statusText, e,
                    ToolException.ErrorCode.EXECUTION_ERROR);
        }
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("transportSuccess", true);
        result.put("environment", environment);
        result.put("origin", origin);
        result.put("method", method);
        result.put("path", path);
        result.put("httpStatus", httpStatus);
        result.put("responseBody", responseBody);
        result.put("responseTruncated", processOutput.truncated());
        result.put("costMs", costMs);
        return JsonSupport.toJSON(result);
    }

    private String validateEnvironment(String environment) {
        String normalized = StringUtils.defaultIfBlank(
                environment, ENVIRONMENT_PRE_RELEASE).toUpperCase(Locale.ROOT);
        if (!ALLOWED_ENVIRONMENTS.contains(normalized)) {
            throw new ToolException("Unsupported curl environment: " + environment,
                    ToolException.ErrorCode.INVALID_PARAMS);
        }
        return normalized;
    }

    private String validateSourceType(String sourceType) {
        String normalized = StringUtils.defaultIfBlank(sourceType, SOURCE_TYPE_API_CENTER)
                .toUpperCase(Locale.ROOT);
        if (!ALLOWED_SOURCE_TYPES.contains(normalized)) {
            throw new ToolException("Unsupported curl sourceType: " + sourceType,
                    ToolException.ErrorCode.INVALID_PARAMS);
        }
        return normalized;
    }

    private String directOrigin(Map<String, Object> input) {
        String protocol = StringUtils.defaultIfBlank(MapUtils.getString(input, FIELD_PROTOCOL), PROTOCOL_HTTPS)
                .toLowerCase(Locale.ROOT);
        if (!StringUtils.equalsAny(protocol, PROTOCOL_HTTP, PROTOCOL_HTTPS)) {
            throw new ToolException("HTTP_REQUEST protocol must be http or https",
                    ToolException.ErrorCode.INVALID_PARAMS);
        }
        String host = StringUtils.trimToEmpty(MapUtils.getString(input, FIELD_HOST));
        if (StringUtils.isBlank(host) || !host.matches("^[A-Za-z0-9.-]+$")) {
            throw new ToolException("HTTP_REQUEST host is missing or invalid",
                    ToolException.ErrorCode.INVALID_PARAMS);
        }
        int port = directPort(input.get(FIELD_PORT));
        return protocol + "://" + host + (port == 0 ? StringUtils.EMPTY : ":" + port);
    }

    private int directPort(Object value) {
        if (value == null || StringUtils.isBlank(String.valueOf(value))) {
            return 0;
        }
        if (!(value instanceof Number)) {
            throw new ToolException("HTTP_REQUEST port must be an integer",
                    ToolException.ErrorCode.INVALID_PARAMS);
        }
        int port = ((Number) value).intValue();
        if (port < 1 || port > 65535) {
            throw new ToolException("HTTP_REQUEST port must be between 1 and 65535",
                    ToolException.ErrorCode.INVALID_PARAMS);
        }
        return port;
    }

    private String validatePath(String path) {
        String normalized = StringUtils.trimToEmpty(path);
        if (!StringUtils.startsWith(normalized, "/")
                || StringUtils.startsWith(normalized, "//")
                || StringUtils.contains(normalized, "://")
                || StringUtils.containsAny(normalized, "\r", "\n", "#")) {
            throw new ToolException("curl path must begin with / and must not contain origin or fragment",
                    ToolException.ErrorCode.INVALID_PARAMS);
        }
        return normalized;
    }

    private String validateMethod(String method) {
        String normalized = StringUtils.defaultIfBlank(method, DEFAULT_METHOD).toUpperCase(Locale.ROOT);
        if (!ALLOWED_METHODS.contains(normalized)) {
            throw new ToolException("Unsupported HTTP method: " + method, ToolException.ErrorCode.INVALID_PARAMS);
        }
        return normalized;
    }

    private String validateCookie(String cookie) {
        String value = StringUtils.defaultString(cookie);
        if (StringUtils.containsAny(value, "\r", "\n")) {
            throw new ToolException("curl Cookie contains invalid newline",
                    ToolException.ErrorCode.INVALID_PARAMS);
        }
        return value;
    }

    private int timeoutSeconds(Map<String, Object> input) {
        Object timeoutObject = input.get(FIELD_TIMEOUT);
        if (!(timeoutObject instanceof Number timeoutNumber)) {
            return DEFAULT_TIMEOUT_SECONDS;
        }
        return Math.max(1, Math.min(timeoutNumber.intValue(), MAX_TIMEOUT_SECONDS));
    }

    private int maxOutputChars(Map<String, Object> input) {
        Object maxOutputObject = input.get(FIELD_MAX_OUTPUT_CHARS);
        if (!(maxOutputObject instanceof Number maxOutputNumber)) {
            return DEFAULT_MAX_OUTPUT_CHARS;
        }
        return Math.max(1, Math.min(maxOutputNumber.intValue(), HARD_MAX_OUTPUT_CHARS));
    }

    private String resolveOrigin(SkillFactoryHttpDebugConfig config, String environment) {
        String configuredOrigin = ENVIRONMENT_PRODUCTION.equals(environment)
                                  ? config.getProductionOrigin() : config.getPreReleaseOrigin();
        String origin = StringUtils.removeEnd(StringUtils.trimToEmpty(configuredOrigin), "/");
        try {
            URI uri = URI.create(origin);
            if (!StringUtils.equalsAnyIgnoreCase(uri.getScheme(), "http", "https")
                    || StringUtils.isBlank(uri.getHost())
                    || uri.getUserInfo() != null
                    || StringUtils.isNotBlank(uri.getQuery())
                    || StringUtils.isNotBlank(uri.getFragment())
                    || StringUtils.isNotBlank(StringUtils.remove(uri.getPath(), "/"))) {
                throw new IllegalArgumentException("invalid origin");
            }
            return origin;
        } catch (IllegalArgumentException e) {
            throw new ToolException("curl environment origin is missing or invalid",
                    e, ToolException.ErrorCode.EXECUTION_ERROR);
        }
    }

    private SkillFactoryHttpDebugConfig httpDebugConfig(ToolContext toolContext) {
        Object config = toolContext.getContext().get(CONTEXT_HTTP_DEBUG_CONFIG);
        if (!(config instanceof SkillFactoryHttpDebugConfig httpDebugConfig)) {
            throw new ToolException("curl HTTP debug config is missing",
                    ToolException.ErrorCode.EXECUTION_ERROR);
        }
        return httpDebugConfig;
    }

    private BooleanSupplier cancelChecker(ToolContext toolContext) {
        Object checker = toolContext.getContext().get(SkillFactoryToolPathResolver.CONTEXT_CANCEL_CHECKER);
        return checker instanceof BooleanSupplier supplier ? supplier : () -> false;
    }

    private String normalizeHeaderName(String headerName) {
        return StringUtils.defaultString(headerName)
                .replace("-", "")
                .replace("_", "")
                .trim()
                .toLowerCase(Locale.ROOT);
    }

    private boolean isForbiddenHeaderName(String normalizedHeaderName) {
        return FORBIDDEN_HEADER_NAMES.contains(normalizedHeaderName)
                || StringUtils.endsWith(normalizedHeaderName, "cookie")
                || FORBIDDEN_CREDENTIAL_HEADER_PARTS.stream().anyMatch(normalizedHeaderName::contains);
    }

    private void terminateProcess(Process process) {
        if (process == null || !process.isAlive()) {
            return;
        }
        process.destroyForcibly();
        try {
            process.waitFor(OUTPUT_WAIT_SECONDS, TimeUnit.SECONDS);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    private record ProcessOutput(String text, boolean truncated) {
    }

    private record CurlExecutionRequest(
            Map<String, Object> input,
            CurlTarget target) {
    }

    private record CurlTarget(
            String sourceType,
            String environment,
            String origin,
            String path,
            String targetUrl,
            String method,
            String cookie) {
    }
}
