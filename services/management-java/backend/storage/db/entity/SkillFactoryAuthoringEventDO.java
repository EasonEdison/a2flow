package dev.a2flow.management.storage.db.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * SkillFactory Authoring Chat 结构化流式事件数据对象。
 *
 * <p>该 DO 按结构化协议字段持久化模型内容、运行态 payload 和工具信息，不把整条事件压成无法查询的
 * content 黑盒。recordId 是实时事件与历史回放稳定合并的幂等身份。
 */
@Data
@Accessors(chain = true)
@TableName("skill_factory_authoring_event")
public class SkillFactoryAuthoringEventDO {

    @TableId(value = "id", type = IdType.AUTO)
    private Long id;

    @TableField("record_id")
    private String recordId;

    @TableField("session_id")
    private String sessionId;

    @TableField("schema_version")
    private String schemaVersion;

    @TableField("event_type")
    private String eventType;

    @TableField("event_id")
    private String eventId;

    @TableField("block_id")
    private String blockId;

    @TableField("\"source\"")
    private String source;

    @TableField("workspace_id")
    private String workspaceId;

    @TableField("invoke_id")
    private String invokeId;

    @TableField("message_id")
    private String messageId;

    @TableField("run_id")
    private String runId;

    @TableField("conversation_id")
    private String conversationId;

    @TableField("thread_id")
    private String threadId;

    @TableField("trace_id")
    private String traceId;

    @TableField("model_content_block_json")
    private String modelContentBlockJson;

    @TableField("payload_type")
    private String payloadType;

    @TableField("payload_json")
    private String payloadJson;

    @TableField("\"content\"")
    private String content;

    @TableField("tool_call_id")
    private String toolCallId;

    @TableField("tool_name")
    private String toolName;

    @TableField("tool_args")
    private String toolArgs;

    @TableField("tool_success")
    private Integer toolSuccess;

    @TableField("token_count")
    private Long tokenCount;

    @TableField("enter_token_count")
    private Long enterTokenCount;

    @TableField("output_token_count")
    private Long outputTokenCount;

    @TableField("has_knowledge")
    private Integer hasKnowledge;

    @TableField("\"timestamp\"")
    private Long timestamp;

    @TableField("answer_agent_id")
    private Long answerAgentId;

    @TableField("\"attribute\"")
    private String attribute;

    @TableField("deleted")
    private Integer deleted;

    @TableField("create_time")
    private Long createTime;

    @TableField("update_time")
    private Long updateTime;
}
