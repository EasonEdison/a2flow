package dev.a2flow.management.aicoding.validation;

import java.util.HashMap;
import java.util.Map;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * SkillFactory 只读模拟 Skill 请求结果。
 *
 * <p>`simulate_skill_request` 工具返回该对象，CheckAgent 必须基于它生成 ValidationReport。
 * 当前对象区分“工具已执行”和“真实 runtime adapter 是否接通”，避免把静态文件扫描伪装成真实运行通过。
 */
@Data
@Accessors(chain = true)
public class SkillSimulationResult {

    public static final String STATUS_PASSED = "PASSED";
    public static final String STATUS_FAILED = "FAILED";
    public static final String STATUS_PARTIAL = "PARTIAL";
    public static final String TOOL_NAME = "simulate_skill_request";

    private String simulationId;
    private String status;
    private String reason;
    private String workspaceId;
    private String skillCode;
    private String testInput;
    private String fileTreeDigest;
    private String rawOutput;
    private String stdoutSummary;
    private boolean runtimeAdapterConnected;
    private long timestamp;
    private Map<String, Object> metadata = new HashMap<>();
}
