package dev.a2flow.management.agentcore.runtime.session;

import java.util.List;

import org.apache.commons.collections4.CollectionUtils;
import org.apache.commons.collections4.ListUtils;
import org.apache.commons.lang3.StringUtils;
import org.springframework.ai.chat.messages.AssistantMessage;
import org.springframework.ai.chat.messages.Message;
import org.springframework.ai.chat.messages.SystemMessage;
import org.springframework.ai.chat.messages.ToolResponseMessage;
import org.springframework.ai.chat.messages.UserMessage;

import com.google.common.collect.Lists;
import dev.a2flow.management.support.DeploymentEnvironment;

import lombok.Data;
import lombok.extern.slf4j.Slf4j;

/**
 * Agent会话管理
 * 消息顺序：UserMessage → AssistantMessage(toolCalls) → ToolResponseMessage → AssistantMessage(final)

 * Created on 2026-04-25
 */
@Data
@Slf4j
public class AgentSession {
    private String conversationId;
    @com.fasterxml.jackson.databind.annotation.JsonSerialize(using = com.fasterxml.jackson.databind.ser.std.ToStringSerializer.class)
    private Long userId;
    private long agentId;
    private String invokeId;
    /**
     * 历史会话消息，已完成闭环的消息
     */
    private List<Message> historyMessages = Lists.newArrayList();
    /**
     * 当前会话消息，本轮对话的消息
     */
    private List<Message> messages = Lists.newArrayList();
    /**
     * 待添加的工具响应，用于收集同一轮调用的所有工具结果
     */
    private List<ToolResponseMessage.ToolResponse> pendingToolResponses = Lists.newArrayList();

    public void addUserMessage(String content) {
        messages.add(new UserMessage(content));
    }

    /**
     * 添加助手消息（带工具调用）
     * 添加后初始化待处理的工具响应列表
     */
    public void addAssistantMessage(String content, List<AssistantMessage.ToolCall> toolCalls) {
        AssistantMessage.Builder builder = AssistantMessage.builder().content(StringUtils.defaultString(content));
        builder.toolCalls(ListUtils.emptyIfNull(toolCalls));
        messages.add(builder.build());

        // 如果有工具调用，初始化待处理的工具响应列表
        if (CollectionUtils.isNotEmpty(toolCalls)) {
            pendingToolResponses = Lists.newArrayListWithExpectedSize(toolCalls.size());
        }
    }

    /**
     * 添加工具响应到待处理列表
     * 注意：必须先调用 addAssistantMessage 添加带工具调用的消息
     */
    public void addToolMessage(String toolCallId, String toolName, String result) {
        ToolResponseMessage.ToolResponse toolResponse =
                new ToolResponseMessage.ToolResponse(toolCallId, toolName, result);
        pendingToolResponses.add(toolResponse);
    }

    /**
     * 提交所有待处理的工具响应为一个 ToolResponseMessage
     * 必须在所有工具执行完毕后调用
     */
    public void commitToolResponses() {
        if (CollectionUtils.isNotEmpty(pendingToolResponses)) {
            ToolResponseMessage.Builder builder = ToolResponseMessage.builder()
                    .responses(pendingToolResponses);
            messages.add(builder.build());
            pendingToolResponses = Lists.newArrayList();
        }
    }

    /**
     * 构建调用大模型的消息列表
     * 顺序：SystemMessage → 历史消息 → 当前消息
     */
    public List<Message> buildCallMessages(String systemPrompt) {
        List<Message> callMessages = Lists.newArrayList();
        // 系统提示词
        callMessages.add(new SystemMessage(systemPrompt));
        // 历史消息（已闭环）
        if (CollectionUtils.isNotEmpty(historyMessages)) {
            callMessages.addAll(historyMessages);
        }
        // 当前消息
        callMessages.addAll(messages);
        if (!DeploymentEnvironment.isProd()) {
            log.info("AgentSession构建模型消息完成, conversationId={}, invokeId={}, historyMessageCount={}, "
                            + "currentMessageCount={}, callMessageCount={}",
                    conversationId, invokeId, CollectionUtils.size(historyMessages),
                    CollectionUtils.size(messages), callMessages.size());
        }
        return callMessages;
    }
}
