package dev.a2flow.management.config;

import java.util.List;

import lombok.Data;

/**
 * SkillFactory 专用 agent properties 配置模型。
 *
 * <p>该模型镜像 `skillFactoryAgentBizSummaryMapConfig.*.propertiesConfig` 中 SkillFactory 关心的字段，
 * 包括 workspace 根目录、AI Coding 审批策略、workspace 文件变更检测策略和 Authoring Chat 引导配置。
 * 上游由 KConf JSON 直接反序列化，下游提供给 AI Coding / lifecycle 读取器；
 * 它不参与公共 agent 配置模型的引擎选择、工具注册和数字员工运行态逻辑。
 */
@Data
public class SkillFactoryAgentPropertiesConfig {

    private String workspace;
    private String defaultEngineStrategy;
    private Integer maxIterations;
    private List<String> tools;
    /**
     * 当前 bizKey 使用的系统提示词 String KConf 完整键，不存放提示词正文。
     *
     * <p>例如配置 `kwaishop.kwaishop-sellerdata-operation-service.HADES_SKILL_FACTORY_SYT_PROMPT`
     * 后，配置装配阶段
     * 会直接读取该 key，并把解析后的正文写入运行时 {@code AgentPropertiesConfig}。
     */
    private String engineSystemPrompt;
    private Boolean thoughtsAndAnswers;
    private Boolean storeMessages;
    private Boolean sessionLock;
    private Integer sessionLockTimeouts;
    private String sessionLockTips;
    private Integer cancelCacheTimeouts;
    private WorkspaceChangeGuardConfig workspaceChangeGuardConfig;
    private SkillFactoryAgentToolConfig agentToolConfig;
    private SkillFactoryHttpDebugConfig httpDebugConfig;
    private AuthoringGuideConfig authoringGuideConfig;
}
