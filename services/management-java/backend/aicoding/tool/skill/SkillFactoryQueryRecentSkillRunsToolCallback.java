package dev.a2flow.management.aicoding.tool.skill;

import java.util.Map;
import java.util.Set;

import jakarta.annotation.Resource;

import org.springframework.ai.tool.ToolCallback;
import org.springframework.ai.tool.definition.ToolDefinition;
import org.springframework.stereotype.Component;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.agentcore.runtime.tool.ToolException;


/**
 * 通用 Skill 运行记录列表查询 Tool。
 *
 * <p>模型显式提供时间范围、分页和任意 Adviser Lab 过滤条件；本 Tool 不读取当前 workspace 的
 * skillCode，不做 seller/Skill 归属校验，也不自动翻页或拉取详情。下游每次只执行一次只读 KRPC 查询。
 */
@Component
public class SkillFactoryQueryRecentSkillRunsToolCallback implements ToolCallback {

    public static final String TOOL_NAME = "query_recent_skill_runs";

    private static final String FIELD_START_TIME = "startTime";
    private static final String FIELD_END_TIME = "endTime";
    private static final String FIELD_SELLER_ID = "sellerId";
    private static final String FIELD_USER_ID = "userId";
    private static final String FIELD_CONVERSATION_ID = "conversationId";
    private static final String FIELD_MESSAGE_ID = "messageId";
    private static final String FIELD_BIZ_IDENTIFY_ID = "bizIdentifyId";
    private static final String FIELD_AGENT_ID = "agentId";
    private static final String FIELD_SKILL_CODE = "skillCode";
    private static final String FIELD_SKILL_KEYWORD = "skillKeyword";
    private static final String FIELD_RUN_STATUS = "runStatus";
    private static final String FIELD_PAGE = "page";
    private static final String FIELD_PAGE_SIZE = "pageSize";
    private static final String FIELD_SORT_FIELD = "sortField";
    private static final String FIELD_SORT_ORDER = "sortOrder";
    private static final int DEFAULT_PAGE = 1;
    private static final int DEFAULT_PAGE_SIZE = 20;
    private static final int MAX_PAGE = Integer.MAX_VALUE;
    private static final int MAX_PAGE_SIZE = 100;
    private static final long MAX_TIME_RANGE_MILLIS = 7L * 24 * 60 * 60 * 1000;
    private static final Set<String> RUN_STATUSES = Set.of("SUCCESS", "FAIL", "TIMEOUT");
    private static final Set<String> SORT_FIELDS = Set.of("TOTAL_TOKEN_COUNT", "DURATION_MS");
    private static final Set<String> SORT_ORDERS = Set.of("ASC", "DESC");
    private static final String ERROR_END_TIME_ORDER =
            "endTime must be greater than or equal to startTime";
    private static final String ERROR_TIME_RANGE = "time range must not exceed 7 days";
    private static final Set<String> ALLOWED_FIELDS = Set.of(
            FIELD_START_TIME, FIELD_END_TIME, FIELD_SELLER_ID, FIELD_USER_ID, FIELD_CONVERSATION_ID,
            FIELD_MESSAGE_ID, FIELD_BIZ_IDENTIFY_ID, FIELD_AGENT_ID, FIELD_SKILL_CODE, FIELD_SKILL_KEYWORD,
            FIELD_RUN_STATUS, FIELD_PAGE, FIELD_PAGE_SIZE, FIELD_SORT_FIELD, FIELD_SORT_ORDER);
    private static final String TOOL_DESCRIPTION =
            "Query one read-only page of Skill runtime messages from Adviser Lab. startTime and endTime are required "
                    + "epoch milliseconds and may span at most 7 days. Optional filters include sellerId, userId, "
                    + "conversationId, messageId, bizIdentifyId, agentId, skillCode, skillKeyword and runStatus. "
                    + "skillCode must describe the diagnosis target; it is not inferred from the current workspace. "
                    + "pageSize is at most 100. For 200 runs, call pages 1 and 2 yourself. Use returned messageId and "
                    + "agentId together when calling query_skill_run_detail.";
    private static final String INPUT_SCHEMA = """
            {
              "type": "object",
              "properties": {
                "startTime": {"type": "integer", "minimum": 1, "description": "Start epoch milliseconds"},
                "endTime": {"type": "integer", "minimum": 1, "description": "End epoch milliseconds"},
                "sellerId": {"type": "integer", "minimum": 1},
                "userId": {"type": "string"},
                "conversationId": {"type": "string"},
                "messageId": {"type": "string"},
                "bizIdentifyId": {"type": "string"},
                "agentId": {"type": "integer", "minimum": 1},
                "skillCode": {"type": "string", "description": "Exact diagnosis target skillCode"},
                "skillKeyword": {"type": "string", "description": "Fuzzy Skill name or code keyword"},
                "runStatus": {"type": "string", "enum": ["SUCCESS", "FAIL", "TIMEOUT"]},
                "page": {"type": "integer", "minimum": 1, "default": 1},
                "pageSize": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
                "sortField": {"type": "string", "enum": ["TOTAL_TOKEN_COUNT", "DURATION_MS"]},
                "sortOrder": {"type": "string", "enum": ["ASC", "DESC"]}
              },
              "required": ["startTime", "endTime"],
              "additionalProperties": false
            }
            """;

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

    /** 映射显式过滤条件并查询一页运行记录。 */
    @Override
    public String call(String toolInput) {
        Map<String, Object> input = SkillFactoryLabToolInputSupport.parseObject(toolInput, ALLOWED_FIELDS);
        long startTime = SkillFactoryLabToolInputSupport.requiredPositiveLong(input, FIELD_START_TIME);
        long endTime = SkillFactoryLabToolInputSupport.requiredPositiveLong(input, FIELD_END_TIME);
        validateTimeRange(startTime, endTime);

        QueryLabMessageListRequest.Builder builder = QueryLabMessageListRequest.newBuilder()
                .setStartTime(startTime)
                .setEndTime(endTime)
                .setPage(SkillFactoryLabToolInputSupport.positiveInt(
                        input, FIELD_PAGE, DEFAULT_PAGE, MAX_PAGE))
                .setPageSize(SkillFactoryLabToolInputSupport.positiveInt(
                        input, FIELD_PAGE_SIZE, DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE));
        Long sellerId = SkillFactoryLabToolInputSupport.optionalPositiveLong(input, FIELD_SELLER_ID);
        if (sellerId != null) {
            builder.setSellerId(sellerId);
        }
        Long agentId = SkillFactoryLabToolInputSupport.optionalPositiveLong(input, FIELD_AGENT_ID);
        if (agentId != null) {
            builder.setAgentId(agentId);
        }
        setOptionalStrings(builder, input);
        return JsonSupport.toJSON(labRuntimeQueryClient.queryRecentSkillRuns(builder.build()));
    }

    private void validateTimeRange(long startTime, long endTime) {
        if (endTime < startTime) {
            throw new ToolException(ERROR_END_TIME_ORDER, ToolException.ErrorCode.INVALID_PARAMS);
        }
        if (endTime - startTime > MAX_TIME_RANGE_MILLIS) {
            throw new ToolException(ERROR_TIME_RANGE, ToolException.ErrorCode.INVALID_PARAMS);
        }
    }

    private void setOptionalStrings(QueryLabMessageListRequest.Builder builder, Map<String, Object> input) {
        setIfPresent(input, FIELD_USER_ID, builder::setUserId);
        setIfPresent(input, FIELD_CONVERSATION_ID, builder::setConversationId);
        setIfPresent(input, FIELD_MESSAGE_ID, builder::setMessageId);
        setIfPresent(input, FIELD_BIZ_IDENTIFY_ID, builder::setBizIdentifyId);
        setIfPresent(input, FIELD_SKILL_CODE, builder::setSkillCode);
        setIfPresent(input, FIELD_SKILL_KEYWORD, builder::setSkillKeyword);
        setIfPresent(SkillFactoryLabToolInputSupport.optionalEnum(input, FIELD_RUN_STATUS, RUN_STATUSES),
                builder::setRunStatus);
        setIfPresent(SkillFactoryLabToolInputSupport.optionalEnum(input, FIELD_SORT_FIELD, SORT_FIELDS),
                builder::setSortField);
        setIfPresent(SkillFactoryLabToolInputSupport.optionalEnum(input, FIELD_SORT_ORDER, SORT_ORDERS),
                builder::setSortOrder);
    }

    private void setIfPresent(Map<String, Object> input, String field,
            java.util.function.Consumer<String> setter) {
        setIfPresent(SkillFactoryLabToolInputSupport.optionalString(input, field), setter);
    }

    private void setIfPresent(String value, java.util.function.Consumer<String> setter) {
        if (value != null) {
            setter.accept(value);
        }
    }
}
