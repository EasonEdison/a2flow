package dev.a2flow.management.aicoding.validation;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * SkillFactory 动态运行验证报告。
 *
 * <p>CheckAgent 只读执行当前 Skill 工作区后返回该结构，主 Agent 和前端都消费同一份报告。
 * 报告用于驱动“运行验证卡片”和后续“让主 Agent 修复”，不代表发布态版本或生命周期状态。
 */
@Data
@Accessors(chain = true)
public class ValidationReport {

    public static final String STATUS_PASSED = "PASSED";
    public static final String STATUS_FAILED = "FAILED";
    public static final String STATUS_PARTIAL = "PARTIAL";

    private String taskId;
    private String reportId;
    private String status;
    private String workspaceId;
    private String skillCode;
    private String fileTreeDigest;
    private String testInput;
    private String rawOutput;
    private String stdoutSummary;
    private Protocol protocol = new Protocol();
    private List<CheckItem> checks = new ArrayList<>();
    private List<Issue> issues = new ArrayList<>();
    private Map<String, Object> agentInvocationEvidence = new HashMap<>();
    private Map<String, Object> simulationEvidence = new HashMap<>();
    private String repairPrompt;

    /**
     * Skill 输出协议识别结果。
     */
    @Data
    @Accessors(chain = true)
    public static class Protocol {
        private String type;
        private String code;
        private Object payload;
    }

    /**
     * 单项验证检查结果。
     */
    @Data
    @Accessors(chain = true)
    public static class CheckItem {
        private String key;
        private String label;
        private String status;
        private String message;
    }

    /**
     * 需要主 Agent 或用户关注的问题。
     */
    @Data
    @Accessors(chain = true)
    public static class Issue {
        private String severity;
        private String source;
        private String message;
        private String repairHint;
    }
}
