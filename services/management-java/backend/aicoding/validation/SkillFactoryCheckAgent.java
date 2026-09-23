package dev.a2flow.management.aicoding.validation;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Collectors;
import java.util.stream.Stream;

import jakarta.annotation.Resource;

import org.apache.commons.collections4.MapUtils;
import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Component;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.fileguard.WorkspaceSnapshot;
import dev.a2flow.management.fileguard.WorkspaceSnapshotService;

import lombok.extern.slf4j.Slf4j;

/**
 * SkillFactory 动态验证 CheckAgent。
 *
 * <p>该组件是 AI Coding 主 Agent 的只读子任务：读取当前
 * `{workspaceRoot}/{skillCode}/preprod/current` 快照，识别 Skill 输出协议并形成
 * `ValidationReport`。它不生成代码、不写 workspace、不创建 patch，也不实现 lifecycle 发布接口。
 */
@SuppressWarnings("checkstyle:MagicNumber")
@Slf4j
@Component
public class SkillFactoryCheckAgent {

    private static final String FIELD_WORKSPACE_ID = "workspaceId";
    private static final String FIELD_SKILL_CODE = "skillCode";
    private static final String FIELD_WORKSPACE_ROOT = "workspaceRoot";
    private static final String FIELD_TEST_INPUT = "testInput";
    private static final String FIELD_MESSAGE = "message";
    private static final String FIELD_USER_NAME = "userName";
    private static final String FIELD_REFERENCE_RENDER_ASSETS = "referenceRenderAssets";
    private static final String DEFAULT_TEST_INPUT = "请用当前 Skill 处理一个典型用户请求";
    private static final String PREPROD_DIR = "preprod";
    private static final String CURRENT_DIR = "current";
    private static final String STATUS_PASSED = ValidationReport.STATUS_PASSED;
    private static final String STATUS_FAILED = ValidationReport.STATUS_FAILED;
    private static final String STATUS_PARTIAL = ValidationReport.STATUS_PARTIAL;
    private static final String PROTOCOL_AGENT_UI_DSL = "agentUiDsl";
    private static final String PROTOCOL_COMPONENT_NAME = "componentName";
    private static final String PROTOCOL_LOCAL_METHOD = "localMethod";
    private static final String PROTOCOL_TEXT = "text";
    private static final String PROTOCOL_UNKNOWN = "unknown";
    private static final String ISSUE_ERROR = "ERROR";
    private static final String ISSUE_WARN = "WARN";
    private static final int MAX_READ_FILE_COUNT = 8;
    private static final int MAX_READ_FILE_BYTES = 12 * 1024;
    private static final int RAW_OUTPUT_MAX_LENGTH = 24000;
    private static final Pattern SAFE_WORKSPACE_ID = Pattern.compile("[A-Za-z0-9._-]+");
    private static final Pattern JSON_STRING_FIELD =
            Pattern.compile("\"%s\"\\s*:\\s*\"([^\"]+)\"");
    private static final Pattern YAML_STRING_FIELD =
            Pattern.compile("(?m)^\\s*%s\\s*:\\s*['\"]?([^'\"\\n#]+)['\"]?\\s*$");

    @Resource
    private SkillFactorySimulateSkillRequestService simulateSkillRequestService;

    @Resource
    private WorkspaceSnapshotService workspaceSnapshotService;

    /**
     * 对当前 Skill 工作区执行只读动态验证。
     */
    public ValidationReport validate(Map<String, String> params) {
        long startTime = System.currentTimeMillis();
        ValidationTaskSpec task = buildTaskSpec(params);
        ValidationReport report = new ValidationReport()
                .setTaskId(task.getTaskId())
                .setReportId(task.getTaskId())
                .setWorkspaceId(task.getWorkspaceId())
                .setSkillCode(task.getSkillCode())
                .setTestInput(task.getTestInput());
        log.info("SkillFactoryCheckAgent开始只读验证, taskId={}, workspaceId={}, skillCode={}, "
                        + "testInputLength={}, referenceAssetCount={}",
                task.getTaskId(), task.getWorkspaceId(), task.getSkillCode(),
                StringUtils.length(task.getTestInput()), task.getReferenceRenderAssets().size());
        try {
            Path workingDir = resolveWorkingDir(params, task.getWorkspaceId());
            report.getChecks().add(newCheck("readOnly", "只读执行约束", STATUS_PASSED,
                    "CheckAgent 仅读取 preprod/current，不生成 patch，不写 workspace。"));
            SkillSimulationResult simulationResult = simulateSkillRequestService.simulate(params);
            report.setSimulationEvidence(simulationEvidence(simulationResult));
            appendSimulationCheck(report, simulationResult);
            if (!Files.isDirectory(workingDir)) {
                report.getChecks().add(newCheck("workspaceSnapshot", "读取当前 workspace 快照", STATUS_FAILED,
                        "当前 Skill 可编辑区不存在: " + workingDir));
                report.getIssues().add(newIssue(ISSUE_ERROR, "workspace",
                        "未找到 preprod/current 工作区。", "请先通过注册或新建变更创建当前工作区。"));
                return finish(report, STATUS_FAILED, workingDir, startTime);
            }

            WorkspaceSnapshot snapshot = workspaceSnapshotService.capture(workingDir);
            String digest = snapshot.getFileTreeDigest();
            task.setFileTreeDigest(digest);
            report.setFileTreeDigest(digest);
            List<Path> files = listRegularFiles(workingDir);
            report.getChecks().add(newCheck("workspaceSnapshot", "读取当前 workspace 快照", STATUS_PASSED,
                    "已读取文件 " + files.size() + " 个，digest=" + digest));
            appendEntryChecks(report, workingDir, files);

            String rawOutput = StringUtils.defaultIfBlank(simulationResult.getRawOutput(),
                    captureWorkspaceOutput(workingDir, files));
            report.setRawOutput(rawOutput);
            report.setStdoutSummary(StringUtils.defaultIfBlank(simulationResult.getStdoutSummary(),
                    StringUtils.abbreviate(rawOutput.replaceAll("\\s+", " ").trim(), 600)));
            report.setProtocol(detectProtocol(rawOutput));
            appendProtocolChecks(report);
            appendRuntimeCheck(report, simulationResult);
            return finish(report, resolveStatus(report), workingDir, startTime);
        } catch (Exception e) {
            log.error("SkillFactoryCheckAgent只读验证异常, taskId={}, workspaceId={}, skillCode={}",
                    task.getTaskId(), task.getWorkspaceId(), task.getSkillCode(), e);
            report.getChecks().add(newCheck("checkAgent", "CheckAgent 执行", STATUS_FAILED,
                    StringUtils.defaultString(e.getMessage())));
            report.getIssues().add(newIssue(ISSUE_ERROR, "check-agent",
                    "CheckAgent 执行异常: " + StringUtils.defaultString(e.getMessage()),
                    "请根据日志定位工作区路径、文件编码或协议解析问题。"));
            return finish(report, STATUS_FAILED, null, startTime);
        }
    }

    private ValidationTaskSpec buildTaskSpec(Map<String, String> params) {
        String workspaceId = StringUtils.defaultIfBlank(MapUtils.getString(params, FIELD_WORKSPACE_ID),
                MapUtils.getString(params, FIELD_SKILL_CODE));
        String skillCode = StringUtils.defaultIfBlank(MapUtils.getString(params, FIELD_SKILL_CODE), workspaceId);
        String testInput = StringUtils.defaultIfBlank(MapUtils.getString(params, FIELD_TEST_INPUT),
                StringUtils.defaultIfBlank(MapUtils.getString(params, FIELD_MESSAGE), DEFAULT_TEST_INPUT));
        Map<String, Object> mockContext = new HashMap<>();
        mockContext.put("digitalEmployeeId", "mock");
        mockContext.put("operator", StringUtils.defaultString(MapUtils.getString(params, FIELD_USER_NAME)));
        return new ValidationTaskSpec()
                .setTaskId("validation_" + UUID.randomUUID().toString().replace("-", ""))
                .setWorkspaceId(workspaceId)
                .setSkillCode(skillCode)
                .setTestInput(testInput)
                .setMockContext(mockContext)
                .setReferenceRenderAssets(parseReferenceRenderAssets(
                        MapUtils.getString(params, FIELD_REFERENCE_RENDER_ASSETS)));
    }

    private void appendSimulationCheck(ValidationReport report, SkillSimulationResult simulationResult) {
        if (simulationResult == null) {
            report.getChecks().add(newCheck("simulateSkillRequest", "模拟 Skill 请求", STATUS_FAILED,
                    "simulate_skill_request 未返回结果。"));
            report.getIssues().add(newIssue(ISSUE_ERROR, "runtime",
                    "未拿到 simulate_skill_request 工具证据。", "确认 CheckAgent 配置包含 simulate_skill_request 工具。"));
            return;
        }
        String status = StringUtils.defaultIfBlank(simulationResult.getStatus(), STATUS_FAILED);
        report.getChecks().add(newCheck("simulateSkillRequest", "模拟 Skill 请求", status,
                "simulate_skill_request 已执行，状态=" + status + "，原因="
                        + StringUtils.defaultString(simulationResult.getReason())));
        if (!StringUtils.equals(STATUS_PASSED, status)) {
            report.getIssues().add(newIssue(
                    StringUtils.equals(STATUS_FAILED, status) ? ISSUE_ERROR : ISSUE_WARN,
                    "runtime",
                    "模拟 Skill 请求未完全通过: " + StringUtils.defaultString(simulationResult.getReason()),
                    "接入真实 Skill runtime adapter 后再判断真实输出是否符合预期。"));
        }
    }

    private Map<String, Object> simulationEvidence(SkillSimulationResult simulationResult) {
        if (simulationResult == null) {
            return Map.of("toolName", SkillSimulationResult.TOOL_NAME, "called", false);
        }
        Map<String, Object> evidence = new HashMap<>();
        evidence.put("toolName", SkillSimulationResult.TOOL_NAME);
        evidence.put("called", true);
        evidence.put("simulationId", simulationResult.getSimulationId());
        evidence.put("status", simulationResult.getStatus());
        evidence.put("reason", simulationResult.getReason());
        evidence.put("runtimeAdapterConnected", simulationResult.isRuntimeAdapterConnected());
        evidence.put("fileTreeDigest", simulationResult.getFileTreeDigest());
        evidence.put("metadata", simulationResult.getMetadata());
        return evidence;
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> parseReferenceRenderAssets(String value) {
        if (StringUtils.isBlank(value)) {
            return new ArrayList<>();
        }
        try {
            Object parsed = JsonSupport.fromJSON(value, Object.class);
            if (!(parsed instanceof List)) {
                return new ArrayList<>();
            }
            List<?> list = (List<?>) parsed;
            return list.stream()
                    .filter(Map.class::isInstance)
                    .map(item -> (Map<String, Object>) item)
                    .collect(Collectors.toList());
        } catch (Exception e) {
            log.info("SkillFactoryCheckAgent解析参考资产失败，按空列表处理, payloadLength={}",
                    StringUtils.length(value));
            return new ArrayList<>();
        }
    }

    private Path resolveWorkingDir(Map<String, String> params, String workspaceId) {
        String workspaceRoot = MapUtils.getString(params, FIELD_WORKSPACE_ROOT);
        if (StringUtils.isBlank(workspaceRoot)) {
            throw new IllegalArgumentException("workspaceRoot 为空，无法执行动态验证");
        }
        if (StringUtils.isBlank(workspaceId) || !SAFE_WORKSPACE_ID.matcher(workspaceId).matches()) {
            throw new IllegalArgumentException("workspaceId 非法，无法执行动态验证");
        }
        Path root = Paths.get(workspaceRoot).toAbsolutePath().normalize();
        Path identityRoot = root.resolve(workspaceId).normalize();
        Path workingDir = identityRoot.resolve(PREPROD_DIR).resolve(CURRENT_DIR).normalize();
        if (!workingDir.startsWith(identityRoot)) {
            throw new IllegalArgumentException("工作区路径越界，拒绝动态验证");
        }
        return workingDir;
    }

    private List<Path> listRegularFiles(Path workingDir) throws IOException {
        try (Stream<Path> stream = Files.walk(workingDir)) {
            return stream.filter(Files::isRegularFile)
                    .sorted(Comparator.comparing(path -> workingDir.relativize(path).toString()))
                    .collect(Collectors.toList());
        }
    }

    private void appendEntryChecks(ValidationReport report, Path workingDir, List<Path> files) {
        boolean hasSkillMarkdown = Files.isRegularFile(workingDir.resolve("SKILL.md"));
        boolean hasSkillYaml = Files.isRegularFile(workingDir.resolve("skill.yaml"))
                || Files.isRegularFile(workingDir.resolve("skill.yml"));
        if (hasSkillMarkdown || hasSkillYaml) {
            report.getChecks().add(newCheck("skillEntry", "Skill 入口文件", STATUS_PASSED,
                    hasSkillMarkdown ? "已找到 SKILL.md。" : "已找到 skill.yaml / skill.yml。"));
        } else {
            report.getChecks().add(newCheck("skillEntry", "Skill 入口文件", STATUS_FAILED,
                    "缺少 SKILL.md 或 skill.yaml。"));
            report.getIssues().add(newIssue(ISSUE_ERROR, "skill-output",
                    "当前工作区缺少 Skill 入口文件。", "补齐 SKILL.md 或 skill.yaml 后再运行验证。"));
        }
        if (files.isEmpty()) {
            report.getChecks().add(newCheck("workspaceFiles", "工作区文件", STATUS_FAILED,
                    "当前 preprod/current 没有任何文件。"));
            report.getIssues().add(newIssue(ISSUE_ERROR, "workspace",
                    "当前工作区为空，无法执行动态验证。", "先用 Chat 或 ZIP 导入生成 Skill 文件。"));
        } else {
            report.getChecks().add(newCheck("workspaceFiles", "工作区文件", STATUS_PASSED,
                    "当前 preprod/current 文件数: " + files.size()));
        }
    }

    private String captureWorkspaceOutput(Path workingDir, List<Path> files) {
        StringBuilder builder = new StringBuilder();
        List<Path> candidates = files.stream()
                .filter(this::isReadableCandidate)
                .limit(MAX_READ_FILE_COUNT)
                .collect(Collectors.toList());
        for (Path file : candidates) {
            Path relative = workingDir.relativize(file);
            builder.append("\n--- file: ").append(relative).append(" ---\n");
            builder.append(readPreview(file));
        }
        return StringUtils.abbreviate(builder.toString(), RAW_OUTPUT_MAX_LENGTH);
    }

    private boolean isReadableCandidate(Path path) {
        String fileName = StringUtils.lowerCase(path.getFileName().toString());
        return fileName.endsWith(".md")
                || fileName.endsWith(".json")
                || fileName.endsWith(".yaml")
                || fileName.endsWith(".yml")
                || fileName.endsWith(".txt")
                || StringUtils.equals(fileName, "skill");
    }

    private String readPreview(Path file) {
        try {
            byte[] bytes = Files.readAllBytes(file);
            int limit = Math.min(bytes.length, MAX_READ_FILE_BYTES);
            return new String(bytes, 0, limit, StandardCharsets.UTF_8);
        } catch (Exception e) {
            return "文件读取失败: " + StringUtils.defaultString(e.getMessage());
        }
    }

    private ValidationReport.Protocol detectProtocol(String rawOutput) {
        ValidationReport.Protocol protocol = new ValidationReport.Protocol()
                .setType(PROTOCOL_UNKNOWN)
                .setCode(StringUtils.EMPTY)
                .setPayload(Map.of());
        if (StringUtils.isBlank(rawOutput)) {
            return protocol;
        }
        Object parsedJson = tryParseJson(rawOutput);
        String agentUiDsl = findStringKey(parsedJson, PROTOCOL_AGENT_UI_DSL);
        if (StringUtils.isBlank(agentUiDsl)) {
            agentUiDsl = extractField(rawOutput, PROTOCOL_AGENT_UI_DSL);
        }
        if (StringUtils.isNotBlank(agentUiDsl)) {
            return protocol.setType(PROTOCOL_AGENT_UI_DSL).setCode(agentUiDsl).setPayload(parsedJsonPayload(parsedJson));
        }
        String componentName = findStringKey(parsedJson, PROTOCOL_COMPONENT_NAME);
        if (StringUtils.isBlank(componentName)) {
            componentName = extractField(rawOutput, PROTOCOL_COMPONENT_NAME);
        }
        if (StringUtils.isNotBlank(componentName)) {
            return protocol.setType(PROTOCOL_COMPONENT_NAME).setCode(componentName)
                    .setPayload(parsedJsonPayload(parsedJson));
        }
        String localMethod = findStringKey(parsedJson, PROTOCOL_LOCAL_METHOD);
        if (StringUtils.isBlank(localMethod)) {
            localMethod = extractField(rawOutput, PROTOCOL_LOCAL_METHOD);
        }
        if (StringUtils.isNotBlank(localMethod)) {
            return protocol.setType(PROTOCOL_LOCAL_METHOD).setCode(localMethod)
                    .setPayload(parsedJsonPayload(parsedJson));
        }
        return protocol.setType(PROTOCOL_TEXT).setCode(StringUtils.EMPTY).setPayload(Map.of("preview",
                StringUtils.abbreviate(rawOutput.replaceAll("\\s+", " ").trim(), 500)));
    }

    private Object tryParseJson(String value) {
        String trimmed = StringUtils.trimToEmpty(value);
        if (!trimmed.startsWith("{") && !trimmed.startsWith("[")) {
            return null;
        }
        try {
            return JsonSupport.fromJSON(trimmed, Object.class);
        } catch (Exception e) {
            return null;
        }
    }

    private Object parsedJsonPayload(Object parsedJson) {
        return parsedJson == null ? Map.of() : parsedJson;
    }

    @SuppressWarnings("unchecked")
    private String findStringKey(Object node, String key) {
        if (node instanceof Map) {
            Map<Object, Object> map = (Map<Object, Object>) node;
            Object value = map.get(key);
            if (value != null && !(value instanceof Map) && !(value instanceof List)) {
                return StringUtils.trimToEmpty(String.valueOf(value));
            }
            for (Object child : map.values()) {
                String nested = findStringKey(child, key);
                if (StringUtils.isNotBlank(nested)) {
                    return nested;
                }
            }
        }
        if (node instanceof List) {
            for (Object child : (List<?>) node) {
                String nested = findStringKey(child, key);
                if (StringUtils.isNotBlank(nested)) {
                    return nested;
                }
            }
        }
        return StringUtils.EMPTY;
    }

    private String extractField(String rawOutput, String key) {
        String jsonRegex = String.format(JSON_STRING_FIELD.pattern(), Pattern.quote(key));
        Matcher jsonMatcher = Pattern.compile(jsonRegex).matcher(rawOutput);
        if (jsonMatcher.find()) {
            return StringUtils.trimToEmpty(jsonMatcher.group(1));
        }
        String yamlRegex = String.format(YAML_STRING_FIELD.pattern(), Pattern.quote(key));
        Matcher yamlMatcher = Pattern.compile(yamlRegex).matcher(rawOutput);
        if (yamlMatcher.find()) {
            return StringUtils.trimToEmpty(yamlMatcher.group(1));
        }
        return StringUtils.EMPTY;
    }

    private void appendProtocolChecks(ValidationReport report) {
        String protocolType = report.getProtocol() == null ? PROTOCOL_UNKNOWN : report.getProtocol().getType();
        if (StringUtils.equals(protocolType, PROTOCOL_UNKNOWN)) {
            report.getChecks().add(newCheck("protocolIdentify", "输出协议识别", STATUS_FAILED,
                    "未识别到 agentUiDsl、componentName、localMethod 或文本输出。"));
            report.getIssues().add(newIssue(ISSUE_ERROR, "skill-output",
                    "当前输出协议无法识别。", "在 SKILL.md / 示例中明确输出 agentUiDsl、componentName 或 localMethod。"));
            return;
        }
        if (StringUtils.equals(protocolType, PROTOCOL_TEXT)) {
            report.getChecks().add(newCheck("protocolIdentify", "输出协议识别", STATUS_PARTIAL,
                    "只识别到文本 / Markdown 输出，未发现可渲染协议。"));
            report.getIssues().add(newIssue(ISSUE_WARN, "runtime",
                    "当前输出可能只能按文本承接。", "如果需要前端卡片，请补齐 agentUiDsl + params 或 componentName + data。"));
            return;
        }
        report.getChecks().add(newCheck("protocolIdentify", "输出协议识别", STATUS_PASSED,
                "识别到 " + protocolType + "=" + StringUtils.defaultString(report.getProtocol().getCode())));
    }

    private void appendRuntimeCheck(ValidationReport report, SkillSimulationResult simulationResult) {
        if (simulationResult == null || !simulationResult.isRuntimeAdapterConnected()) {
            report.getChecks().add(newCheck("runtimeAdapter", "adviser runtime 承接", STATUS_PARTIAL,
                    "simulate_skill_request 已执行，但真实 adviser runtime / renderer / EntityContext 尚未接入本链路。"));
            report.getIssues().add(newIssue(ISSUE_WARN, "runtime",
                    "运行态承接校验仍为 PARTIAL。", "接入 adviser runtime API 后补充 A2UI 转换、action 和 EntityContext 校验。"));
            return;
        }
        report.getChecks().add(newCheck("runtimeAdapter", "adviser runtime 承接", STATUS_PASSED,
                "simulate_skill_request 已通过真实 runtime adapter 返回结果。"));
    }

    private String resolveStatus(ValidationReport report) {
        boolean failed = report.getChecks().stream()
                .anyMatch(item -> StringUtils.equals(STATUS_FAILED, item.getStatus()));
        if (failed) {
            return STATUS_FAILED;
        }
        boolean partial = report.getChecks().stream()
                .anyMatch(item -> StringUtils.equals(STATUS_PARTIAL, item.getStatus()));
        return partial ? STATUS_PARTIAL : STATUS_PASSED;
    }

    private ValidationReport finish(ValidationReport report, String status, Path workingDir, long startTime) {
        if (StringUtils.isBlank(report.getReportId())) {
            report.setReportId(report.getTaskId());
        }
        report.setStatus(status);
        report.setRepairPrompt(buildRepairPrompt(report));
        log.info("SkillFactoryCheckAgent只读验证完成, taskId={}, workspaceId={}, skillCode={}, status={}, "
                        + "checkCount={}, issueCount={}, workingDir={}, costMs={}",
                report.getTaskId(), report.getWorkspaceId(), report.getSkillCode(), report.getStatus(),
                report.getChecks().size(), report.getIssues().size(), workingDir, System.currentTimeMillis() - startTime);
        return report;
    }

    private String buildRepairPrompt(ValidationReport report) {
        return "请基于以下运行验证报告修复当前 Skill，只能生成 patch 草稿，不能直接写文件。"
                + "\nstatus=" + StringUtils.defaultString(report.getStatus())
                + "\nprotocol=" + JsonSupport.toJSON(report.getProtocol())
                + "\nchecks=" + JsonSupport.toJSON(report.getChecks())
                + "\nissues=" + JsonSupport.toJSON(report.getIssues());
    }

    private ValidationReport.CheckItem newCheck(String key, String label, String status, String message) {
        return new ValidationReport.CheckItem()
                .setKey(key)
                .setLabel(label)
                .setStatus(status)
                .setMessage(message);
    }

    private ValidationReport.Issue newIssue(String severity, String source, String message, String repairHint) {
        return new ValidationReport.Issue()
                .setSeverity(severity)
                .setSource(source)
                .setMessage(message)
                .setRepairHint(repairHint);
    }
}
