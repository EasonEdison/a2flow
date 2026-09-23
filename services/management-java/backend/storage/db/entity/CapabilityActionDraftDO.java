package dev.a2flow.management.storage.db.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * 能力中心草稿数据对象。
 *
 * <p>该 DO 对应 `skill_capability_action_draft` 表，只保存 M 端编辑中的完整规范化草稿。
 * 已发布版本、执行绑定快照、审计和 Skill 绑定会在后续独立表中建模；当前 DO 不承载运行时 Tool
 * 或外部调用状态。
 */
@Data
@Accessors(chain = true)
@TableName("skill_capability_action_draft")
public class CapabilityActionDraftDO {

    @TableId(value = "id", type = IdType.AUTO)
    private Long id;

    @TableField("draft_id")
    private String draftId;

    @TableField("action_code")
    private String actionCode;

    @TableField("name_cn")
    private String nameCn;

    @TableField("business_domain")
    private String businessDomain;

    @TableField("technical_owner")
    private String technicalOwner;

    @TableField("source_type")
    private String sourceType;

    @TableField("side_effect_level")
    private String sideEffectLevel;

    @TableField("approval_policy")
    private String approvalPolicy;

    @TableField("status")
    private String status;

    @TableField("revision")
    private Integer revision;

    @TableField("draft_json")
    private String draftJson;

    @TableField("validation_json")
    private String validationJson;

    @TableField("creator")
    private String creator;

    @TableField("modifier")
    private String modifier;

    @TableField("deleted")
    private Integer deleted;

    @TableField("create_time")
    private Long createTime;

    @TableField("update_time")
    private Long updateTime;
}
