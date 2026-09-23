package dev.a2flow.management.agentcore.infrastructrue.kconf.model;

import java.util.List;

import org.apache.commons.collections4.ListUtils;

import com.google.common.collect.Lists;

import lombok.Data;

/**

 * Created on 2026-04-26
 */
@Data
public class AgentPropertiesConfig {
    /**
     * 工作空间目录 path
     */
    private String workspace;
    /**
     * 最大推理轮次
     */
    private int maxIterations = 30;
    /**
     * 可使用tools
     */
    private List<String> tools = Lists.newArrayList();
    /**
     * 禁止执行的脚本文件
     */
    private List<String> blackScriptList = Lists.newArrayList();
    /**
     * 禁止使用的SKILL Name
     */
    private List<String> blackSkillNameList = Lists.newArrayList();

    private String defaultEngineStrategy; // 执行策略

    // 子agent策略
    private String defaultSubEngineStrategy;

    private String notMatchSubBottomStrategy;

    private boolean hasBottomAnswer;

    private String bottomAnswer;

    private boolean storeMessages = false;

    private boolean thoughtsAndAnswers = false;

    private boolean sessionLock = true;

    private int sessionLockTimeouts = 180_000; // 默认3分钟

    private String sessionLockTips;

    private int cancelCacheTimeouts = 300_000; // 默认5分钟

    /**
     * 配置装配阶段已经解析完成的系统提示词正文。
     *
     * <p>Engine 只消费该字段，不再按策略或 bizKey 二次读取 KConf。
     */
    private String engineSystemPrompt;

    public boolean checkBlackScript(String script) {
        return ListUtils.emptyIfNull(this.blackScriptList).contains(script);
    }

    public boolean checkBlackSkill(String skillName) {
        return ListUtils.emptyIfNull(this.blackSkillNameList).contains(skillName);
    }
}
