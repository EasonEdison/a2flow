package dev.a2flow.management.lifecycle.domain;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * Workflow 定义元数据视图（不含完整草稿 payload）。
 *
 * <p>该视图由 WorkflowDefinitionService 在 getWorkflow / updateWorkflowBasicInfo 等只读或基础信息
 * 变更操作后返回，仅暴露稳定身份与 common-v2 发布状态投影，不携带 draftPayloadJson。创建结果使用
 * 独立 WorkflowCreateResult，避免把详情投影混入创建响应。
 * 获取完整草稿内容须调用 getWorkflowDraftPayload。
 *
 * <p>上游：WorkflowDefinitionService。
 * <p>下游：sellerdata SkillFactory 统一 dispatcher 的 Workflow 控制面方法。
 * <p>status 只从 common-v2 Change/Build/Version/环境指针投影，不对应 workflow_definition 列。
 * <p>不负责：运行态字段、发布版本指针（preprodVersion/onlineVersion 由发布 Adapter 补充）。
 */
@Data
@Accessors(chain = true)
public class WorkflowDefinitionView {

    private String workflowCode;
    private String specialistCode;
    private String displayName;
    private String description;
    private String status;
    private long draftRevision;
    private String draftDigest;
    private int draftContractVersion;
    private String createdBy;
    private String updatedBy;
    private long createTime;
    private long updateTime;
}
