package dev.a2flow.management.aicoding.validation;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * SkillFactory 动态运行验证任务描述。
 *
 * <p>该对象只服务 AI Coding Chat 内部的 CheckAgent 子任务，用来描述本轮只读验证要读取的
 * workspace、测试输入、mock 上下文和安全约束。它不是 lifecycle 发布任务，也不会写入 workspace。
 */
@Data
@Accessors(chain = true)
public class ValidationTaskSpec {

    private String taskId;
    private String workspaceId;
    private String skillCode;
    private String fileTreeDigest;
    private String testInput;
    private Map<String, Object> mockContext = new HashMap<>();
    private List<Map<String, Object>> referenceRenderAssets = new ArrayList<>();
    private Constraints constraints = new Constraints();

    /**
     * CheckAgent 执行约束。
     */
    @Data
    @Accessors(chain = true)
    public static class Constraints {
        private boolean readOnly = true;
        private boolean noPatch = true;
        private boolean noWorkspaceWrite = true;
        private boolean noBusinessSideEffect = true;
        private long timeoutMs = 60000L;
    }
}
