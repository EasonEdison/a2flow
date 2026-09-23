package dev.a2flow.management.aicoding.engine;

import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Consumer;

import jakarta.annotation.Resource;

import org.apache.commons.collections4.CollectionUtils;
import org.apache.commons.collections4.MapUtils;
import org.apache.commons.lang3.StringUtils;
import org.springframework.ai.chat.messages.AssistantMessage;
import org.springframework.ai.chat.messages.Message;
import org.springframework.ai.chat.messages.SystemMessage;
import org.springframework.ai.chat.model.ChatResponse;
import org.springframework.ai.chat.model.ToolContext;
import org.springframework.ai.tool.ToolCallback;
import org.springframework.stereotype.Component;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.agentcore.infrastructrue.kconf.model.AgentPropertiesConfig;
import dev.a2flow.management.agentcore.runtime.engine.model.AgentEngineContext;
import dev.a2flow.management.agentcore.runtime.engine.model.AgentEngineResult;
import dev.a2flow.management.agentcore.runtime.engine.model.BaseAgentContext;
import dev.a2flow.management.agentcore.runtime.enums.AgentEngineResultCode;
import dev.a2flow.management.agentcore.runtime.prompt.PromptManager;
import dev.a2flow.management.agentcore.runtime.session.AgentSession;
import dev.a2flow.management.agentcore.runtime.session.SessionManager;
import dev.a2flow.management.agentcore.runtime.skill.SkillFactoryMountedSkillResolver;
import dev.a2flow.management.agentcore.runtime.skill.SkillManager;
import dev.a2flow.management.agentcore.runtime.skill.SkillMetadata;
import dev.a2flow.management.agentcore.runtime.tool.ToolException;
import dev.a2flow.management.agentcore.runtime.tool.ToolExecutor;
import dev.a2flow.management.agentcore.runtime.tool.ToolManager;
import dev.a2flow.management.agentcore.runtime.tool.model.ToolResult;
import dev.a2flow.management.agentcore.tool.AgentBizTool;
import dev.a2flow.management.aicoding.AiCodingActionCodes;
import dev.a2flow.management.aicoding.SkillFactoryAiCodingService;
import dev.a2flow.management.aicoding.dependency.SkillAuthoringDependencyService;
import dev.a2flow.management.aicoding.tool.common.SkillFactoryCurlToolCallback;
import dev.a2flow.management.aicoding.tool.common.SkillFactoryPythonToolCallback;
import dev.a2flow.management.aicoding.tool.common.SkillFactoryReadToolCallback;
import dev.a2flow.management.aicoding.tool.common.SkillFactoryToolPathResolver;
import dev.a2flow.management.aicoding.tool.common.SkillFactoryTreeToolCallback;
import dev.a2flow.management.aicoding.tool.skill.SkillFactoryQueryRecentSkillRunsToolCallback;
import dev.a2flow.management.aicoding.tool.skill.SkillFactoryQuerySkillRunDetailToolCallback;
import dev.a2flow.management.aicoding.tool.skill.SkillFactoryUseSkillToolCallback;
import dev.a2flow.management.aicoding.validation.SkillFactoryPeerAgentInvocationService;
import dev.a2flow.management.aicoding.validation.SkillFactoryValidationReportStore;
import dev.a2flow.management.aicoding.validation.ValidationReport;

import dev.a2flow.management.config.SkillFactoryConfigReader;
import dev.a2flow.management.event.AiCodingEventCode;
import dev.a2flow.management.event.AiCodingEventPayload;
import dev.a2flow.management.event.AiCodingEventPayloadCodec;
import dev.a2flow.management.event.AiCodingEventPayloadFactory;
import dev.a2flow.management.event.AiCodingStreamEvent;
import dev.a2flow.management.event.AiCodingStreamEventFactory;
import dev.a2flow.management.fileguard.WorkspaceModelContext;
import dev.a2flow.management.fileguard.WorkspaceSnapshot;

import lombok.extern.slf4j.Slf4j;

/**
 * SkillFactory AI Coding 专用流式引擎。
 *
 * <p>该引擎承接 M 端 Skill 工程生成/修改对话，以及业务能力中心、组件中心的表单 Authoring 对话，
 * 负责把 adviser 透传的 chat 直接字段转换成 ReAct 参数。Skill 工程对话必须绑定已注册文件工作区；
 * 表单 Authoring 只使用请求内表单上下文和受控表单 Tool，不创建或读取 Skill workspace。场景仍由
 * bizKey、agentId、prompt profile 和工具配置区分；本类不负责 SkillFactory lifecycle、工作区通用接口、
 * 包发布和持久层能力。
 */
@SuppressWarnings({"checkstyle:ParameterNumber", "checkstyle:MagicNumber"})
@Slf4j
@Component
public class AiCodingReActEngine {

    private static final String FIELD_ACTION = "action";
    private static final String FIELD_WORKSPACE_ID = "workspaceId";
    private static final String FIELD_SKILL_CODE = "skillCode";
    private static final String FIELD_SESSION_ID = "sessionId";
    private static final String FIELD_MESSAGE = "message";
    private static final String FIELD_USER_NAME = "userName";
    private static final String FIELD_PATCH_ID = "patchId";

    private static final String FIELD_DECISION = "decision";
    private static final String FIELD_DECISION_MESSAGE = "decisionMessage";
    private static final String FIELD_IDEMPOTENCY_KEY = "idempotencyKey";
    private static final String FIELD_WORKSPACE_ROOT = "workspaceRoot";
    private static final String FIELD_TRACE_ID = "traceId";
    private static final String FIELD_RUN_ID = "runId";
    private static final String FIELD_CONVERSATION_ID = "conversationId";
    private static final String FIELD_MESSAGE_ID = "messageId";
    private static final String FIELD_BIZ_KEY = "bizKey";
    private static final String FIELD_SURFACE_ID = "surfaceId";
    private static final String FIELD_SOURCE_COMPONENT_ID = "sourceComponentId";
    private static final String FIELD_ACTION_CODE = "actionCode";
    private static final String FIELD_ACTION_PARAMS = "actionParams";
    private static final String FIELD_REFERENCE_COMPONENT_CODES = "referenceComponentCodes";
    private static final String FIELD_REFERENCE_RENDER_ASSETS = "referenceRenderAssets";
    private static final String FIELD_TEST_INPUT = "testInput";
    private static final String FIELD_VALIDATION_REPORT = "validationReport";
    private static final String FIELD_VALIDATION_REPORT_ID = "validationReportId";
    private static final String FIELD_AUTHORING_DOMAIN = "authoringDomain";
    private static final String FIELD_ASSET_TYPE = "assetType";
    private static final String FIELD_ASSET_ID = "assetId";
    private static final String FIELD_DRAFT_ID = "draftId";
    private static final String FIELD_FORM_KEY = "formKey";
    private static final String FIELD_ENTITY_ID = "entityId";
    private static final String FIELD_REVISION = "revision";
    private static final String FIELD_CURRENT_DRAFT = "currentDraft";
    private static final String FIELD_EVENT_CODE = "eventCode";

    private static final String FIELD_REQUIRED = "required";
    private static final String FIELD_ERROR_MSG = "errorMsg";
    private static final String FIELD_TASK_TYPE = "taskType";
    private static final String FIELD_EXPECTED_OUTPUT_TYPE = "expectedOutputType";
    private static final String FIELD_CONTENT = "content";
    private static final String FIELD_PAYLOAD_TYPE = "payloadType";
    private static final String FIELD_SUMMARY = "summary";
    private static final String FIELD_REPORT = "report";
    private static final String FIELD_AI_CODING_RUNTIME_CONTEXT = "aiCodingRuntimeContext";

    private static final String DEFAULT_SKILL_CODE = "ai-coding-draft";
    private static final String ENGINE_STRATEGY_AI_CODING_REACT = "aiCodingReAct";
    private static final String TOOL_TREE = "tree";
    private static final String TOOL_FIND = "find";
    private static final String TOOL_GREP = "grep";
    private static final String TOOL_READ = "read";
    private static final String TOOL_DIFF = "diff";
    private static final String TOOL_PYTHON = "python";
    private static final String TOOL_CURL = "curl";
    private static final String TOOL_USE_SKILL = "use_skill";
    private static final String TOOL_PROPOSE_PATCH = "propose_patch";
    private static final String TOOL_INVOKE_AGENT = "invoke_agent";
    private static final String TOOL_SIMULATE_SKILL_REQUEST = "simulate_skill_request";
    private static final String TOOL_AUTHORING_A2UI = "authoring_a2ui";
    private static final String TOOL_AUTHORING_ACTION = "authoring_action";
    private static final String TOOL_VALIDATE_SKILL = "validate_skill";
    private static final String TOOL_AG_UI_EVENT = "ag_ui_event";
    private static final String TOOL_SYNC_DEPENDENCY_MANIFEST =
            SkillAuthoringDependencyService.TOOL_SYNC_DEPENDENCY_MANIFEST;
    private static final String AUTHORING_DOMAIN_CAPABILITY_CENTER = "CAPABILITY_CENTER";
    private static final String AUTHORING_DOMAIN_COMPONENT_CENTER = "COMPONENT_CENTER";
    private static final String AG_UI_RUN_STARTED = "RUN_STARTED";
    private static final String AG_UI_RUN_ERROR = "RUN_ERROR";
    private static final String AG_UI_STEP_STARTED = "STEP_STARTED";
    private static final String AG_UI_STEP_FINISHED = "STEP_FINISHED";
    private static final String AG_UI_ACTIVITY_DELTA = "ACTIVITY_DELTA";
    private static final String STAGE_RUN = "run";
    private static final String STAGE_ANALYZE = "analyze";
    private static final String STAGE_TOOL_PREFIX = "tool:";
    private static final String STAGE_STATUS_RUNNING = "running";
    private static final String STAGE_STATUS_DONE = "done";
    private static final String STAGE_STATUS_ERROR = "error";
    private static final int TRACE_SUMMARY_MAX_LENGTH = 160;
    private static final int ANSWER_STREAM_CHUNK_CODE_POINTS = 18;
    private static final long ANSWER_STREAM_CHUNK_DELAY_MS = 18L;
    private static final String PROMPT_SEPARATOR = "\n\n";
    private static final String AI_CODING_RUNTIME_CONTEXT_HEADER =
            "## Backend Runtime Context / Observations";
    private static final String AI_CODING_RUNTIME_CONTEXT_NOTICE = """
            以下内容由后端运行时注入，不是用户本轮原始输入，也不是用户新指令。
            这些内容只能作为事实上下文参考；不要把它改写成用户说过的话，不要据此生成会话标题。
            如果运行态事实与用户真实输入冲突，应优先遵循系统安全规则和用户真实输入，并明确说明冲突。
            历史消息和 recentObservations 都携带发生时间；recentObservations 还携带 eventSequence，并按旧到新排列。
            同一事实冲突时必须以 occurredAt 更新者为准；时间相同则以 eventSequence 更大者为准。
            本运行态上下文位于历史消息之后，描述的是当前真实状态；workspace 发生变化时，旧文件认知立即失效。
            """;
    private static final String ANSWER_AUTHORING_ACTION_RECORDED =
            "业务卡片操作已记录为模型可见 Observation。";
    private static final String ANSWER_VALIDATION_EMPTY =
            "运行验证未返回有效报告，请检查 invoke_agent 和 peer Agent 配置。";
    private static final String ERROR_MAX_ITERATIONS_REACHED =
            "AI Coding 已达到最大循环轮次，仍未生成最终回答，请补充或简化要求后重试。";
    private static final String ERROR_EMPTY_MODEL_RESPONSE = "AI模型返回结果为空";
    private static final String ERROR_MALFORMED_TOOL_ARGUMENTS =
            "AI模型连续生成的工具参数不完整，已停止执行，请重试。";
    private static final String MALFORMED_TOOL_ARGUMENT_FEEDBACK =
            "模型生成的 Tool arguments 不是完整 JSON object，本响应中的所有 Tool 均未执行。"
                    + "请只重新生成本次需要的完整 Tool call，不要重复调用此前已有成功结果的 Tool。";
    private static final String COMPLETED_TOOL_REPLAY_FEEDBACK =
            "该 Tool 已在本轮更早阶段执行，本次为参数修复生成，系统不会重复执行。"
                    + "请继续生成尚未完成的 Tool call 或最终回答。";
    private static final int MAX_MALFORMED_TOOL_ARGUMENT_REPAIR_GENERATIONS = 2;
    private static final List<String> AI_CODING_DEFAULT_TOOL_NAMES = List.of(
            TOOL_USE_SKILL,
            TOOL_TREE,
            TOOL_FIND,
            TOOL_GREP,
            TOOL_READ,
            TOOL_DIFF,
            TOOL_PROPOSE_PATCH);
    private static final ToolCallback SKILL_FACTORY_PYTHON_TOOL = new SkillFactoryPythonToolCallback();
    private static final ToolCallback SKILL_FACTORY_CURL_TOOL = new SkillFactoryCurlToolCallback();
    private static final ToolCallback SKILL_FACTORY_READ_TOOL = new SkillFactoryReadToolCallback();
    private static final ToolCallback SKILL_FACTORY_TREE_TOOL = new SkillFactoryTreeToolCallback();

    @Resource
    private SkillFactoryAiCodingService aiCodingService;

    @Resource
    private SkillAuthoringDependencyService authoringDependencyService;

    @Resource
    private SkillFactoryPeerAgentInvocationService peerAgentInvocationService;

    @Resource
    private SkillFactoryValidationReportStore validationReportStore;

    @Resource
    private AiCodingEventPayloadFactory aiCodingEventPayloadFactory;

    @Resource
    private AiCodingEventPayloadCodec aiCodingEventPayloadCodec;

    @Resource
    private AiCodingStreamEventFactory aiCodingStreamEventFactory;

    @Resource
    private SessionManager sessionManager;

    @Resource
    private SkillFactoryAiCodingModelClient skillFactoryAiCodingModelClient;

    @Resource
    private ToolManager toolManager;

    @Resource
    private ToolExecutor toolExecutor;

    @Resource
    private PromptManager promptManager;

    @Resource
    private SkillManager skillManager;

    @Resource
    private SkillFactoryMountedSkillResolver mountedSkillResolver;

    @Resource
    private SkillFactoryQueryRecentSkillRunsToolCallback queryRecentSkillRunsToolCallback;

    @Resource
    private SkillFactoryQuerySkillRunDetailToolCallback querySkillRunDetailToolCallback;

    @Resource
    private AgentBizTool agentBizTool;

    @Resource
    private SkillFactoryConfigReader skillFactoryConfigReader;

    @Resource
    private List<AiCodingModelStreamAdapter> modelStreamAdapters;

    public String getEngineStrategy() {
        return ENGINE_STRATEGY_AI_CODING_REACT;
    }

    /**
     * AI Coding 的统一结构化执行入口。
     *
     * <p>该方法只根据 chat 请求中的 `action` 做 AI Coding 内部动作分流：普通对话进入
     * 本类自己的模型流式循环，确认/丢弃 patch 进入受控文件操作。这里不承接
     * SkillFactory lifecycle、组件中心、发布、版本管理或持久层职责。
     * 本方法输出 SkillFactory 专用 `AiCodingStreamEvent`，公共引擎兼容转换由包外
     * bridge 承接，避免 SkillFactory 层继续依赖通用事件模型。
     */
    public AgentEngineResult execute(AgentEngineContext engineContext, Consumer<AiCodingStreamEvent> sink) {
        long agentId = engineContext.getAgentId();
        Map<String, String> params = buildParams(engineContext);
        String action = StringUtils.defaultString(params.get(FIELD_ACTION));
        try {
            log.info("AiCodingReActEngine开始执行, agentId={}, traceId={}, summary={}",
                    agentId, engineContext.getTraceId(), paramsSummary(params));
            if (StringUtils.equalsIgnoreCase(AiCodingActionCodes.CODING_VALIDATE, action)) {
                log.info("AiCodingReActEngine路由到动态运行验证, agentId={}, summary={}",
                        agentId, paramsSummary(params));
                return runValidation(agentId, params, sink);
            }
            if (StringUtils.equalsIgnoreCase(AiCodingActionCodes.AUTHORING_UI_ACTION, action)) {
                log.info("AiCodingReActEngine路由到A2UI业务动作, agentId={}, summary={}",
                        agentId, paramsSummary(params));
                return recordAuthoringAction(agentId, params, sink);
            }
            if (StringUtils.equalsIgnoreCase(AiCodingActionCodes.CODING_VALIDATION_REPAIR, action)) {
                log.info("AiCodingReActEngine路由到运行验证报告修复, agentId={}, summary={}",
                        agentId, paramsSummary(params));
            }
            log.info("AiCodingReActEngine路由到模型ReAct流式chat, agentId={}, summary={}",
                    agentId, paramsSummary(params));
            WorkspaceSnapshot workspaceSnapshot = prepareModelChatContext(engineContext, params);
            return executeModelChat(engineContext, params, workspaceSnapshot, sink);
        } catch (AiCodingCancellationException e) {
            emit(sink, aiCodingStreamEventFactory.runCancelled(agentId, params));
            log.info("AiCodingReActEngine已观测取消并输出终态, agentId={}, sessionId={}, invokeId={}",
                    agentId, engineContext.getConversationId(), engineContext.getInvokeId());
            return AgentEngineResult.error(AgentEngineResultCode.termination);
        } catch (Throwable e) {
            emitAgUiEvent(agentId, params, sink, AG_UI_RUN_ERROR, STAGE_RUN, "执行过程异常",
                    StringUtils.defaultString(e.getMessage()), STAGE_STATUS_ERROR, null, null, false);
            String errorMessage = StringUtils.defaultIfBlank(e.getMessage(), e.getClass().getSimpleName());
            emit(sink, aiCodingStreamEventFactory.error(agentId, params, errorMessage));
            emit(sink, aiCodingStreamEventFactory.runFailed(agentId, params, errorMessage));
            log.warn("AiCodingReActEngine执行异常并已输出终态, agentId={}, summary={}",
                    agentId, paramsSummary(params), e);
            return AgentEngineResult.error(e.getMessage());
        }
    }

    private AgentEngineResult recordAuthoringAction(long agentId, Map<String, String> params,
            Consumer<AiCodingStreamEvent> sink) {
        long startTime = System.currentTimeMillis();
        String toolCallId = buildToolCallId(TOOL_AUTHORING_ACTION, params.get(FIELD_MESSAGE_ID));
        log.info("AiCodingReActEngine开始处理A2UI业务动作, agentId={}, toolCallId={}, summary={}",
                agentId, toolCallId, paramsSummary(params));
        emit(sink, aiCodingStreamEventFactory.runStarted(agentId, params));
        emit(sink, aiCodingStreamEventFactory.toolCallStarted(agentId, params, toolCallId, TOOL_AUTHORING_ACTION,
                safeToolArgs(params)));
        String payloadJson = aiCodingService.recordAuthoringActionObservation(params);
        emit(sink, aiCodingStreamEventFactory.toolCallFinished(agentId, params, toolCallId,
                TOOL_AUTHORING_ACTION, payloadJson, true, false));
        emit(sink, aiCodingStreamEventFactory.observationCreated(agentId, params, toolCallId,
                TOOL_AUTHORING_ACTION, payloadJson));
        emit(sink, aiCodingStreamEventFactory.modelTextDelta(agentId, params,
                ANSWER_AUTHORING_ACTION_RECORDED));
        emit(sink, aiCodingStreamEventFactory.runCompleted(agentId, params));
        log.info("AiCodingReActEngine处理A2UI业务动作完成, agentId={}, toolCallId={}, costMs={}, summary={}",
                agentId, toolCallId, System.currentTimeMillis() - startTime, paramsSummary(params));
        return AgentEngineResult.success(ANSWER_AUTHORING_ACTION_RECORDED, agentId);
    }

    /**
     * 执行当前 Skill 工作区的只读动态运行验证。
     *
     * <p>该路径由主 Agent 在同一条 chat 流里启动 CheckAgent 子任务。CheckAgent 只返回结构化
     * `ValidationReport`，不生成代码、不写 workspace，也不调用 lifecycle 发布接口。
     */
    private AgentEngineResult runValidation(long agentId, Map<String, String> params, Consumer<AiCodingStreamEvent> sink) {
        long startTime = System.currentTimeMillis();
        String toolCallId = buildToolCallId(TOOL_VALIDATE_SKILL, params.get(FIELD_MESSAGE_ID));
        log.info("AiCodingReActEngine开始动态运行验证, agentId={}, toolCallId={}, summary={}",
                agentId, toolCallId, paramsSummary(params));
        emit(sink, aiCodingStreamEventFactory.runStarted(agentId, params));
        emitAgUiEvent(agentId, params, sink, AG_UI_STEP_STARTED, "validation", "正在运行验证",
                "CheckAgent 将只读读取当前 preprod/current 工作区并识别输出协议。", STAGE_STATUS_RUNNING,
                toolCallId, TOOL_VALIDATE_SKILL, true);
        emit(sink, aiCodingStreamEventFactory.validationTaskStarted(agentId, params, toolCallId,
                TOOL_VALIDATE_SKILL, safeValidationTaskPayload(params)));
        emit(sink, aiCodingStreamEventFactory.toolCallStarted(agentId, params, toolCallId, TOOL_VALIDATE_SKILL,
                safeValidationToolArgs(params)));
        String payloadJson = peerAgentInvocationService.invoke(params, validationPeerAgentInput(params));
        ValidationReport report = validationReportFromPayload(payloadJson);
        boolean toolSuccess = report != null;
        emit(sink, aiCodingStreamEventFactory.toolCallFinished(agentId, params, toolCallId,
                TOOL_VALIDATE_SKILL, payloadJson, toolSuccess, false));
        emit(sink, aiCodingStreamEventFactory.validationReportCreated(agentId, params, toolCallId,
                TOOL_VALIDATE_SKILL, payloadJson, toolSuccess));
        emitAgUiEvent(agentId, params, sink, AG_UI_STEP_FINISHED, "validation", "运行验证完成",
                report == null ? "运行验证未返回有效报告。" : validationTraceSummary(report),
                report == null || StringUtils.equals(ValidationReport.STATUS_FAILED,
                        report.getStatus()) ? STAGE_STATUS_ERROR : STAGE_STATUS_DONE,
                toolCallId, TOOL_VALIDATE_SKILL,
                report != null && !StringUtils.equals(ValidationReport.STATUS_FAILED, report.getStatus()));
        String finalAnswer = report == null ? ANSWER_VALIDATION_EMPTY : validationAnswerSummary(report);
        emit(sink, aiCodingStreamEventFactory.modelTextDelta(agentId, params, finalAnswer));
        emit(sink, aiCodingStreamEventFactory.runCompleted(agentId, params));
        log.info("AiCodingReActEngine动态运行验证完成, agentId={}, toolCallId={}, status={}, checkCount={}, "
                        + "issueCount={}, costMs={}, summary={}",
                agentId, toolCallId, report == null ? "UNKNOWN" : report.getStatus(),
                report == null ? 0 : report.getChecks().size(), report == null ? 0 : report.getIssues().size(),
                System.currentTimeMillis() - startTime, paramsSummary(params));
        return AgentEngineResult.success(finalAnswer, agentId);
    }

    private Map<String, Object> validationPeerAgentInput(Map<String, String> params) {
        Map<String, Object> input = new HashMap<>();
        input.put(FIELD_TASK_TYPE, "SKILL_RUNTIME_VALIDATION");
        input.put(FIELD_EXPECTED_OUTPUT_TYPE, "ValidationReport");
        input.put(FIELD_WORKSPACE_ID, params.get(FIELD_WORKSPACE_ID));
        input.put(FIELD_SKILL_CODE, params.get(FIELD_SKILL_CODE));
        input.put(FIELD_TEST_INPUT, params.get(FIELD_TEST_INPUT));
        input.put(FIELD_REFERENCE_RENDER_ASSETS, params.get(FIELD_REFERENCE_RENDER_ASSETS));
        input.put(FIELD_MESSAGE, "请作为 CheckAgent 只读运行验证当前 Skill，必须先调用 simulate_skill_request。");
        return input;
    }

    private ValidationReport validationReportFromPayload(String payloadJson) {
        try {
            Map<String, Object> payload = parsePayloadRecord(payloadJson);
            Map<String, Object> content = mapValue(payload.get(FIELD_CONTENT));
            Object report = content.get(FIELD_REPORT);
            if (report == null) {
                return null;
            }
            return JsonSupport.fromJSON(JsonSupport.toJSON(report), ValidationReport.class);
        } catch (Exception e) {
            log.warn("AiCodingReActEngine解析运行验证报告失败, payloadLength={}",
                    StringUtils.length(payloadJson), e);
            return null;
        }
    }

    private void emitAuthoringBusinessCard(long agentId, Map<String, String> params, Consumer<AiCodingStreamEvent> sink) {
        String toolCallId = buildToolCallId(TOOL_AUTHORING_A2UI, params.get(FIELD_MESSAGE_ID));
        try {
            String payloadJson = aiCodingService.buildAuthoringA2uiMessage(params);
            emit(sink, aiCodingStreamEventFactory.businessInteractionCreated(agentId, params, toolCallId,
                    TOOL_AUTHORING_A2UI, payloadJson));
            log.info("AiCodingReActEngine已发送A2UI业务卡片, agentId={}, toolCallId={}, summary={}",
                    agentId, toolCallId, paramsSummary(params));
        } catch (Exception e) {
            log.warn("AiCodingReActEngine发送A2UI业务卡片失败, agentId={}, toolCallId={}, summary={}",
                    agentId, toolCallId, paramsSummary(params), e);
        }
    }

    /**
     * 执行 AI Coding 模型对话循环。
     *
     * <p>这里直接使用 SkillFactory 本地模型客户端、ToolManager、ToolExecutor 和 AgentSession
     * 组装 AI Coding 专属 ReAct 流，不复用普通数字员工的 `ReActAgentStreamEngine#execute`。
     * 每轮模型输出先收集完整 assistant message，再执行工具并把工具响应提交回 session。
     */
    private AgentEngineResult executeModelChat(AgentEngineContext engineContext, Map<String, String> params,
            WorkspaceSnapshot workspaceSnapshot, Consumer<AiCodingStreamEvent> sink) {
        long startTime = System.currentTimeMillis();
        long agentId = engineContext.getAgentId();
        BaseAgentContext agentContext = engineContext.getAgentContext();
        AgentPropertiesConfig properties = engineContext.getAgentPropertiesConfig();
        String conversationId = engineContext.getConversationId();
        String cancelSessionId = StringUtils.defaultIfBlank(engineContext.getPrimaryConversationId(), conversationId);
        emit(sink, aiCodingStreamEventFactory.runStarted(agentId, params));
        logSkippedBasicInfo(agentId, params);
        List<ToolCallback> tools = resolveAiCodingToolCallbacks(properties, engineContext);
        AgentSession session = sessionManager.buildAgentSession(agentId, engineContext.getUserId(),
                conversationId, engineContext.getAgentMemoryConfig(), engineContext.getInvokeId());
        session.addUserMessage(agentContext.getUserMessage());
        AtomicInteger iteration = new AtomicInteger(0);
        AtomicInteger totalTokens = new AtomicInteger(0);
        AtomicInteger enterTokens = new AtomicInteger(0);
        AtomicInteger outputTokens = new AtomicInteger(0);
        String systemPrompt = buildAiCodingSystemPrompt(engineContext);
        boolean answered = false;
        boolean workspaceSnapshotRecorded = false;
        String finallyAnswer = StringUtils.EMPTY;
        String runtimeContext = resolveAiCodingRuntimeContext(agentContext);
        AiCodingMalformedToolRepairState malformedToolRepairState =
                new AiCodingMalformedToolRepairState(MAX_MALFORMED_TOOL_ARGUMENT_REPAIR_GENERATIONS);
        Set<String> completedToolNames = new HashSet<>();

        emitAgUiEvent(agentId, params, sink, AG_UI_RUN_STARTED, STAGE_RUN, "开始处理请求",
                "已进入 SkillFactory AI Coding 引擎，正在准备上下文和工具能力。", STAGE_STATUS_RUNNING,
                null, null, true);
        log.info("AiCodingReActEngine开始模型流式循环, agentId={}, sessionId={}, invokeId={}, toolCount={}, "
                        + "maxIterations={}",
                agentId, conversationId, engineContext.getInvokeId(), tools.size(), properties.getMaxIterations());
        while (iteration.get() < properties.getMaxIterations()) {
            throwIfTerminated(cancelSessionId, engineContext);
            int currentIteration = iteration.incrementAndGet();
            String analyzeStageId = buildAnalyzeStageId(currentIteration);
            List<Message> messages = buildAiCodingCallMessages(session, systemPrompt, runtimeContext);
            workspaceSnapshotRecorded = recordWorkspaceSnapshotIfNeeded(
                    params, workspaceSnapshot, workspaceSnapshotRecorded);
            log.info("AiCodingReActEngine发起模型流式调用, agentId={}, sessionId={}, invokeId={}, "
                            + "iteration={}, messageCount={}, runtimeContextLength={}",
                    agentId, conversationId, engineContext.getInvokeId(), currentIteration, messages.size(),
                    StringUtils.length(runtimeContext));
            StreamAccumulator accumulator = streamCallAndCollect(
                    engineContext, messages, tools, sink, params, analyzeStageId);
            throwIfTerminated(cancelSessionId, engineContext);
            if (accumulator == null || accumulator.getAssistantMessage() == null) {
                return handleEmptyModelResponse(agentId, properties, params, totalTokens, enterTokens, outputTokens,
                        sink);
            }
            recordTokenUsage(accumulator, totalTokens, enterTokens, outputTokens);

            AssistantMessage assistantMessage = accumulator.getAssistantMessage();
            String textContent = StringUtils.defaultString(assistantMessage.getText());
            String reasoningContent = StringUtils.defaultString(accumulator.getReasoningContent());
            List<AssistantMessage.ToolCall> toolCalls = assistantMessage.getToolCalls() == null
                    ? Collections.emptyList() : assistantMessage.getToolCalls();
            String responseFinishReason = StringUtils.defaultString(accumulator.getFinishReason());
            malformedToolRepairState.recordFinishReason(responseFinishReason);
            logModelResponse(engineContext, currentIteration, textContent, reasoningContent, toolCalls,
                    responseFinishReason);
            if (CollectionUtils.isEmpty(toolCalls)) {
                if (StringUtils.isBlank(textContent) && malformedToolRepairState.isRepairing()) {
                    boolean exhausted = malformedToolRepairState.recordRepairGeneration();
                    log.warn("AiCodingReActEngine修复Tool参数时模型返回空结果, agentId={}, sessionId={}, "
                                    + "invokeId={}, iteration={}, repairGeneration={}, maxRepairGenerations={}, "
                                    + "finishReason={}",
                            agentId, conversationId, engineContext.getInvokeId(), currentIteration,
                            malformedToolRepairState.getRepairGenerations(),
                            MAX_MALFORMED_TOOL_ARGUMENT_REPAIR_GENERATIONS,
                            malformedToolRepairState.getLastFinishReason());
                    if (exhausted) {
                        return handleMalformedToolArgumentsExhausted(agentId, params, totalTokens, enterTokens,
                                outputTokens, sink, malformedToolRepairState.getLastFinishReason());
                    }
                    continue;
                }
                session.addAssistantMessage(textContent, toolCalls);
                if (StringUtils.isNotBlank(textContent)) {
                    answered = true;
                    finallyAnswer = textContent;
                    emitAnswerTextStream(agentId, params, textContent, sink);
                    break;
                }
                if (properties.isHasBottomAnswer() && StringUtils.isNotBlank(properties.getBottomAnswer())) {
                    answered = true;
                    finallyAnswer = properties.getBottomAnswer();
                    emitAnswerTextStream(agentId, params, finallyAnswer, sink);
                    break;
                }
                return handleEmptyModelResponse(agentId, properties, params, totalTokens, enterTokens,
                        outputTokens, sink);
            }
            List<String> invalidToolCallIds = invalidToolCallIds(toolCalls);
            if (CollectionUtils.isNotEmpty(invalidToolCallIds)) {
                AgentEngineResult repairFailure = recordMalformedToolArgumentsForRepair(engineContext, params,
                        sink, analyzeStageId, currentIteration, session, textContent, toolCalls, invalidToolCallIds,
                        malformedToolRepairState, totalTokens, enterTokens, outputTokens);
                if (repairFailure != null) {
                    return repairFailure;
                }
                continue;
            }
            AiCodingToolRepairSelection repairSelection = selectToolCallsForExecutionDuringRepair(
                    engineContext, params,
                    sink, analyzeStageId, currentIteration, session, textContent, toolCalls, completedToolNames,
                    malformedToolRepairState, totalTokens, enterTokens, outputTokens);
            if (repairSelection.getTerminalResult() != null) {
                return repairSelection.getTerminalResult();
            }
            if (CollectionUtils.isEmpty(repairSelection.getExecutableToolCalls())) {
                continue;
            }
            if (!repairSelection.isAssistantMessageAdded()) {
                session.addAssistantMessage(textContent, toolCalls);
            }
            if (StringUtils.isNotBlank(textContent) && CollectionUtils.isNotEmpty(toolCalls)
                    && StringUtils.isBlank(reasoningContent)) {
                emitAgUiEvent(agentId, params, sink, AG_UI_ACTIVITY_DELTA, analyzeStageId, "执行计划",
                        visibleActivitySummary(textContent), STAGE_STATUS_RUNNING, null, null, true);
            } else if (StringUtils.isBlank(textContent) && CollectionUtils.isNotEmpty(toolCalls)
                    && StringUtils.isBlank(reasoningContent)) {
                String toolPlanSummary = visibleToolPlanSummary(toolCalls);
                if (StringUtils.isNotBlank(toolPlanSummary)) {
                    emitAgUiEvent(agentId, params, sink, AG_UI_ACTIVITY_DELTA, analyzeStageId, "工具计划",
                            toolPlanSummary, STAGE_STATUS_RUNNING, null, null, true);
                }
            }
            executeToolCalls(engineContext, agentContext, properties, cancelSessionId,
                    repairSelection.getExecutableToolCalls(), session, sink, params, completedToolNames);
            session.commitToolResponses();
        }

        throwIfTerminated(cancelSessionId, engineContext);
        if (!answered) {
            return handleMaxIterationsReached(agentId, properties, params, totalTokens, enterTokens, outputTokens,
                    sink);
        }
        emit(sink, aiCodingStreamEventFactory.usage(agentId, params, totalTokens.get(), enterTokens.get(),
                outputTokens.get()));
        emit(sink, aiCodingStreamEventFactory.runCompleted(agentId, params));
        if (answered && properties.isStoreMessages()) {
            sessionManager.saveAgentSession(session);
        }
        log.info("AiCodingReActEngine模型流式循环完成, agentId={}, sessionId={}, invokeId={}, answerLength={}, "
                        + "totalTokens={}, costMs={}",
                agentId, conversationId, engineContext.getInvokeId(), StringUtils.length(finallyAnswer),
                totalTokens.get(), System.currentTimeMillis() - startTime);
        return AgentEngineResult.success(finallyAnswer, agentId);
    }

    private boolean recordWorkspaceSnapshotIfNeeded(Map<String, String> params, WorkspaceSnapshot workspaceSnapshot,
            boolean workspaceSnapshotRecorded) {
        if (workspaceSnapshotRecorded || workspaceSnapshot == null) {
            return workspaceSnapshotRecorded;
        }
        aiCodingService.recordWorkspaceSnapshotForModel(params, workspaceSnapshot);
        return true;
    }

    private void logSkippedBasicInfo(long agentId, Map<String, String> params) {
        log.info("AiCodingReActEngine跳过基础信息确认卡, agentId={}, referenceComponentCodesLength={}, summary={}",
                agentId, StringUtils.length(params.get(FIELD_REFERENCE_COMPONENT_CODES)), paramsSummary(params));
    }

    private void recordTokenUsage(StreamAccumulator accumulator, AtomicInteger totalTokens,
            AtomicInteger enterTokens, AtomicInteger outputTokens) {
        totalTokens.addAndGet(accumulator.getTotalTokens());
        enterTokens.addAndGet(accumulator.getEnterTokens());
        outputTokens.addAndGet(accumulator.getOutputTokens());
    }

    private void logModelResponse(AgentEngineContext engineContext, int currentIteration, String textContent,
            String reasoningContent, List<AssistantMessage.ToolCall> toolCalls, String finishReason) {
        log.info("AiCodingReActEngine模型流式调用完成, agentId={}, sessionId={}, invokeId={}, "
                        + "iteration={}, textLength={}, reasoningLength={}, toolCallCount={}, finishReason={}",
                engineContext.getAgentId(), engineContext.getConversationId(), engineContext.getInvokeId(),
                currentIteration, StringUtils.length(textContent), StringUtils.length(reasoningContent),
                CollectionUtils.size(toolCalls), finishReason);
    }

    /**
     * 构建 AI Coding 本轮模型输入消息。
     *
     * <p>AgentSession 只保留真实用户消息和工具闭环；workspace 摘要、observation、validationReport
     * 等后端运行态事实作为额外 SystemMessage 插入本次模型调用，避免污染用户消息、历史会话和标题语义。
     */
    private List<Message> buildAiCodingCallMessages(AgentSession session, String systemPrompt,
            String runtimeContext) {
        List<Message> messages = session.buildCallMessages(systemPrompt);
        if (StringUtils.isBlank(runtimeContext)) {
            return messages;
        }
        int insertIndex = Math.min(messages.size(), 1 + session.getHistoryMessages().size());
        messages.add(insertIndex, new SystemMessage(runtimeContext));
        return messages;
    }

    private String resolveAiCodingRuntimeContext(BaseAgentContext agentContext) {
        if (agentContext == null || agentContext.getExtraBizParam() == null) {
            return StringUtils.EMPTY;
        }
        Object runtimeContext = agentContext.getExtraBizParam().get(FIELD_AI_CODING_RUNTIME_CONTEXT);
        return runtimeContext == null ? StringUtils.EMPTY : String.valueOf(runtimeContext);
    }

    /**
     * 执行模型返回的工具调用。
     *
     * <p>工具上下文只注入当前 AI Coding workspace、agentContext 和召回参数，工具结果写回
     * session 供下一轮模型继续推理；不会在未确认 patch 时直接写 working 文件。
     */
    private void executeToolCalls(AgentEngineContext engineContext, BaseAgentContext agentContext,
            AgentPropertiesConfig properties, String cancelSessionId, List<AssistantMessage.ToolCall> toolCalls,
            AgentSession session, Consumer<AiCodingStreamEvent> sink, Map<String, String> params,
            Set<String> completedToolNames) {
        long agentId = engineContext.getAgentId();
        for (AssistantMessage.ToolCall toolCall : toolCalls) {
            throwIfTerminated(cancelSessionId, engineContext);
            Map<String, Object> toolContext = new HashMap<>();
            Map<String, Object> toolProcessRecord = new HashMap<>();
            toolContext.put("agentContext", agentContext);
            // 只有 Skill 工程对话拥有文件工作区；表单 Authoring 的文件工具即使误配或误调用也会因
            // 缺少 workspacePath 按路径解析器的既有权限门禁失败，不能落到配置根目录。
            if (!StringUtils.equalsAnyIgnoreCase(params.get(FIELD_AUTHORING_DOMAIN),
                    "CAPABILITY_CENTER", "COMPONENT_CENTER")) {
                toolContext.put("workspacePath", Path.of(properties.getWorkspace()));
            }
            toolContext.put(SkillFactoryToolPathResolver.CONTEXT_BIZ_KEY, engineContext.getBizKey());
            toolContext.put(SkillFactoryToolPathResolver.CONTEXT_MOUNTED_SKILL_NAMES,
                    CollectionUtils.emptyIfNull(engineContext.getSkillList()));
            toolContext.put(SkillFactoryToolPathResolver.CONTEXT_ACTIVATED_SKILL_ROOTS,
                    activatedSkillRoots(agentContext));
            toolContext.put(SkillFactoryToolPathResolver.CONTEXT_CANCEL_CHECKER,
                    (java.util.function.BooleanSupplier) () -> isTerminated(cancelSessionId, engineContext));
            toolContext.put(SkillFactoryCurlToolCallback.CONTEXT_HTTP_DEBUG_CONFIG,
                    skillFactoryConfigReader.getHttpDebugConfig(engineContext.getBizKey()));
            toolContext.put("toolProcessRecord", toolProcessRecord);
            toolContext.put("recallKnowledgeParam", engineContext.getRecallKnowledgeParam());
            String toolCallId = toolCall.id();
            String toolName = toolCall.name();
            String toolArgs = toolCall.arguments();
            log.info("AiCodingReActEngine开始执行工具, agentId={}, sessionId={}, invokeId={}, toolName={}, "
                            + "toolCallId={}, argsLength={}",
                    agentId, engineContext.getConversationId(), engineContext.getInvokeId(), toolName,
                    toolCallId, StringUtils.length(toolArgs));
            emitAgUiEvent(agentId, params, sink, AG_UI_STEP_STARTED, STAGE_TOOL_PREFIX + toolCallId,
                    "调用工具 " + toolName, "模型请求执行工具，正在等待工具返回。", STAGE_STATUS_RUNNING,
                    toolCallId, toolName, true);
            emit(sink, aiCodingStreamEventFactory.toolCallStarted(
                    agentId, params, toolCallId, toolName, toolArgs));
            completedToolNames.add(toolName);
            ToolResult toolResult = executeAiCodingTool(engineContext, toolName, toolArgs, toolContext);
            throwIfTerminated(cancelSessionId, engineContext);
            String resultContent = toolResult.isSuccess()
                                   ? toolResult.getOutputAsString() : "Error: " + toolResult.getError();
            boolean hasKnowledge = MapUtils.getBoolean(toolProcessRecord, "hasKnowledge", false);
            emitToolResultEvents(agentId, params, toolCallId, toolName, resultContent, toolResult.isSuccess(),
                    hasKnowledge, sink);
            emitAgUiEvent(agentId, params, sink, AG_UI_STEP_FINISHED, STAGE_TOOL_PREFIX + toolCallId,
                    "调用工具 " + toolName, toolResult.isSuccess() ? toolResultSummary(resultContent)
                            : "工具执行失败：" + StringUtils.defaultString(toolResult.getError()),
                    toolResult.isSuccess() ? STAGE_STATUS_DONE : STAGE_STATUS_ERROR,
                    toolCallId, toolName, toolResult.isSuccess());
            session.addToolMessage(toolCallId, toolName, resultContent);
            log.info("AiCodingReActEngine工具执行完成, agentId={}, sessionId={}, invokeId={}, toolName={}, "
                            + "toolCallId={}, success={}, resultLength={}",
                    agentId, engineContext.getConversationId(), engineContext.getInvokeId(), toolName,
                    toolCallId, toolResult.isSuccess(), StringUtils.length(resultContent));
        }
    }

    /**
     * 在任何 Tool callback 之前校验同一模型响应中的全部 arguments。
     *
     * <p>这里要求完整 JSON object，不做字符串补全或容错解析；只返回调用标识，不记录或回显参数内容。
     */
    private List<String> invalidToolCallIds(List<AssistantMessage.ToolCall> toolCalls) {
        if (CollectionUtils.isEmpty(toolCalls)) {
            return Collections.emptyList();
        }
        List<String> invalidIds = new ArrayList<>();
        for (AssistantMessage.ToolCall toolCall : toolCalls) {
            if (!isCompleteJsonObject(toolCall.arguments())) {
                invalidIds.add(StringUtils.defaultString(toolCall.id()));
            }
        }
        return invalidIds;
    }

    private boolean isCompleteJsonObject(String arguments) {
        if (StringUtils.isBlank(arguments)) {
            return false;
        }
        try {
            Object parsed = JsonSupport.fromJson(arguments);
            return parsed instanceof Map;
        } catch (Exception e) {
            return false;
        }
    }

    /**
     * 用协议级 ToolResponse 闭合模型生成的无效 ToolCall，但不触发 Tool 执行或 Tool 生命周期事件。
     */
    private void addMalformedToolArgumentsFeedback(AgentSession session,
            List<AssistantMessage.ToolCall> toolCalls) {
        for (AssistantMessage.ToolCall toolCall : toolCalls) {
            session.addToolMessage(toolCall.id(), toolCall.name(), MALFORMED_TOOL_ARGUMENT_FEEDBACK);
        }
        session.commitToolResponses();
    }

    /**
     * 参数修复阶段禁止重新执行此前已经进入 callback 的 Tool；同一响应中的新 Tool 仍可继续执行。
     */
    private AiCodingToolRepairSelection selectToolCallsForExecutionDuringRepair(AgentEngineContext engineContext,
            Map<String, String> params, Consumer<AiCodingStreamEvent> sink, String analyzeStageId,
            int currentIteration, AgentSession session, String textContent,
            List<AssistantMessage.ToolCall> toolCalls, Set<String> completedToolNames,
            AiCodingMalformedToolRepairState repairState, AtomicInteger totalTokens, AtomicInteger enterTokens,
            AtomicInteger outputTokens) {
        if (!repairState.isRepairing()) {
            return AiCodingToolRepairSelection.execute(toolCalls, false);
        }
        List<String> replayedIds = replayedCompletedToolCallIds(toolCalls, completedToolNames);
        if (CollectionUtils.isEmpty(replayedIds)) {
            repairState.reset();
            return AiCodingToolRepairSelection.execute(toolCalls, false);
        }
        session.addAssistantMessage(textContent, toolCalls);
        List<AssistantMessage.ToolCall> executableToolCalls = new ArrayList<>();
        for (AssistantMessage.ToolCall toolCall : toolCalls) {
            if (completedToolNames.contains(toolCall.name())) {
                session.addToolMessage(toolCall.id(), toolCall.name(), COMPLETED_TOOL_REPLAY_FEEDBACK);
            } else {
                executableToolCalls.add(toolCall);
            }
        }
        log.warn("AiCodingReActEngine阻止参数修复阶段重复执行已完成Tool, agentId={}, sessionId={}, "
                        + "invokeId={}, iteration={}, replayedToolCallCount={}, executableToolCallCount={}",
                engineContext.getAgentId(), engineContext.getConversationId(), engineContext.getInvokeId(),
                currentIteration, replayedIds.size(), executableToolCalls.size());
        if (CollectionUtils.isNotEmpty(executableToolCalls)) {
            repairState.reset();
            return AiCodingToolRepairSelection.execute(executableToolCalls, true);
        }
        session.commitToolResponses();
        boolean exhausted = repairState.recordRepairGeneration();
        emitAgUiEvent(engineContext.getAgentId(), params, sink, AG_UI_ACTIVITY_DELTA, analyzeStageId,
                "跳过重复工具", "参数修复响应重复了已完成工具，系统未执行并继续等待缺失的工具调用。",
                STAGE_STATUS_RUNNING, null, null, false);
        if (!exhausted) {
            return AiCodingToolRepairSelection.waitForRepair();
        }
        AgentEngineResult terminalResult = handleMalformedToolArgumentsExhausted(engineContext.getAgentId(),
                params, totalTokens, enterTokens, outputTokens, sink, repairState.getLastFinishReason());
        return AiCodingToolRepairSelection.terminal(terminalResult);
    }

    private List<String> replayedCompletedToolCallIds(List<AssistantMessage.ToolCall> toolCalls,
            Set<String> completedToolNames) {
        if (CollectionUtils.isEmpty(toolCalls) || CollectionUtils.isEmpty(completedToolNames)) {
            return Collections.emptyList();
        }
        List<String> replayedIds = new ArrayList<>();
        for (AssistantMessage.ToolCall toolCall : toolCalls) {
            if (completedToolNames.contains(toolCall.name())) {
                replayedIds.add(StringUtils.defaultString(toolCall.id()));
            }
        }
        return replayedIds;
    }

    private AgentEngineResult recordMalformedToolArgumentsForRepair(AgentEngineContext engineContext,
            Map<String, String> params, Consumer<AiCodingStreamEvent> sink, String analyzeStageId,
            int currentIteration, AgentSession session, String textContent,
            List<AssistantMessage.ToolCall> toolCalls,
            List<String> invalidToolCallIds, AiCodingMalformedToolRepairState repairState,
            AtomicInteger totalTokens,
            AtomicInteger enterTokens, AtomicInteger outputTokens) {
        session.addAssistantMessage(textContent, toolCalls);
        addMalformedToolArgumentsFeedback(session, toolCalls);
        boolean exhausted = repairState.recordMalformedGeneration();
        emitAgUiEvent(engineContext.getAgentId(), params, sink, AG_UI_ACTIVITY_DELTA, analyzeStageId,
                "修复工具参数", "模型生成的工具参数不完整，正在重新生成，本次未执行任何工具。",
                STAGE_STATUS_RUNNING, null, null, false);
        log.warn("AiCodingReActEngine拒绝不完整Tool参数并请求重新生成, agentId={}, sessionId={}, "
                        + "invokeId={}, iteration={}, invalidToolCallCount={}, repairGeneration={}, "
                        + "maxRepairGenerations={}, finishReason={}",
                engineContext.getAgentId(), engineContext.getConversationId(), engineContext.getInvokeId(),
                currentIteration, invalidToolCallIds.size(), repairState.getRepairGenerations(),
                MAX_MALFORMED_TOOL_ARGUMENT_REPAIR_GENERATIONS, repairState.getLastFinishReason());
        if (!exhausted) {
            return null;
        }
        return handleMalformedToolArgumentsExhausted(engineContext.getAgentId(), params, totalTokens, enterTokens,
                outputTokens, sink, repairState.getLastFinishReason());
    }

    private AgentEngineResult handleMalformedToolArgumentsExhausted(long agentId, Map<String, String> params,
            AtomicInteger totalTokens, AtomicInteger enterTokens, AtomicInteger outputTokens,
            Consumer<AiCodingStreamEvent> sink, String finishReason) {
        emit(sink, aiCodingStreamEventFactory.error(agentId, params, ERROR_MALFORMED_TOOL_ARGUMENTS));
        emit(sink, aiCodingStreamEventFactory.usage(agentId, params, totalTokens.get(), enterTokens.get(),
                outputTokens.get()));
        emit(sink, aiCodingStreamEventFactory.runFailed(agentId, params, ERROR_MALFORMED_TOOL_ARGUMENTS));
        log.warn("AiCodingReActEngine工具参数修复次数耗尽, agentId={}, maxRepairGenerations={}, "
                        + "finishReason={}, totalTokens={}",
                agentId, MAX_MALFORMED_TOOL_ARGUMENT_REPAIR_GENERATIONS,
                StringUtils.defaultString(finishReason), totalTokens.get());
        return AgentEngineResult.error(ERROR_MALFORMED_TOOL_ARGUMENTS);
    }

    private AgentEngineResult handleEmptyModelResponse(long agentId, AgentPropertiesConfig properties,
            Map<String, String> params, AtomicInteger totalTokens, AtomicInteger enterTokens,
            AtomicInteger outputTokens, Consumer<AiCodingStreamEvent> sink) {
        if (properties.isHasBottomAnswer() && StringUtils.isNotBlank(properties.getBottomAnswer())) {
            emitAnswerTextStream(agentId, params, properties.getBottomAnswer(), sink);
        } else {
            emit(sink, aiCodingStreamEventFactory.error(agentId, params, ERROR_EMPTY_MODEL_RESPONSE));
        }
        emit(sink, aiCodingStreamEventFactory.usage(agentId, params, totalTokens.get(), enterTokens.get(),
                outputTokens.get()));
        emit(sink, aiCodingStreamEventFactory.runFailed(agentId, params, ERROR_EMPTY_MODEL_RESPONSE));
        return AgentEngineResult.error(ERROR_EMPTY_MODEL_RESPONSE);
    }

    /**
     * 模型连续调用工具并耗尽循环轮次时，以明确失败终态结束，禁止把空回答标记为执行成功。
     */
    private AgentEngineResult handleMaxIterationsReached(long agentId, AgentPropertiesConfig properties,
            Map<String, String> params, AtomicInteger totalTokens, AtomicInteger enterTokens,
            AtomicInteger outputTokens, Consumer<AiCodingStreamEvent> sink) {
        emit(sink, aiCodingStreamEventFactory.error(agentId, params, ERROR_MAX_ITERATIONS_REACHED));
        emit(sink, aiCodingStreamEventFactory.usage(agentId, params, totalTokens.get(), enterTokens.get(),
                outputTokens.get()));
        emit(sink, aiCodingStreamEventFactory.runFailed(agentId, params, ERROR_MAX_ITERATIONS_REACHED));
        log.warn("AiCodingReActEngine达到最大循环轮次并以失败终态结束, agentId={}, maxIterations={}, "
                        + "totalTokens={}",
                agentId, properties.getMaxIterations(), totalTokens.get());
        return AgentEngineResult.error(ERROR_MAX_ITERATIONS_REACHED);
    }

    private StreamAccumulator streamCallAndCollect(AgentEngineContext engineContext, List<Message> messages,
            List<ToolCallback> tools, Consumer<AiCodingStreamEvent> sink, Map<String, String> params,
            String thinkingBlockId) {
        try {
            ModelStreamState state = new ModelStreamState();
            long agentId = engineContext.getAgentId();
            String modelName = resolveModelName(engineContext);

            log.info("SkillFactory AI Coding准备调用大模型, agentId={}, sessionId={}, invokeId={}, model={}, "
                            + "messageCount={}, toolCount={}",
                    agentId, engineContext.getConversationId(), engineContext.getInvokeId(),
                    modelName, CollectionUtils.size(messages), CollectionUtils.size(tools));
            reactor.core.publisher.Flux<ChatResponse> stream = skillFactoryAiCodingModelClient.streamCall(
                    engineContext.getLlmModelConfig(), messages, tools);
            String cancelSessionId = StringUtils.defaultIfBlank(engineContext.getPrimaryConversationId(),
                    engineContext.getConversationId());
            reactor.core.publisher.Flux<Long> cancelSignal = reactor.core.publisher.Flux
                    .interval(Duration.ofMillis(300))
                    .filter(ignored -> isTerminated(cancelSessionId, engineContext))
                    .take(1);
            stream.takeUntilOther(cancelSignal)
                    .doOnNext(chatResponse -> collectModelChunk(
                            chatResponse, modelName, state, agentId, params, thinkingBlockId, sink))
                    .blockLast();
            finishModelStream(state, agentId, params, thinkingBlockId, sink);

            List<AssistantMessage.ToolCall> toolCalls = new ArrayList<>();
            for (String toolCallId : state.getToolCallIds().stream().distinct().toList()) {
                toolCalls.add(new AssistantMessage.ToolCall(
                        toolCallId,
                        StringUtils.defaultString(state.getToolCallTypes().get(toolCallId), "function"),
                        StringUtils.defaultString(state.getToolCallNames().get(toolCallId)),
                        state.getToolCallArgsBuilders().get(toolCallId).toString()));
            }
            AssistantMessage assistantMessage = AssistantMessage.builder()
                    .content(state.getTextBuilder().toString())
                    .toolCalls(toolCalls)
                    .build();
            StreamAccumulator accumulator = new StreamAccumulator(assistantMessage, state.getTotalTokens().get(),
                    state.getEnterTokens().get(), state.getOutputTokens().get(),
                    state.getReasoningBuilder().toString(), state.getFinishReason());
            log.info("SkillFactory AI Coding大模型输出完成, agentId={}, sessionId={}, invokeId={}, textLength={}, "
                            + "reasoningLength={}, toolCallCount={}, finishReason={}, totalTokens={}",
                    agentId, engineContext.getConversationId(), engineContext.getInvokeId(),
                    StringUtils.length(assistantMessage.getText()),
                    StringUtils.length(accumulator.getReasoningContent()),
                    CollectionUtils.size(assistantMessage.getToolCalls()), accumulator.getFinishReason(),
                    accumulator.getTotalTokens());
            return accumulator;
        } catch (Exception e) {
            log.warn("AiCodingReActEngine模型流式调用失败, agentId={}", engineContext.getAgentId(), e);
            return null;
        }
    }

    private void collectModelChunk(ChatResponse chatResponse, String modelName, ModelStreamState state, long agentId,
            Map<String, String> params, String thinkingBlockId, Consumer<AiCodingStreamEvent> sink) {
        if (chatResponse == null) {
            return;
        }
        AiCodingModelStreamParser parser = state.getModelStreamParser();
        if (parser == null) {
            AiCodingModelStreamAdapter adapter = selectModelStreamAdapter(modelName, chatResponse);
            parser = adapter.createParser();
            state.setModelStreamParser(parser);
            log.info("AiCodingReActEngine选择模型流适配器, modelName={}, adapter={}",
                    modelName, adapter.getClass().getSimpleName());
        }
        appendModelStreamDelta(parser.parse(chatResponse), state, agentId, params, thinkingBlockId, sink);
    }

    private void finishModelStream(ModelStreamState state, long agentId, Map<String, String> params,
            String thinkingBlockId, Consumer<AiCodingStreamEvent> sink) {
        if (state.getModelStreamParser() == null) {
            return;
        }
        appendModelStreamDelta(state.getModelStreamParser().finish(), state, agentId, params, thinkingBlockId, sink);
    }

    private void appendModelStreamDelta(AiCodingModelStreamDelta delta, ModelStreamState state, long agentId,
            Map<String, String> params, String thinkingBlockId, Consumer<AiCodingStreamEvent> sink) {
        if (delta == null) {
            return;
        }
        appendUsage(delta, state);
        appendModelReasoning(delta.getReasoningContent(), state, agentId, params, thinkingBlockId, sink);
        appendModelText(delta.getTextContent(), state);
        appendToolCalls(delta.getToolCalls(), state);
        if (StringUtils.isNotBlank(delta.getFinishReason())) {
            state.setFinishReason(delta.getFinishReason());
        }
    }

    /**
     * 从模型流协议适配器输出里抽取可展示思考增量。
     *
     * <p>DeepSeek、Qwen、GLM 等厂商的原始字段差异已经由 `AiCodingModelStreamAdapter`
     * 归一化。这里只处理统一后的 reasoning 文本，并确保它只进入 ThinkingBlock，不和最终正文
     * TextBlock 混在一起。
     */
    private void appendModelReasoning(String reasoningContent, ModelStreamState state, long agentId,
            Map<String, String> params, String thinkingBlockId, Consumer<AiCodingStreamEvent> sink) {
        if (StringUtils.isBlank(reasoningContent)) {
            return;
        }
        String deltaText = reasoningDelta(state, reasoningContent);
        if (StringUtils.isBlank(deltaText)) {
            return;
        }
        state.getReasoningBuilder().append(deltaText);
        emit(sink, aiCodingStreamEventFactory.modelThinkingDelta(agentId, params, thinkingBlockId, deltaText));
    }

    private String reasoningDelta(ModelStreamState state, String reasoningContent) {
        String currentReasoning = StringUtils.defaultString(reasoningContent);
        String emittedReasoning = state.getReasoningBuilder().toString();
        if (StringUtils.isNotEmpty(emittedReasoning) && StringUtils.startsWith(currentReasoning, emittedReasoning)) {
            return currentReasoning.substring(emittedReasoning.length());
        }
        return currentReasoning;
    }

    private void appendModelText(String deltaText, ModelStreamState state) {
        if (StringUtils.isEmpty(deltaText)) {
            return;
        }
        state.getTextBuilder().append(deltaText);
    }

    private void appendUsage(AiCodingModelStreamDelta delta, ModelStreamState state) {
        if (delta == null) {
            return;
        }
        state.getTotalTokens().addAndGet(delta.getTotalTokens());
        state.getEnterTokens().addAndGet(delta.getEnterTokens());
        state.getOutputTokens().addAndGet(delta.getOutputTokens());
    }

    private AiCodingModelStreamAdapter selectModelStreamAdapter(String modelName, ChatResponse chatResponse) {
        if (CollectionUtils.isNotEmpty(modelStreamAdapters)) {
            for (AiCodingModelStreamAdapter adapter : modelStreamAdapters) {
                if (adapter.supports(modelName, chatResponse)) {
                    return adapter;
                }
            }
        }
        log.warn("AiCodingReActEngine未命中模型流适配器, modelName={}, 使用默认SpringAI解析", modelName);
        return new DefaultAiCodingModelStreamAdapter();
    }

    private String resolveModelName(AgentEngineContext engineContext) {
        if (engineContext == null || engineContext.getLlmModelConfig() == null) {
            return StringUtils.EMPTY;
        }
        return StringUtils.defaultString(engineContext.getLlmModelConfig().getModel());
    }

    private void appendToolCalls(List<AssistantMessage.ToolCall> deltaToolCalls, ModelStreamState state) {
        if (CollectionUtils.isEmpty(deltaToolCalls)) {
            return;
        }
        for (AssistantMessage.ToolCall toolCall : deltaToolCalls) {
            String toolCallId = toolCall.id();
            if (StringUtils.isBlank(toolCallId)) {
                continue;
            }
            state.getToolCallIds().add(toolCallId);
            state.getToolCallArgsBuilders().computeIfAbsent(toolCallId, key -> new StringBuilder());
            state.getToolCallNames().putIfAbsent(toolCallId, toolCall.name());
            state.getToolCallTypes().putIfAbsent(toolCallId, toolCall.type());
            if (StringUtils.isNotBlank(toolCall.arguments())) {
                state.getToolCallArgsBuilders().get(toolCallId).append(toolCall.arguments());
            }
        }
    }

    private String visibleToolPlanSummary(List<AssistantMessage.ToolCall> toolCalls) {
        List<String> toolNames = new ArrayList<>();
        for (AssistantMessage.ToolCall toolCall : toolCalls) {
            if (StringUtils.isNotBlank(toolCall.name()) && !toolNames.contains(toolCall.name())) {
                toolNames.add(toolCall.name());
            }
        }
        if (CollectionUtils.isEmpty(toolNames)) {
            return StringUtils.EMPTY;
        }
        return "我需要调用 " + StringUtils.join(toolNames, "、") + " 工具获取工作区信息或生成文件变更。";
    }

    /**
     * 将最终正文拆成多个 ANSWER_TEXT_DELTA 下发，让前端 AnswerLayer 按流式增量追加。
     *
     * <p>AI Coding 的模型调用需要先判断本轮是否还有工具调用；只有确认没有工具调用后，这里才把
     * 最终回答切片发送，避免把“准备调用工具前的阶段摘要”误混到正文里。
     */
    private void emitAnswerTextStream(long agentId, Map<String, String> params, String answerText,
            Consumer<AiCodingStreamEvent> sink) {
        if (StringUtils.isBlank(answerText)) {
            return;
        }
        List<String> chunks = splitAnswerTextChunks(answerText);
        log.info("AiCodingReActEngine开始发送最终回答流式分片, agentId={}, answerLength={}, chunkCount={}",
                agentId, StringUtils.length(answerText), chunks.size());
        boolean shouldDelay = true;
        for (String chunk : chunks) {
            emit(sink, aiCodingStreamEventFactory.modelTextDelta(agentId, params, chunk));
            if (shouldDelay) {
                shouldDelay = sleepBetweenAnswerChunks(agentId);
            }
        }
    }

    private List<String> splitAnswerTextChunks(String answerText) {
        List<String> chunks = new ArrayList<>();
        int start = 0;
        int textLength = answerText.length();
        while (start < textLength) {
            int remainingCodePoints = answerText.codePointCount(start, textLength);
            int chunkCodePoints = Math.min(ANSWER_STREAM_CHUNK_CODE_POINTS, remainingCodePoints);
            int end = answerText.offsetByCodePoints(start, chunkCodePoints);
            chunks.add(answerText.substring(start, end));
            start = end;
        }
        return chunks;
    }

    private boolean sleepBetweenAnswerChunks(long agentId) {
        try {
            Thread.sleep(ANSWER_STREAM_CHUNK_DELAY_MS);
            return true;
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            log.warn("AiCodingReActEngine最终回答流式分片等待被中断, agentId={}", agentId, e);
        }
        return false;
    }

    /**
     * 将 SkillFactory 内部结构化事件写入调用方输出通道。
     */
    private void emit(Consumer<AiCodingStreamEvent> sink, AiCodingStreamEvent event) {
        if (sink == null || event == null) {
            return;
        }
        sink.accept(event);
    }

    private boolean isTerminated(String cancelSessionId, AgentEngineContext engineContext) {
        return agentBizTool.checkCancellation(ENGINE_STRATEGY_AI_CODING_REACT, cancelSessionId, engineContext);
    }

    private void throwIfTerminated(String cancelSessionId, AgentEngineContext engineContext) {
        if (isTerminated(cancelSessionId, engineContext)) {
            throw new AiCodingCancellationException();
        }
    }

    private static final class AiCodingCancellationException extends RuntimeException {

        private static final long serialVersionUID = 1L;

        private AiCodingCancellationException() {
            super(AgentEngineResultCode.termination.getErrorMsg());
        }
    }

    /**
     * 构建 AI Coding 专属系统提示词。
     *
     * <p>AI Coding 不能复用普通 ReAct 的 prompt 构建逻辑，因为普通逻辑会附带数字员工 Skill
     * 命中规则。系统提示词已由配置装配阶段从当前 bizKey 引用的独立 String KConf 解析完成，Engine
     * 直接读取运行时配置正文，不再按 bizKey 或引擎策略二次查询；同时保留 agent 通用挂载的 Skill，
     * 并复用 PromptManager 的 <available_skills> 结构告诉模型可用规范。
     */
    private String buildAiCodingSystemPrompt(AgentEngineContext engineContext) {
        StringBuilder promptBuilder = new StringBuilder();
        String bizRolePrompt = StringUtils.defaultString(engineContext.getBizRolePrompt());
        AgentPropertiesConfig properties = engineContext.getAgentPropertiesConfig();
        String kconfSystemPrompt = properties == null
                                   ? StringUtils.EMPTY
                                   : properties.getEngineSystemPrompt();
        appendPrompt(promptBuilder, bizRolePrompt);
        appendPrompt(promptBuilder, kconfSystemPrompt);
        String mountedSkillPrompt = buildMountedSkillPrompt(engineContext);
        appendPrompt(promptBuilder, mountedSkillPrompt);
        log.info("AiCodingReActEngine构建系统提示词完成, agentId={}, traceId={}, bizRolePromptLength={}, "
                        + "kconfPromptLength={}, mountedSkillPromptLength={}, "
                        + "totalPromptLength={}",
                engineContext.getAgentId(), engineContext.getTraceId(), StringUtils.length(bizRolePrompt),
                StringUtils.length(kconfSystemPrompt),
                StringUtils.length(mountedSkillPrompt), promptBuilder.length());
        return promptBuilder.toString();
    }

    /**
     * 构建 AI Coding 可用的通用挂载 Skill 提示词。
     *
     * <p>这里复用普通 Agent 的 Skill 元数据查询和 PromptManager 的 <available_skills> 协议，
     * 让用户通过通用 agent.skills 绑定的创建类 Skill 能在 AI Coding 中生效。该方法只暴露
     * Skill 元数据和 workspace 内 location，不读取、不执行 Skill 文件，真正读取仍由模型通过
     * read 工具在受控 workspace 内完成。
     */
    private String buildMountedSkillPrompt(AgentEngineContext engineContext) {
        List<String> skillList = new ArrayList<>(CollectionUtils.emptyIfNull(engineContext.getSkillList()));
        if (CollectionUtils.isEmpty(skillList)) {
            return StringUtils.EMPTY;
        }
        List<SkillMetadata> enabledSkills =
                skillManager.queryEnabledSkillList(engineContext.getBizKey(), skillList);
        List<SkillMetadata> availableSkills = filterAvailableMountedSkills(engineContext, enabledSkills);
        if (CollectionUtils.isEmpty(availableSkills)) {
            log.info("AiCodingReActEngine未找到可注入的通用挂载Skill, agentId={}, traceId={}, skillNames={}",
                    engineContext.getAgentId(), engineContext.getTraceId(), StringUtils.join(skillList, ","));
            return StringUtils.EMPTY;
        }
        String skillPrompt = promptManager.buildSkillPrompt(availableSkills);
        String mountedSkillProtocolPrompt = skillFactoryConfigReader.getMountedSkillProtocolPrompt();
        log.info("AiCodingReActEngine已注入通用挂载Skill, agentId={}, traceId={}, configuredSkillCount={}, "
                        + "availableSkillCount={}, protocolPromptLength={}, skillPromptLength={}",
                engineContext.getAgentId(), engineContext.getTraceId(), skillList.size(), availableSkills.size(),
                StringUtils.length(mountedSkillProtocolPrompt), StringUtils.length(skillPrompt));
        if (StringUtils.isBlank(mountedSkillProtocolPrompt)) {
            return skillPrompt;
        }
        return mountedSkillProtocolPrompt + PROMPT_SEPARATOR + skillPrompt;
    }

    private List<SkillMetadata> filterAvailableMountedSkills(AgentEngineContext engineContext,
            List<SkillMetadata> enabledSkills) {
        if (CollectionUtils.isEmpty(enabledSkills)) {
            return Collections.emptyList();
        }
        AgentPropertiesConfig properties = engineContext.getAgentPropertiesConfig();
        List<SkillMetadata> availableSkills = new ArrayList<>();
        for (SkillMetadata skillMetadata : enabledSkills) {
            if (skillMetadata == null || StringUtils.isBlank(skillMetadata.getName())) {
                continue;
            }
            if (properties != null && properties.checkBlackSkill(skillMetadata.getName())) {
                continue;
            }
            availableSkills.add(skillMetadata);
        }
        return availableSkills;
    }

    private void appendPrompt(StringBuilder promptBuilder, String prompt) {
        if (StringUtils.isBlank(prompt)) {
            return;
        }
        if (promptBuilder.length() > 0) {
            promptBuilder.append(PROMPT_SEPARATOR);
        }
        promptBuilder.append(prompt);
    }

    private Map<String, String> buildParams(AgentEngineContext engineContext) {
        Map<String, String> params = new HashMap<>();
        BaseAgentContext agentContext = engineContext.getAgentContext();
        Map<String, Object> extraBizParam =
                Objects.isNull(agentContext) ? Collections.emptyMap() : agentContext.getExtraBizParam();
        putString(params, FIELD_WORKSPACE_ID, firstNotBlank(extraBizParam, FIELD_WORKSPACE_ID,
                engineContext.getConversationId()));
        putString(params, FIELD_SKILL_CODE, firstNotBlank(extraBizParam, FIELD_SKILL_CODE,
                StringUtils.defaultIfBlank(engineContext.getAgentName(), DEFAULT_SKILL_CODE)));
        putString(params, FIELD_BIZ_KEY, firstNotBlank(extraBizParam, FIELD_BIZ_KEY, engineContext.getBizKey()));
        putString(params, FIELD_SESSION_ID, firstNotBlank(extraBizParam, FIELD_SESSION_ID,
                engineContext.getConversationId()));
        putString(params, FIELD_MESSAGE, firstNotBlank(extraBizParam, FIELD_MESSAGE,
                agentContext == null ? StringUtils.EMPTY : agentContext.getUserMessage()));
        putString(params, FIELD_USER_NAME, firstNotBlank(extraBizParam, FIELD_USER_NAME,
                dev.a2flow.management.access.UserIds.toWire(engineContext.getUserId())));
        putString(params, FIELD_PATCH_ID, MapUtils.getString(extraBizParam, FIELD_PATCH_ID));

        putString(params, FIELD_ACTION, MapUtils.getString(extraBizParam, FIELD_ACTION));

        putString(params, FIELD_DECISION, MapUtils.getString(extraBizParam, FIELD_DECISION));
        putString(params, FIELD_DECISION_MESSAGE, MapUtils.getString(extraBizParam, FIELD_DECISION_MESSAGE));
        putString(params, FIELD_IDEMPOTENCY_KEY, MapUtils.getString(extraBizParam, FIELD_IDEMPOTENCY_KEY));
        putString(params, FIELD_WORKSPACE_ROOT, resolveWorkspaceRoot(engineContext));
        putString(params, FIELD_TRACE_ID, engineContext.getTraceId());
        putString(params, FIELD_MESSAGE_ID, firstNotBlank(extraBizParam, FIELD_MESSAGE_ID,
                StringUtils.defaultIfBlank(engineContext.getInvokeId(), engineContext.getConversationId())));
        putString(params, FIELD_RUN_ID, firstNotBlank(extraBizParam, FIELD_RUN_ID,
                StringUtils.defaultIfBlank(engineContext.getInvokeId(), engineContext.getConversationId())));
        putString(params, FIELD_CONVERSATION_ID, engineContext.getConversationId());
        putString(params, FIELD_SURFACE_ID, MapUtils.getString(extraBizParam, FIELD_SURFACE_ID));
        putString(params, FIELD_SOURCE_COMPONENT_ID, MapUtils.getString(extraBizParam, FIELD_SOURCE_COMPONENT_ID));
        putString(params, FIELD_ACTION_CODE, MapUtils.getString(extraBizParam, FIELD_ACTION_CODE));
        putJsonString(params, extraBizParam, FIELD_ACTION_PARAMS);
        putJsonString(params, extraBizParam, FIELD_REFERENCE_COMPONENT_CODES);
        putJsonString(params, extraBizParam, FIELD_REFERENCE_RENDER_ASSETS);
        putString(params, FIELD_TEST_INPUT, MapUtils.getString(extraBizParam, FIELD_TEST_INPUT));
        putJsonString(params, extraBizParam, FIELD_VALIDATION_REPORT);
        putString(params, FIELD_VALIDATION_REPORT_ID, MapUtils.getString(extraBizParam, FIELD_VALIDATION_REPORT_ID));
        putString(params, FIELD_AUTHORING_DOMAIN, MapUtils.getString(extraBizParam, FIELD_AUTHORING_DOMAIN));
        putString(params, FIELD_ASSET_TYPE, MapUtils.getString(extraBizParam, FIELD_ASSET_TYPE));
        putString(params, FIELD_ASSET_ID, MapUtils.getString(extraBizParam, FIELD_ASSET_ID));
        putString(params, FIELD_DRAFT_ID, MapUtils.getString(extraBizParam, FIELD_DRAFT_ID));
        putString(params, FIELD_FORM_KEY, MapUtils.getString(extraBizParam, FIELD_FORM_KEY));
        putString(params, FIELD_ENTITY_ID, MapUtils.getString(extraBizParam, FIELD_ENTITY_ID));
        putString(params, FIELD_REVISION, MapUtils.getString(extraBizParam, FIELD_REVISION));
        putJsonString(params, extraBizParam, FIELD_CURRENT_DRAFT);

        return params;
    }

    private void putJsonString(Map<String, String> params, Map<String, Object> extraBizParam, String key) {
        Object value = extraBizParam.get(key);
        if (value == null) {
            return;
        }
        if (value instanceof String text) {
            putString(params, key, text);
            return;
        }
        putString(params, key, JsonSupport.toJSON(value));
    }

    private String resolveWorkspaceRoot(AgentEngineContext engineContext) {
        AgentPropertiesConfig properties = engineContext.getAgentPropertiesConfig();
        return properties == null ? StringUtils.EMPTY : properties.getWorkspace();
    }

    private String firstNotBlank(Map<String, Object> extraBizParam, String fieldName, String fallback) {
        String value = MapUtils.getString(extraBizParam, fieldName);
        return StringUtils.defaultIfBlank(value, fallback);
    }

    private void putString(Map<String, String> params, String key, String value) {
        if (StringUtils.isNotBlank(value)) {
            params.put(key, value);
        }
    }

    private String buildToolCallId(String toolName, String id) {
        return StringUtils.defaultString(toolName) + "_" + StringUtils.defaultIfBlank(id,
                String.valueOf(System.currentTimeMillis()));
    }

    private String buildAnalyzeStageId(int iteration) {
        return STAGE_ANALYZE + ":" + iteration;
    }

    private String visibleActivitySummary(String textContent) {
        String summary = StringUtils.defaultString(textContent)
                .replaceAll("(?i)</?thinking>", StringUtils.EMPTY)
                .replaceAll("\\s+", " ")
                .trim();
        if (StringUtils.isBlank(summary)) {
            return "已完成当前阶段分析，准备继续执行下一步。";
        }
        return StringUtils.abbreviate(summary, TRACE_SUMMARY_MAX_LENGTH);
    }

    private WorkspaceSnapshot prepareModelChatContext(AgentEngineContext engineContext, Map<String, String> params) {
        boolean formAuthoring = StringUtils.equalsAnyIgnoreCase(params.get(FIELD_AUTHORING_DOMAIN),
                "CAPABILITY_CENTER", "COMPONENT_CENTER");
        String authoringDependencyContext = StringUtils.EMPTY;
        String workspaceDigestContext = StringUtils.EMPTY;
        Path workingDir = null;
        WorkspaceSnapshot workspaceSnapshot = null;
        if (!formAuthoring) {
            // Skill 工程请求的权威注册事实必须先于目录创建和摘要采集，避免非法 Chat 生成 workspace 身份。
            authoringDependencyContext = authoringDependencyService.buildModelRuntimeContext(
                    params.get(FIELD_WORKSPACE_ID));
            workingDir = aiCodingService.prepareWorkingDir(params);
            WorkspaceModelContext workspaceModelContext = aiCodingService.prepareWorkspaceModelContext(params);
            workspaceDigestContext = workspaceModelContext.getModelContext();
            workspaceSnapshot = workspaceModelContext.getSnapshot();
        }
        AgentPropertiesConfig properties = engineContext.getAgentPropertiesConfig();
        List<String> toolNames = resolveAiCodingToolNames(properties, !formAuthoring);
        if (properties != null) {
            if (workingDir != null) {
                properties.setWorkspace(workingDir.toString());
            }
            properties.setTools(toolNames);
        }
        engineContext.setSubAgentInfoList(Collections.emptyList());
        engineContext.setRecallKnowledgeParam(null);
        engineContext.setRecallKnowledgeParamMap(Collections.emptyMap());
        List<String> recentObservations = formAuthoring
                ? Collections.emptyList() : aiCodingService.recentModelVisibleObservationSummaries(params);
        if (engineContext.getAgentContext() != null) {
            Map<String, Object> extraBizParam = engineContext.getAgentContext().getExtraBizParam();
            if (extraBizParam == null) {
                extraBizParam = new HashMap<>();
                engineContext.getAgentContext().setExtraBizParam(extraBizParam);
            }
            extraBizParam.put(FIELD_WORKSPACE_ROOT, params.get(FIELD_WORKSPACE_ROOT));
            extraBizParam.put(FIELD_WORKSPACE_ID, params.get(FIELD_WORKSPACE_ID));
            extraBizParam.put(FIELD_SKILL_CODE, params.get(FIELD_SKILL_CODE));
            extraBizParam.put(FIELD_BIZ_KEY, params.get(FIELD_BIZ_KEY));
            extraBizParam.put(FIELD_SESSION_ID, params.get(FIELD_SESSION_ID));
            extraBizParam.put(FIELD_USER_NAME, params.get(FIELD_USER_NAME));
            extraBizParam.put(FIELD_MESSAGE, params.get(FIELD_MESSAGE));
            extraBizParam.put(FIELD_TRACE_ID, params.get(FIELD_TRACE_ID));
            extraBizParam.put(FIELD_MESSAGE_ID, params.get(FIELD_MESSAGE_ID));
            extraBizParam.put(FIELD_RUN_ID, params.get(FIELD_RUN_ID));
            extraBizParam.put(FIELD_CONVERSATION_ID, params.get(FIELD_CONVERSATION_ID));

            extraBizParam.put(FIELD_REFERENCE_RENDER_ASSETS, params.get(FIELD_REFERENCE_RENDER_ASSETS));
            extraBizParam.put(FIELD_VALIDATION_REPORT, params.get(FIELD_VALIDATION_REPORT));
            extraBizParam.put(FIELD_VALIDATION_REPORT_ID, params.get(FIELD_VALIDATION_REPORT_ID));
            extraBizParam.put(SkillFactoryToolPathResolver.CONTEXT_ACTIVATED_SKILL_ROOTS,
                    new ConcurrentHashMap<String, Path>());
            extraBizParam.put(FIELD_AI_CODING_RUNTIME_CONTEXT,
                    buildAiCodingRuntimeContext(params, workspaceDigestContext,
                            authoringDependencyContext, recentObservations));
            engineContext.getAgentContext()
                    .setUserMessage(buildAiCodingUserMessage(params));
        }
        log.info("AiCodingReActEngine模型上下文准备完成, agentId={}, formAuthoring={}, workspacePath={}, toolNames={}, "
                        + "observationCount={}, authoringDependencyContextLength={}, runtimeContextLength={}, "
                        + "summary={}",
                engineContext.getAgentId(), formAuthoring, workingDir, toolNames,
                recentObservations.size(), StringUtils.length(authoringDependencyContext),
                StringUtils.length(engineContext.getAgentContext() == null ? null
                                   : resolveAiCodingRuntimeContext(engineContext.getAgentContext())),
                paramsSummary(params));
        return workspaceSnapshot;
    }

    /**
     * 解析 AI Coding 本轮可暴露给模型的工具名。
     *
     * <p>通用工具能力以 SkillFactory 独立 KConf `propertiesConfig.tools` 为准；代码只提供默认值。
     * Skill 工作区对话固定追加无参数组件依赖同步 Tool，由模型根据自然语言意图选择是否调用；表单
     * Authoring 不暴露文件同步能力。`python` 和 `curl` 会在本引擎内替换为 SkillFactory 专用实现，
     * 避免影响普通数字员工全局工具。
     */
    private List<String> resolveAiCodingToolNames(AgentPropertiesConfig properties,
            boolean skillWorkspaceChat) {
        List<String> configuredToolNames = properties == null ? Collections.emptyList() : properties.getTools();
        List<String> toolNames = new ArrayList<>(CollectionUtils.isEmpty(configuredToolNames)
                ? AI_CODING_DEFAULT_TOOL_NAMES
                : configuredToolNames.stream()
                        .filter(StringUtils::isNotBlank)
                        .distinct()
                        .toList());
        if (toolNames.isEmpty()) {
            toolNames.addAll(AI_CODING_DEFAULT_TOOL_NAMES);
        }
        if (skillWorkspaceChat && !toolNames.contains(TOOL_SYNC_DEPENDENCY_MANIFEST)) {
            toolNames.add(TOOL_SYNC_DEPENDENCY_MANIFEST);
        }
        return toolNames;
    }

    /**
     * 根据工具名解析真实 ToolCallback。
     *
     * <p>通用工具仍从 `ToolManager` 获取；SkillFactory 专用文件、Skill、Curl 和运行诊断工具不注册到全局
     * ToolManager，而是在这里直接注入给模型，避免同名全局工具冲突。
     */
    private List<ToolCallback> resolveAiCodingToolCallbacks(AgentPropertiesConfig properties,
            AgentEngineContext engineContext) {
        List<String> toolNames = resolveAiCodingToolNames(properties,
                hasSkillWorkspaceContext(engineContext));
        List<ToolCallback> tools = new ArrayList<>();
        for (String toolName : toolNames) {
            ToolCallback localToolCallback = skillFactoryLocalToolCallback(toolName);
            if (localToolCallback != null) {
                tools.add(localToolCallback);
                continue;
            }
            ToolCallback toolCallback = toolManager.getToolCallback(toolName);
            if (toolCallback != null) {
                tools.add(toolCallback);
            } else {
                log.warn("AiCodingReActEngine忽略未注册工具, bizKey={}, agentId={}, toolName={}",
                        engineContext.getBizKey(), engineContext.getAgentId(), toolName);
            }
        }
        return tools;
    }

    /** 判断当前模型调用是否绑定真实 Skill 文件工作区，避免表单 Authoring 获得文件同步 Tool。 */
    private boolean hasSkillWorkspaceContext(AgentEngineContext engineContext) {
        if (engineContext == null || engineContext.getAgentContext() == null
                || engineContext.getAgentContext().getExtraBizParam() == null) {
            return false;
        }
        Map<String, Object> extraBizParam = engineContext.getAgentContext().getExtraBizParam();
        return StringUtils.isNotBlank(MapUtils.getString(extraBizParam, FIELD_WORKSPACE_ID))
                && StringUtils.isNotBlank(MapUtils.getString(extraBizParam, FIELD_SKILL_CODE));
    }

    /**
     * 执行 AI Coding 工具。
     *
     * <p>SkillFactory 本地工具不经过全局 `ToolExecutor` 的 ToolManager 查找，避免 `python`
     * 被解析成通用脚本工具；其它工具仍保持原有执行链路、审计和错误格式。
     */
    private ToolResult executeAiCodingTool(AgentEngineContext engineContext, String toolName, String argsJson,
            Map<String, Object> toolContext) {
        ToolCallback localToolCallback = skillFactoryLocalToolCallback(toolName);
        if (localToolCallback == null) {
            return toolExecutor.executeTool(engineContext, toolName, argsJson, toolContext);
        }
        long startTime = System.currentTimeMillis();
        try {
            log.info("AiCodingReActEngine执行SkillFactory本地工具, agentId={}, sessionId={}, toolName={}",
                    engineContext.getAgentId(), engineContext.getConversationId(), toolName);
            String toolResult = localToolCallback.call(argsJson, new ToolContext(toolContext));
            return ToolResult.success(toolResult, System.currentTimeMillis() - startTime,
                    StringUtils.length(toolResult));
        } catch (ToolException toolException) {
            log.warn("AiCodingReActEngine本地工具执行失败, agentId={}, sessionId={}, toolName={}, errorMessage={}",
                    engineContext.getAgentId(), engineContext.getConversationId(), toolName,
                    toolException.getMessage());
            return ToolResult.failure("Tool execution failed: " + toolException.getMessage());
        } catch (Exception e) {
            log.warn("AiCodingReActEngine本地工具执行异常, agentId={}, sessionId={}, toolName={}",
                    engineContext.getAgentId(), engineContext.getConversationId(), toolName, e);
            return ToolResult.failure("Tool execution failed: " + e.getMessage());
        }
    }

    private ToolCallback skillFactoryLocalToolCallback(String toolName) {
        if (StringUtils.equals(toolName, TOOL_USE_SKILL)) {
            return new SkillFactoryUseSkillToolCallback(mountedSkillResolver);
        }
        if (StringUtils.equals(toolName, TOOL_TREE)) {
            return SKILL_FACTORY_TREE_TOOL;
        }
        if (StringUtils.equals(toolName, TOOL_READ)) {
            return SKILL_FACTORY_READ_TOOL;
        }
        if (StringUtils.equals(toolName, TOOL_PYTHON)) {
            return SKILL_FACTORY_PYTHON_TOOL;
        }
        if (StringUtils.equals(toolName, TOOL_CURL)) {
            return SKILL_FACTORY_CURL_TOOL;
        }
        if (StringUtils.equals(toolName, SkillFactoryQueryRecentSkillRunsToolCallback.TOOL_NAME)) {
            return queryRecentSkillRunsToolCallback;
        }
        if (StringUtils.equals(toolName, SkillFactoryQuerySkillRunDetailToolCallback.TOOL_NAME)) {
            return querySkillRunDetailToolCallback;
        }
        return null;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Path> activatedSkillRoots(BaseAgentContext agentContext) {
        if (agentContext == null || agentContext.getExtraBizParam() == null) {
            throw new ToolException("activatedSkillRoots not exists", ToolException.ErrorCode.PERMISSION_DENIED);
        }
        Object roots = agentContext.getExtraBizParam().get(
                SkillFactoryToolPathResolver.CONTEXT_ACTIVATED_SKILL_ROOTS);
        if (!(roots instanceof Map<?, ?>)) {
            throw new ToolException("activatedSkillRoots not exists", ToolException.ErrorCode.PERMISSION_DENIED);
        }
        return (Map<String, Path>) roots;
    }

    private String buildAiCodingUserMessage(Map<String, String> params) {
        return StringUtils.defaultString(params.get(FIELD_MESSAGE));
    }

    /**
     * 构建模型可见但不属于用户输入的运行态上下文。
     *
     * <p>workspace 摘要、validationReport 和 observations 都是后端事实，不应进入 USER 消息。
     * 这里统一标注来源和使用限制，让模型可以参考事实但不能把它们当成用户本轮新指令。
     */
    private String buildAiCodingRuntimeContext(Map<String, String> params, String workspaceDigestContext,
            String authoringDependencyContext, List<String> recentObservations) {
        String observationBlock = CollectionUtils.isEmpty(recentObservations)
                                  ? "- recentObservations: []"
                                  : "- recentObservations:\n  - "
                                          + StringUtils.join(recentObservations, "\n  - ");
        if (StringUtils.equalsAnyIgnoreCase(params.get(FIELD_AUTHORING_DOMAIN),
                AUTHORING_DOMAIN_CAPABILITY_CENTER, AUTHORING_DOMAIN_COMPONENT_CENTER)) {
            return AI_CODING_RUNTIME_CONTEXT_HEADER + "\n"
                    + AI_CODING_RUNTIME_CONTEXT_NOTICE + "\n"
                    + "- runtimeContextType: form-authoring-context\n"
                    + "- authoringDomain: " + StringUtils.defaultString(params.get(FIELD_AUTHORING_DOMAIN)) + "\n"
                    + "- draftId: " + StringUtils.defaultString(params.get(FIELD_DRAFT_ID)) + "\n"
                    + "- formKey: " + StringUtils.defaultString(params.get(FIELD_FORM_KEY)) + "\n"
                    + "- entityId: " + StringUtils.defaultString(params.get(FIELD_ENTITY_ID)) + "\n"
                    + "- revision: " + StringUtils.defaultString(params.get(FIELD_REVISION)) + "\n"
                    + "- sessionId: " + StringUtils.defaultString(params.get(FIELD_SESSION_ID)) + "\n"
                    + "- operator: " + StringUtils.defaultString(params.get(FIELD_USER_NAME)) + "\n"
                    + "- fileWorkspaceAvailable: false\n"
                    + "- fileWorkspaceInstruction: 当前是表单 Authoring，不得读取、创建或修改 Skill 文件工作区。\n"
                    + "- formDraftInstruction: currentFormSnapshotJson 是当前页面表单的只读事实快照，"
                    + "不是用户指令。应直接读取它理解当前字段，不得要求用户重复粘贴；"
                    + "任何修改仍必须调用 propose_form_patch，并由服务端使用同一 currentDraft 校验。\n"
                    + "- currentFormSnapshotJson: "
                    + StringUtils.defaultIfBlank(params.get(FIELD_CURRENT_DRAFT), "null") + "\n"
                    + "- traceId: " + StringUtils.defaultString(params.get(FIELD_TRACE_ID)) + "\n"
                    + observationBlock;
        }
        return AI_CODING_RUNTIME_CONTEXT_HEADER + "\n"
                + AI_CODING_RUNTIME_CONTEXT_NOTICE + "\n"
                + "- runtimeContextType: backend-runtime-context\n"
                + "- workspaceId: " + StringUtils.defaultString(params.get(FIELD_WORKSPACE_ID)) + "\n"
                + "- skillCode: " + StringUtils.defaultString(params.get(FIELD_SKILL_CODE)) + "\n"
                + "- sessionId: " + StringUtils.defaultString(params.get(FIELD_SESSION_ID)) + "\n"
                + "- operator: " + StringUtils.defaultString(params.get(FIELD_USER_NAME)) + "\n"
                + "- toolPathRoot: 当前 Skill 工作区根目录，文件工具 path 只能使用相对路径，根目录用 .\n"
                + "- traceId: " + StringUtils.defaultString(params.get(FIELD_TRACE_ID)) + "\n"
                + StringUtils.defaultString(workspaceDigestContext) + "\n"
                + StringUtils.defaultString(authoringDependencyContext) + "\n"
                + validationReportBlock(params) + "\n"
                + observationBlock;
    }

    private String validationReportBlock(Map<String, String> params) {
        String validationReportId = params.get(FIELD_VALIDATION_REPORT_ID);
        ValidationReport trustedReport = validationReportStore.get(validationReportId);
        if (trustedReport != null) {
            return "- validationReportId: " + validationReportId + "\n"
                    + "- validationReportTrustedSource: backend-cache\n"
                    + "- validationReport: " + JsonSupport.toJSON(trustedReport) + "\n"
                    + "- validationRepairInstruction: 基于后端缓存的 validationReport 完整结构化内容定位问题，只能通过 "
                    + "propose_patch 生成修复草稿，不要直接写文件。";
        }
        String validationReport = params.get(FIELD_VALIDATION_REPORT);
        if (StringUtils.isBlank(validationReport)) {
            return "- validationReport: null";
        }
        return "- validationReportId: " + StringUtils.defaultString(validationReportId) + "\n"
                + "- validationReportTrustedSource: frontend-fallback\n"
                + "- validationReport: " + validationReport + "\n"
                + "- validationRepairInstruction: 优先使用后端缓存报告；当前仅收到前端回传报告，需要谨慎校验后再基于问题通过 "
                + "propose_patch 生成修复草稿，不要直接写文件。";
    }

    private String paramsSummary(Map<String, String> params) {
        Map<String, Object> summary = new HashMap<>();
        summary.put(FIELD_ACTION, params.get(FIELD_ACTION));
        summary.put(FIELD_WORKSPACE_ID, params.get(FIELD_WORKSPACE_ID));
        summary.put(FIELD_SKILL_CODE, params.get(FIELD_SKILL_CODE));
        summary.put(FIELD_BIZ_KEY, params.get(FIELD_BIZ_KEY));
        summary.put(FIELD_SESSION_ID, params.get(FIELD_SESSION_ID));
        summary.put(FIELD_PATCH_ID, params.get(FIELD_PATCH_ID));
        summary.put(FIELD_USER_NAME, params.get(FIELD_USER_NAME));

        summary.put(FIELD_IDEMPOTENCY_KEY, params.get(FIELD_IDEMPOTENCY_KEY));

        summary.put(FIELD_WORKSPACE_ROOT, params.get(FIELD_WORKSPACE_ROOT));
        summary.put(FIELD_TRACE_ID, params.get(FIELD_TRACE_ID));
        summary.put(FIELD_MESSAGE_ID, params.get(FIELD_MESSAGE_ID));
        summary.put(FIELD_RUN_ID, params.get(FIELD_RUN_ID));
        summary.put(FIELD_CONVERSATION_ID, params.get(FIELD_CONVERSATION_ID));
        summary.put(FIELD_SURFACE_ID, params.get(FIELD_SURFACE_ID));
        summary.put(FIELD_ACTION_CODE, params.get(FIELD_ACTION_CODE));
        summary.put(FIELD_AUTHORING_DOMAIN, params.get(FIELD_AUTHORING_DOMAIN));
        summary.put(FIELD_ASSET_TYPE, params.get(FIELD_ASSET_TYPE));
        summary.put(FIELD_ASSET_ID, params.get(FIELD_ASSET_ID));
        summary.put(FIELD_DRAFT_ID, params.get(FIELD_DRAFT_ID));
        summary.put(FIELD_FORM_KEY, params.get(FIELD_FORM_KEY));
        summary.put(FIELD_ENTITY_ID, params.get(FIELD_ENTITY_ID));
        summary.put(FIELD_REVISION, params.get(FIELD_REVISION));
        summary.put("testInputLength", StringUtils.length(params.get(FIELD_TEST_INPUT)));
        summary.put("referenceRenderAssetsLength", StringUtils.length(params.get(FIELD_REFERENCE_RENDER_ASSETS)));
        summary.put("validationReportLength", StringUtils.length(params.get(FIELD_VALIDATION_REPORT)));
        summary.put(FIELD_VALIDATION_REPORT_ID, params.get(FIELD_VALIDATION_REPORT_ID));
        summary.put("actionParamsLength", StringUtils.length(params.get(FIELD_ACTION_PARAMS)));
        summary.put("currentDraftLength", StringUtils.length(params.get(FIELD_CURRENT_DRAFT)));
        summary.put("messageLength", StringUtils.length(params.get(FIELD_MESSAGE)));
        return JsonSupport.toJSON(summary);
    }

    private String safeToolArgs(Map<String, String> params) {
        Map<String, Object> summary = new HashMap<>();
        summary.put(FIELD_ACTION, params.get(FIELD_ACTION));
        summary.put(FIELD_MESSAGE_ID, params.get(FIELD_MESSAGE_ID));
        summary.put(FIELD_RUN_ID, params.get(FIELD_RUN_ID));
        summary.put(FIELD_SURFACE_ID, params.get(FIELD_SURFACE_ID));
        summary.put(FIELD_ACTION_CODE, params.get(FIELD_ACTION_CODE));
        summary.put(FIELD_IDEMPOTENCY_KEY, params.get(FIELD_IDEMPOTENCY_KEY));
        summary.put("actionParamsLength", StringUtils.length(params.get(FIELD_ACTION_PARAMS)));
        return JsonSupport.toJSON(summary);
    }

    private String safeValidationToolArgs(Map<String, String> params) {
        Map<String, Object> summary = new HashMap<>();
        summary.put(FIELD_WORKSPACE_ID, params.get(FIELD_WORKSPACE_ID));
        summary.put(FIELD_SKILL_CODE, params.get(FIELD_SKILL_CODE));
        summary.put(FIELD_MESSAGE_ID, params.get(FIELD_MESSAGE_ID));
        summary.put(FIELD_RUN_ID, params.get(FIELD_RUN_ID));
        summary.put("testInputLength", StringUtils.length(params.get(FIELD_TEST_INPUT)));
        summary.put("referenceRenderAssetsLength", StringUtils.length(params.get(FIELD_REFERENCE_RENDER_ASSETS)));
        summary.put("constraints", Map.of(
                "readOnly", true,
                "noPatch", true,
                "noWorkspaceWrite", true,
                "noBusinessSideEffect", true,
                "timeoutMs", 60000));
        return JsonSupport.toJSON(summary);
    }

    private String safeValidationTaskPayload(Map<String, String> params) {
        Map<String, Object> payload = new HashMap<>();
        payload.put(FIELD_WORKSPACE_ID, params.get(FIELD_WORKSPACE_ID));
        payload.put(FIELD_SKILL_CODE, params.get(FIELD_SKILL_CODE));
        payload.put(FIELD_MESSAGE_ID, params.get(FIELD_MESSAGE_ID));
        payload.put(FIELD_RUN_ID, params.get(FIELD_RUN_ID));
        payload.put(FIELD_CONVERSATION_ID, params.get(FIELD_CONVERSATION_ID));
        payload.put(FIELD_TEST_INPUT, StringUtils.defaultString(params.get(FIELD_TEST_INPUT)));
        payload.put("readOnly", true);
        return JsonSupport.toJSON(payload);
    }

    private String validationTraceSummary(ValidationReport report) {
        if (report == null) {
            return "运行验证未返回报告。";
        }
        String protocol = report.getProtocol() == null ? "unknown" : report.getProtocol().getType();
        return "验证状态 " + StringUtils.defaultString(report.getStatus()) + "，协议识别 " + protocol
                + "，问题数 " + report.getIssues().size() + "。";
    }

    private String validationAnswerSummary(ValidationReport report) {
        if (report == null) {
            return "运行验证未返回报告，请查看执行过程日志。";
        }
        String protocol = report.getProtocol() == null ? "unknown" : report.getProtocol().getType();
        String code = report.getProtocol() == null ? StringUtils.EMPTY
                                                   : StringUtils.defaultString(report.getProtocol().getCode());
        return "运行验证完成，状态：" + StringUtils.defaultString(report.getStatus())
                + "。\n\n协议识别：" + protocol + (StringUtils.isBlank(code) ? "" : " = " + code)
                + "。\n\n发现问题：" + report.getIssues().size()
                + " 个。可以在验证卡片里查看原始输出和检查项，也可以点击“让主 Agent 修复”生成 patch。";
    }

    /**
     * 发送 AI Coding 专属 AG-UI-like 过程事件。
     *
     * <p>这里生成 AI Coding 运行态 payload 事件；公共引擎兼容传输由包外 bridge 负责，
     * 普通 ReAct 引擎不会感知该协议。
     */
    private void emitAgUiEvent(long agentId, Map<String, String> params, Consumer<AiCodingStreamEvent> sink,
            String eventType, String stageId, String title, String summary, String status, String toolCallId,
            String toolName, boolean success) {
        try {
            AiCodingEventPayload payload = aiCodingEventPayloadFactory.agUiEvent(
                    params.get(FIELD_WORKSPACE_ID),
                    params.get(FIELD_SESSION_ID),
                    params.get(FIELD_MESSAGE_ID),
                    params.get(FIELD_RUN_ID),
                    params.get(FIELD_CONVERSATION_ID),
                    params.get(FIELD_TRACE_ID),
                    eventType,
                    stageId,
                    title,
                    StringUtils.abbreviate(StringUtils.defaultString(summary), TRACE_SUMMARY_MAX_LENGTH),
                    status,
                    toolCallId,
                    toolName,
                    success,
                    Collections.emptyMap());
            String payloadJson = aiCodingEventPayloadCodec.toJson(payload);
            String eventId = stageId + "_" + eventType + "_" + System.currentTimeMillis();
            emit(sink, aiCodingStreamEventFactory.executionTrace(agentId, params,
                    buildToolCallId(TOOL_AG_UI_EVENT, eventId), TOOL_AG_UI_EVENT, payloadJson, success));
        } catch (Exception e) {
            log.warn("AiCodingReActEngine发送过程事件失败, agentId={}, eventType={}, stageId={}, summary={}",
                    agentId, eventType, stageId, paramsSummary(params), e);
        }
    }

    private String toolResultSummary(String resultContent) {
        if (StringUtils.isBlank(resultContent)) {
            return "工具已返回空结果。";
        }
        return "工具已返回：" + StringUtils.abbreviate(resultContent.replaceAll("\\s+", " ").trim(),
                TRACE_SUMMARY_MAX_LENGTH);
    }

    /**
     * 根据工具结果内容分流结构化 runtime 事件。
     *
     * <p>每个工具结果先返回 `TOOL_CALL_FINISHED` 闭合通用生命周期。如果工具结果本身是
     * AI Coding 标准 payload，再按 eventCode 追加 patch artifact、审批请求、业务交互或
     * observation 等领域投影，避免前端继续从 `content` 里猜测业务 JSON。
     */
    private void emitToolResultEvents(long agentId, Map<String, String> params, String toolCallId, String toolName,
            String resultContent, boolean success, boolean hasKnowledge, Consumer<AiCodingStreamEvent> sink) {
        emit(sink, aiCodingStreamEventFactory.toolCallFinished(agentId, params, toolCallId, toolName,
                resultContent, success, hasKnowledge));
        Map<String, Object> payload = parsePayloadRecord(resultContent);
        String eventCode = MapUtils.getString(payload, FIELD_EVENT_CODE);
        if (StringUtils.equals(eventCode, AiCodingEventCode.PATCH_PROPOSED.getCode())
                || StringUtils.equals(eventCode, AiCodingEventCode.PATCH_APPLIED.getCode())
                || StringUtils.equals(eventCode, AiCodingEventCode.PATCH_DISCARDED.getCode())
                || StringUtils.equals(eventCode, AiCodingEventCode.PATCH_CONFLICT.getCode())) {
            emit(sink, aiCodingStreamEventFactory.artifactCreated(agentId, params, toolCallId, toolName,
                    resultContent, success));

            return;
        }
        if (StringUtils.equals(eventCode, AiCodingEventCode.A2UI_MESSAGE.getCode())) {
            emit(sink, aiCodingStreamEventFactory.businessInteractionCreated(agentId, params, toolCallId, toolName,
                    resultContent));
            return;
        }
        if (StringUtils.equals(eventCode, AiCodingEventCode.AUTHORING_DRAFT_CHANGE.getCode())
                || StringUtils.equals(eventCode, AiCodingEventCode.CAPABILITY_DRAFT_VALIDATED.getCode())) {
            Map<String, Object> content = mapValue(payload.get(FIELD_CONTENT));
            String payloadType = MapUtils.getString(content, FIELD_PAYLOAD_TYPE);
            if (StringUtils.isBlank(payloadType)) {
                emit(sink, aiCodingStreamEventFactory.error(agentId, params,
                        "Authoring Tool 结果缺少 payloadType"));
                return;
            }
            emit(sink, aiCodingStreamEventFactory.runtimeArtifactCreated(agentId, params, toolCallId, toolName,
                    payloadType, resultContent, MapUtils.getString(content, FIELD_SUMMARY,
                            "结构化草稿产物已生成"), success));
            return;
        }
        if (StringUtils.equals(eventCode, AiCodingEventCode.AUTHORING_OBSERVATION.getCode())) {
            emit(sink, aiCodingStreamEventFactory.observationCreated(agentId, params, toolCallId, toolName,
                    resultContent));
            return;
        }
        if (StringUtils.equals(eventCode, AiCodingEventCode.AG_UI_EVENT.getCode())) {
            emit(sink, aiCodingStreamEventFactory.executionTrace(agentId, params, toolCallId, toolName,
                    resultContent, success));
            return;
        }
        if (StringUtils.equals(eventCode, AiCodingEventCode.VALIDATION_REPORT_CREATED.getCode())) {
            emit(sink, aiCodingStreamEventFactory.validationReportCreated(agentId, params, toolCallId, toolName,
                    resultContent, success));
            return;
        }
        if (StringUtils.equals(eventCode, AiCodingEventCode.FAILED.getCode())) {
            emit(sink, aiCodingStreamEventFactory.toolError(agentId, params, toolCallId, toolName,
                    resultContent, MapUtils.getString(payload, FIELD_ERROR_MSG, resultContent)));
            return;
        }
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> mapValue(Object value) {
        if (value instanceof Map) {
            return (Map<String, Object>) value;
        }
        return Collections.emptyMap();
    }

    private Map<String, Object> parsePayloadRecord(String resultContent) {
        if (StringUtils.isBlank(resultContent)) {
            return Collections.emptyMap();
        }
        try {
            Map<String, Object> payload = JsonSupport.fromJson(resultContent);
            return payload == null ? Collections.emptyMap() : payload;
        } catch (Exception e) {
            return Collections.emptyMap();
        }
    }

    private static class StreamAccumulator {
        private final AssistantMessage assistantMessage;
        private final int totalTokens;
        private final int enterTokens;
        private final int outputTokens;
        private final String reasoningContent;
        private final String finishReason;

        StreamAccumulator(AssistantMessage assistantMessage, int totalTokens, int enterTokens, int outputTokens,
                String reasoningContent, String finishReason) {
            this.assistantMessage = assistantMessage;
            this.totalTokens = totalTokens;
            this.enterTokens = enterTokens;
            this.outputTokens = outputTokens;
            this.reasoningContent = reasoningContent;
            this.finishReason = StringUtils.defaultString(finishReason);
        }

        AssistantMessage getAssistantMessage() {
            return assistantMessage;
        }

        int getTotalTokens() {
            return totalTokens;
        }

        int getEnterTokens() {
            return enterTokens;
        }

        int getOutputTokens() {
            return outputTokens;
        }

        String getReasoningContent() {
            return reasoningContent;
        }

        String getFinishReason() {
            return finishReason;
        }
    }

    private static class ModelStreamState {
        private final StringBuilder textBuilder = new StringBuilder();
        private final StringBuilder reasoningBuilder = new StringBuilder();
        private final List<String> toolCallIds = new ArrayList<>();
        private final Map<String, StringBuilder> toolCallArgsBuilders = new HashMap<>();
        private final Map<String, String> toolCallNames = new HashMap<>();
        private final Map<String, String> toolCallTypes = new HashMap<>();
        private final AtomicInteger totalTokens = new AtomicInteger(0);
        private final AtomicInteger enterTokens = new AtomicInteger(0);
        private final AtomicInteger outputTokens = new AtomicInteger(0);
        private String finishReason = StringUtils.EMPTY;
        private AiCodingModelStreamParser modelStreamParser;

        StringBuilder getTextBuilder() {
            return textBuilder;
        }

        StringBuilder getReasoningBuilder() {
            return reasoningBuilder;
        }

        List<String> getToolCallIds() {
            return toolCallIds;
        }

        Map<String, StringBuilder> getToolCallArgsBuilders() {
            return toolCallArgsBuilders;
        }

        Map<String, String> getToolCallNames() {
            return toolCallNames;
        }

        Map<String, String> getToolCallTypes() {
            return toolCallTypes;
        }

        AtomicInteger getTotalTokens() {
            return totalTokens;
        }

        AtomicInteger getEnterTokens() {
            return enterTokens;
        }

        AtomicInteger getOutputTokens() {
            return outputTokens;
        }

        String getFinishReason() {
            return finishReason;
        }

        void setFinishReason(String finishReason) {
            this.finishReason = StringUtils.defaultString(finishReason);
        }

        AiCodingModelStreamParser getModelStreamParser() {
            return modelStreamParser;
        }

        void setModelStreamParser(AiCodingModelStreamParser modelStreamParser) {
            this.modelStreamParser = modelStreamParser;
        }
    }

}
