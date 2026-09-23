package dev.a2flow.management.storage.db.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * SkillFactory Authoring Chat 会话数据对象。
 *
 * <p>该 DO 只映射会话身份、scope 和最近沟通状态。会话业务规则由领域仓储处理，页面返回结构不从
 * DO 直接导出。
 */
@Data
@Accessors(chain = true)
@TableName("skill_factory_authoring_session")
public class SkillFactoryAuthoringSessionDO {

    @TableId(value = "id", type = IdType.AUTO)
    private Long id;

    @TableField("session_id")
    private String sessionId;

    @TableField("biz_key")
    private String bizKey;

    @TableField("scope_type")
    private String scopeType;

    @TableField("scope_id")
    private String scopeId;

    @TableField("workspace_id")
    private String workspaceId;

    @TableField("\"title\"")
    private String title;

    @TableField("creator")
    private String creator;

    @TableField("last_operator")
    private String lastOperator;

    @TableField("\"active\"")
    private Integer active;

    @TableField("message_count")
    private Long messageCount;

    @TableField("last_message_time")
    private Long lastMessageTime;

    @TableField("\"attribute\"")
    private String attribute;

    @TableField("deleted")
    private Integer deleted;

    @TableField("create_time")
    private Long createTime;

    @TableField("update_time")
    private Long updateTime;
}
