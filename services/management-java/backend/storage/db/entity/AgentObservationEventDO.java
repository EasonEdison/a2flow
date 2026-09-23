package dev.a2flow.management.storage.db.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * Agent observation 事件数据对象。
 *
 * <p>该 DO 是人类审批、确定性命令结果、工具结果等外部事实进入 agent 上下文的分布式事件日志。
 * 上游由 Agent Engine、命令处理器或审批服务写入，下游由模型上下文组装和链路透视读取。它只保存
 * 语义摘要和脱敏后的 stateDelta，不保存完整工具原文、cookie、token 或大文件正文。
 */
@Data
@Accessors(chain = true)
@TableName("agent_observation_event")
public class AgentObservationEventDO {

    /**
     * 主键。
     */
    @TableId(value = "id", type = IdType.AUTO)
    private Long id;

    /**
     * observation 唯一标识。
     */
    @TableField("observation_id")
    private String observationId;

    /**
     * 业务域标识，例如 HADES_SKILL_FACTORY。
     */
    @TableField("biz_key")
    private String bizKey;

    /**
     * 一次 agent 运行标识。
     */
    @TableField("run_id")
    private String runId;

    /**
     * 可恢复线程标识。
     */
    @TableField("thread_id")
    private String threadId;

    /**
     * Agent runtime conversationId。
     */
    @TableField("conversation_id")
    private String conversationId;

    /**
     * 业务 coding sessionId。
     */
    @TableField("session_id")
    private String sessionId;

    /**
     * 业务工作区标识。
     */
    @TableField("workspace_id")
    private String workspaceId;

    /**
     * observation 类型，例如 human_decision_observation。
     */
    @TableField("observation_type")
    private String observationType;

    /**
     * 事件来源，例如 human_approval、confirm_patch。
     */
    @TableField("source")
    private String source;

    /**
     * 控制面动作幂等键。
     *
     * <p>该字段独立于 stateDelta 业务事实，用于数据库唯一约束和直接查询，避免扫描并解析 JSON。
     */
    @TableField("idempotency_key")
    private String idempotencyKey;

    /**
     * 可注入模型上下文的脱敏摘要。
     */
    @TableField("summary")
    private String summary;

    /**
     * 状态增量 JSON，只保存模型后续需要理解的结构化事实。
     */
    @TableField("state_delta_json")
    private String stateDeltaJson;

    /**
     * 是否允许注入模型上下文。
     */
    @TableField("visible_to_model")
    private Integer visibleToModel;

    /**
     * 操作人。
     */
    @TableField("operator")
    private String operator;

    /**
     * 链路追踪 ID。
     */
    @TableField("trace_id")
    private String traceId;

    /**
     * 扩展属性 JSON，用于后续灰度字段或非核心结构化信息扩展。
     */
    @TableField("attribute")
    private String attribute;

    /**
     * 逻辑删除标记。
     */
    @TableField("deleted")
    private Integer deleted;

    /**
     * 创建时间，毫秒时间戳。
     */
    @TableField("create_time")
    private Long createTime;

    /**
     * 更新时间，毫秒时间戳。
     */
    @TableField("update_time")
    private Long updateTime;
}
