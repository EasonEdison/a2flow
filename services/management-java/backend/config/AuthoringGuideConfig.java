package dev.a2flow.management.config;

import java.util.List;

import lombok.Data;

/**
 * Authoring Chat 的 Agent 使用引导配置。
 *
 * <p>该配置挂在 `skillFactoryAgentBizSummaryMapConfig.*.propertiesConfig.authoringGuideConfig` 下，
 * 上游由不同 bizKey 的 KConf 管理，下游返回给前端共享 Authoring Chat 渲染欢迎消息和快捷入口。
 * 它只描述 M 端 Authoring Chat 的欢迎消息、展示和快捷输入行为，不参与模型提示词拼接、
 * 权限判断或文件写入。
 */
@Data
public class AuthoringGuideConfig {

    private Boolean enabled;
    private String welcomeMessage;
    private List<AuthoringGuidePrompt> quickPrompts;
    private List<AuthoringGuidePrompt> composerPrompts;

    /**
     * 单个引导入口配置。
     *
     * <p>`text` 是用户可见文案，`sendMsg` 是实际填入或发送给模型的内容；
     * `actionType` 由前端解释为直接发送或仅填入输入框，后端不执行该动作。
     */
    @Data
    public static class AuthoringGuidePrompt {
        private String key;
        private String text;
        private String sendMsg;
        private String actionType;
    }
}
