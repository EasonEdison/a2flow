package dev.a2flow.management.entry;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.atomic.AtomicReference;

import org.apache.commons.collections4.CollectionUtils;
import org.apache.commons.collections4.MapUtils;
import org.apache.commons.lang3.StringUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;

import dev.a2flow.management.support.BoundedExecutors;
import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.support.TraceIds;
import dev.a2flow.management.agentcore.domain.AgentService;
import dev.a2flow.management.agentcore.domain.SessionService;
import dev.a2flow.management.agentcore.entity.Agent;
import dev.a2flow.management.agentcore.entity.Session;
import dev.a2flow.management.agentcore.exception.AgentServiceException;
import dev.a2flow.management.agentcore.exception.ResultCode;
import dev.a2flow.management.agentcore.infrastructrue.kconf.model.AgentPropertiesConfig;
import dev.a2flow.management.agentcore.runtime.engine.model.AgentEngineContext;
import dev.a2flow.management.agentcore.runtime.engine.model.AgentEngineResult;
import dev.a2flow.management.agentcore.runtime.engine.model.BaseAgentContext;
import dev.a2flow.management.agentcore.runtime.engine.model.SubAgentInfo;
import dev.a2flow.management.agentcore.tool.Constants;
import dev.a2flow.management.agentcore.tool.lock.Locker;
import dev.a2flow.management.agentcore.tool.lock.RedisLockFactory;
import dev.a2flow.management.agentcore.util.ToolUtil;
import dev.a2flow.management.aicoding.engine.AiCodingReActEngine;
import dev.a2flow.management.aicoding.run.SkillFactoryRunControlService;
import dev.a2flow.management.aicoding.run.SkillFactoryRunStatus;
import dev.a2flow.management.authoring.session.AuthoringSessionService;
import dev.a2flow.management.authoring.session.AuthoringSessionService.AuthoringRunContext;
import dev.a2flow.management.config.SkillFactoryAgentBizSummaryConfig;
import dev.a2flow.management.config.SkillFactoryConfigReader;
import dev.a2flow.management.event.AiCodingStreamEvent;
import dev.a2flow.management.event.AiCodingStreamEventFactory;
import dev.a2flow.management.event.AiCodingStreamResponseConverter;
import dev.a2flow.management.protobuf.InvokeRequest;
import dev.a2flow.management.protobuf.RecallKnowledgeParam;
import dev.a2flow.management.protobuf.SkillFactoryChatResponse;

import io.grpc.stub.StreamObserver;
import lombok.extern.slf4j.Slf4j;

/**
 * SkillFactory 专用流式运行时服务。
 *
 * <p>该类把原先依赖通用 {@code AgentRuntimeServiceImpl#invoke} 的 AI Coding 运行链路复制到
 * SkillFactory 目录内，负责参数校验、Agent/Session 校验、bizKey 配置加载、会话锁和事件响应
 * 转换。上游由 SkillFactory 专用 RPC 壳调用，下游直接执行 SkillFactory 结构化流式引擎，
 * 运行配置只读取 SkillFactory 独立 KConf `skillFactoryAgentBizSummaryMapConfig`。
 * 它不承接普通数字员工 Invoke、debug、cancel、知识库检查或 SkillFactory lifecycle 方法分发。
 */
@Component
@Slf4j
public class SkillFactoryChatRuntimeService {
    @jakarta.annotation.Resource
    private dev.a2flow.management.access.ManagementIdentityProvider managementIdentityProvider;

    private static final String BIZ_CONTEXT_CLIENT = "client";
    private static final String BIZ_CONTEXT_EXTRA_BIZ_PARAM = "extraBizParam";
    private static final String BIZ_CONTEXT_COOKIE = "cookie";
    private static final String FIELD_ACTION = "action";
    private static final String FIELD_WORKSPACE_ID = "workspaceId";
    private static final String FIELD_SKILL_CODE = "skillCode";
    private static final String FIELD_PATCH_ID = "patchId";
    private static final String FIELD_MESSAGE = "message";
    private static final String FIELD_QUERY = "query";
    private static final String FIELD_MESSAGE_LENGTH = "messageLength";
    private static final String FIELD_KEYS = "keys";
    private static final String FIELD_BIZ_KEY = "bizKey";
    private static final String FIELD_OWNER_ID = "ownerId";
    private static final String FIELD_AGENT_ID = "agentId";
    private static final String FIELD_SESSION_ID = "sessionId";
    private static final String FIELD_USER_ID = "userId";
    private static final String FIELD_INVOKE_ID = "invokeId";
    private static final String FIELD_MESSAGE_ID = "messageId";
    private static final String FIELD_RUN_ID = "runId";
    private static final String FIELD_CONVERSATION_ID = "conversationId";
    private static final String FIELD_CREATE_SESSION = "createSession";
    private static final String FIELD_CLIENT = "client";
    private static final String FIELD_BIZ_CONTEXT_KEYS = "bizContextKeys";
    private static final int DEFAULT_INVOKE_AGENT_THREAD_COUNT = 200;
    @Autowired
    private AiCodingReActEngine aiCodingReActEngine;

    @Autowired
    private RedisLockFactory redisLockFactory;

    @Autowired
    private AgentService agentService;

    @Autowired
    private SessionService sessionService;

    @Autowired
    private SkillFactoryConfigReader skillFactoryConfigReader;

    @Autowired
    private AuthoringSessionService authoringSessionService;

    @Autowired
    private AiCodingStreamEventFactory aiCodingStreamEventFactory;

    @Autowired
    private AiCodingStreamResponseConverter streamResponseConverter;

    @Autowired
    private SkillFactoryRunControlService runControlService;

    private final ExecutorService executorService =
            BoundedExecutors.fixed( DEFAULT_INVOKE_AGENT_THREAD_COUNT,
                    "skill-factory-chat-executor-%d");

    /**
     * 执行 SkillFactory AI Coding chat 流式请求。
     *
     * <p>该入口只服务 SkillFactory Authoring Chat。调用方传入业务 bizKey 和 scope 字段即可，
     * sessionId 由后端统一创建和管理；初始化成功后会在线程池里执行，避免阻塞 gRPC IO 线程。
     */
    public void invoke(InvokeRequest request, StreamObserver<SkillFactoryChatResponse> responseObserver) {
        log.info("SkillFactoryChatRuntimeService收到AI Coding流式请求, summary={}",
                invokeRequestSummary(request));
        AgentEngineContext context = new AgentEngineContext();
        AuthoringRunContext runContext;
        InvokeRequest runtimeRequest;
        try {
            checkInvokeParams(request);
            checkSkillFactoryBizKey(request);
            runContext = authoringSessionService.prepareRun(request);
            runtimeRequest = runContext.getRequest();
            Agent agent = bizCheck(runtimeRequest);
            buildEngineContext(context, runtimeRequest, agent);
            authoringSessionService.appendUserTurn(runContext, runtimeRequest);
        } catch (Exception e) {
            log.error("SkillFactoryChatRuntimeService请求初始化失败, summary={}",
                    invokeRequestSummary(request), e);
            responseObserver.onError(e);
            responseObserver.onCompleted();
            return;
        }

        AgentPropertiesConfig agentPropertiesConfig = context.getAgentPropertiesConfig();
        boolean sessionLock = agentPropertiesConfig.isSessionLock();
        String sessionId = runtimeRequest.getSessionId();
        String lockKey = Constants.SESSION_LOCK_KEY_PREFIX + sessionId;
        String lockValue = runtimeRequest.getInvokeId();
        AtomicReference<Locker> lockerRef = null;
        try {
            if (sessionLock) {
                lockerRef = new AtomicReference<>(redisLockFactory.getNonReentrantLock(lockKey, lockValue,
                        agentPropertiesConfig.getSessionLockTimeouts()));
            }
        } catch (Exception e) {
            log.warn("SkillFactoryChatRuntimeService获取会话锁失败, sessionId={}, lockKey={}, invokeId={}",
                    sessionId, lockKey, runtimeRequest.getInvokeId());
            if (StringUtils.isNotEmpty(agentPropertiesConfig.getSessionLockTips())) {
                Map<String, String> lockParams = new HashMap<>();
                lockParams.put(FIELD_SESSION_ID, StringUtils.defaultString(sessionId));
                SkillFactoryChatResponse lockTipResponse = streamResponseConverter.convert(
                        aiCodingStreamEventFactory.modelTextDelta(context.getAgentId(), lockParams,
                                agentPropertiesConfig.getSessionLockTips()), runtimeRequest.getInvokeId());
                AiCodingStreamEvent terminalEvent = isCancellationRequested(runtimeRequest)
                        ? aiCodingStreamEventFactory.runCancelled(context.getAgentId(), lockParams)
                        : aiCodingStreamEventFactory.runCompleted(context.getAgentId(), lockParams);
                SkillFactoryChatResponse terminalResponse = streamResponseConverter.convert(
                        terminalEvent,
                        runtimeRequest.getInvokeId());
                authoringSessionService.appendStreamEvent(runContext, lockTipResponse);
                authoringSessionService.appendAssistantTurn(
                        runContext, runtimeRequest, agentPropertiesConfig.getSessionLockTips());
                authoringSessionService.appendStreamEvent(runContext, terminalResponse);
                updateTerminalRunStatus(runtimeRequest, terminalEvent.getEventType());
                sendResponse(responseObserver, lockTipResponse, sessionId, lockTipResponse.getEventType());
                sendResponse(responseObserver, terminalResponse, sessionId, terminalResponse.getEventType());
            } else {
                responseObserver.onError(new AgentServiceException(ResultCode.SESSION_CONCURRENT_LOCK_FAILED));
            }
            completeObserver(responseObserver);
            return;
        }

        AtomicReference<Locker> finalLockerRef = lockerRef;
        log.info("SkillFactoryChatRuntimeService已提交AI Coding执行线程, agentId={}, sessionId={}, "
                        + "invokeId={}, bizKey={}",
                runtimeRequest.getAgentId(), runtimeRequest.getSessionId(), runtimeRequest.getInvokeId(),
                runtimeRequest.getBizKey());
        executorService.submit(() ->
                processWithLock(context, runtimeRequest, runContext, finalLockerRef, responseObserver));
    }

    private void checkSkillFactoryBizKey(InvokeRequest request) {
        if (skillFactoryConfigReader.getAgentBizSummaryConfig(request.getBizKey()) == null) {
            log.warn("SkillFactoryChatRuntimeService拒绝未配置的SkillFactory bizKey, requestBizKey={}, summary={}",
                    request.getBizKey(), invokeRequestSummary(request));
            throw new AgentServiceException(ResultCode.PARAM_ERROR);
        }
    }

    private void processWithLock(AgentEngineContext context, InvokeRequest request, AuthoringRunContext runContext,
            AtomicReference<Locker> lockerRef, StreamObserver<SkillFactoryChatResponse> responseObserver) {
        AtomicReference<String> terminalEventTypeRef = new AtomicReference<>();
        try {
            runControlService.registerCancellationToken(request.getSessionId(), request.getInvokeId(),
                    context.getCancellationRequested());
            log.info("SkillFactoryChatRuntimeService开始执行AI Coding引擎, agentId={}, sessionId={}, "
                            + "invokeId={}, bizKey={}",
                    context.getAgentId(), request.getSessionId(), request.getInvokeId(), request.getBizKey());
            SkillFactoryRunStatus runningStatus =
                    runControlService.markRunning(request.getSessionId(), request.getInvokeId());
            if (runningStatus.isTerminal()) {
                log.info("SkillFactoryChatRuntimeService忽略已结束运行的重复执行, sessionId={}, invokeId={}, "
                                + "status={}",
                        request.getSessionId(), request.getInvokeId(), runningStatus.getStatus());
                completeObserver(responseObserver);
                return;
            }
            if (StringUtils.equals(runningStatus.getStatus(), SkillFactoryRunStatus.STATUS_CANCELLING)) {
                context.getCancellationRequested().set(true);
                context.getCancellationObserved().set(true);
                handleEvent(aiCodingStreamEventFactory.runCancelled(context.getAgentId(), terminalParams(request)),
                        request.getSessionId(), request.getInvokeId(), runContext, responseObserver,
                        terminalEventTypeRef);
                completeObserver(responseObserver);
                return;
            }
            SkillFactoryRunCompletedEventGate runCompletedEventGate = new SkillFactoryRunCompletedEventGate(
                    event -> handleEvent(event, request.getSessionId(), request.getInvokeId(), runContext,
                            responseObserver, terminalEventTypeRef));
            AgentEngineResult engineResult = aiCodingReActEngine.execute(context, runCompletedEventGate);
            authoringSessionService.appendAssistantTurn(
                    runContext, request, engineResult.getFinallyAnswer());
            runCompletedEventGate.releaseRunCompleted();
            ensureTerminalEvent(context, request, runContext, responseObserver, terminalEventTypeRef);
            completeObserver(responseObserver);
        } catch (Throwable throwable) {
            // 先持久化终态再记录异常，避免日志依赖异常再次中断流并留下永久 RUNNING。
            completeWithTerminalFailure(context, request, runContext, responseObserver, terminalEventTypeRef,
                    throwable);
            log.warn("SkillFactoryChatRuntimeService执行异常并已补齐终态, sessionId={}, invokeId={}, bizKey={}",
                    request.getSessionId(), request.getInvokeId(), request.getBizKey(), throwable);
        } finally {
            runControlService.unregisterCancellationToken(request.getSessionId(), request.getInvokeId(),
                    context.getCancellationRequested());
            releaseSessionLock(lockerRef, request.getSessionId());
        }
    }

    private void ensureTerminalEvent(AgentEngineContext context, InvokeRequest request, AuthoringRunContext runContext,
            StreamObserver<SkillFactoryChatResponse> responseObserver,
            AtomicReference<String> terminalEventTypeRef) {
        if (StringUtils.isNotBlank(terminalEventTypeRef.get())) {
            return;
        }
        AiCodingStreamEvent terminalEvent = context.getCancellationObserved().get()
                ? aiCodingStreamEventFactory.runCancelled(context.getAgentId(), terminalParams(request))
                : aiCodingStreamEventFactory.runCompleted(context.getAgentId(), terminalParams(request));
        handleEvent(terminalEvent, request.getSessionId(), request.getInvokeId(), runContext, responseObserver,
                terminalEventTypeRef);
    }

    private void completeWithTerminalFailure(AgentEngineContext context, InvokeRequest request,
            AuthoringRunContext runContext, StreamObserver<SkillFactoryChatResponse> responseObserver,
            AtomicReference<String> terminalEventTypeRef, Throwable throwable) {
        if (StringUtils.isNotBlank(terminalEventTypeRef.get())) {
            retryTerminalRunStatus(request, terminalEventTypeRef.get());
            completeObserver(responseObserver);
            return;
        }
        Map<String, String> params = terminalParams(request);
        try {
            String errorMessage =
                    StringUtils.defaultIfBlank(throwable.getMessage(), throwable.getClass().getSimpleName());
            if (context.getCancellationObserved().get()) {
                handleEvent(aiCodingStreamEventFactory.runCancelled(context.getAgentId(), params),
                        request.getSessionId(), request.getInvokeId(), runContext, responseObserver,
                        terminalEventTypeRef);
            } else {
                emitDiagnosticError(context, request, runContext, responseObserver, terminalEventTypeRef,
                        params, errorMessage);
                handleEvent(aiCodingStreamEventFactory.runFailed(context.getAgentId(), params, errorMessage),
                        request.getSessionId(), request.getInvokeId(), runContext, responseObserver,
                        terminalEventTypeRef);
            }
            completeObserver(responseObserver);
        } catch (Throwable terminalThrowable) {
            String terminalEventType = terminalEventTypeRef.get();
            if (StringUtils.isNotBlank(terminalEventType)) {
                retryTerminalRunStatus(request, terminalEventType);
            } else {
                log.warn("SkillFactoryChatRuntimeService补齐终态历史失败并保留非终态状态, sessionId={}, "
                                + "invokeId={}",
                        request.getSessionId(), request.getInvokeId(), terminalThrowable);
            }
            completeObserver(responseObserver);
        }
    }

    private void retryTerminalRunStatus(InvokeRequest request, String terminalEventType) {
        try {
            // 终态历史已经落库而状态更新失败时，只重试状态；禁止再生成第二个终态事件。
            updateTerminalRunStatus(request, terminalEventType);
        } catch (Throwable statusThrowable) {
            log.warn("SkillFactoryChatRuntimeService重试更新终态状态失败, sessionId={}, invokeId={}, "
                            + "terminalType={}",
                    request.getSessionId(), request.getInvokeId(), terminalEventType, statusThrowable);
        }
    }

    private void emitDiagnosticError(AgentEngineContext context, InvokeRequest request,
            AuthoringRunContext runContext, StreamObserver<SkillFactoryChatResponse> responseObserver,
            AtomicReference<String> terminalEventTypeRef, Map<String, String> params, String errorMessage) {
        try {
            handleEvent(aiCodingStreamEventFactory.error(context.getAgentId(), params, errorMessage),
                    request.getSessionId(), request.getInvokeId(), runContext, responseObserver,
                    terminalEventTypeRef);
        } catch (Throwable diagnosticThrowable) {
            log.warn("SkillFactoryChatRuntimeService记录错误诊断事件失败, sessionId={}, invokeId={}",
                    request.getSessionId(), request.getInvokeId(), diagnosticThrowable);
        }
    }

    private void updateTerminalRunStatus(InvokeRequest request, String terminalEventType) {
        if (StringUtils.equals(AiCodingStreamEventFactory.EVENT_RUN_CANCELLED, terminalEventType)) {
            runControlService.markCancelled(request.getSessionId(), request.getInvokeId());
            return;
        }
        if (StringUtils.equals(AiCodingStreamEventFactory.EVENT_RUN_FAILED, terminalEventType)) {
            runControlService.markFailed(request.getSessionId(), request.getInvokeId());
            return;
        }
        runControlService.markCompleted(request.getSessionId(), request.getInvokeId());
    }

    private Map<String, String> terminalParams(InvokeRequest request) {
        Map<String, String> params = new HashMap<>();
        params.put(FIELD_SESSION_ID, StringUtils.defaultString(request.getSessionId()));
        params.put(FIELD_INVOKE_ID, StringUtils.defaultString(request.getInvokeId()));
        params.put(FIELD_MESSAGE_ID, StringUtils.defaultString(request.getInvokeId()));
        params.put(FIELD_RUN_ID, StringUtils.defaultString(request.getInvokeId()));
        params.put(FIELD_CONVERSATION_ID, StringUtils.defaultString(request.getSessionId()));
        return params;
    }

    private void handleEvent(AiCodingStreamEvent event, String sessionId, String invokeId, AuthoringRunContext runContext,
            StreamObserver<SkillFactoryChatResponse> responseObserver,
            AtomicReference<String> terminalEventTypeRef) {
        String eventType = event.getEventType();
        boolean terminalEvent = isTerminalEventType(eventType);
        if (terminalEvent) {
            if (!terminalEventTypeRef.compareAndSet(null, eventType)) {
                log.info("SkillFactoryChatRuntimeService忽略重复终态事件, sessionId={}, invokeId={}, "
                                + "acceptedTerminal={}, ignoredTerminal={}",
                        sessionId, invokeId, terminalEventTypeRef.get(), eventType);
                return;
            }
        } else if (StringUtils.isNotBlank(terminalEventTypeRef.get())) {
            log.info("SkillFactoryChatRuntimeService忽略终态后的非终态事件, sessionId={}, invokeId={}, "
                            + "terminalType={}, ignoredEventType={}",
                    sessionId, invokeId, terminalEventTypeRef.get(), eventType);
            return;
        }

        boolean eventPersisted = false;
        try {
            SkillFactoryChatResponse response = streamResponseConverter.convert(event, invokeId);
            // 历史和运行状态必须先于网络发送落地，刷新页面时才能恢复同一个确定终态。
            authoringSessionService.appendStreamEvent(runContext, response);
            eventPersisted = true;
            if (terminalEvent) {
                updateTerminalRunStatus(runContext.getRequest(), eventType);
            }
            sendResponse(responseObserver, response, sessionId, eventType);
        } catch (Throwable throwable) {
            // 只有终态尚未落历史时才允许后续补偿；已经持久化的终态是本次运行的唯一事实。
            if (terminalEvent && !eventPersisted) {
                terminalEventTypeRef.compareAndSet(eventType, null);
            }
            throw throwable;
        }
    }

    private boolean isTerminalEventType(String eventType) {
        return StringUtils.equalsAny(eventType, AiCodingStreamEventFactory.EVENT_RUN_COMPLETED,
                AiCodingStreamEventFactory.EVENT_RUN_FAILED, AiCodingStreamEventFactory.EVENT_RUN_CANCELLED);
    }

    private boolean isCancellationRequested(InvokeRequest request) {
        return isCancellationRequested(request.getSessionId(), request.getInvokeId());
    }

    private boolean isCancellationRequested(String sessionId, String invokeId) {
        SkillFactoryRunStatus currentStatus = runControlService.queryStatus(sessionId, invokeId);
        return StringUtils.equalsAny(currentStatus.getStatus(), SkillFactoryRunStatus.STATUS_CANCELLED,
                SkillFactoryRunStatus.STATUS_CANCELLING);
    }

    private Map<String, String> terminalParams(String sessionId, String invokeId) {
        Map<String, String> params = new HashMap<>();
        params.put(FIELD_SESSION_ID, StringUtils.defaultString(sessionId));
        params.put(FIELD_INVOKE_ID, StringUtils.defaultString(invokeId));
        params.put(FIELD_MESSAGE_ID, StringUtils.defaultString(invokeId));
        params.put(FIELD_RUN_ID, StringUtils.defaultString(invokeId));
        params.put(FIELD_CONVERSATION_ID, StringUtils.defaultString(sessionId));
        return params;
    }

    private void sendResponse(StreamObserver<SkillFactoryChatResponse> responseObserver,
            SkillFactoryChatResponse response, String sessionId, String eventType) {
        try {
            responseObserver.onNext(response);
        } catch (Throwable e) {
            // 客户端断连不能中断引擎和历史终态落库，停止运行必须走后端取消接口。
            log.warn("SkillFactoryChatRuntimeService发送流式事件失败但事件已落历史, sessionId={}, eventType={}",
                    sessionId, eventType);
        }
    }

    private void completeObserver(StreamObserver<SkillFactoryChatResponse> responseObserver) {
        try {
            responseObserver.onCompleted();
        } catch (Throwable throwable) {
            log.info("SkillFactoryChatRuntimeService完成流式响应时客户端已断开");
        }
    }

    private void releaseSessionLock(AtomicReference<Locker> lockerRef, String sessionId) {
        if (Objects.isNull(lockerRef)) {
            return;
        }
        Locker locker = lockerRef.getAndSet(null);
        if (locker != null) {
            try {
                locker.close();
                log.info("SkillFactoryChatRuntimeService释放会话锁, sessionId={}", sessionId);
            } catch (Exception e) {
                log.warn("SkillFactoryChatRuntimeService释放会话锁异常, sessionId={}", sessionId, e);
            }
        }
    }

    private Agent bizCheck(InvokeRequest request) {
        Agent agent = agentService.queryById(request.getBizKey(), request.getAgentId());
        if (agent == null) {
            throw new AgentServiceException(ResultCode.AGENT_NOT_FOUND);
        }
        if (StringUtils.isNotBlank(agent.getOwnerId()) && !agent.getOwnerId().equals(request.getOwnerId())) {
            throw new AgentServiceException(ResultCode.AGENT_OWNER_MISMATCH);
        }
        if (StringUtils.isBlank(agent.getOwnerId())) {
            agent.setOwnerId(request.getOwnerId());
        }
        if (StringUtils.isBlank(agent.getBizKey())) {
            agent.setBizKey(request.getBizKey());
        }

        Session session = sessionService.queryBySessionId(request.getSessionId());
        if (session == null && request.getCreateSession()) {
            session = new Session();
            session.setAgentId(request.getAgentId());
            session.setUserId(dev.a2flow.management.access.UserIds.parseWire(request.getUserId()));
            session.setSessionId(request.getSessionId());
            session.setCreateTime(System.currentTimeMillis());
            session.setUpdateTime(System.currentTimeMillis());
            sessionService.create(session);
            log.info("SkillFactoryChatRuntimeService已创建AI Coding会话, agentId={}, userId={}, sessionId={}",
                    request.getAgentId(), request.getUserId(), request.getSessionId());
        }
        if (session == null) {
            throw new AgentServiceException(ResultCode.PARAM_ERROR);
        }
        if (!session.getAgentId().equals(request.getAgentId())) {
            throw new AgentServiceException(ResultCode.SESSION_AGENT_MISMATCH);
        }
        if (!session.getUserId().equals(dev.a2flow.management.access.UserIds.parseWire(request.getUserId()))) {
            log.warn("SkillFactoryChatRuntimeService检测到共享session userId不一致, sessionId={}, "
                            + "sessionUserId={}, requestUserId={}",
                    request.getSessionId(), session.getUserId(), request.getUserId());
        }
        return agent;
    }

    private void checkInvokeParams(InvokeRequest request) {
        if (request == null || StringUtils.isBlank(request.getBizKey()) || StringUtils.isBlank(request.getOwnerId())
                || request.getAgentId() <= 0 || StringUtils.isBlank(request.getMessage())) {
            throw new AgentServiceException(ResultCode.PARAM_ERROR);
        }
        Long userId = dev.a2flow.management.access.UserIds.parseWire(request.getUserId());
        if (userId != managementIdentityProvider.userId()) {
            throw new IllegalArgumentException("Request userId does not match authenticated identity");
        }
    }

    private void buildEngineContext(AgentEngineContext context, InvokeRequest request, Agent agent) {
        context.setInvokeId(request.getInvokeId());
        context.setTraceId(TraceIds.currentOrCreate());
        context.setBizKey(request.getBizKey());
        context.setAgentId(agent.getAgentId());
        context.setAgentName(agent.getAgentName());
        context.setConversationId(request.getSessionId());
        context.setOwnerId(agent.getOwnerId());
        context.setUserId(dev.a2flow.management.access.UserIds.parseWire(request.getUserId()));
        context.setRecallKnowledgeParamMap(request.getRecallKnowledgeParamMap());
        RecallKnowledgeParam recallKnowledgeParam =
                MapUtils.getObject(request.getRecallKnowledgeParamMap(), agent.getAgentId());
        context.setRecallKnowledgeParam(recallKnowledgeParam);
        SkillFactoryAgentBizSummaryConfig skillFactoryBizConfig =
                skillFactoryConfigReader.getAgentBizSummaryConfig(request.getBizKey());
        if (skillFactoryBizConfig == null || skillFactoryBizConfig.getPropertiesConfig() == null) {
            log.warn("SkillFactoryChatRuntimeService未找到独立业务KConf, bizKey={}, agentId={}, sessionId={}",
                    request.getBizKey(), request.getAgentId(), request.getSessionId());
            throw new AgentServiceException(ResultCode.AGENT_BIZ_CONFIG_NOT_REGISTER);
        }
        AgentPropertiesConfig agentPropertiesConfig =
                skillFactoryConfigReader.buildAgentPropertiesConfig(skillFactoryBizConfig);
        if (StringUtils.isBlank(agentPropertiesConfig.getDefaultEngineStrategy())) {
            log.warn("SkillFactoryChatRuntimeService独立业务KConf缺少默认引擎策略, bizKey={}, agentId={}, sessionId={}",
                    request.getBizKey(), request.getAgentId(), request.getSessionId());
            throw new AgentServiceException(ResultCode.AGENT_BIZ_CONFIG_NOT_REGISTER);
        }
        log.info("SkillFactoryChatRuntimeService已加载AI Coding业务配置, requestBizKey={}, agentBizKey={}, "
                        + "agentId={}, sessionId={}, invokeId={}, defaultEngineStrategy={}",
                request.getBizKey(), agent.getBizKey(), request.getAgentId(), request.getSessionId(),
                request.getInvokeId(), agentPropertiesConfig.getDefaultEngineStrategy());
        context.setAgentPropertiesConfig(agentPropertiesConfig);
        context.setLlmModelConfig(skillFactoryConfigReader.buildLlmModelConfig(skillFactoryBizConfig));
        context.setAgentMemoryConfig(skillFactoryConfigReader.buildAgentMemoryConfig(skillFactoryBizConfig));
        List<String> skillList = CollectionUtils.emptyIfNull(agent.getSkills())
                .stream()
                .filter(skillName -> !agentPropertiesConfig.checkBlackSkill(skillName))
                .toList();
        context.setSkillList(skillList);
        context.setBizRolePrompt(agent.getSystemPrompt());

        BaseAgentContext agentContext = new BaseAgentContext();
        agentContext.setUserMessage(request.getMessage());
        agentContext.setOwnerId(request.getOwnerId());
        agentContext.setUserId(dev.a2flow.management.access.UserIds.parseWire(request.getUserId()));
        fillExtraBizParam(agentContext, request);
        agentContext.setEnv(ToolUtil.getEnvName());
        agentContext.setClient(MapUtils.getString(request.getBizContextMap(), BIZ_CONTEXT_CLIENT, StringUtils.EMPTY));
        agentContext.setCookie(MapUtils.getString(request.getBizContextMap(), BIZ_CONTEXT_COOKIE, StringUtils.EMPTY));
        context.setAgentContext(agentContext);

        List<Agent> subAgentList = agentService.querySubAgent(request.getAgentId());
        List<SubAgentInfo> subAgentInfoList = CollectionUtils.emptyIfNull(subAgentList).stream().map(
                subAgent -> {
                    SubAgentInfo agentInfo = new SubAgentInfo();
                    agentInfo.setAgentId(subAgent.getAgentId());
                    agentInfo.setAgentName(subAgent.getAgentName());
                    agentInfo.setBizRolePrompt(StringUtils.defaultString(subAgent.getSystemPrompt()));
                    agentInfo.setHitRangeDesc(StringUtils.defaultString(subAgent.getDescription()));
                    List<String> subAgentSkillList = CollectionUtils.emptyIfNull(subAgent.getSkills())
                            .stream()
                            .filter(skillName -> !agentPropertiesConfig.checkBlackSkill(skillName))
                            .toList();
                    agentInfo.setSkillList(subAgentSkillList);
                    return agentInfo;
                }
        ).toList();
        context.setSubAgentInfoList(subAgentInfoList);
    }

    private void fillExtraBizParam(BaseAgentContext agentContext, InvokeRequest request) {
        String extraBizParamStr = MapUtils.getString(request.getBizContextMap(), BIZ_CONTEXT_EXTRA_BIZ_PARAM,
                StringUtils.EMPTY);
        if (StringUtils.isBlank(extraBizParamStr)) {
            return;
        }
        try {
            Map<String, Object> extraBizParam = JsonSupport.fromJson(extraBizParamStr);
            agentContext.setExtraBizParam(extraBizParam);
            log.info("SkillFactoryChatRuntimeService extraBizParam解析完成, agentId={}, sessionId={}, "
                            + "invokeId={}, summary={}",
                    request.getAgentId(), request.getSessionId(), request.getInvokeId(),
                    extraBizParamSummary(extraBizParam));
        } catch (Exception e) {
            log.error("SkillFactoryChatRuntimeService解析extraBizParam异常, length={}",
                    StringUtils.length(extraBizParamStr), e);
        }
    }

    private String invokeRequestSummary(InvokeRequest request) {
        if (request == null) {
            return "{}";
        }
        Map<String, Object> summary = new HashMap<>();
        summary.put(FIELD_BIZ_KEY, request.getBizKey());
        summary.put(FIELD_OWNER_ID, request.getOwnerId());
        summary.put(FIELD_AGENT_ID, request.getAgentId());
        summary.put(FIELD_SESSION_ID, request.getSessionId());
        summary.put(FIELD_USER_ID, request.getUserId());
        summary.put(FIELD_INVOKE_ID, request.getInvokeId());
        summary.put(FIELD_CREATE_SESSION, request.getCreateSession());
        summary.put(FIELD_MESSAGE_LENGTH, StringUtils.length(request.getMessage()));
        summary.put(FIELD_CLIENT, MapUtils.getString(request.getBizContextMap(), BIZ_CONTEXT_CLIENT));
        summary.put(FIELD_BIZ_CONTEXT_KEYS, request.getBizContextMap().keySet().toString());
        return JsonSupport.toJSON(summary);
    }

    private String extraBizParamSummary(Map<String, Object> extraBizParam) {
        if (extraBizParam == null) {
            return "{}";
        }
        Map<String, Object> summary = new HashMap<>();
        summary.put(FIELD_ACTION, MapUtils.getString(extraBizParam, FIELD_ACTION));
        summary.put(FIELD_WORKSPACE_ID, MapUtils.getString(extraBizParam, FIELD_WORKSPACE_ID));
        summary.put(FIELD_SKILL_CODE, MapUtils.getString(extraBizParam, FIELD_SKILL_CODE));
        summary.put(FIELD_PATCH_ID, MapUtils.getString(extraBizParam, FIELD_PATCH_ID));
        summary.put(FIELD_MESSAGE_LENGTH, StringUtils.length(StringUtils.defaultIfBlank(
                MapUtils.getString(extraBizParam, FIELD_MESSAGE), MapUtils.getString(extraBizParam, FIELD_QUERY))));
        summary.put(FIELD_KEYS, extraBizParam.keySet().toString());
        return JsonSupport.toJSON(summary);
    }
}
