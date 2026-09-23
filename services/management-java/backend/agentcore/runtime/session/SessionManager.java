package dev.a2flow.management.agentcore.runtime.session;

import java.time.Instant;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import java.util.stream.Collectors;

import jakarta.annotation.Resource;

import org.apache.commons.collections4.CollectionUtils;
import org.apache.commons.collections4.ListUtils;
import org.apache.commons.lang3.StringUtils;
import org.springframework.ai.chat.messages.AssistantMessage;
import org.springframework.ai.chat.messages.Message;
import org.springframework.ai.chat.messages.MessageType;
import org.springframework.ai.chat.messages.ToolResponseMessage;
import org.springframework.ai.chat.messages.UserMessage;
import org.springframework.stereotype.Component;

import com.google.common.collect.Lists;
import dev.a2flow.management.support.DeploymentEnvironment;
import dev.a2flow.management.agentcore.infrastructrue.kconf.model.AgentMemoryConfig;
import dev.a2flow.management.authoring.session.domain.AuthoringChatTurn;
import dev.a2flow.management.authoring.session.domain.AuthoringChatTurnRepository;

import lombok.extern.slf4j.Slf4j;

/**
 * SkillFactory AI Coding 模型会话装配器。
 *
 * <p>该类从 Authoring Chat turn 仓储读取当前 session 的完整用户/助手消息，并按照记忆配置裁剪后
 * 交给模型。sessionId 是唯一隔离边界，禁止跨 session 读取；当前 invoke 对应的用户 turn 已在引擎
 * 启动前持久化，因此装配历史时必须排除，避免本轮消息重复进入模型。
 */
@Slf4j
@Component
public class SessionManager {

    private static final String ROLE_USER = "user";
    private static final String ROLE_ASSISTANT = "assistant";
    private static final String STRATEGY_WINDOW_LIMIT = "windowLimit";
    private static final String STRATEGY_CHARACTERS_LIMIT = "charactersLimit";
    private static final String STRATEGY_MEMORY_START_TIME_LIMIT = "memoryStartTimeLimit";

    @Resource
    private AuthoringChatTurnRepository authoringChatTurnRepository;

    /**
     * 构建一次模型调用使用的会话对象。
     */
    public AgentSession buildAgentSession(long agentId, Long userId, String conversationId,
            AgentMemoryConfig memoryConfig, String invokeId) {
        AgentSession agentSession = new AgentSession();
        agentSession.setAgentId(agentId);
        agentSession.setConversationId(conversationId);
        agentSession.setUserId(userId);
        agentSession.setInvokeId(invokeId);
        List<Message> historyMessages =
                buildHistoryMessages(agentId, userId, conversationId, memoryConfig, invokeId);
        agentSession.setHistoryMessages(formatMessages(historyMessages));
        if (!DeploymentEnvironment.isProd()) {
            log.info("SkillFactory SessionManager构建模型会话完成, agentId={}, userId={}, conversationId={}, "
                            + "invokeId={}, historyMessageCount={}",
                    agentId, userId, conversationId, invokeId,
                    CollectionUtils.size(agentSession.getHistoryMessages()));
        }
        return agentSession;
    }

    /**
     * 按当前 session 精确加载模型历史，并排除当前 invoke 已提前落库的用户 turn。
     */
    public List<Message> buildHistoryMessages(long agentId, Long userId, String conversationId,
            AgentMemoryConfig memoryConfig, String invokeId) {
        if (StringUtils.isBlank(conversationId)) {
            return Lists.newArrayList();
        }
        List<AuthoringChatTurn> sessionTurns =
                authoringChatTurnRepository.listBySessionId(conversationId);
        List<AuthoringChatTurn> selectedTurns = selectHistoryTurns(sessionTurns, memoryConfig, invokeId);
        List<Message> messages = selectedTurns.stream()
                .map(this::toMessage)
                .filter(Objects::nonNull)
                .collect(Collectors.toList());
        dropLeadingAssistantMessages(messages);
        log.info("SkillFactory SessionManager已装载当前会话历史, agentId={}, userId={}, sessionId={}, "
                        + "storedTurnCount={}, historyMessageCount={}, excludedInvokeId={}",
                agentId, userId, conversationId, CollectionUtils.size(sessionTurns), messages.size(),
                StringUtils.defaultString(invokeId));
        return messages;
    }

    private List<AuthoringChatTurn> selectHistoryTurns(List<AuthoringChatTurn> turns,
            AgentMemoryConfig memoryConfig, String invokeId) {
        if (CollectionUtils.isEmpty(turns)) {
            return Lists.newArrayList();
        }
        AgentMemoryConfig config = memoryConfig == null ? new AgentMemoryConfig() : memoryConfig;
        List<AuthoringChatTurn> candidates = turns.stream()
                .filter(Objects::nonNull)
                .filter(turn -> StringUtils.isNotBlank(turn.getText()))
                .filter(turn -> StringUtils.equalsAny(turn.getRole(), ROLE_USER, ROLE_ASSISTANT))
                .filter(turn -> !StringUtils.equals(turn.getMessageId(), invokeId))
                .filter(turn -> withinMemoryWindow(turn, config))
                .collect(Collectors.toList());
        int pullLimit = positiveLimit(config.getPullMessageCount(), candidates.size());
        int start = Math.max(0, candidates.size() - pullLimit);
        List<AuthoringChatTurn> pulled = Lists.newArrayList(candidates.subList(start, candidates.size()));
        int countLimit = positiveLimit(config.getMaxMessageCount(), pulled.size());
        if (pulled.size() > countLimit) {
            pulled = Lists.newArrayList(pulled.subList(pulled.size() - countLimit, pulled.size()));
        }
        return applyCharactersLimit(pulled, config);
    }

    private boolean withinMemoryWindow(AuthoringChatTurn turn, AgentMemoryConfig config) {
        List<String> strategies = ListUtils.emptyIfNull(config.getFilterStrategyList());
        long timestamp = turn.getTimestamp();
        if (strategies.contains(STRATEGY_MEMORY_START_TIME_LIMIT)
                && config.getMemoryStartTimeLimit() > 0
                && timestamp < config.getMemoryStartTimeLimit()) {
            return false;
        }
        if (!strategies.contains(STRATEGY_WINDOW_LIMIT) || config.getMemorySecondsTime() <= 0) {
            return true;
        }
        long earliestTimestamp = System.currentTimeMillis() - config.getMemorySecondsTime() * 1000L;
        return timestamp <= 0 || timestamp >= earliestTimestamp;
    }

    private List<AuthoringChatTurn> applyCharactersLimit(List<AuthoringChatTurn> turns,
            AgentMemoryConfig config) {
        if (!ListUtils.emptyIfNull(config.getFilterStrategyList()).contains(STRATEGY_CHARACTERS_LIMIT)
                || config.getMaxCharacters() <= 0) {
            return turns;
        }
        List<AuthoringChatTurn> selected = Lists.newArrayList();
        int characters = 0;
        for (int index = turns.size() - 1; index >= 0; index--) {
            AuthoringChatTurn turn = turns.get(index);
            int nextLength = StringUtils.length(turn.getText());
            if (!selected.isEmpty() && characters + nextLength > config.getMaxCharacters()) {
                break;
            }
            selected.add(0, turn);
            characters += nextLength;
        }
        return selected;
    }

    private int positiveLimit(int configuredLimit, int fallback) {
        return configuredLimit > 0 ? configuredLimit : fallback;
    }

    private Message toMessage(AuthoringChatTurn turn) {
        String timestampedText = timestampedHistoryText(turn);
        if (StringUtils.equals(turn.getRole(), ROLE_USER)) {
            return new UserMessage(timestampedText);
        }
        if (StringUtils.equals(turn.getRole(), ROLE_ASSISTANT)) {
            return AssistantMessage.builder().content(timestampedText).build();
        }
        return null;
    }

    /**
     * 为历史 turn 添加可供模型比较先后的时间事实；当前用户输入仍保持原文。
     */
    private String timestampedHistoryText(AuthoringChatTurn turn) {
        long timestamp = turn.getTimestamp();
        String occurredAt = timestamp > 0 ? Instant.ofEpochMilli(timestamp).toString() : "unknown";
        return "[history occurredAt=" + occurredAt
                + ", occurredAtEpochMs=" + timestamp
                + ", messageId=" + StringUtils.defaultString(turn.getMessageId())
                + "]\n" + turn.getText();
    }

    private void dropLeadingAssistantMessages(List<Message> messages) {
        while (!messages.isEmpty() && messages.get(0).getMessageType() != MessageType.USER) {
            messages.remove(0);
        }
    }

    /**
     * 格式化消息列表，确保消息顺序符合大模型API要求：
     * 顺序：UserMessage → AssistantMessage(toolCalls) → ToolResponseMessage → AssistantMessage(final)
     * 要求：ToolResponseMessage的callId必须与AssistantMessage的toolCall.id匹配
     */
    public List<Message> formatMessages(List<Message> messages) {
        if (CollectionUtils.isEmpty(messages)) {
            return Lists.newArrayList();
        }
        List<Message> result = Lists.newArrayList();
        Set<String> pendingToolCallIds = new HashSet<>();
        AssistantMessage lastAssistantWithTools = null;

        for (Message msg : messages) {
            if (Objects.isNull(msg)) {
                continue;
            }
            MessageType msgType = msg.getMessageType();
            switch (msgType) {
                case SYSTEM:
                    // 系统消息通常放在最前面
                    result.add(msg);
                    break;
                case USER:
                    // 用户消息前必须确保之前的工具调用已闭环
                    if (!pendingToolCallIds.isEmpty() && lastAssistantWithTools != null) {
                        // 补充缺失的ToolResponseMessage（空结果）
                        result.add(buildEmptyToolResponse(lastAssistantWithTools));
                        pendingToolCallIds.clear();
                        lastAssistantWithTools = null;
                    }
                    result.add(msg);
                    break;
                case ASSISTANT:
                    AssistantMessage assistantMsg = (AssistantMessage) msg;
                    List<AssistantMessage.ToolCall> toolCalls = assistantMsg.getToolCalls();
                    // 如果之前有未闭环的工具调用，先补充空结果
                    if (!pendingToolCallIds.isEmpty() && lastAssistantWithTools != null) {
                        result.add(buildEmptyToolResponse(lastAssistantWithTools));
                        pendingToolCallIds.clear();
                    }
                    result.add(msg);
                    // 记录本轮工具调用的ID
                    if (CollectionUtils.isNotEmpty(toolCalls)) {
                        lastAssistantWithTools = assistantMsg;
                        for (AssistantMessage.ToolCall tc : toolCalls) {
                            if (StringUtils.isNotBlank(tc.id())) {
                                pendingToolCallIds.add(tc.id());
                            }
                        }
                    }
                    break;

                case TOOL:
                    ToolResponseMessage toolMsg = (ToolResponseMessage) msg;
                    List<ToolResponseMessage.ToolResponse> responses = toolMsg.getResponses();
                    // 必须有待匹配的AssistantMessage
                    if (lastAssistantWithTools == null) {
                        log.warn("ToolResponseMessage without matching AssistantMessage, skipping");
                        continue;
                    }
                    // 过滤掉callId不匹配的响应
                    List<ToolResponseMessage.ToolResponse> validResponses = Lists.newArrayList();
                    for (ToolResponseMessage.ToolResponse resp : ListUtils.emptyIfNull(responses)) {
                        String respId = resp.id();
                        if (StringUtils.isNotBlank(respId) && pendingToolCallIds.contains(respId)) {
                            validResponses.add(resp);
                            pendingToolCallIds.remove(respId);
                        } else {
                            log.warn("ToolResponse callId {} not found in pending tool calls", respId);
                        }
                    }
                    // 添加有效的工具响应
                    if (CollectionUtils.isNotEmpty(validResponses)) {
                        ToolResponseMessage validToolMsg = ToolResponseMessage.builder()
                                .responses(validResponses)
                                .build();
                        result.add(validToolMsg);
                    }
                    // 如果所有工具调用都已闭环，清空状态
                    if (pendingToolCallIds.isEmpty()) {
                        lastAssistantWithTools = null;
                    }
                    break;

                default:
                    log.warn("Unknown message type: {}, skipping", msgType);
                    break;
            }
        }

        // 处理末尾未闭环的工具调用
        if (!pendingToolCallIds.isEmpty()) {
            result.add(buildEmptyToolResponse(lastAssistantWithTools));
        }

        return result;
    }

    /**
     * 为未闭环的工具调用构建空的ToolResponseMessage
     */
    private ToolResponseMessage buildEmptyToolResponse(AssistantMessage assistantMessage) {
        List<ToolResponseMessage.ToolResponse> responses = Lists.newArrayList();
        for (AssistantMessage.ToolCall tc : ListUtils.emptyIfNull(assistantMessage.getToolCalls())) {
            if (StringUtils.isNotBlank(tc.id())) {
                responses.add(new ToolResponseMessage.ToolResponse(tc.id(), tc.name(), "Tool execution skipped"));
            }
        }
        return ToolResponseMessage.builder().responses(responses).build();
    }

    public void saveAgentSession(AgentSession agentSession) {
        if (Objects.nonNull(agentSession)) {
            log.info("SkillFactory SessionManager不重复持久化模型消息, agentId={}, userId={}, conversationId={}",
                    agentSession.getAgentId(), agentSession.getUserId(), agentSession.getConversationId());
        }
    }
}
