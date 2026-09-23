package dev.a2flow.management.lifecycle.domain;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * Workflow 草稿 CAS 更新成功结果。
 *
 * <p>由 WorkflowDefinitionService.updateWorkflowDraft 在 CAS 成功后返回，携带递增后的新
 * draftRevision 和重新计算的 draftDigest，供前端下次保存时作为 expectedDraftRevision 传入。
 *
 * <p>上游：WorkflowDefinitionService。
 * <p>下游：sellerdata SkillFactory 统一 dispatcher 的 WORKFLOW_DRAFT_UPDATE 方法。
 */
@Data
@Accessors(chain = true)
public class WorkflowDraftUpdateResult {

    private String workflowCode;
    private long draftRevision;
    private String draftDigest;
}
