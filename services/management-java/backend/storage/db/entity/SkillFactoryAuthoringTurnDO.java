package dev.a2flow.management.storage.db.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * SkillFactory Authoring Chat 对话 turn 数据对象。
 *
 * <p>该表保存用户输入和欢迎消息等可回放 turn。模型流式事件由独立事件表保存，避免文本消息与运行
 * 过程混为一体。
 */
@Data
@Accessors(chain = true)
@TableName("skill_factory_authoring_turn")
public class SkillFactoryAuthoringTurnDO {

    @TableId(value = "id", type = IdType.AUTO)
    private Long id;

    @TableField("turn_id")
    private String turnId;

    @TableField("session_id")
    private String sessionId;

    @TableField("\"role\"")
    private String role;

    @TableField("message_id")
    private String messageId;

    @TableField("\"text\"")
    private String text;

    @TableField("\"operator\"")
    private String operator;

    @TableField("\"timestamp\"")
    private Long timestamp;

    @TableField("\"attribute\"")
    private String attribute;

    @TableField("deleted")
    private Integer deleted;

    @TableField("create_time")
    private Long createTime;

    @TableField("update_time")
    private Long updateTime;
}
