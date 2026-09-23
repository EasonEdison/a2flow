package dev.a2flow.management.lifecycle;

/**
 * Workflow 草稿乐观并发冲突异常。
 *
 * <p>当 updateWorkflowDraft 的 expectedDraftRevision 与数据库当前版本不符时抛出。
 * 上层 RPC handler 应将此异常映射为 DRAFT_CONFLICT 错误码（HTTP 409 语义），
 * 前端收到后必须重新拉取最新草稿再重试。
 *
 * <p>不携带 payload、operator 或其他敏感业务内容。
 */
public class WorkflowDraftConflictException extends IllegalStateException {

    private final String workflowCode;
    private final long expectedDraftRevision;

    public WorkflowDraftConflictException(String workflowCode, long expectedDraftRevision) {
        super("DRAFT_CONFLICT: workflowCode=" + workflowCode
                + ", expectedRevision=" + expectedDraftRevision);
        this.workflowCode = workflowCode;
        this.expectedDraftRevision = expectedDraftRevision;
    }

    public String getWorkflowCode() {
        return workflowCode;
    }

    public long getExpectedDraftRevision() {
        return expectedDraftRevision;
    }
}
