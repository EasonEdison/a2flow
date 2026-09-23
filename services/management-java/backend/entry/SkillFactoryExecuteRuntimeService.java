package dev.a2flow.management.entry;

import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.UUID;

import jakarta.annotation.Resource;

import org.apache.commons.collections4.MapUtils;
import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Component;

import com.google.common.collect.ImmutableSet;
import com.google.common.collect.Maps;
import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.access.AssetAction;
import dev.a2flow.management.access.AssetAuthorizationService;
import dev.a2flow.management.aicoding.AiCodingActionCodes;
import dev.a2flow.management.aicoding.SkillFactoryAiCodingService;
import dev.a2flow.management.aicoding.domain.SkillFactoryPatchApplyResult;
import dev.a2flow.management.authoring.session.AuthoringSessionService;
import dev.a2flow.management.event.AiCodingEventPayload;
import dev.a2flow.management.event.AiCodingEventPayloadCodec;
import dev.a2flow.management.event.AiCodingEventPayloadFactory;
import dev.a2flow.management.event.AiCodingStreamEvent;
import dev.a2flow.management.event.AiCodingStreamEventFactory;
import dev.a2flow.management.event.AiCodingStreamResponseConverter;
import dev.a2flow.management.lifecycle.SkillFactoryMethodDispatcher;
import dev.a2flow.management.model.SkillFactoryExecutionResult;
import dev.a2flow.management.protobuf.SkillFactoryChatResponse;
import dev.a2flow.management.release.ReleaseAssetType;

import lombok.extern.slf4j.Slf4j;

/**
 * SkillFactory 非流式运行时入口。
 *
 * <p>该类承接原 gateway RPC 中的 method 分流逻辑：AI Coding patch 确认/丢弃进入
 * `runtime/skillfactory/aicoding`，其他非 chat 方法继续委托既有 lifecycle dispatcher。
 * 它负责运行时编排、M 端 Patch 动作授权和结果 JSON 化，不负责 HTTP/KRPC 协议包装，也不实现
 * workspace/package/component-center 的具体业务逻辑。
 */
@Component
@Slf4j
public class SkillFactoryExecuteRuntimeService {

    private static final String PARAM_USER_NAME = "userName";
    private static final String PARAM_WORKSPACE_ID = "workspaceId";
    private static final String PARAM_SKILL_CODE = "skillCode";
    private static final String PARAM_SESSION_ID = "sessionId";
    private static final String PARAM_MESSAGE_ID = "messageId";
    private static final String PARAM_RUN_ID = "runId";
    private static final String PARAM_CONVERSATION_ID = "conversationId";
    private static final String PARAM_INVOKE_ID = "invokeId";
    private static final String PARAM_TRACE_ID = "traceId";
    private static final String PARAM_AGENT_ID = "agentId";
    private static final String PARAM_PATCH_ID = "patchId";
    private static final String PARAM_IDEMPOTENCY_KEY = "idempotencyKey";
    private static final String EVENT_ID_PREFIX = "evt_control_";
    private static final String PATCH_CONFIRM_CONTENT = "Patch 已应用";
    private static final String PATCH_DISCARD_CONTENT = "Patch 已丢弃";
    private static final String PATCH_FAILURE_CONTENT = "Patch 操作失败";
    private static final ImmutableSet<String> CODING_PATCH_METHODS = ImmutableSet.of(
            AiCodingActionCodes.CODING_PATCH_CONFIRM,
            AiCodingActionCodes.CODING_PATCH_DISCARD);

    @Resource
    private SkillFactoryMethodDispatcher methodDispatcher;

    @Resource
    private SkillFactoryAiCodingService aiCodingService;

    @Resource
    private AssetAuthorizationService assetAuthorizationService;

    @Resource
    private AiCodingEventPayloadFactory eventPayloadFactory;

    @Resource
    private AiCodingEventPayloadCodec eventPayloadCodec;

    @Resource
    private AiCodingStreamEventFactory streamEventFactory;

    @Resource
    private AiCodingStreamResponseConverter streamResponseConverter;

    @Resource
    private AuthoringSessionService authoringSessionService;

    /**
     * 执行 SkillFactory 非流式 method。
     *
     * <p>调用方必须传入已校验的 userName、method 和 params；本方法会补齐 userName 到 params
     * 并按 method 路由。日志只输出 method、workspaceId、traceId 等定位字段，不输出完整文件内容。
     */
    public SkillFactoryExecuteRuntimeResult execute(String userName, String method, Map<String, String> params,
            String traceId) {
        Map<String, String> safeParams = params == null ? Maps.newHashMap() : Maps.newHashMap(params);
        safeParams.put(PARAM_USER_NAME, userName);
        safeParams.put(PARAM_TRACE_ID, traceId);
        log.info("SkillFactoryExecuteRuntimeService开始执行非流式方法, userName:{}, method:{}, "
                        + "workspaceId:{}, traceId:{}",
                userName, method, safeParams.get(PARAM_WORKSPACE_ID), traceId);
        if (CODING_PATCH_METHODS.contains(method)) {
            return executeCodingPatchMethod(method, safeParams, traceId);
        }
        SkillFactoryExecutionResult result = methodDispatcher.execute(userName, method, safeParams);
        if (!result.isSuccess()) {
            log.warn("SkillFactoryExecuteRuntimeService方法执行失败, userName:{}, method:{}, workspaceId:{}, "
                            + "traceId:{}, errorMsg:{}",
                    userName, method, safeParams.get(PARAM_WORKSPACE_ID), traceId, result.getErrorMsg());
            return SkillFactoryExecuteRuntimeResult.fail(result.getErrorMsg(),
                    result.getData() == null ? null : JsonSupport.toJSON(result.getData()));
        }
        log.info("SkillFactoryExecuteRuntimeService方法执行成功, userName:{}, method:{}, workspaceId:{}, "
                        + "traceId:{}, isList:{}",
                userName, method, safeParams.get(PARAM_WORKSPACE_ID), traceId, result.isList());
        return SkillFactoryExecuteRuntimeResult.success(JsonSupport.toJSON(result.getData()), result.isList());
    }

    private SkillFactoryExecuteRuntimeResult executeCodingPatchMethod(String method, Map<String, String> params,
            String traceId) {
        String skillCode = StringUtils.defaultIfBlank(
                params.get(PARAM_SKILL_CODE), params.get(PARAM_WORKSPACE_ID));
        log.info("SkillFactoryExecuteRuntimeService执行M端Patch权限校验, userName:{}, method:{}, "
                        + "skillCode:{}, traceId:{}",
                params.get(PARAM_USER_NAME), method, skillCode, traceId);
        assetAuthorizationService.requirePermission(
                params.get(PARAM_USER_NAME), ReleaseAssetType.SKILL, skillCode, AssetAction.EDIT);
        log.info("SkillFactoryExecuteRuntimeService执行AI Coding patch方法, method:{}, workspaceId:{}, traceId:{}",
                method, params.get(PARAM_WORKSPACE_ID), traceId);
        SkillFactoryPatchApplyResult result;
        if (AiCodingActionCodes.CODING_PATCH_CONFIRM.equals(method)) {
            result = aiCodingService.confirmPatch(params);
        } else {
            result = aiCodingService.discardPatch(params);
        }
        appendPatchActionEvent(method, params, result, traceId);
        if (!result.isSuccess()) {
            log.warn("SkillFactoryExecuteRuntimeService AI Coding patch方法失败, method:{}, workspaceId:{}, "
                            + "patchId:{}, traceId:{}, errorMsg:{}",
                    method, result.getWorkspaceId(), result.getPatchId(), traceId, result.getErrorMsg());
            return SkillFactoryExecuteRuntimeResult.fail(result.getErrorMsg());
        }
        log.info("SkillFactoryExecuteRuntimeService AI Coding patch方法成功, method:{}, workspaceId:{}, "
                        + "patchId:{}, traceId:{}",
                method, result.getWorkspaceId(), result.getPatchId(), traceId);
        return SkillFactoryExecuteRuntimeResult.success(JsonSupport.toJSON(result), false);
    }

    /**
     * 把 handler Patch 动作投影到 Authoring 历史。
     *
     * <p>该路径不追加用户消息、不创建 RUN_STARTED/RUN_COMPLETED，也不执行模型；它只复用标准领域 payload
     * 和事件仓储记录应用、丢弃、冲突或失败结果。模型在下一轮通过 AI Coding Service 已写入的
     * HumanDecision/Observation 感知该动作。
     */
    private void appendPatchActionEvent(String method, Map<String, String> params,
            SkillFactoryPatchApplyResult result, String traceId) {
        AiCodingEventPayload payload = buildPatchActionPayload(method, params, result, traceId);
        String payloadJson = eventPayloadCodec.toJson(payload);
        boolean success = result.isSuccess();
        String content = success
                ? (AiCodingActionCodes.CODING_PATCH_DISCARD.equals(method)
                        ? PATCH_DISCARD_CONTENT : PATCH_CONFIRM_CONTENT)
                : PATCH_FAILURE_CONTENT;
        long agentId = MapUtils.getLongValue(params, PARAM_AGENT_ID);
        AiCodingStreamEvent event = streamEventFactory.controlDomainResult(
                agentId, params, AiCodingStreamEventFactory.PAYLOAD_PATCH_ARTIFACT,
                payloadJson, content, success);
        String invokeId = StringUtils.defaultIfBlank(
                MapUtils.getString(params, PARAM_INVOKE_ID),
                MapUtils.getString(params, PARAM_MESSAGE_ID));
        SkillFactoryChatResponse response = streamResponseConverter.convert(event, invokeId)
                .toBuilder()
                .setEventId(stableControlEventId(method, params))
                .build();
        authoringSessionService.appendControlEvent(params, response);
        log.info("SkillFactoryExecuteRuntimeService已记录Patch控制面事件, method:{}, sessionId:{}, "
                        + "invokeId:{}, patchId:{}, eventType:{}, traceId:{}",
                method, MapUtils.getString(params, PARAM_SESSION_ID), invokeId, result.getPatchId(),
                response.getEventType(), traceId);
    }

    private AiCodingEventPayload buildPatchActionPayload(String method, Map<String, String> params,
            SkillFactoryPatchApplyResult result, String traceId) {
        String sessionId = MapUtils.getString(params, PARAM_SESSION_ID);
        AiCodingEventPayload payload;
        if (!result.isSuccess()) {
            payload = StringUtils.isNotBlank(result.getErrorCode())
                    ? eventPayloadFactory.patchConflict(result, sessionId, traceId)
                    : eventPayloadFactory.failed(result.getWorkspaceId(), sessionId, result.getPatchId(),
                            traceId, result.getErrorMsg());
        } else if (AiCodingActionCodes.CODING_PATCH_DISCARD.equals(method)) {
            payload = eventPayloadFactory.patchDiscarded(result, sessionId, traceId, null);
        } else {
            payload = eventPayloadFactory.patchApplied(result, sessionId, traceId, null, false);
        }
        return payload
                .setMessageId(MapUtils.getString(params, PARAM_MESSAGE_ID))
                .setRunId(MapUtils.getString(params, PARAM_RUN_ID))
                .setThreadId(sessionId)
                .setConversationId(StringUtils.defaultIfBlank(
                        MapUtils.getString(params, PARAM_CONVERSATION_ID), sessionId));
    }

    private String stableControlEventId(String method, Map<String, String> params) {
        String identity = String.join("|",
                StringUtils.defaultString(method),
                MapUtils.getString(params, PARAM_PATCH_ID, StringUtils.EMPTY),
                MapUtils.getString(params, PARAM_IDEMPOTENCY_KEY, StringUtils.EMPTY));
        return EVENT_ID_PREFIX + UUID.nameUUIDFromBytes(identity.getBytes(StandardCharsets.UTF_8))
                .toString().replace("-", "");
    }
}
