package dev.a2flow.management.lifecycle.domain;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * Workflow 草稿完整 payload 视图。
 *
 * <p>由 WorkflowDefinitionService.getWorkflowDraftPayload 返回，包含完整聚合草稿 JSON、
 * 当前乐观并发版本号和内容摘要，用于前端加载/回显草稿时携带 expectedDraftRevision。
 *
 * <p>上游：WorkflowDefinitionService。
 * <p>下游：sellerdata SkillFactory 统一 dispatcher 的 WORKFLOW_DRAFT_DETAIL 方法。
 * <p>不负责：运行态数据、发布版本快照。
 */
@Data
@Accessors(chain = true)
public class WorkflowDraftPayloadView {

    private String workflowCode;
    private String draftPayloadJson;
    private long draftRevision;
    private String draftDigest;
}
