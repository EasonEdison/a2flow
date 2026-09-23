package dev.a2flow.management.aicoding.domain;

import java.util.List;

import com.google.common.collect.Lists;

import lombok.Data;

/**
 * SkillFactory AI Coding patch 应用结果。
 *
 * <p>该结果对象只在 AI Coding patch 确认/丢弃链路中传递文件写入结果和 observation
 * 标识。它不保存 patch 正文，不执行文件操作，也不承担 adviser 或 lifecycle 状态同步。
 */
@Data
public class SkillFactoryPatchApplyResult {

    private boolean success;
    private String errorMsg;
    private String workspaceId;
    private String patchId;

    private String observationId;
    private String fileTreeDigest;
    private String baseFileTreeDigest;
    private String errorCode;
    private List<String> changedFiles = Lists.newArrayList();
    private List<String> conflictFiles = Lists.newArrayList();

    public static SkillFactoryPatchApplyResult success(String workspaceId, String patchId,
            List<String> changedFiles, String fileTreeDigest) {
        SkillFactoryPatchApplyResult result = new SkillFactoryPatchApplyResult();
        result.setSuccess(true);
        result.setWorkspaceId(workspaceId);
        result.setPatchId(patchId);
        result.setChangedFiles(changedFiles);
        result.setFileTreeDigest(fileTreeDigest);
        return result;
    }

    public static SkillFactoryPatchApplyResult fail(String workspaceId, String patchId, String errorMsg) {
        SkillFactoryPatchApplyResult result = new SkillFactoryPatchApplyResult();
        result.setSuccess(false);
        result.setWorkspaceId(workspaceId);
        result.setPatchId(patchId);
        result.setErrorMsg(errorMsg);
        return result;
    }

    public static SkillFactoryPatchApplyResult conflict(String workspaceId, String patchId, String errorMsg,
            String baseFileTreeDigest, String currentFileTreeDigest, String errorCode,
            List<String> conflictFiles) {
        SkillFactoryPatchApplyResult result = fail(workspaceId, patchId, errorMsg);
        result.setBaseFileTreeDigest(baseFileTreeDigest);
        result.setFileTreeDigest(currentFileTreeDigest);
        result.setErrorCode(errorCode);
        result.setConflictFiles(conflictFiles);
        return result;
    }
}
