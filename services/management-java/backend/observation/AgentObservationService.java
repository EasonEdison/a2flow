package dev.a2flow.management.observation;

import java.time.Instant;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.stream.Collectors;

import jakarta.annotation.Resource;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.agentcore.enums.DeletedEnum;
import dev.a2flow.management.storage.db.entity.AgentObservationEventDO;
import dev.a2flow.management.storage.db.repository.AgentObservationEventRepository;

import lombok.extern.slf4j.Slf4j;

/**
 * Agent observation 领域服务。
 *
 * <p>该服务负责把人类决策、命令执行结果和后续工具结果沉淀成可审计、可注入模型上下文的
 * observation。它只做 observation 规范化和读写，不执行 UI command、不调用模型、不保存大文件正文。
 */
@SuppressWarnings("checkstyle:ParameterNumber")
@Service
@Slf4j
public class AgentObservationService {

    private static final String ID_PREFIX_OBSERVATION = "obs_";
    private static final int VISIBLE_TO_MODEL = 1;
    private static final int HIDDEN_FROM_MODEL = 0;

    @Resource
    private AgentObservationEventRepository observationEventRepository;

    /**
     * 新增 observation 事件。
     */
    public AgentObservationEventDO appendObservation(String bizKey, String runId, String threadId,
            String conversationId, String sessionId, String workspaceId, String observationType, String source,
            String summary, Map<String, Object> stateDelta, boolean visibleToModel, String operator,
            String traceId) {
        return appendObservationInternal(bizKey, runId, threadId, conversationId, sessionId, workspaceId,
                observationType, source, summary, stateDelta, visibleToModel, operator, traceId, null);
    }

    private AgentObservationEventDO appendObservationInternal(String bizKey, String runId, String threadId,
            String conversationId, String sessionId, String workspaceId, String observationType, String source,
            String summary, Map<String, Object> stateDelta, boolean visibleToModel, String operator,
            String traceId, String idempotencyKey) {
        long now = System.currentTimeMillis();
        AgentObservationEventDO eventDO = new AgentObservationEventDO()
                .setObservationId(ID_PREFIX_OBSERVATION + UUID.randomUUID().toString().replace("-", ""))
                .setBizKey(bizKey)
                .setRunId(runId)
                .setThreadId(threadId)
                .setConversationId(conversationId)
                .setSessionId(sessionId)
                .setWorkspaceId(workspaceId)
                .setObservationType(observationType)
                .setSource(source)
                .setIdempotencyKey(StringUtils.trimToNull(idempotencyKey))
                .setSummary(StringUtils.defaultString(summary))
                .setStateDeltaJson(JsonSupport.toJSON(
                        stateDelta == null ? Collections.emptyMap() : stateDelta))
                .setVisibleToModel(visibleToModel ? VISIBLE_TO_MODEL : HIDDEN_FROM_MODEL)
                .setOperator(operator)
                .setTraceId(traceId)
                .setDeleted(DeletedEnum.VALID.getCode())
                .setCreateTime(now)
                .setUpdateTime(now);
        log.info("Agent observation服务准备写入, observationId={}, bizKey={}, threadId={}, type={}, "
                        + "source={}, visibleToModel={}",
                eventDO.getObservationId(), bizKey, threadId, observationType, source, visibleToModel);
        return observationEventRepository.insert(eventDO);
    }

    /**
     * 幂等新增 observation 事件。
     *
     * <p>该方法用于 M 端 A2UI action 这类用户可能重复点击的控制面动作。幂等键只参与去重和审计，
     * 不改变 observation 的业务语义，也不会把原始前端组件树注入模型上下文。
     */
    public AgentObservationEventDO appendObservationOnce(String bizKey, String runId, String threadId,
            String conversationId, String sessionId, String workspaceId, String observationType, String source,
            String summary, Map<String, Object> stateDelta, boolean visibleToModel, String operator,
            String traceId, String idempotencyKey) {
        if (StringUtils.isNotBlank(idempotencyKey)) {
            AgentObservationEventDO existing =
                    observationEventRepository.findByDedupeKey(bizKey, threadId, source, idempotencyKey);
            if (existing != null) {
                log.info("Agent observation幂等命中，复用已有记录, observationId={}, bizKey={}, threadId={}, "
                                + "source={}",
                        existing.getObservationId(), bizKey, threadId, source);
                return existing;
            }
        }
        return appendObservationInternal(bizKey, runId, threadId, conversationId, sessionId, workspaceId,
                observationType, source, summary, stateDelta, visibleToModel, operator, traceId,
                idempotencyKey);
    }

    /**
     * 查询最近可注入模型的 observation 文本摘要。
     */
    public List<String> listRecentVisibleSummaries(String bizKey, String threadId, int limit) {
        List<AgentObservationEventDO> events = observationEventRepository.listRecentVisible(bizKey, threadId, limit);
        Collections.reverse(events);
        return events.stream()
                .filter(event -> StringUtils.isNotBlank(event.getSummary()))
                .map(this::modelVisibleSummary)
                .collect(Collectors.toList());
    }

    /**
     * 为模型可见 observation 添加发生时间和稳定事件顺序。
     */
    private String modelVisibleSummary(AgentObservationEventDO eventDO) {
        long occurredAtEpochMs = eventDO.getCreateTime() == null ? 0L : eventDO.getCreateTime();
        String occurredAt = occurredAtEpochMs > 0
                            ? Instant.ofEpochMilli(occurredAtEpochMs).toString() : "unknown";
        return "occurredAt=" + occurredAt
                + ", occurredAtEpochMs=" + occurredAtEpochMs
                + ", eventSequence=" + (eventDO.getId() == null ? "unknown" : eventDO.getId())
                + ", observationType=" + StringUtils.defaultString(eventDO.getObservationType())
                + ", source=" + StringUtils.defaultString(eventDO.getSource())
                + ", fact=" + eventDO.getSummary();
    }

    /**
     * 查询指定类型的最新 observation。
     */
    public AgentObservationEventDO findLatestByType(String bizKey, String threadId, String workspaceId,
            String observationType, String source) {
        AgentObservationEventDO eventDO = observationEventRepository.findLatestByType(
                bizKey, threadId, workspaceId, observationType, source);
        log.info("Agent observation服务查询最新类型完成, bizKey={}, threadId={}, workspaceId={}, type={}, "
                        + "source={}, found={}",
                bizKey, threadId, workspaceId, observationType, source, eventDO != null);
        return eventDO;
    }
}
