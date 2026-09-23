package dev.a2flow.management.aicoding.domain;

import java.util.List;

import com.google.common.collect.Lists;

/**
 * AI Coding 一批选中文件的三方合并计算结果。
 */
public class SkillFactoryPatchMergePlan {

    private final List<SkillFactoryPreparedPatchChange> changes = Lists.newArrayList();
    private final List<String> conflictFiles = Lists.newArrayList();

    public void addChange(SkillFactoryPreparedPatchChange change) {
        changes.add(change);
    }

    public void addConflict(String path) {
        conflictFiles.add(path);
    }

    public boolean hasConflict() {
        return !conflictFiles.isEmpty();
    }

    public List<SkillFactoryPreparedPatchChange> getChanges() {
        return changes;
    }

    public List<String> getConflictFiles() {
        return conflictFiles;
    }
}
