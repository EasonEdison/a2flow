package dev.a2flow.management.agentcore.infrastructrue.kconf.model;

import java.util.List;

import com.google.common.collect.Lists;

import lombok.Data;

/**
 * AgentMemory配置
 *

 * Created on 2026-04-27
 */
@Data
public class AgentMemoryConfig {
    /**
     * 记忆策略类型: windowLimit(时间窗口) / countLimit(消息数量) / charactersLimit(characters限制) / memoryStartTimeLimit (开始时间限制)
     */
    private List<String> filterStrategyList = Lists.newArrayList();

    /**
     * 时间窗口策略: 记忆保留时长(秒)，默认1小时
     */
    private long memorySecondsTime = 3600L;

    /**
     * 消息数量策略: 最大保留消息条数
     */
    private int maxMessageCount = 20;

    /**
     * 字符限制策略: 最大字符数
     */
    private int maxCharacters = 16000;


    private long memoryStartTimeLimit;


    private int pullMessageCount = 100;
}
