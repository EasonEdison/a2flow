package dev.a2flow.management.config;

import lombok.Data;

/**
 * SkillFactory 视角的独立 biz 配置。
 *
 * <p>该模型只映射 SkillFactory AI Coding 需要读取的 `propertiesConfig`、`modelConfig` 和 `memoryConfig`，
 * 上游是 `SkillFactoryConfigReader`，下游是 KConf `skillFactoryAgentBizSummaryMapConfig`。
 * 它不依赖 agent-service 公共 biz 配置模型，也不承接普通数字员工 ReActEngine
 * 的配置解析；当前只在 SkillFactory 专用运行入口转换成通用执行器需要的上下文对象。
 */
@Data
public class SkillFactoryAgentBizSummaryConfig {

    private SkillFactoryAgentPropertiesConfig propertiesConfig;
    private SkillFactoryLlmModelConfig modelConfig;
    private SkillFactoryMemoryConfig memoryConfig;
}
