package dev.a2flow.management.aicoding.validation;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
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
 * SkillFactory 只读模拟 Skill 请求服务。
 *
 * <p>该服务是 `simulate_skill_request` 工具的后端实现。它只读取
 * `{workspaceRoot}/{workspaceId}/preprod/current`，不写 workspace、不生成 patch、不触发业务副作用。
 * 在真实 adviser/runtime adapter 接入前，服务会明确返回 PARTIAL，禁止把静态文件扫描伪装成 PASSED。
 */
@SuppressWarnings("checkstyle:MagicNumber")
@Slf4j
@Component
public class SkillFactorySimulateSkillRequestService {

    private static final String FIELD_WORKSPACE_ID = "workspaceId";
    private static final String FIELD_SKILL_CODE = "skillCode";
    private static final String FIELD_WORKSPACE_ROOT = "workspaceRoot";
    private static final String FIELD_TEST_INPUT = "testInput";
    private static final String FIELD_MESSAGE = "message";
    private static final String PREPROD_DIR = "preprod";
    private static final String CURRENT_DIR = "current";
    private static final int PREVIEW_FILE_COUNT = 6;
    private static final int PREVIEW_BYTES = 4096;
    private static final Pattern SAFE_WORKSPACE_ID = Pattern.compile("[A-Za-z0-9._-]+");

    @Resource
    private WorkspaceSnapshotService workspaceSnapshotService;

    /**
     * 执行只读模拟请求。
     */
    public SkillSimulationResult simulate(Map<String, String> params) {
        long startTime = System.currentTimeMillis();
        String workspaceId = StringUtils.defaultIfBlank(MapUtils.getString(params, FIELD_WORKSPACE_ID),
                MapUtils.getString(params, FIELD_SKILL_CODE));
        String skillCode = StringUtils.defaultIfBlank(MapUtils.getString(params, FIELD_SKILL_CODE), workspaceId);
        String testInput = StringUtils.defaultIfBlank(MapUtils.getString(params, FIELD_TEST_INPUT),
                MapUtils.getString(params, FIELD_MESSAGE));
        SkillSimulationResult result = new SkillSimulationResult()
                .setSimulationId("simulation_" + UUID.randomUUID().toString().replace("-", ""))
                .setWorkspaceId(workspaceId)
                .setSkillCode(skillCode)
                .setTestInput(testInput)
                .setTimestamp(System.currentTimeMillis());
        try {
            Path workingDir = resolveWorkingDir(params, workspaceId);
            if (!Files.isDirectory(workingDir)) {
                return result.setStatus(SkillSimulationResult.STATUS_FAILED)
                        .setReason("WORKSPACE_NOT_FOUND")
                        .setRawOutput("当前 Skill 可编辑区不存在: " + workingDir)
                        .setStdoutSummary("preprod/current 不存在，无法模拟请求。");
            }
            List<Path> files = listRegularFiles(workingDir);
            WorkspaceSnapshot snapshot = workspaceSnapshotService.capture(workingDir);
            String digest = snapshot.getFileTreeDigest();
            Map<String, Object> metadata = new HashMap<>();
            metadata.put("toolName", SkillSimulationResult.TOOL_NAME);
            metadata.put("called", true);
            metadata.put("workspaceFileCount", files.size());
            metadata.put("workingDir", workingDir.toString());
            metadata.put("readOnly", true);
            metadata.put("noPatch", true);
            metadata.put("noWorkspaceWrite", true);
            String preview = workspacePreview(workingDir, files);
            String rawOutput = JsonSupport.toJSON(Map.of(
                    "simulationStatus", "RUNTIME_ADAPTER_NOT_CONNECTED",
                    "testInput", StringUtils.defaultString(testInput),
                    "fileTreeDigest", digest,
                    "workspacePreview", preview));
            result.setStatus(SkillSimulationResult.STATUS_PARTIAL)
                    .setReason("RUNTIME_ADAPTER_NOT_CONNECTED")
                    .setFileTreeDigest(digest)
                    .setRawOutput(rawOutput)
                    .setStdoutSummary("simulate_skill_request 已只读读取 workspace，但真实 Skill runtime adapter 尚未接入。")
                    .setRuntimeAdapterConnected(false)
                    .setMetadata(metadata);
            log.info("SkillFactory模拟Skill请求完成, simulationId={}, workspaceId={}, skillCode={}, "
                            + "status={}, fileCount={}, costMs={}",
                    result.getSimulationId(), workspaceId, skillCode, result.getStatus(), files.size(),
                    System.currentTimeMillis() - startTime);
            return result;
        } catch (Exception e) {
            log.error("SkillFactory模拟Skill请求异常, workspaceId={}, skillCode={}", workspaceId, skillCode, e);
            return result.setStatus(SkillSimulationResult.STATUS_FAILED)
                    .setReason("SIMULATE_TOOL_ERROR")
                    .setRawOutput(StringUtils.defaultString(e.getMessage()))
                    .setStdoutSummary("simulate_skill_request 执行失败: " + StringUtils.defaultString(e.getMessage()));
        }
    }

    private Path resolveWorkingDir(Map<String, String> params, String workspaceId) {
        String workspaceRoot = MapUtils.getString(params, FIELD_WORKSPACE_ROOT);
        if (StringUtils.isBlank(workspaceRoot)) {
            throw new IllegalArgumentException("workspaceRoot 为空，无法模拟 Skill 请求");
        }
        if (StringUtils.isBlank(workspaceId) || !SAFE_WORKSPACE_ID.matcher(workspaceId).matches()) {
            throw new IllegalArgumentException("workspaceId 非法，无法模拟 Skill 请求");
        }
        Path root = Paths.get(workspaceRoot).toAbsolutePath().normalize();
        Path identityRoot = root.resolve(workspaceId).normalize();
        Path workingDir = identityRoot.resolve(PREPROD_DIR).resolve(CURRENT_DIR).normalize();
        if (!workingDir.startsWith(identityRoot)) {
            throw new IllegalArgumentException("工作区路径越界，拒绝模拟 Skill 请求");
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

    private String workspacePreview(Path workingDir, List<Path> files) {
        StringBuilder builder = new StringBuilder();
        files.stream().limit(PREVIEW_FILE_COUNT).forEach(file -> {
            Path relative = workingDir.relativize(file);
            builder.append("\n--- file: ").append(relative).append(" ---\n");
            builder.append(readPreview(file));
        });
        return StringUtils.abbreviate(builder.toString(), 12000);
    }

    private String readPreview(Path file) {
        try {
            byte[] bytes = Files.readAllBytes(file);
            int limit = Math.min(bytes.length, PREVIEW_BYTES);
            return new String(bytes, 0, limit, StandardCharsets.UTF_8);
        } catch (Exception e) {
            return "文件读取失败: " + StringUtils.defaultString(e.getMessage());
        }
    }

}
