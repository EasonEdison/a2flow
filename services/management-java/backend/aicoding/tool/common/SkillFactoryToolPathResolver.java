package dev.a2flow.management.aicoding.tool.common;

import java.nio.file.Path;
import java.util.Collection;
import java.util.Map;
import java.util.Objects;

import org.apache.commons.collections4.CollectionUtils;
import org.apache.commons.lang3.StringUtils;
import org.springframework.ai.chat.model.ToolContext;

import dev.a2flow.management.agentcore.runtime.tool.ToolException;

/**
 * SkillFactory AI Coding 工具路径解析器。
 *
 * <p>普通相对路径落在当前编辑工作区；绝对路径只允许落在当前工作区或本轮通过 {@code use_skill}
 * 激活的最新正式 Skill 包根。未激活的绝对路径和路径逃逸都会被拒绝。
 */
public final class SkillFactoryToolPathResolver {

    public static final String CONTEXT_WORKSPACE_PATH = "workspacePath";
    public static final String CONTEXT_BIZ_KEY = "bizKey";
    public static final String CONTEXT_MOUNTED_SKILL_NAMES = "mountedSkillNames";
    public static final String CONTEXT_ACTIVATED_SKILL_ROOTS = "activatedSkillRoots";
    public static final String CONTEXT_CANCEL_CHECKER = "cancelChecker";

    private SkillFactoryToolPathResolver() {
    }

    /** 解析模型传入路径，并校验当前工作区或已挂载 Skill 边界。 */
    public static ResolvedPath resolve(String rawPath, ToolContext toolContext) {
        if (StringUtils.isBlank(rawPath) || Objects.isNull(toolContext)) {
            throw new ToolException("path is required", ToolException.ErrorCode.INVALID_PARAMS);
        }
        Map<String, Object> context = toolContext.getContext();
        Path workspacePath = requiredPath(context, CONTEXT_WORKSPACE_PATH);
        Path requestedPath = Path.of(rawPath);
        if (!requestedPath.isAbsolute()) {
            Path resolved = workspacePath.resolve(requestedPath).normalize();
            requireWithin(resolved, workspacePath, rawPath);
            return new ResolvedPath(resolved, workspacePath, false);
        }
        Path resolved = requestedPath.toAbsolutePath().normalize();
        if (resolved.startsWith(workspacePath)) {
            return new ResolvedPath(resolved, workspacePath, false);
        }
        Path activatedRoot = findActivatedRoot(context, resolved);
        if (activatedRoot == null) {
            throw new ToolException("Absolute path is not activated by use_skill: " + rawPath,
                    ToolException.ErrorCode.PERMISSION_DENIED);
        }
        return new ResolvedPath(resolved, activatedRoot, true);
    }

    private static Path requiredPath(Map<String, Object> context, String key) {
        Object value = context.get(key);
        if (value instanceof Path path) {
            return path.toAbsolutePath().normalize();
        }
        if (value instanceof String path && StringUtils.isNotBlank(path)) {
            return Path.of(path).toAbsolutePath().normalize();
        }
        throw new ToolException(key + " not exists", ToolException.ErrorCode.PERMISSION_DENIED);
    }

    /** 校验 Skill 是否由当前 Agent 显式挂载。 */
    public static void requireMountedSkill(Map<String, Object> context, String skillName) {
        Object value = context.get(CONTEXT_MOUNTED_SKILL_NAMES);
        if (!(value instanceof Collection<?> skillNames)
                || CollectionUtils.isEmpty(skillNames)
                || skillNames.stream().map(String::valueOf).noneMatch(skillName::equals)) {
            throw new ToolException("Skill is not mounted: " + skillName,
                    ToolException.ErrorCode.PERMISSION_DENIED);
        }
    }

    private static Path findActivatedRoot(Map<String, Object> context, Path resolved) {
        Object value = context.get(CONTEXT_ACTIVATED_SKILL_ROOTS);
        if (!(value instanceof Map<?, ?> roots)) {
            return null;
        }
        return roots.values().stream()
                .map(SkillFactoryToolPathResolver::toPath)
                .filter(Objects::nonNull)
                .filter(resolved::startsWith)
                .findFirst()
                .orElse(null);
    }

    private static Path toPath(Object value) {
        if (value instanceof Path path) {
            return path.toAbsolutePath().normalize();
        }
        if (value instanceof String path && StringUtils.isNotBlank(path)) {
            return Path.of(path).toAbsolutePath().normalize();
        }
        return null;
    }

    private static void requireWithin(Path path, Path root, String rawPath) {
        if (!path.startsWith(root)) {
            throw new ToolException("Path outside authorized workspace: " + rawPath,
                    ToolException.ErrorCode.PERMISSION_DENIED);
        }
    }

    /** 工具实际文件路径及其执行工作目录。 */
    public record ResolvedPath(Path path, Path workingDirectory, boolean mountedSkill) {
    }
}
