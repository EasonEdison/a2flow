package dev.a2flow.management.fileguard;

/**
 * workspace 单文件三方文本合并结果。
 *
 * <p>该对象只表达合并成功后的文本或不可自动合并的原因，不读取文件、不写 workspace，
 * 也不携带 Patch、审批或会话状态。
 */
public class WorkspaceTextMergeResult {

    private boolean conflict;
    private String mergedContent;
    private String conflictReason;

    public static WorkspaceTextMergeResult merged(String mergedContent) {
        WorkspaceTextMergeResult result = new WorkspaceTextMergeResult();
        result.setMergedContent(mergedContent);
        return result;
    }

    public static WorkspaceTextMergeResult conflict(String conflictReason) {
        WorkspaceTextMergeResult result = new WorkspaceTextMergeResult();
        result.setConflict(true);
        result.setConflictReason(conflictReason);
        return result;
    }

    public boolean isConflict() {
        return conflict;
    }

    public void setConflict(boolean conflict) {
        this.conflict = conflict;
    }

    public String getMergedContent() {
        return mergedContent;
    }

    public void setMergedContent(String mergedContent) {
        this.mergedContent = mergedContent;
    }

    public String getConflictReason() {
        return conflictReason;
    }

    public void setConflictReason(String conflictReason) {
        this.conflictReason = conflictReason;
    }
}
