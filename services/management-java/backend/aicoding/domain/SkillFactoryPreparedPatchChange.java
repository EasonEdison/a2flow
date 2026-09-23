package dev.a2flow.management.aicoding.domain;

import java.nio.file.Path;

/**
 * AI Coding 单文件三方合并完成后的待执行动作。
 *
 * <p>该对象只携带已经校验的目标路径和动作，不执行文件写入，也不感知审批或会话状态。
 */
public class SkillFactoryPreparedPatchChange {

    public enum Action {
        WRITE,
        DELETE,
        NONE
    }

    private final String relativePath;
    private final Path targetPath;
    private final Action action;
    private final String content;

    private SkillFactoryPreparedPatchChange(String relativePath, Path targetPath, Action action, String content) {
        this.relativePath = relativePath;
        this.targetPath = targetPath;
        this.action = action;
        this.content = content;
    }

    public static SkillFactoryPreparedPatchChange write(String relativePath, Path targetPath, String content) {
        return new SkillFactoryPreparedPatchChange(relativePath, targetPath, Action.WRITE, content);
    }

    public static SkillFactoryPreparedPatchChange delete(String relativePath, Path targetPath) {
        return new SkillFactoryPreparedPatchChange(relativePath, targetPath, Action.DELETE, null);
    }

    public static SkillFactoryPreparedPatchChange none(String relativePath, Path targetPath) {
        return new SkillFactoryPreparedPatchChange(relativePath, targetPath, Action.NONE, null);
    }

    public String getRelativePath() {
        return relativePath;
    }

    public Path getTargetPath() {
        return targetPath;
    }

    public Action getAction() {
        return action;
    }

    public String getContent() {
        return content;
    }
}
