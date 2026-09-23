package dev.a2flow.management.storage.db.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * Workflow 稳定资产与聚合草稿数据对象。
 *
 * <p>该 DO 对应 {@code workflow_definition} 表，存储 SkillFactory Workflow 的稳定身份标识、
 * 基础信息和完整聚合草稿。workflowCode 由后端生成，创建后不可变；specialistCode 绑定于创建时，
 * 创建后不可修改。
 *
 * <p>上游：WorkflowDefinitionRepository（唯一合法访问入口）。
 * <p>下游：workflow_definition 表（sellerdata schema owner）。
 * <p>不负责：运行态字段（workflow_run / workflow_run_item）、发布版本快照（通过 publish-center-common
 * ReleaseVersion Adapter 管理）、Adviser runtime 状态。
 */
@Data
@Accessors(chain = true)
@TableName("workflow_definition")
public class WorkflowDefinitionDO {

    @TableId(value = "id", type = IdType.AUTO)
    private Long id;

    @TableField("workflow_code")
    private String workflowCode;

    @TableField("specialist_code")
    private String specialistCode;

    @TableField("display_name")
    private String displayName;

    @TableField("description")
    private String description;

    @TableField("draft_contract_version")
    private Integer draftContractVersion;

    @TableField("draft_revision")
    private Long draftRevision;

    @TableField("draft_digest")
    private String draftDigest;

    @TableField("draft_payload_json")
    private String draftPayloadJson;

    @TableField("attribute_json")
    private String attributeJson;

    @TableField("created_by")
    private String createdBy;

    @TableField("updated_by")
    private String updatedBy;

    @TableField("deleted")
    private Integer deleted;

    @TableField("create_time")
    private Long createTime;

    @TableField("update_time")
    private Long updateTime;
}
