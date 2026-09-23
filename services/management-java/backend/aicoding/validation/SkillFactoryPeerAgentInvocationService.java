package dev.a2flow.management.aicoding.validation;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;

import jakarta.annotation.Resource;

import org.apache.commons.collections4.CollectionUtils;
import org.apache.commons.collections4.MapUtils;
import org.apache.commons.lang3.StringUtils;
import org.apache.commons.lang3.math.NumberUtils;
import org.springframework.stereotype.Component;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.agentcore.infrastructrue.kconf.model.AgentPropertiesConfig;
import dev.a2flow.management.agentcore.runtime.engine.model.AgentEngineContext;
import dev.a2flow.management.agentcore.runtime.engine.model.BaseAgentContext;
import dev.a2flow.management.agentcore.util.ToolUtil;
import dev.a2flow.management.config.SkillFactoryAgentBizSummaryConfig;
import dev.a2flow.management.config.SkillFactoryAgentToolConfig;
import dev.a2flow.management.config.SkillFactoryConfigReader;
import dev.a2flow.management.config.SkillFactoryInvokeAgentConfig;
import dev.a2flow.management.config.SkillFactoryPeerAgentConfig;
import dev.a2flow.management.event.AiCodingEventPayload;
import dev.a2flow.management.event.AiCodingEventPayloadCodec;
import dev.a2flow.management.event.AiCodingEventPayloadFactory;

import lombok.extern.slf4j.Slf4j;

/**
 * SkillFactory peer Agent 调用服务。
 *
 * <p>该服务是 `invoke_agent` 工具的后端白名单和任务分发层。它不把某个 Agent 固定为子 Agent，
 * 只在一次工具调用里根据配置把平级 Agent 当作工具型执行者使用，并记录调用证据。
 */
@Slf4j
@Component
public class SkillFactoryPeerAgentInvocationService {

    private static final String FIELD_BIZ_KEY = "bizKey";
    private static final String FIELD_AGENT_ID = "agentId";
    private static final String FIELD_ALIAS = "alias";
    private static final String FIELD_TASK_TYPE = "taskType";
    private static final String FIELD_EXPECTED_OUTPUT_TYPE = "expectedOutputType";
    private static final String FIELD_WORKSPACE_ID = "workspaceId";
    private static final String FIELD_SKILL_CODE = "skillCode";
    private static final String FIELD_TEST_INPUT = "testInput";
    private static final String FIELD_MESSAGE = "message";
    private static final String FIELD_WORKSPACE_ROOT = "workspaceRoot";
    private static final String FIELD_SESSION_ID = "sessionId";
    private static final String FIELD_MESSAGE_ID = "messageId";
    private static final String FIELD_RUN_ID = "runId";
    private static final String FIELD_CONVERSATION_ID = "conversationId";
    private static final String FIELD_TRACE_ID = "traceId";
    private static final String FIELD_REFERENCE_RENDER_ASSETS = "referenceRenderAssets";
    private static final String FIELD_OWNER_ID = "ownerId";
    private static final String FIELD_USER_ID = "userId";
    private static final String FIELD_CLIENT = "client";
    private static final String TASK_TYPE_SKILL_RUNTIME_VALIDATION = "SKILL_RUNTIME_VALIDATION";
    private static final String OUTPUT_VALIDATION_REPORT = "ValidationReport";
    private static final String STATUS_PASSED = ValidationReport.STATUS_PASSED;
    private static final String STATUS_FAILED = ValidationReport.STATUS_FAILED;
    private static final String STATUS_PARTIAL = ValidationReport.STATUS_PARTIAL;
    private static final String ISSUE_ERROR = "ERROR";
    private static final String ISSUE_WARN = "WARN";
    private static final String PROTOCOL_AGENT_UI_DSL = "agentUiDsl";
    private static final String PROTOCOL_COMPONENT_NAME = "componentName";
    private static final String PROTOCOL_LOCAL_METHOD = "localMethod";
    private static final String PROTOCOL_TEXT = "text";
    private static final String PROTOCOL_UNKNOWN = "unknown";
    private static final String EXECUTION_MODE_AGENT_ENGINE = "AGENT_ENGINE_EXECUTOR";
    private static final int CHILD_FINAL_ANSWER_PREVIEW_LENGTH = 4000;
    private static final int REPORT_PROMPT_PREVIEW_LENGTH = 3000;

    @Resource
    private SkillFactoryConfigReader skillFactoryConfigReader;

    @Resource
    private SkillFactoryValidationReportStore validationReportStore;

    @Resource
    private AiCodingEventPayloadFactory aiCodingEventPayloadFactory;

    @Resource
    private AiCodingEventPayloadCodec aiCodingEventPayloadCodec;

    @Resource
    private SkillFactoryPeerAgentEngineInvoker peerAgentEngineInvoker;

    /**
     * 执行 peer Agent 调用并返回标准 AI Coding payload JSON。
     */
    public String invoke(Map<String, String> callerParams, Map<String, Object> input) {
        String callerBizKey = StringUtils.defaultString(MapUtils.getString(callerParams, FIELD_BIZ_KEY));
        SkillFactoryPeerAgentConfig calleeConfig = matchCallee(callerBizKey, input);
        if (calleeConfig == null) {
            log.info("SkillFactory invoke_agent拒绝未授权Agent调用, callerBizKey={}, input={}",
                    callerBizKey, safeInputSummary(input));
            return failedPayload(callerParams, "invoke_agent 未找到已授权的 peer Agent 配置");
        }
        String taskType = StringUtils.defaultIfBlank(MapUtils.getString(input, FIELD_TASK_TYPE),
                firstTaskType(calleeConfig));
        String expectedOutputType = StringUtils.defaultIfBlank(MapUtils.getString(input, FIELD_EXPECTED_OUTPUT_TYPE),
                calleeConfig.getExpectedOutputType());
        log.info("SkillFactory invoke_agent开始调用peer Agent, callerBizKey={}, calleeAlias={}, "
                        + "calleeBizKey={}, calleeAgentId={}, taskType={}, expectedOutputType={}",
                callerBizKey, calleeConfig.getAlias(), calleeConfig.getBizKey(), calleeConfig.getAgentId(),
                taskType, expectedOutputType);
        if (!StringUtils.equals(taskType, TASK_TYPE_SKILL_RUNTIME_VALIDATION)
                || !StringUtils.equalsIgnoreCase(expectedOutputType, OUTPUT_VALIDATION_REPORT)) {
            return failedPayload(callerParams, "invoke_agent 当前仅支持 SKILL_RUNTIME_VALIDATION -> ValidationReport");
        }
        if (!CollectionUtils.emptyIfNull(calleeConfig.getRequiredTools())
                .contains(SkillSimulationResult.TOOL_NAME)) {
            return failedPayload(callerParams, "invoke_agent 配置缺少 simulate_skill_request 必要工具");
        }
        Map<String, String> delegateParams = buildDelegateParams(callerParams, input, calleeConfig);
        SkillFactoryPeerAgentRunResult runResult = executePeerAgent(callerBizKey, delegateParams, input,
                calleeConfig, taskType, expectedOutputType);
        ValidationReport report = buildValidationReport(callerBizKey, delegateParams, calleeConfig, runResult,
                taskType, expectedOutputType);
        validationReportStore.put(report);
        AiCodingEventPayload payload = aiCodingEventPayloadFactory.validationReport(
                delegateParams.get(FIELD_WORKSPACE_ID),
                delegateParams.get(FIELD_SESSION_ID),
                delegateParams.get(FIELD_MESSAGE_ID),
                delegateParams.get(FIELD_RUN_ID),
                delegateParams.get(FIELD_CONVERSATION_ID),
                delegateParams.get(FIELD_TRACE_ID),
                report);
        log.info("SkillFactory invoke_agent完成peer Agent调用, callerBizKey={}, calleeAlias={}, reportId={}, "
                        + "status={}, issueCount={}",
                callerBizKey, calleeConfig.getAlias(), report.getReportId(), report.getStatus(),
                report.getIssues().size());
        return aiCodingEventPayloadCodec.toJson(payload);
    }

    private SkillFactoryPeerAgentConfig matchCallee(String callerBizKey, Map<String, Object> input) {
        SkillFactoryAgentToolConfig agentToolConfig = skillFactoryConfigReader.getAgentToolConfig(callerBizKey);
        SkillFactoryInvokeAgentConfig invokeAgentConfig = agentToolConfig == null
                                                         ? null : agentToolConfig.getInvokeAgent();
        if (invokeAgentConfig == null || !invokeAgentConfig.isEnabled()
                || CollectionUtils.isEmpty(invokeAgentConfig.getAllowedAgents())) {
            return null;
        }
        String alias = MapUtils.getString(input, FIELD_ALIAS);
        String bizKey = MapUtils.getString(input, FIELD_BIZ_KEY);
        String agentId = MapUtils.getString(input, FIELD_AGENT_ID);
        String taskType = MapUtils.getString(input, FIELD_TASK_TYPE);
        boolean hasIdentity = StringUtils.isNotBlank(alias) || StringUtils.isNotBlank(bizKey)
                || StringUtils.isNotBlank(agentId);
        for (SkillFactoryPeerAgentConfig config : invokeAgentConfig.getAllowedAgents()) {
            if (hasIdentity && !matchIdentity(config, alias, bizKey, agentId)) {
                continue;
            }
            if (StringUtils.isNotBlank(taskType)
                    && CollectionUtils.isNotEmpty(config.getTaskTypes())
                    && !config.getTaskTypes().contains(taskType)) {
                continue;
            }
            return config;
        }
        return null;
    }

    private boolean matchIdentity(SkillFactoryPeerAgentConfig config, String alias, String bizKey, String agentId) {
        if (config == null) {
            return false;
        }
        if (StringUtils.isNotBlank(alias) && StringUtils.equals(alias, config.getAlias())) {
            return true;
        }
        if (StringUtils.isNotBlank(bizKey) && StringUtils.equals(bizKey, config.getBizKey())) {
            return true;
        }
        return StringUtils.isNotBlank(agentId) && StringUtils.equals(agentId, config.getAgentId());
    }

    private Map<String, String> buildDelegateParams(Map<String, String> callerParams, Map<String, Object> input,
            SkillFactoryPeerAgentConfig calleeConfig) {
        Map<String, String> delegateParams = new HashMap<>(callerParams);
        putString(delegateParams, FIELD_BIZ_KEY, StringUtils.defaultIfBlank(calleeConfig.getBizKey(),
                callerParams.get(FIELD_BIZ_KEY)));
        putString(delegateParams, FIELD_AGENT_ID, calleeConfig.getAgentId());
        putString(delegateParams, FIELD_WORKSPACE_ID, firstNotBlank(input, FIELD_WORKSPACE_ID,
                callerParams.get(FIELD_WORKSPACE_ID)));
        putString(delegateParams, FIELD_SKILL_CODE, firstNotBlank(input, FIELD_SKILL_CODE,
                callerParams.get(FIELD_SKILL_CODE)));
        putString(delegateParams, FIELD_TEST_INPUT, firstNotBlank(input, FIELD_TEST_INPUT,
                firstNotBlank(input, FIELD_MESSAGE, callerParams.get(FIELD_MESSAGE))));
        putString(delegateParams, FIELD_REFERENCE_RENDER_ASSETS, firstNotBlank(input, FIELD_REFERENCE_RENDER_ASSETS,
                callerParams.get(FIELD_REFERENCE_RENDER_ASSETS)));
        putString(delegateParams, FIELD_WORKSPACE_ROOT, callerParams.get(FIELD_WORKSPACE_ROOT));
        putString(delegateParams, FIELD_SESSION_ID, callerParams.get(FIELD_SESSION_ID));
        putString(delegateParams, FIELD_MESSAGE_ID, callerParams.get(FIELD_MESSAGE_ID));
        putString(delegateParams, FIELD_RUN_ID, callerParams.get(FIELD_RUN_ID));
        putString(delegateParams, FIELD_CONVERSATION_ID, callerParams.get(FIELD_CONVERSATION_ID));
        putString(delegateParams, FIELD_TRACE_ID, callerParams.get(FIELD_TRACE_ID));
        putString(delegateParams, FIELD_OWNER_ID, callerParams.get(FIELD_OWNER_ID));
        putString(delegateParams, FIELD_USER_ID, callerParams.get(FIELD_USER_ID));
        putString(delegateParams, FIELD_CLIENT, callerParams.get(FIELD_CLIENT));
        return delegateParams;
    }

    private SkillFactoryPeerAgentRunResult executePeerAgent(String callerBizKey, Map<String, String> delegateParams,
            Map<String, Object> input, SkillFactoryPeerAgentConfig calleeConfig, String taskType,
            String expectedOutputType) {
        long startTime = System.currentTimeMillis();
        SkillFactoryPeerAgentRunResult runResult = new SkillFactoryPeerAgentRunResult()
                .setCalleeAlias(calleeConfig.getAlias())
                .setCalleeBizKey(StringUtils.defaultIfBlank(calleeConfig.getBizKey(),
                        delegateParams.get(FIELD_BIZ_KEY)))
                .setCalleeAgentId(calleeConfig.getAgentId())
                .setTaskType(taskType)
                .setExpectedOutputType(expectedOutputType);
        try {
            AgentEngineContext childContext = buildPeerAgentContext(callerBizKey, delegateParams, input,
                    calleeConfig, taskType, expectedOutputType, runResult);
            SkillFactoryPeerAgentRunCollector collector = new SkillFactoryPeerAgentRunCollector(runResult,
                    SkillSimulationResult.TOOL_NAME);
            peerAgentEngineInvoker.process(childContext, collector);
            return collector.finish().setCostMs(System.currentTimeMillis() - startTime);
        } catch (Exception e) {
            log.error("SkillFactory invoke_agent执行peer Agent异常, callerBizKey={}, calleeAlias={}, "
                            + "calleeBizKey={}, taskType={}",
                    callerBizKey, calleeConfig.getAlias(), calleeConfig.getBizKey(), taskType, e);
            return runResult.setErrorMessage(StringUtils.defaultString(e.getMessage()))
                    .setCostMs(System.currentTimeMillis() - startTime);
        }
    }

    private AgentEngineContext buildPeerAgentContext(String callerBizKey, Map<String, String> delegateParams,
            Map<String, Object> input, SkillFactoryPeerAgentConfig calleeConfig, String taskType,
            String expectedOutputType, SkillFactoryPeerAgentRunResult runResult) {
        String calleeBizKey = StringUtils.defaultIfBlank(calleeConfig.getBizKey(), delegateParams.get(FIELD_BIZ_KEY));
        long calleeAgentId = NumberUtils.toLong(calleeConfig.getAgentId(), 0L);
        if (calleeAgentId <= 0L) {
            throw new IllegalArgumentException("invoke_agent calleeAgentId 非法");
        }
        SkillFactoryAgentBizSummaryConfig calleeBizConfig =
                skillFactoryConfigReader.getAgentBizSummaryConfig(calleeBizKey);
        if (calleeBizConfig == null || calleeBizConfig.getPropertiesConfig() == null) {
            throw new IllegalArgumentException("invoke_agent 未找到 callee bizKey 配置: " + calleeBizKey);
        }
        AgentPropertiesConfig propertiesConfig = skillFactoryConfigReader.buildAgentPropertiesConfig(calleeBizConfig);
        if (!CollectionUtils.emptyIfNull(propertiesConfig.getTools()).contains(SkillSimulationResult.TOOL_NAME)) {
            throw new IllegalArgumentException("invoke_agent callee tools 未配置 simulate_skill_request");
        }
        String childSessionId = buildChildSessionId(calleeConfig, delegateParams);
        String childRunId = "run_" + childSessionId;
        runResult.setChildSessionId(childSessionId).setChildRunId(childRunId);

        AgentEngineContext childContext = new AgentEngineContext();
        childContext.setBizKey(calleeBizKey);
        childContext.setAgentId(calleeAgentId);
        childContext.setAgentName(StringUtils.defaultIfBlank(calleeConfig.getAlias(), "SkillFactoryPeerAgent"));
        childContext.setOwnerId(delegateParams.get(FIELD_OWNER_ID));
        childContext.setUserId(dev.a2flow.management.access.UserIds.parseWire(delegateParams.get(FIELD_USER_ID)));
        childContext.setBizRolePrompt(StringUtils.defaultString(calleeConfig.getDescription()));
        childContext.setConversationId(childSessionId);
        childContext.setPrimaryConversationId(delegateParams.get(FIELD_SESSION_ID));
        childContext.setInvokeId(childRunId);
        childContext.setTraceId(delegateParams.get(FIELD_TRACE_ID));
        childContext.setAgentPropertiesConfig(propertiesConfig);
        childContext.setLlmModelConfig(skillFactoryConfigReader.buildLlmModelConfig(calleeBizConfig));
        childContext.setAgentMemoryConfig(skillFactoryConfigReader.buildAgentMemoryConfig(calleeBizConfig));
        childContext.setSkillList(List.of());
        childContext.setAgentContext(buildPeerBaseAgentContext(callerBizKey, delegateParams, input, calleeConfig,
                taskType, expectedOutputType, runResult));
        return childContext;
    }

    private BaseAgentContext buildPeerBaseAgentContext(String callerBizKey, Map<String, String> delegateParams,
            Map<String, Object> input, SkillFactoryPeerAgentConfig calleeConfig, String taskType,
            String expectedOutputType, SkillFactoryPeerAgentRunResult runResult) {
        BaseAgentContext agentContext = new BaseAgentContext();
        agentContext.setOwnerId(delegateParams.get(FIELD_OWNER_ID));
        agentContext.setUserId(dev.a2flow.management.access.UserIds.parseWire(delegateParams.get(FIELD_USER_ID)));
        agentContext.setClient(delegateParams.get(FIELD_CLIENT));
        agentContext.setEnv(ToolUtil.getEnvName());
        agentContext.setUserMessage(buildPeerAgentMessage(delegateParams, input, calleeConfig, taskType,
                expectedOutputType));
        Map<String, Object> extraBizParam = new HashMap<>();
        extraBizParam.putAll(delegateParams);
        extraBizParam.put("callerBizKey", callerBizKey);
        extraBizParam.put("calleeAlias", calleeConfig.getAlias());
        extraBizParam.put("calleeDescription", calleeConfig.getDescription());
        extraBizParam.put("taskType", taskType);
        extraBizParam.put("expectedOutputType", expectedOutputType);
        extraBizParam.put("requiredTools", calleeConfig.getRequiredTools());
        extraBizParam.put("readOnly", calleeConfig.isReadOnly());
        extraBizParam.put("noPatch", calleeConfig.isNoPatch());
        extraBizParam.put("noWorkspaceWrite", calleeConfig.isNoWorkspaceWrite());
        extraBizParam.put("noBusinessSideEffect", calleeConfig.isNoBusinessSideEffect());
        extraBizParam.put("timeoutMs", calleeConfig.getTimeoutMs());
        extraBizParam.put("parentSessionId", delegateParams.get(FIELD_SESSION_ID));
        extraBizParam.put("parentRunId", delegateParams.get(FIELD_RUN_ID));
        String childSessionId = runResult.getChildSessionId();
        String childRunId = runResult.getChildRunId();
        extraBizParam.put(FIELD_SESSION_ID, childSessionId);
        extraBizParam.put(FIELD_CONVERSATION_ID, childSessionId);
        extraBizParam.put(FIELD_RUN_ID, childRunId);
        extraBizParam.put(FIELD_MESSAGE_ID, "msg_" + childRunId);
        extraBizParam.put(FIELD_MESSAGE, MapUtils.getString(input, FIELD_MESSAGE,
                delegateParams.get(FIELD_MESSAGE)));
        agentContext.setExtraBizParam(extraBizParam);
        return agentContext;
    }

    private String buildPeerAgentMessage(Map<String, String> delegateParams, Map<String, Object> input,
            SkillFactoryPeerAgentConfig calleeConfig, String taskType, String expectedOutputType) {
        Map<String, Object> taskSpec = new HashMap<>();
        taskSpec.put("taskType", taskType);
        taskSpec.put("expectedOutputType", expectedOutputType);
        taskSpec.put(FIELD_WORKSPACE_ID, delegateParams.get(FIELD_WORKSPACE_ID));
        taskSpec.put(FIELD_SKILL_CODE, delegateParams.get(FIELD_SKILL_CODE));
        taskSpec.put(FIELD_TEST_INPUT, delegateParams.get(FIELD_TEST_INPUT));
        taskSpec.put(FIELD_REFERENCE_RENDER_ASSETS, delegateParams.get(FIELD_REFERENCE_RENDER_ASSETS));
        taskSpec.put("constraints", Map.of(
                "readOnly", calleeConfig.isReadOnly(),
                "noPatch", calleeConfig.isNoPatch(),
                "noWorkspaceWrite", calleeConfig.isNoWorkspaceWrite(),
                "noBusinessSideEffect", calleeConfig.isNoBusinessSideEffect(),
                "timeoutMs", calleeConfig.getTimeoutMs()));
        return """
                你正被主 Agent 作为一次性 peer Agent 工具调用。
                任务：%s，期望输出：%s。
                你必须先调用 simulate_skill_request 工具，使用 taskSpec 中的 workspaceId、skillCode 和 testInput。
                工具返回后，请用中文判断 Skill 的真实输出或模拟输出是否符合用户预期、参考组件协议和 runtime 承接要求。
                只允许只读验证，不要生成 patch，不要写 workspace，不要调用发布或注册接口。
                如果 simulate_skill_request 没有执行成功，必须明确返回 FAILED/PARTIAL，不允许伪装通过。

                taskSpec:
                %s

                主 Agent 传入的自然语言任务：
                %s
                """.formatted(taskType, expectedOutputType, JsonSupport.toJSON(taskSpec),
                StringUtils.defaultIfBlank(MapUtils.getString(input, FIELD_MESSAGE),
                        delegateParams.get(FIELD_MESSAGE)));
    }

    private ValidationReport buildValidationReport(String callerBizKey, Map<String, String> delegateParams,
            SkillFactoryPeerAgentConfig calleeConfig, SkillFactoryPeerAgentRunResult runResult, String taskType,
            String expectedOutputType) {
        SkillSimulationResult simulationResult = runResult.getSimulationResult();
        String taskId = "validation_" + UUID.randomUUID().toString().replace("-", "");
        ValidationReport report = new ValidationReport()
                .setTaskId(taskId)
                .setReportId(taskId)
                .setWorkspaceId(delegateParams.get(FIELD_WORKSPACE_ID))
                .setSkillCode(delegateParams.get(FIELD_SKILL_CODE))
                .setTestInput(delegateParams.get(FIELD_TEST_INPUT))
                .setRawOutput(resolveRawOutput(simulationResult, runResult))
                .setStdoutSummary(resolveStdoutSummary(simulationResult, runResult))
                .setFileTreeDigest(simulationResult == null ? StringUtils.EMPTY
                        : StringUtils.defaultString(simulationResult.getFileTreeDigest()))
                .setProtocol(detectProtocol(resolveRawOutput(simulationResult, runResult)));
        appendPeerInvocationChecks(report, runResult, simulationResult);
        report.setStatus(resolveReportStatus(runResult, simulationResult));
        report.setAgentInvocationEvidence(agentInvocationEvidence(callerBizKey, calleeConfig, runResult, taskType,
                expectedOutputType));
        report.setSimulationEvidence(simulationEvidence(runResult, simulationResult));
        report.setRepairPrompt(buildRepairPrompt(report, runResult));
        return report;
    }

    private void appendPeerInvocationChecks(ValidationReport report, SkillFactoryPeerAgentRunResult runResult,
            SkillSimulationResult simulationResult) {
        boolean invokeSuccess = StringUtils.isBlank(runResult.getErrorMessage());
        report.getChecks().add(newCheck("invokeAgent", "peer Agent 调用", invokeSuccess ? STATUS_PASSED
                : STATUS_FAILED, invokeSuccess ? "已通过 SkillFactory 本地引擎调用器执行 peer Agent。"
                : "peer Agent 调用失败: " + runResult.getErrorMessage()));
        if (!invokeSuccess) {
            report.getIssues().add(newIssue(ISSUE_ERROR, "invoke-agent",
                    "peer Agent 调用失败: " + runResult.getErrorMessage(),
                    "检查 callee bizKey、agentId、模型配置和默认引擎策略。"));
        }
        report.getChecks().add(newCheck("simulateSkillRequest", "simulate_skill_request 工具证据",
                runResult.isSimulateToolCalled() && runResult.isSimulateToolSucceeded() ? STATUS_PASSED
                        : STATUS_FAILED,
                runResult.isSimulateToolCalled() ? "peer Agent 已调用 simulate_skill_request。"
                        : "peer Agent 未调用 simulate_skill_request。"));
        if (!runResult.isSimulateToolCalled() || !runResult.isSimulateToolSucceeded()) {
            report.getIssues().add(newIssue(ISSUE_ERROR, "runtime",
                    "未拿到成功的 simulate_skill_request 工具结果。",
                    "确认 CheckAgent KConf tools 只暴露并强制使用 simulate_skill_request。"));
            return;
        }
        if (simulationResult == null) {
            report.getIssues().add(newIssue(ISSUE_ERROR, "runtime",
                    "simulate_skill_request 结果无法解析。", "检查工具返回是否为 SkillSimulationResult JSON。"));
            return;
        }
        String simulationStatus = StringUtils.defaultIfBlank(simulationResult.getStatus(), STATUS_FAILED);
        report.getChecks().add(newCheck("simulationStatus", "模拟 Skill 请求结果", simulationStatus,
                "simulate_skill_request 状态=" + simulationStatus + "，原因="
                        + StringUtils.defaultString(simulationResult.getReason())));
        if (!StringUtils.equals(STATUS_PASSED, simulationStatus)) {
            report.getIssues().add(newIssue(StringUtils.equals(STATUS_FAILED, simulationStatus)
                            ? ISSUE_ERROR : ISSUE_WARN, "runtime",
                    "模拟 Skill 请求未完全通过: " + StringUtils.defaultString(simulationResult.getReason()),
                    "根据 rawOutput 和子 Agent 分析修复 Skill 输出协议或等待真实 runtime adapter 接入。"));
        }
        report.getChecks().add(newCheck("runtimeAdapter", "runtime adapter 接入", simulationResult
                .isRuntimeAdapterConnected() ? STATUS_PASSED : STATUS_PARTIAL,
                simulationResult.isRuntimeAdapterConnected() ? "真实 runtime adapter 已接入。"
                        : "真实 Skill runtime adapter 尚未接入，只能给出 PARTIAL 判断。"));
    }

    private String resolveReportStatus(SkillFactoryPeerAgentRunResult runResult, SkillSimulationResult simulation) {
        if (StringUtils.isNotBlank(runResult.getErrorMessage()) || !runResult.isSimulateToolCalled()
                || !runResult.isSimulateToolSucceeded() || simulation == null) {
            return STATUS_FAILED;
        }
        if (StringUtils.equals(STATUS_FAILED, simulation.getStatus())) {
            return STATUS_FAILED;
        }
        if (StringUtils.equals(STATUS_PASSED, simulation.getStatus()) && simulation.isRuntimeAdapterConnected()) {
            return STATUS_PASSED;
        }
        return STATUS_PARTIAL;
    }

    private Map<String, Object> agentInvocationEvidence(String callerBizKey, SkillFactoryPeerAgentConfig calleeConfig,
            SkillFactoryPeerAgentRunResult runResult, String taskType, String expectedOutputType) {
        Map<String, Object> evidence = new HashMap<>();
        evidence.put("toolName", "invoke_agent");
        evidence.put("executionMode", EXECUTION_MODE_AGENT_ENGINE);
        evidence.put("callerBizKey", callerBizKey);
        evidence.put("calleeAlias", calleeConfig.getAlias());
        evidence.put("calleeBizKey", calleeConfig.getBizKey());
        evidence.put("calleeAgentId", calleeConfig.getAgentId());
        evidence.put("childSessionId", runResult.getChildSessionId());
        evidence.put("childRunId", runResult.getChildRunId());
        evidence.put("childCompleted", runResult.isCompleted());
        evidence.put("childErrorMessage", runResult.getErrorMessage());
        evidence.put("childFinalAnswer", StringUtils.abbreviate(StringUtils.defaultString(runResult.getFinalAnswer()),
                CHILD_FINAL_ANSWER_PREVIEW_LENGTH));
        evidence.put("childEventSummary", runResult.getChildEventSummary());
        evidence.put("taskType", taskType);
        evidence.put("expectedOutputType", expectedOutputType);
        evidence.put("requiredTools", calleeConfig.getRequiredTools());
        evidence.put("requiredToolEvidence", runResult.getRequiredToolEvidence());
        evidence.put("readOnly", calleeConfig.isReadOnly());
        evidence.put("noPatch", calleeConfig.isNoPatch());
        evidence.put("noWorkspaceWrite", calleeConfig.isNoWorkspaceWrite());
        evidence.put("noBusinessSideEffect", calleeConfig.isNoBusinessSideEffect());
        evidence.put("timeoutMs", calleeConfig.getTimeoutMs());
        evidence.put("costMs", runResult.getCostMs());
        return evidence;
    }

    private Map<String, Object> simulationEvidence(SkillFactoryPeerAgentRunResult runResult,
            SkillSimulationResult simulationResult) {
        Map<String, Object> evidence = new HashMap<>();
        evidence.put("toolName", SkillSimulationResult.TOOL_NAME);
        evidence.put("called", runResult.isSimulateToolCalled());
        evidence.put("success", runResult.isSimulateToolSucceeded());
        if (simulationResult != null) {
            evidence.put("simulationId", simulationResult.getSimulationId());
            evidence.put("status", simulationResult.getStatus());
            evidence.put("reason", simulationResult.getReason());
            evidence.put("runtimeAdapterConnected", simulationResult.isRuntimeAdapterConnected());
            evidence.put("fileTreeDigest", simulationResult.getFileTreeDigest());
            evidence.put("metadata", simulationResult.getMetadata());
        }
        return evidence;
    }

    private ValidationReport.Protocol detectProtocol(String rawOutput) {
        ValidationReport.Protocol protocol = new ValidationReport.Protocol()
                .setType(PROTOCOL_UNKNOWN)
                .setCode(StringUtils.EMPTY)
                .setPayload(rawOutput);
        if (StringUtils.isBlank(rawOutput)) {
            return protocol;
        }
        if (StringUtils.contains(rawOutput, PROTOCOL_AGENT_UI_DSL)) {
            return protocol.setType(PROTOCOL_AGENT_UI_DSL).setCode(PROTOCOL_AGENT_UI_DSL);
        }
        if (StringUtils.contains(rawOutput, PROTOCOL_COMPONENT_NAME)) {
            return protocol.setType(PROTOCOL_COMPONENT_NAME).setCode(PROTOCOL_COMPONENT_NAME);
        }
        if (StringUtils.contains(rawOutput, PROTOCOL_LOCAL_METHOD)) {
            return protocol.setType(PROTOCOL_LOCAL_METHOD).setCode(PROTOCOL_LOCAL_METHOD);
        }
        return protocol.setType(PROTOCOL_TEXT).setCode(PROTOCOL_TEXT);
    }

    private String resolveRawOutput(SkillSimulationResult simulationResult, SkillFactoryPeerAgentRunResult runResult) {
        return simulationResult == null ? StringUtils.defaultString(runResult.getFinalAnswer())
                                        : StringUtils.defaultIfBlank(simulationResult.getRawOutput(),
                                                runResult.getFinalAnswer());
    }

    private String resolveStdoutSummary(SkillSimulationResult simulationResult,
            SkillFactoryPeerAgentRunResult runResult) {
        if (simulationResult == null) {
            return StringUtils.abbreviate(StringUtils.defaultString(runResult.getFinalAnswer()), 1000);
        }
        return StringUtils.defaultIfBlank(simulationResult.getStdoutSummary(),
                StringUtils.abbreviate(StringUtils.defaultString(runResult.getFinalAnswer()), 1000));
    }

    private String buildRepairPrompt(ValidationReport report, SkillFactoryPeerAgentRunResult runResult) {
        return """
                ValidationReport Summary:
                - status: %s
                - protocol: %s
                - issues: %s
                - peerAgentFinalAnswer: %s
                - rawOutput: %s
                请基于上述动态验证报告修复当前 Skill，仅通过 propose_patch 生成补丁，禁止直接写文件。
                """.formatted(report.getStatus(), report.getProtocol().getType(),
                JsonSupport.toJSON(report.getIssues()),
                StringUtils.abbreviate(StringUtils.defaultString(runResult.getFinalAnswer()),
                        REPORT_PROMPT_PREVIEW_LENGTH),
                StringUtils.abbreviate(StringUtils.defaultString(report.getRawOutput()),
                        REPORT_PROMPT_PREVIEW_LENGTH));
    }

    private ValidationReport.CheckItem newCheck(String key, String label, String status, String message) {
        return new ValidationReport.CheckItem()
                .setKey(key)
                .setLabel(label)
                .setStatus(status)
                .setMessage(message);
    }

    private ValidationReport.Issue newIssue(String severity, String source, String message, String repairHint) {
        return new ValidationReport.Issue()
                .setSeverity(severity)
                .setSource(source)
                .setMessage(message)
                .setRepairHint(repairHint);
    }

    private String buildChildSessionId(SkillFactoryPeerAgentConfig calleeConfig, Map<String, String> delegateParams) {
        return "peer_" + StringUtils.defaultIfBlank(calleeConfig.getAlias(), "agent") + "_"
                + StringUtils.defaultIfBlank(delegateParams.get(FIELD_RUN_ID), "run") + "_"
                + UUID.randomUUID().toString().replace("-", "");
    }

    private String failedPayload(Map<String, String> callerParams, String errorMsg) {
        return aiCodingEventPayloadCodec.toJson(aiCodingEventPayloadFactory.failed(
                callerParams.get(FIELD_WORKSPACE_ID),
                callerParams.get(FIELD_SESSION_ID),
                null,
                callerParams.get(FIELD_TRACE_ID),
                errorMsg));
    }

    private String safeInputSummary(Map<String, Object> input) {
        Map<String, Object> summary = new HashMap<>();
        summary.put(FIELD_ALIAS, MapUtils.getString(input, FIELD_ALIAS));
        summary.put(FIELD_BIZ_KEY, MapUtils.getString(input, FIELD_BIZ_KEY));
        summary.put(FIELD_AGENT_ID, MapUtils.getString(input, FIELD_AGENT_ID));
        summary.put(FIELD_TASK_TYPE, MapUtils.getString(input, FIELD_TASK_TYPE));
        summary.put(FIELD_EXPECTED_OUTPUT_TYPE, MapUtils.getString(input, FIELD_EXPECTED_OUTPUT_TYPE));
        return JsonSupport.toJSON(summary);
    }

    private String firstTaskType(SkillFactoryPeerAgentConfig config) {
        List<String> taskTypes = config.getTaskTypes();
        return CollectionUtils.isEmpty(taskTypes) ? StringUtils.EMPTY : taskTypes.get(0);
    }

    private String firstNotBlank(Map<String, Object> input, String fieldName, String fallback) {
        Object value = input.get(fieldName);
        if (Objects.isNull(value)) {
            return fallback;
        }
        if (value instanceof String text) {
            return StringUtils.defaultIfBlank(text, fallback);
        }
        return JsonSupport.toJSON(value);
    }

    private void putString(Map<String, String> params, String key, String value) {
        if (StringUtils.isNotBlank(value)) {
            params.put(key, value);
        }
    }
}
