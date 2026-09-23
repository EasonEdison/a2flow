package dev.a2flow.management.aicoding.tool.common;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

import org.apache.commons.lang3.StringUtils;
import org.springframework.ai.chat.model.ToolContext;
import org.springframework.ai.tool.ToolCallback;
import org.springframework.ai.tool.definition.ToolDefinition;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.agentcore.runtime.tool.ToolException;

/** SkillFactory AI Coding 专用目录树工具，支持当前工作区和 use_skill 已激活的正式 Skill 包。 */
public class SkillFactoryTreeToolCallback implements ToolCallback {

    public static final String TOOL_NAME = "tree";
    private static final String FIELD_PATH = "path";
    private static final String FIELD_MAX_DEPTH = "maxDepth";
    private static final int DEFAULT_MAX_DEPTH = 4;
    private static final int MAX_DEPTH = 10;
    private static final int MAX_ENTRIES = 500;
    private static final String INPUT_SCHEMA = """
            {
              "type":"object",
              "properties":{
                "path":{"type":"string","description":"目录路径；当前工作区可用相对路径，use_skill 返回目录使用绝对路径"},
                "maxDepth":{"type":"integer","minimum":1,"maximum":10,"default":4}
              }
            }
            """;

    @Override
    public ToolDefinition getToolDefinition() {
        return ToolDefinition.builder()
                .name(TOOL_NAME)
                .description("List a directory tree. Use this for directories; read only accepts exact file paths.")
                .inputSchema(INPUT_SCHEMA)
                .build();
    }

    @Override
    public String call(String toolInput) {
        return StringUtils.EMPTY;
    }

    /** 读取授权目录结构，不读取文件内容。 */
    @Override
    public String call(String toolInput, ToolContext toolContext) {
        Map<String, Object> input = StringUtils.isBlank(toolInput) ? Map.of()
                : JsonSupport.fromJson(toolInput);
        String rawPath = input == null || input.get(FIELD_PATH) == null
                ? "." : StringUtils.defaultIfBlank(String.valueOf(input.get(FIELD_PATH)), ".");
        int maxDepth = resolveMaxDepth(input);
        SkillFactoryToolPathResolver.ResolvedPath resolved =
                SkillFactoryToolPathResolver.resolve(rawPath, toolContext);
        Path path = resolved.path();
        if (!Files.isDirectory(path)) {
            throw new ToolException("Directory not found: " + rawPath, ToolException.ErrorCode.FILE_NOT_FOUND);
        }
        return SkillFactoryFileTreeReader.renderTree(path, maxDepth, MAX_ENTRIES);
    }

    private int resolveMaxDepth(Map<String, Object> input) {
        if (input == null || !(input.get(FIELD_MAX_DEPTH) instanceof Number number)) {
            return DEFAULT_MAX_DEPTH;
        }
        return Math.max(1, Math.min(number.intValue(), MAX_DEPTH));
    }
}
