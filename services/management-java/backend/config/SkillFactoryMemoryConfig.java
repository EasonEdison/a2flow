package dev.a2flow.management.config;

import java.util.List;

import com.google.common.collect.Lists;

import lombok.Data;

/**
 * SkillFactory 专用记忆配置。
 *
 * <p>该模型映射 `skillFactoryAgentBizSummaryMapConfig.*.memoryConfig`，用于 AI Coding
 * 会话历史和上下文裁剪。上游是 SkillFactory 独立 KConf，下游由 SkillFactory 运行入口转换给
 * 当前通用 memory 组件；它不复用公共 `agentBizSummaryMapConfig` 的 value 类型，迁移 SkillFactory
 * 能力时可以跟随配置模型一起迁出。
 */
@Data
public class SkillFactoryMemoryConfig {

    private List<String> filterStrategyList = Lists.newArrayList();
    private long memorySecondsTime = 3600L;
    private int maxMessageCount = 20;
    private int maxCharacters = 16000;
    private long memoryStartTimeLimit;
    private int pullMessageCount = 100;
}
