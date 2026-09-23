package dev.a2flow.management.aicoding.tool.common;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

import org.apache.commons.lang3.StringUtils;
import org.springframework.ai.chat.model.ToolContext;
import org.springframework.ai.tool.ToolCallback;
import org.springframework.ai.tool.definition.ToolDefinition;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.agentcore.runtime.tool.ToolException;
import dev.a2flow.management.aicoding.tool.common.SkillFactoryToolPathResolver.ResolvedPath;

/** SkillFactory AI Coding 专用只读文件工具，支持当前工作区和 use_skill 已激活的正式 Skill 包。 */
public class SkillFactoryReadToolCallback implements ToolCallback {

    public static final String TOOL_NAME = "read";
    private static final String FIELD_PATH = "path";
    private static final int MAX_CONTENT_CHARS = 50000;
    private static final String INPUT_SCHEMA = """
            {
              "type":"object",
              "properties":{"path":{"type":"string","description":"Workspace or mounted Skill file path"}},
              "required":["path"]
            }
            """;

    @Override
    public ToolDefinition getToolDefinition() {
        return ToolDefinition.builder()
                .name(TOOL_NAME)
                .description("Read an exact file from the current workspace or a use_skill-activated absolute "
                        + "Skill path. This tool does not read directories; use tree for directories.")
                .inputSchema(INPUT_SCHEMA)
                .build();
    }

    @Override
    public String call(String toolInput) {
        return StringUtils.EMPTY;
    }

    /** 读取授权目录中的 UTF-8 文本文件。 */
    @Override
    public String call(String toolInput, ToolContext toolContext) {
        Map<String, Object> input = JsonSupport.fromJson(toolInput);
        Object pathValue = input == null ? null : input.get(FIELD_PATH);
        String rawPath = pathValue == null ? StringUtils.EMPTY : String.valueOf(pathValue);
        ResolvedPath resolved =
                SkillFactoryToolPathResolver.resolve(rawPath, toolContext);
        Path path = resolved.path();
        if (Files.isDirectory(path)) {
            throw new ToolException("Path is a directory, not a file. Use tree instead: " + rawPath,
                    ToolException.ErrorCode.INVALID_PARAMS);
        }
        if (!Files.isRegularFile(path)) {
            throw new ToolException("File not found: " + rawPath, ToolException.ErrorCode.FILE_NOT_FOUND);
        }
        try {
            return StringUtils.abbreviate(Files.readString(path, StandardCharsets.UTF_8), MAX_CONTENT_CHARS);
        } catch (IOException e) {
            throw new ToolException("Read file failed: " + rawPath, e, ToolException.ErrorCode.EXECUTION_ERROR);
        }
    }
}
