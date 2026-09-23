package dev.a2flow.management.aicoding.validation;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * SkillFactory peer Agent 流式事件快照。
 *
 * <p>该对象是 `invoke_agent` 工具在 SkillFactory 层消费的最小事件模型，只保留运行验证
 * 需要的模型文本、工具调用、工具结果和生命周期信息。公共运行时事件会在包外 outlet 中转换成
 * 本对象，SkillFactory 包内不直接依赖通用事件模型。
 */
@Data
@Accessors(chain = true)
public class SkillFactoryPeerAgentStreamEvent {

    private String eventType;

    private String content;

    private String toolCallId;

    private String toolName;

    private String toolArgs;

    private boolean success;

    private long timestamp;
}
