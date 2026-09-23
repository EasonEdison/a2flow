package dev.a2flow.management.aicoding.tool.skill;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.stream.Collectors;

import jakarta.annotation.Resource;

import org.apache.commons.lang3.StringUtils;
import org.springframework.ai.tool.ToolCallback;
import org.springframework.ai.tool.definition.ToolDefinition;
import org.springframework.stereotype.Component;

import dev.a2flow.management.support.BoundedExecutors;
import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.agentcore.runtime.tool.ToolException;

import lombok.extern.slf4j.Slf4j;

/**
 * Skill 运行链路详情批量查询 Tool。
 *
 * <p>上游模型提交一批由运行列表返回的 messageId 与分表键 agentId，本 Tool 完整校验后去重，并通过
 * 项目统一动态线程池受控并发调用现有单条 Adviser Lab KRPC。它保留首次出现顺序和每项独立结果，
 * 不增加 sellerId/skillCode 归属校验，不自动翻页、不重试，也不引入备用传输。
 */
@Slf4j
@Component
public class SkillFactoryQuerySkillRunDetailToolCallback implements ToolCallback {

    public static final String TOOL_NAME = "query_skill_run_detail";

    private static final String FIELD_RUNS = "runs";
    private static final String FIELD_MESSAGE_ID = "messageId";
    private static final String FIELD_AGENT_ID = "agentId";
    private static final String FIELD_REQUESTED_COUNT = "requestedCount";
    private static final String FIELD_UNIQUE_COUNT = "uniqueCount";
    private static final String FIELD_SUCCESS_COUNT = "successCount";
    private static final String FIELD_FAILURE_COUNT = "failureCount";
    private static final String FIELD_ITEMS = "items";
    private static final String FIELD_SUCCESS = "success";
    private static final String FIELD_DETAIL = "detail";
    private static final String FIELD_ERROR_MESSAGE = "errorMessage";
    private static final int MAX_BATCH_SIZE = 20;
    private static final int MAX_CONCURRENT_QUERIES = 4;
    private static final int MAX_ERROR_MESSAGE_LENGTH = 500;
    private static final Set<String> ALLOWED_FIELDS = Set.of(FIELD_RUNS);
    private static final Set<String> RUN_ALLOWED_FIELDS = Set.of(FIELD_MESSAGE_ID, FIELD_AGENT_ID);
    private static final String ERROR_RUNS_REQUIRED = "runs is required and must be an array";
    private static final String ERROR_RUNS_SIZE = "runs must contain between 1 and " + MAX_BATCH_SIZE + " items";
    private static final String ERROR_RUN_ITEM_OBJECT = "runs[%d] must be a JSON object";
    private static final String ERROR_RUN_ITEM_FIELDS = "runs[%d] contains unsupported fields";
    private static final String ERROR_RUN_MESSAGE_ID = "runs[%d].messageId is required";
    private static final String ERROR_RUN_AGENT_ID = "runs[%d].agentId is invalid";
    private static final String ERROR_UNKNOWN = "unknown error";
    private static final String TOOL_DESCRIPTION =
            "Read a bounded batch of Skill runtime traces from Adviser Lab. runs must contain 1 to 20 entries; each "
                    + "entry requires messageId and the partition agentId returned by query_recent_skill_runs. "
                    + "Duplicate pairs are queried once in first-occurrence order. Up to four single-detail KRPC "
                    + "calls run concurrently, and ordered per-item success or failure is returned without retry.";
    private static final String INPUT_SCHEMA = """
            {
              "type": "object",
              "properties": {
                "runs": {
                  "type": "array",
                  "minItems": 1,
                  "maxItems": 20,
                  "items": {
                    "type": "object",
                    "properties": {
                      "messageId": {"type": "string", "description": "Message ID returned by the list tool"},
                      "agentId": {
                        "type": "integer",
                        "minimum": 1,
                        "description": "Partition agentId returned by the same list row"
                      }
                    },
                    "required": ["messageId", "agentId"],
                    "additionalProperties": false
                  }
                }
              },
              "required": ["runs"],
              "additionalProperties": false
            }
            """;
    private static final ExecutorService DETAIL_QUERY_EXECUTOR =
            BoundedExecutors.fixed( MAX_CONCURRENT_QUERIES,
                    "skill-factory-run-detail-query-%d");

    @Resource
    private SkillFactoryLabRuntimeQueryClient labRuntimeQueryClient;

    @Override
    public ToolDefinition getToolDefinition() {
        return ToolDefinition.builder()
                .name(TOOL_NAME)
                .description(TOOL_DESCRIPTION)
                .inputSchema(INPUT_SCHEMA)
                .build();
    }

    /** 校验运行键批次，并受控并发查询每条运行链路。 */
    @Override
    public String call(String toolInput) {
        Map<String, Object> input = SkillFactoryLabToolInputSupport.parseObject(toolInput, ALLOWED_FIELDS);
        List<?> rawRuns = requiredRuns(input);
        List<RunKey> runKeys = parseUniqueRunKeys(rawRuns);
        long startTime = System.currentTimeMillis();
        log.info("Skill运行详情批量Tool开始, requestedCount={}, uniqueCount={}, maxConcurrency={}",
                rawRuns.size(), runKeys.size(), MAX_CONCURRENT_QUERIES);

        List<CompletableFuture<Map<String, Object>>> futures = runKeys.stream()
                .map(runKey -> CompletableFuture.supplyAsync(() -> queryOne(runKey), DETAIL_QUERY_EXECUTOR))
                .collect(Collectors.toList());
        List<Map<String, Object>> items = futures.stream()
                .map(CompletableFuture::join)
                .collect(Collectors.toList());
        int successCount = (int) items.stream()
                .filter(item -> Boolean.TRUE.equals(item.get(FIELD_SUCCESS)))
                .count();

        Map<String, Object> result = new LinkedHashMap<>();
        result.put(FIELD_REQUESTED_COUNT, rawRuns.size());
        result.put(FIELD_UNIQUE_COUNT, runKeys.size());
        result.put(FIELD_SUCCESS_COUNT, successCount);
        result.put(FIELD_FAILURE_COUNT, runKeys.size() - successCount);
        result.put(FIELD_ITEMS, items);
        log.info("Skill运行详情批量Tool完成, requestedCount={}, uniqueCount={}, successCount={}, "
                        + "failureCount={}, costMs={}",
                rawRuns.size(), runKeys.size(), successCount, runKeys.size() - successCount,
                System.currentTimeMillis() - startTime);
        return JsonSupport.toJSON(result);
    }

    private List<?> requiredRuns(Map<String, Object> input) {
        Object rawRuns = input.get(FIELD_RUNS);
        if (!(rawRuns instanceof List<?>)) {
            throw new ToolException(ERROR_RUNS_REQUIRED, ToolException.ErrorCode.INVALID_PARAMS);
        }
        List<?> runs = (List<?>) rawRuns;
        if (runs.isEmpty() || runs.size() > MAX_BATCH_SIZE) {
            throw new ToolException(ERROR_RUNS_SIZE, ToolException.ErrorCode.INVALID_PARAMS);
        }
        return runs;
    }

    private List<RunKey> parseUniqueRunKeys(List<?> rawRuns) {
        Set<RunKey> uniqueRunKeys = new LinkedHashSet<>();
        for (int index = 0; index < rawRuns.size(); index++) {
            uniqueRunKeys.add(parseRunKey(rawRuns.get(index), index));
        }
        return new ArrayList<>(uniqueRunKeys);
    }

    private RunKey parseRunKey(Object rawRun, int index) {
        if (!(rawRun instanceof Map<?, ?>)) {
            throw invalid(String.format(ERROR_RUN_ITEM_OBJECT, index));
        }
        Map<String, Object> run = stringKeyMap((Map<?, ?>) rawRun, index);
        if (!RUN_ALLOWED_FIELDS.containsAll(run.keySet())) {
            throw invalid(String.format(ERROR_RUN_ITEM_FIELDS, index));
        }
        String messageId = SkillFactoryLabToolInputSupport.optionalString(run, FIELD_MESSAGE_ID);
        if (StringUtils.isBlank(messageId)) {
            throw invalid(String.format(ERROR_RUN_MESSAGE_ID, index));
        }
        try {
            return new RunKey(messageId,
                    SkillFactoryLabToolInputSupport.requiredPositiveLong(run, FIELD_AGENT_ID));
        } catch (ToolException e) {
            throw new ToolException(String.format(ERROR_RUN_AGENT_ID, index), e,
                    ToolException.ErrorCode.INVALID_PARAMS);
        }
    }

    private Map<String, Object> stringKeyMap(Map<?, ?> rawRun, int index) {
        Map<String, Object> run = new LinkedHashMap<>();
        for (Map.Entry<?, ?> entry : rawRun.entrySet()) {
            if (!(entry.getKey() instanceof String)) {
                throw invalid(String.format(ERROR_RUN_ITEM_FIELDS, index));
            }
            run.put((String) entry.getKey(), entry.getValue());
        }
        return run;
    }

    private Map<String, Object> queryOne(RunKey runKey) {
        Map<String, Object> item = new LinkedHashMap<>();
        item.put(FIELD_MESSAGE_ID, runKey.messageId);
        item.put(FIELD_AGENT_ID, runKey.agentId);
        QueryLabTraceDetailRequest request = QueryLabTraceDetailRequest.newBuilder()
                .setMessageId(runKey.messageId)
                .setAgentId(runKey.agentId)
                .build();
        try {
            item.put(FIELD_SUCCESS, true);
            item.put(FIELD_DETAIL, labRuntimeQueryClient.querySkillRunDetail(request));
        } catch (Exception e) {
            String errorMessage = safeErrorMessage(e);
            log.warn("Skill运行详情批量Tool单项失败, messageId={}, agentId={}, errorMessage={}",
                    runKey.messageId, runKey.agentId, errorMessage);
            item.put(FIELD_SUCCESS, false);
            item.put(FIELD_ERROR_MESSAGE, errorMessage);
        }
        return item;
    }

    private String safeErrorMessage(Exception exception) {
        String normalized = StringUtils.defaultIfBlank(exception.getMessage(), ERROR_UNKNOWN)
                .replace('\n', ' ')
                .replace('\r', ' ');
        return StringUtils.abbreviate(normalized, MAX_ERROR_MESSAGE_LENGTH);
    }

    private ToolException invalid(String message) {
        return new ToolException(message, ToolException.ErrorCode.INVALID_PARAMS);
    }

    private static final class RunKey {
        private final String messageId;
        private final long agentId;

        private RunKey(String messageId, long agentId) {
            this.messageId = messageId;
            this.agentId = agentId;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof RunKey)) {
                return false;
            }
            RunKey runKey = (RunKey) other;
            return agentId == runKey.agentId && Objects.equals(messageId, runKey.messageId);
        }

        @Override
        public int hashCode() {
            return Objects.hash(messageId, agentId);
        }
    }
}
