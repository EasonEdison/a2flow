package dev.a2flow.management.fileguard;

import java.util.List;

import com.google.common.collect.Lists;

import lombok.Data;

/**
 * SkillFactory workspace 快照差异。
 *
 * <p>该对象描述两次文件快照之间新增、修改、删除的相对路径，用于形成模型可见 observation
 * 或 patch CAS 冲突提示。它不包含文件完整内容，避免把大文件或敏感信息直接注入日志和事件。
 */
@Data
public class WorkspaceSnapshotDiff {

    private List<String> addedFiles = Lists.newArrayList();
    private List<String> modifiedFiles = Lists.newArrayList();
    private List<String> deletedFiles = Lists.newArrayList();

    public boolean hasChange() {
        return !addedFiles.isEmpty() || !modifiedFiles.isEmpty() || !deletedFiles.isEmpty();
    }

    public int changedFileCount() {
        return addedFiles.size() + modifiedFiles.size() + deletedFiles.size();
    }
}
