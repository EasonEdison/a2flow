package dev.a2flow.management.authoring.session;

import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import java.util.stream.Collectors;

import jakarta.annotation.Resource;

import org.apache.commons.collections4.MapUtils;
import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;

import com.google.common.collect.Lists;
import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.agentcore.exception.AgentServiceException;
import dev.a2flow.management.agentcore.exception.ResultCode;
import dev.a2flow.management.authoring.session.domain.AuthoringChatTurn;
import dev.a2flow.management.authoring.session.domain.AuthoringChatTurnRepository;
import dev.a2flow.management.authoring.session.domain.AuthoringSession;
import dev.a2flow.management.authoring.session.domain.AuthoringSessionArchive;
import dev.a2flow.management.authoring.session.domain.AuthoringSessionRepository;
import dev.a2flow.management.authoring.session.domain.AuthoringSessionScope;
import dev.a2flow.management.authoring.session.domain.AuthoringStreamEvent;
import dev.a2flow.management.authoring.session.domain.AuthoringStreamEventRepository;
import dev.a2flow.management.authoring.session.model.AuthoringChatTurnResult;
import dev.a2flow.management.authoring.session.model.AuthoringSessionCreateResult;
import dev.a2flow.management.authoring.session.model.AuthoringSessionHistory;
import dev.a2flow.management.authoring.session.model.AuthoringSessionSummary;
import dev.a2flow.management.authoring.session.model.AuthoringStreamEventResult;
import dev.a2flow.management.config.AuthoringGuideConfig;
import dev.a2flow.management.config.SkillFactoryConfigReader;
import dev.a2flow.management.protobuf.InvokeRequest;
import dev.a2flow.management.protobuf.SkillFactoryChatResponse;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.extern.slf4j.Slf4j;

/**
 * Authoring Chat 会话生命周期服务。
 *
 * <p>该服务负责把前端无感的 scope 映射为后端 sessionId：第一次聊天自动创建 session，
 * 历史查询返回同 scope 下所有 session，`/new` 仅创建并切换新 session，不删除旧历史。所有人共享同一个
 * scope 下的会话，不按 operator 隔离。
 */
@Service
@Slf4j
public class AuthoringSessionService {
    @Resource
    private dev.a2flow.management.access.ManagementIdentityProvider managementIdentityProvider;

    private static final String BIZ_CONTEXT_EXTRA_BIZ_PARAM = "extraBizParam";
    private static final String FIELD_BIZ_KEY = "bizKey";
    private static final String FIELD_SCOPE_TYPE = "scopeType";
    private static final String FIELD_SCOPE_ID = "scopeId";
    private static final String FIELD_USER_NAME = "userName";
    private static final String FIELD_WORKSPACE_ID = "workspaceId";
    private static final String FIELD_SKILL_CODE = "skillCode";
    private static final String FIELD_COMPONENT_CODE = "componentCode";
    private static final String FIELD_COMPONENT_NAME = "componentName";
    private static final String FIELD_ASSET_ID = "assetId";
    private static final String FIELD_DRAFT_ID = "draftId";
    private static final String FIELD_AUTHORING_DOMAIN = "authoringDomain";
    private static final String FIELD_SESSION_ID = "sessionId";
    private static final String FIELD_CONVERSATION_ID = "conversationId";
    private static final String FIELD_THREAD_ID = "threadId";
    private static final String FIELD_MESSAGE_ID = "messageId";
    private static final String FIELD_RUN_ID = "runId";
    private static final String FIELD_INVOKE_ID = "invokeId";
    private static final String FIELD_MESSAGE = "message";
    private static final String DOMAIN_COMPONENT_CENTER = "COMPONENT_CENTER";
    private static final String SCOPE_TYPE_SKILL = "SKILL";
    private static final String SCOPE_TYPE_COMPONENT = "COMPONENT";
    private static final String ROLE_USER = "user";
    private static final String ROLE_ASSISTANT = "assistant";
    private static final String EVENT_MODEL_CONTENT_DELTA = "MODEL_CONTENT_DELTA";
    private static final String EVENT_THINK_TEXT_DELTA = "THINK_TEXT_DELTA";
    private static final String EVENT_RUN_COMPLETED = "RUN_COMPLETED";
    private static final String EVENT_RUN_FAILED = "RUN_FAILED";
    private static final String EVENT_RUN_CANCELLED = "RUN_CANCELLED";
    private static final String EVENT_COMPLETED = "COMPLETED";
    private static final String EVENT_FAILED = "FAILED";
    private static final String EVENT_RECORD_ID_PREFIX = "authoring-event-";
    private static final String ASSISTANT_TURN_ID_PREFIX = "assistant-";
    private static final String GUIDE_TURN_ID_PREFIX = "assistant-guide-";

    @Resource
    private AuthoringSessionRepository authoringSessionRepository;

    @Resource
    private AuthoringChatTurnRepository authoringChatTurnRepository;

    @Resource
    private AuthoringStreamEventRepository authoringStreamEventRepository;

    @Resource
    private SkillFactoryConfigReader skillFactoryConfigReader;

    /**
     * 为流式请求准备后端 session，并把 sessionId/共享 userId 写回 InvokeRequest。
     */
    public AuthoringRunContext prepareRun(InvokeRequest request) {
        AuthoringSessionScope scope = resolveScope(request);
        AuthoringSession session = authoringSessionRepository.ensureSession(scope, request.getSessionId());
        InvokeRequest enrichedRequest = enrichRequest(request, scope, session);
        log.info("SkillFactory Authoring Chat已准备运行session, bizKey={}, scopeType={}, scopeId={}, "
                        + "sessionId={}, userId={}, messageLength={}",
                scope.getBizKey(), scope.getScopeType(), scope.getScopeId(), session.getSessionId(),
                enrichedRequest.getUserId(), StringUtils.length(request.getMessage()));
        return new AuthoringRunContext(scope, session, enrichedRequest);
    }

    /**
     * 查询同一 scope 下 session 列表与选中 session 历史。
     */
    public AuthoringSessionHistory queryHistory(Map<String, String> params) {
        AuthoringSessionScope scope = resolveScope(params);
        String selectedSessionId = MapUtils.getString(params, FIELD_SESSION_ID);
        AuthoringSessionHistory history = attachGuideConfig(scope,
                toHistoryResult(buildSessionArchive(scope, selectedSessionId)));
        log.info("SkillFactory Authoring Chat查询历史完成, bizKey={}, scopeType={}, scopeId={}, "
                        + "selectedSessionId={}, sessionCount={}, eventCount={}, guideEnabled={}",
                scope.getBizKey(), scope.getScopeType(), scope.getScopeId(), history.getSelectedSessionId(),
                history.getSessions() == null ? 0 : history.getSessions().size(),
                history.getEvents() == null ? 0 : history.getEvents().size(),
                history.getAuthoringGuideConfig() == null
                        ? null : history.getAuthoringGuideConfig().getEnabled());
        return history;
    }

    /**
     * 创建一个新的活跃 session；旧 session 保留在列表中。
     */
    public AuthoringSessionCreateResult createSession(Map<String, String> params) {
        AuthoringSessionScope scope = resolveScope(params);
        AuthoringSession session = authoringSessionRepository.createNewSession(scope);
        log.info("SkillFactory Authoring Chat已创建新session, bizKey={}, scopeType={}, scopeId={}, sessionId={}",
                scope.getBizKey(), scope.getScopeType(), scope.getScopeId(), session.getSessionId());
        return new AuthoringSessionCreateResult().setSessionId(session.getSessionId());
    }

    /**
     * 记录用户 turn，供页面刷新后恢复对话时间线。
     */
    public void appendUserTurn(AuthoringRunContext runContext, InvokeRequest request) {
        if (runContext == null || request == null || StringUtils.isBlank(request.getMessage())) {
            return;
        }
        long now = System.currentTimeMillis();
        String messageId = StringUtils.defaultIfBlank(request.getInvokeId(),
                MapUtils.getString(request.getBizContextMap(), FIELD_MESSAGE_ID, "msg_" + now));
        AuthoringChatTurn turn = new AuthoringChatTurn()
                .setTurnId("user-" + messageId)
                .setRole(ROLE_USER)
                .setText(request.getMessage())
                .setOperator(runContext.getScope().getOperator())
                .setTimestamp(now)
                .setSessionId(runContext.getSession().getSessionId())
                .setMessageId(messageId);
        if (authoringChatTurnRepository.append(turn)) {
            authoringSessionRepository.recordTurn(
                    runContext.getScope(), turn.getSessionId(), now, turn.getText());
        }
    }

    /**
     * 记录聚合后的完整 Assistant 回复，供模型上下文和页面历史共同复用。
     *
     * <p>同一个 invokeId 只允许写入一条 Assistant turn。模型文本 delta 不在这里逐段落库，
     * 避免高频写入和历史回放时重复拼接。
     */
    public void appendAssistantTurn(AuthoringRunContext runContext, InvokeRequest request, String answer) {
        if (runContext == null || request == null || StringUtils.isBlank(answer)) {
            return;
        }
        long now = System.currentTimeMillis();
        String messageId = StringUtils.defaultIfBlank(request.getInvokeId(),
                MapUtils.getString(request.getBizContextMap(), FIELD_MESSAGE_ID, "msg_" + now));
        AuthoringChatTurn turn = new AuthoringChatTurn()
                .setTurnId(ASSISTANT_TURN_ID_PREFIX + messageId)
                .setRole(ROLE_ASSISTANT)
                .setText(answer)
                .setOperator(runContext.getScope().getOperator())
                .setTimestamp(now)
                .setSessionId(runContext.getSession().getSessionId())
                .setMessageId(messageId);
        if (!authoringChatTurnRepository.append(turn)) {
            return;
        }
        authoringSessionRepository.recordAssistantTurn(
                runContext.getScope(), turn.getSessionId(), now);
        log.info("SkillFactory Authoring Chat完整Assistant回复已落库, sessionId={}, invokeId={}, "
                        + "answerLength={}",
                turn.getSessionId(), messageId, StringUtils.length(answer));
    }

    /**
     * 记录结构化流式事件，供工具、Patch、审批、错误和终态历史回放。
     *
     * <p>模型正文/思考 delta 只实时下发，不写事件表；完整 Assistant 回复由
     * {@link #appendAssistantTurn(AuthoringRunContext, InvokeRequest, String)} 聚合落库。
     */
    public void appendStreamEvent(AuthoringRunContext runContext, SkillFactoryChatResponse response) {
        if (runContext == null || response == null) {
            return;
        }
        if (StringUtils.equalsAny(
                response.getEventType(), EVENT_MODEL_CONTENT_DELTA, EVENT_THINK_TEXT_DELTA)) {
            return;
        }
        String sessionId = runContext.getSession().getSessionId();
        AuthoringStreamEvent event = new AuthoringStreamEvent()
                .setRecordId(stableEventRecordId(sessionId, response))
                .setSchemaVersion(response.getSchemaVersion())
                .setEventType(response.getEventType())
                .setEventId(response.getEventId())
                .setBlockId(response.getBlockId())
                .setSource(response.getSource())
                .setSessionId(sessionId)
                .setWorkspaceId(runContext.getScope().getWorkspaceId())
                .setInvokeId(response.getInvokeId())
                .setMessageId(firstNonBlank(response.getMessageId(), response.getInvokeId()))
                .setRunId(firstNonBlank(response.getRunId(), response.getInvokeId()))
                .setConversationId(firstNonBlank(response.getConversationId(), sessionId))
                .setThreadId(firstNonBlank(response.getThreadId(), sessionId))
                .setTraceId(response.getTraceId())
                .setModelContentBlockJson(response.getModelContentBlockJson())
                .setPayloadType(response.getPayloadType())
                .setPayloadJson(response.getPayloadJson())
                .setContent(response.getContent())
                .setToolCallId(response.getToolCallId())
                .setToolName(response.getToolName())
                .setToolArgs(response.getToolArgs())
                .setToolSuccess(response.getToolSuccess())
                .setTokenCount(response.getTokenCount())
                .setEnterTokenCount(response.getEnterTokenCount())
                .setOutputTokenCount(response.getOutputTokenCount())
                .setHasKnowledge(response.getHasKnowledge())
                .setTimestamp(response.getTimestamp())
                .setAnswerAgentId(response.getAnswerAgentId());
        if (!authoringStreamEventRepository.append(event) || !isSessionSummaryEvent(event.getEventType())) {
            return;
        }
        try {
            authoringSessionRepository.recordEvent(
                    runContext.getScope(), sessionId, normalizedTimestamp(event.getTimestamp()));
        } catch (Exception e) {
            // 终态事件已经持久化，会话摘要刷新失败不能让运行时误判为终态落库失败并重复补偿。
            log.warn("SkillFactory Authoring Chat刷新会话摘要失败但流式事件已落库, sessionId={}, "
                            + "invokeId={}, eventType={}",
                    sessionId, event.getInvokeId(), event.getEventType(), e);
        }
    }

    /**
     * 记录普通 handler 完成后的 Authoring 控制面事件。
     *
     * <p>Patch 确认/丢弃不创建 Chat run，也不写用户 turn；本方法只用请求中的 scope/session 找到
     * 既有 Authoring 会话，并复用流式事件仓储写入关联领域结果，保证刷新后仍能恢复同一审批状态。
     */
    public void appendControlEvent(Map<String, String> params, SkillFactoryChatResponse response) {
        if (params == null || response == null) {
            return;
        }
        AuthoringSessionScope scope = resolveScope(params);
        String requestedSessionId = MapUtils.getString(params, FIELD_SESSION_ID);
        AuthoringSession session = authoringSessionRepository.findSession(scope, requestedSessionId);
        if (session == null) {
            log.warn("SkillFactory Authoring Chat记录控制面事件失败, 原因=会话不存在, bizKey={}, "
                            + "scopeType={}, scopeId={}, sessionId={}",
                    scope.getBizKey(), scope.getScopeType(), scope.getScopeId(), requestedSessionId);
            throw new AgentServiceException(ResultCode.PARAM_ERROR);
        }
        appendStreamEvent(new AuthoringRunContext(scope, session, null), response);
        log.info("SkillFactory Authoring Chat已记录控制面事件, bizKey={}, scopeType={}, scopeId={}, "
                        + "sessionId={}, invokeId={}, eventType={}, payloadType={}",
                scope.getBizKey(), scope.getScopeType(), scope.getScopeId(), session.getSessionId(),
                response.getInvokeId(), response.getEventType(), response.getPayloadType());
    }

    private boolean isSessionSummaryEvent(String eventType) {
        return StringUtils.equalsAny(
                eventType, EVENT_RUN_COMPLETED, EVENT_RUN_FAILED, EVENT_RUN_CANCELLED,
                EVENT_COMPLETED, EVENT_FAILED);
    }

    /**
     * 为同一条协议事件生成稳定的持久化 ID，避免流重试或历史补录时重复写入。
     */
    private String stableEventRecordId(String sessionId, SkillFactoryChatResponse response) {
        String eventIdentity = StringUtils.isNotBlank(response.getEventId())
                ? response.getEventId()
                : String.join("|",
                        StringUtils.defaultString(response.getInvokeId()),
                        StringUtils.defaultString(response.getMessageId()),
                        StringUtils.defaultString(response.getEventType()),
                        StringUtils.defaultString(response.getBlockId()),
                        StringUtils.defaultString(response.getToolCallId()),
                        String.valueOf(response.getTimestamp()),
                        StringUtils.defaultString(response.getPayloadType()),
                        StringUtils.defaultString(response.getPayloadJson()),
                        StringUtils.defaultString(response.getContent()));
        String recordIdentity = StringUtils.defaultString(sessionId) + "|" + eventIdentity;
        return EVENT_RECORD_ID_PREFIX
                + UUID.nameUUIDFromBytes(recordIdentity.getBytes(StandardCharsets.UTF_8));
    }

    /**
     * 从三个领域仓储组装选中会话的完整历史。
     */
    private AuthoringSessionArchive buildSessionArchive(AuthoringSessionScope scope, String requestedSessionId) {
        List<AuthoringSession> sessions = authoringSessionRepository.listSessions(scope);
        AuthoringSession activeSession = sessions.stream()
                .filter(AuthoringSession::isActive)
                .findFirst()
                .orElse(sessions.isEmpty() ? null : sessions.get(0));
        String activeSessionId = activeSession == null ? StringUtils.EMPTY : activeSession.getSessionId();
        String selectedSessionId = resolveSelectedSessionId(scope, requestedSessionId, activeSessionId);
        List<AuthoringChatTurn> turns = StringUtils.isBlank(selectedSessionId)
                ? Lists.newArrayList()
                : authoringChatTurnRepository.listBySessionId(selectedSessionId);
        List<AuthoringStreamEvent> events = StringUtils.isBlank(selectedSessionId)
                ? Lists.newArrayList()
                : authoringStreamEventRepository.listBySessionId(selectedSessionId);
        log.info("SkillFactory Authoring Chat历史DB查询完成, scopeKey={}, selectedSessionId={}, "
                        + "sessionCount={}, turnCount={}, eventCount={}",
                scope.scopeKey(), selectedSessionId, sessions.size(), turns.size(), events.size());
        return new AuthoringSessionArchive()
                .setScope(scope)
                .setActiveSessionId(activeSessionId)
                .setSelectedSessionId(selectedSessionId)
                .setSessions(sessions)
                .setTurns(turns)
                .setEvents(events);
    }

    private String resolveSelectedSessionId(AuthoringSessionScope scope, String requestedSessionId,
            String activeSessionId) {
        if (StringUtils.isBlank(requestedSessionId)) {
            return activeSessionId;
        }
        return authoringSessionRepository.findSession(scope, requestedSessionId) == null
                ? activeSessionId : requestedSessionId;
    }

    private long normalizedTimestamp(long timestamp) {
        return timestamp > 0 ? timestamp : System.currentTimeMillis();
    }

    private InvokeRequest enrichRequest(InvokeRequest request, AuthoringSessionScope scope,
            AuthoringSession session) {
        Map<String, String> bizContext = new HashMap<>(request.getBizContextMap());
        Map<String, Object> extraBizParam = parseExtraBizParam(bizContext.get(BIZ_CONTEXT_EXTRA_BIZ_PARAM));
        extraBizParam.put(FIELD_BIZ_KEY, scope.getBizKey());
        extraBizParam.put(FIELD_SCOPE_TYPE, scope.getScopeType());
        extraBizParam.put(FIELD_SCOPE_ID, scope.getScopeId());
        extraBizParam.put(FIELD_SESSION_ID, session.getSessionId());
        extraBizParam.put(FIELD_CONVERSATION_ID, session.getSessionId());
        extraBizParam.put(FIELD_THREAD_ID, session.getSessionId());
        extraBizParam.put(FIELD_WORKSPACE_ID, scope.getWorkspaceId());
        if (StringUtils.equals(scope.getScopeType(), SCOPE_TYPE_COMPONENT)
                && StringUtils.isBlank(MapUtils.getString(extraBizParam, FIELD_COMPONENT_CODE))) {
            extraBizParam.put(FIELD_COMPONENT_CODE, scope.getScopeId());
        }
        if (StringUtils.equals(scope.getScopeType(), SCOPE_TYPE_SKILL)
                && StringUtils.isBlank(MapUtils.getString(extraBizParam, FIELD_SKILL_CODE))) {
            extraBizParam.put(FIELD_SKILL_CODE, scope.getScopeId());
        }
        bizContext.put(BIZ_CONTEXT_EXTRA_BIZ_PARAM, JsonSupport.toJSON(extraBizParam));
        String invokeId = StringUtils.defaultIfBlank(request.getInvokeId(),
                MapUtils.getString(extraBizParam, FIELD_MESSAGE_ID, "msg_" + System.currentTimeMillis()));
        return request.toBuilder()
                .clearBizContext()
                .putAllBizContext(bizContext)
                .setSessionId(session.getSessionId())
                .setCreateSession(true)
                .setUserId(dev.a2flow.management.access.UserIds.toWire(managementIdentityProvider.userId()))
                .setInvokeId(invokeId)
                .build();
    }

    private AuthoringSessionHistory attachGuideConfig(AuthoringSessionScope scope, AuthoringSessionHistory history) {
        AuthoringGuideConfig guideConfig = skillFactoryConfigReader.getAuthoringGuideConfig(scope.getBizKey());
        AuthoringSessionHistory nextHistory = history.setAuthoringGuideConfig(guideConfig);
        appendGuideTurnIfEmpty(scope, nextHistory, guideConfig);
        return nextHistory;
    }

    /**
     * 空会话返回一条后端生成的欢迎消息。
     *
     * <p>这条 turn 不写入仓储，只用于页面首次打开时像普通聊天记录一样回显 Agent 使用说明；
     * 后续用户发送消息后，真实 turn/event 历史会自然覆盖空态，不再展示前端自造大块空态文案。
     */
    private void appendGuideTurnIfEmpty(AuthoringSessionScope scope, AuthoringSessionHistory history,
            AuthoringGuideConfig guideConfig) {
        if (history == null || guideConfig == null || !Boolean.TRUE.equals(guideConfig.getEnabled())) {
            return;
        }
        if ((history.getTurns() != null && !history.getTurns().isEmpty())
                || (history.getEvents() != null && !history.getEvents().isEmpty())) {
            return;
        }
        String welcomeMessage = guideConfig.getWelcomeMessage();
        if (StringUtils.isBlank(welcomeMessage)) {
            return;
        }
        long timestamp = selectedSessionCreateTime(history);
        AuthoringChatTurnResult guideTurn = new AuthoringChatTurnResult()
                .setId(GUIDE_TURN_ID_PREFIX + StringUtils.defaultString(history.getSelectedSessionId()))
                .setRole(ROLE_ASSISTANT)
                .setText(welcomeMessage)
                .setTimestamp(timestamp)
                .setSessionId(history.getSelectedSessionId())
                .setMessageId(GUIDE_TURN_ID_PREFIX + timestamp);
        history.setTurns(Lists.newArrayList(guideTurn));
        log.info("SkillFactory Authoring Chat已返回空会话欢迎消息, bizKey={}, scopeType={}, scopeId={}, "
                        + "sessionId={}, messageLength={}",
                scope.getBizKey(), scope.getScopeType(), scope.getScopeId(), history.getSelectedSessionId(),
                StringUtils.length(welcomeMessage));
    }

    private long selectedSessionCreateTime(AuthoringSessionHistory history) {
        if (history.getSessions() != null) {
            for (AuthoringSessionSummary session : history.getSessions()) {
                if (StringUtils.equals(session.getSessionId(), history.getSelectedSessionId())) {
                    return session.getCreateTime() > 0 ? session.getCreateTime() : System.currentTimeMillis();
                }
            }
        }
        return System.currentTimeMillis();
    }

    private AuthoringSessionHistory toHistoryResult(AuthoringSessionArchive archive) {
        AuthoringSessionScope scope = archive.getScope();
        return new AuthoringSessionHistory()
                .setBizKey(scope.getBizKey())
                .setScopeType(scope.getScopeType())
                .setScopeId(scope.getScopeId())
                .setWorkspaceId(scope.getWorkspaceId())
                .setActiveSessionId(archive.getActiveSessionId())
                .setSelectedSessionId(archive.getSelectedSessionId())
                .setSessions(toSessionSummaries(archive.getSessions()))
                .setTurns(toTurnResults(archive.getTurns()))
                .setEvents(toEventResults(archive.getEvents()));
    }

    private List<AuthoringSessionSummary> toSessionSummaries(List<AuthoringSession> sessions) {
        if (sessions == null) {
            return Lists.newArrayList();
        }
        return sessions.stream()
                .map(session -> new AuthoringSessionSummary()
                        .setSessionId(session.getSessionId())
                        .setBizKey(session.getBizKey())
                        .setScopeType(session.getScopeType())
                        .setScopeId(session.getScopeId())
                        .setWorkspaceId(session.getWorkspaceId())
                        .setTitle(session.getTitle())
                        .setCreator(session.getCreator())
                        .setLastOperator(session.getLastOperator())
                        .setActive(session.isActive())
                        .setCreateTime(session.getCreateTime())
                        .setUpdateTime(session.getUpdateTime())
                        .setLastMessageTime(session.getLastMessageTime())
                        .setMessageCount(session.getMessageCount()))
                .collect(Collectors.toList());
    }

    private List<AuthoringChatTurnResult> toTurnResults(List<AuthoringChatTurn> turns) {
        if (turns == null) {
            return Lists.newArrayList();
        }
        return turns.stream()
                .map(turn -> new AuthoringChatTurnResult()
                        .setId(turn.getTurnId())
                        .setSessionId(turn.getSessionId())
                        .setRole(turn.getRole())
                        .setMessageId(turn.getMessageId())
                        .setText(turn.getText())
                        .setOperator(turn.getOperator())
                        .setTimestamp(turn.getTimestamp()))
                .collect(Collectors.toList());
    }

    private List<AuthoringStreamEventResult> toEventResults(List<AuthoringStreamEvent> events) {
        if (events == null) {
            return Lists.newArrayList();
        }
        return events.stream()
                .map(event -> new AuthoringStreamEventResult()
                        .setRecordId(event.getRecordId())
                        .setSchemaVersion(event.getSchemaVersion())
                        .setEventType(event.getEventType())
                        .setEventId(event.getEventId())
                        .setBlockId(event.getBlockId())
                        .setSource(event.getSource())
                        .setSessionId(event.getSessionId())
                        .setWorkspaceId(event.getWorkspaceId())
                        .setInvokeId(event.getInvokeId())
                        .setMessageId(event.getMessageId())
                        .setRunId(event.getRunId())
                        .setConversationId(event.getConversationId())
                        .setThreadId(event.getThreadId())
                        .setTraceId(event.getTraceId())
                        .setModelContentBlockJson(event.getModelContentBlockJson())
                        .setPayloadType(event.getPayloadType())
                        .setPayloadJson(event.getPayloadJson())
                        .setContent(event.getContent())
                        .setToolCallId(event.getToolCallId())
                        .setToolName(event.getToolName())
                        .setToolArgs(event.getToolArgs())
                        .setToolSuccess(event.isToolSuccess())
                        .setTokenCount(event.getTokenCount())
                        .setEnterTokenCount(event.getEnterTokenCount())
                        .setOutputTokenCount(event.getOutputTokenCount())
                        .setHasKnowledge(event.isHasKnowledge())
                        .setTimestamp(event.getTimestamp())
                        .setAnswerAgentId(event.getAnswerAgentId()))
                .collect(Collectors.toList());
    }

    private AuthoringSessionScope resolveScope(InvokeRequest request) {
        Map<String, Object> extraBizParam =
                parseExtraBizParam(request.getBizContextMap().get(BIZ_CONTEXT_EXTRA_BIZ_PARAM));
        String bizKey = StringUtils.defaultIfBlank(request.getBizKey(), MapUtils.getString(extraBizParam, FIELD_BIZ_KEY));
        String authoringDomain = MapUtils.getString(extraBizParam, FIELD_AUTHORING_DOMAIN);
        String scopeType = StringUtils.defaultIfBlank(MapUtils.getString(extraBizParam, FIELD_SCOPE_TYPE),
                StringUtils.equals(authoringDomain, DOMAIN_COMPONENT_CENTER) ? SCOPE_TYPE_COMPONENT : SCOPE_TYPE_SKILL);
        String scopeId = firstNonBlank(
                MapUtils.getString(extraBizParam, FIELD_SCOPE_ID),
                StringUtils.equals(scopeType, SCOPE_TYPE_COMPONENT)
                        ? firstNonBlank(MapUtils.getString(extraBizParam, FIELD_COMPONENT_CODE),
                                MapUtils.getString(extraBizParam, FIELD_COMPONENT_NAME),
                                MapUtils.getString(extraBizParam, FIELD_ASSET_ID),
                                MapUtils.getString(extraBizParam, FIELD_DRAFT_ID))
                        : firstNonBlank(MapUtils.getString(extraBizParam, FIELD_WORKSPACE_ID),
                                MapUtils.getString(extraBizParam, FIELD_SKILL_CODE)),
                request.getSessionId());
        String workspaceId = StringUtils.defaultIfBlank(MapUtils.getString(extraBizParam, FIELD_WORKSPACE_ID), scopeId);
        return buildScope(bizKey, scopeType, scopeId, workspaceId,
                MapUtils.getString(extraBizParam, FIELD_USER_NAME));
    }

    private AuthoringSessionScope resolveScope(Map<String, String> params) {
        String bizKey = MapUtils.getString(params, FIELD_BIZ_KEY);
        String scopeType = MapUtils.getString(params, FIELD_SCOPE_TYPE);
        String authoringDomain = MapUtils.getString(params, FIELD_AUTHORING_DOMAIN);
        if (StringUtils.isBlank(scopeType)) {
            scopeType = StringUtils.equals(authoringDomain, DOMAIN_COMPONENT_CENTER)
                    ? SCOPE_TYPE_COMPONENT : SCOPE_TYPE_SKILL;
        }
        String scopeId = MapUtils.getString(params, FIELD_SCOPE_ID);
        if (StringUtils.isBlank(scopeId)) {
            scopeId = StringUtils.equals(scopeType, SCOPE_TYPE_COMPONENT)
                    ? firstNonBlank(
                            MapUtils.getString(params, FIELD_COMPONENT_CODE),
                            MapUtils.getString(params, FIELD_COMPONENT_NAME),
                            MapUtils.getString(params, FIELD_ASSET_ID),
                            MapUtils.getString(params, FIELD_DRAFT_ID))
                    : firstNonBlank(
                            MapUtils.getString(params, FIELD_WORKSPACE_ID),
                            MapUtils.getString(params, FIELD_SKILL_CODE));
        }
        String workspaceId = StringUtils.defaultIfBlank(MapUtils.getString(params, FIELD_WORKSPACE_ID), scopeId);
        return buildScope(bizKey, scopeType, scopeId, workspaceId, MapUtils.getString(params, FIELD_USER_NAME));
    }

    private AuthoringSessionScope buildScope(String bizKey, String scopeType, String scopeId, String workspaceId,
            String operator) {
        if (StringUtils.isBlank(bizKey) || StringUtils.isBlank(scopeType) || StringUtils.isBlank(scopeId)) {
            log.warn("SkillFactory Authoring Chat scope参数缺失, bizKey={}, scopeType={}, scopeId={}",
                    bizKey, scopeType, scopeId);
            throw new AgentServiceException(ResultCode.PARAM_ERROR);
        }
        return new AuthoringSessionScope()
                .setBizKey(bizKey)
                .setScopeType(scopeType)
                .setScopeId(scopeId)
                .setWorkspaceId(StringUtils.defaultIfBlank(workspaceId, scopeId))
                .setOperator(StringUtils.defaultString(operator));
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> parseExtraBizParam(String extraBizParamStr) {
        if (StringUtils.isBlank(extraBizParamStr)) {
            return new HashMap<>();
        }
        try {
            Object parsed = JsonSupport.fromJson(extraBizParamStr);
            if (parsed instanceof Map) {
                return new HashMap<>((Map<String, Object>) parsed);
            }
        } catch (Exception e) {
            log.warn("SkillFactory Authoring Chat解析extraBizParam失败, length={}, error={}",
                    StringUtils.length(extraBizParamStr), e.getMessage());
        }
        return new HashMap<>();
    }

    private String firstNonBlank(String... values) {
        for (String value : values) {
            if (StringUtils.isNotBlank(value)) {
                return value;
            }
        }
        return StringUtils.EMPTY;
    }


    /**
     * 单次 Authoring Chat 运行时上下文。
     */
    @Data
    @AllArgsConstructor
    public static class AuthoringRunContext {
        private AuthoringSessionScope scope;
        private AuthoringSession session;
        private InvokeRequest request;
    }
}
