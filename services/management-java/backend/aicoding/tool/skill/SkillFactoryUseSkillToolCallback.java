package dev.a2flow.management.aicoding.tool.skill;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.apache.commons.lang3.StringUtils;
import org.springframework.ai.chat.model.ToolContext;
import org.springframework.ai.tool.ToolCallback;
import org.springframework.ai.tool.definition.ToolDefinition;

import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.agentcore.runtime.skill.SkillFactoryMountedSkillResolver;
import dev.a2flow.management.agentcore.runtime.skill.SkillFactoryMountedSkillResolver.ResolvedSkillPackage;
import dev.a2flow.management.agentcore.runtime.tool.ToolException;
import dev.a2flow.management.aicoding.tool.common.SkillFactoryFileTreeReader;
import dev.a2flow.management.aicoding.tool.common.SkillFactoryToolPathResolver;

import lombok.extern.slf4j.Slf4j;

/**
 * SkillFactory 创建态 Skill 激活工具。
 *
 * <p>工具只允许激活当前 Agent 已挂载的 Skill，并固定选择最新正式版。返回值包含完整 SKILL.md、
 * 目录结构和可信绝对包根。调用方可选择一次性加载所有支持资源；默认仍由 read 按需读取，
 * 目录由 tree 查看，脚本由 python 执行。
 */
@Slf4j
public class SkillFactoryUseSkillToolCallback implements ToolCallback {

    public static final String TOOL_NAME = "use_skill";
    private static final String FIELD_SKILL_CODE = "skillCode";
    private static final String FIELD_INCLUDE_ALL_RESOURCES = "includeAllResources";
    private static final String FILE_SKILL_MARKDOWN = "SKILL.md";
    private static final String FIELD_RESOURCE_PATH = "path";
    private static final String FIELD_RESOURCE_ENCODING = "encoding";
    private static final String FIELD_RESOURCE_CONTENT = "content";
    private static final String FIELD_RESOURCE_SIZE = "size";
    private static final String FIELD_RESOURCES = "resources";
    private static final String FIELD_RESOURCE_COUNT = "resourceCount";
    private static final String ENCODING_UTF8 = "UTF-8";
    private static final String ENCODING_BASE64 = "BASE64";
    private static final int MAX_TREE_DEPTH = 8;
    private static final int MAX_TREE_ENTRIES = 300;
    private static final int MAX_SUPPORT_FILES = 300;
    private static final String INPUT_SCHEMA = """
            {
              "type":"object",
              "properties":{
                "skillCode":{"type":"string","description":"Agent 已挂载的 Skill code"},
                "includeAllResources":{
                  "type":"boolean",
                  "description":"是否一次性返回全部支持资源内容；默认 false，仅返回 SKILL.md、绝对目录、目录树和支持文件清单",
                  "default":false
                }
              },
              "required":["skillCode"]
            }
            """;

    private final SkillFactoryMountedSkillResolver mountedSkillResolver;

    public SkillFactoryUseSkillToolCallback(SkillFactoryMountedSkillResolver mountedSkillResolver) {
        this.mountedSkillResolver = mountedSkillResolver;
    }

    @Override
    public ToolDefinition getToolDefinition() {
        return ToolDefinition.builder()
                .name(TOOL_NAME)
                .description("Activate an Agent-mounted Skill. Returns the latest formal SKILL.md, absolute Skill "
                        + "directory and file tree. Set includeAllResources=true to return every support resource; "
                        + "otherwise use tree for directories and read for exact files.")
                .inputSchema(INPUT_SCHEMA)
                .build();
    }

    @Override
    public String call(String toolInput) {
        return StringUtils.EMPTY;
    }

    /** 激活当前 ONLINE 指针对应的正式 Skill 包，并将绝对包根登记到本轮工具上下文。 */
    @Override
    public String call(String toolInput, ToolContext toolContext) {
        Map<String, Object> input = JsonSupport.fromJson(toolInput);
        Object skillCodeValue = input == null ? null : input.get(FIELD_SKILL_CODE);
        String skillCode = skillCodeValue == null ? StringUtils.EMPTY
                : StringUtils.trimToEmpty(String.valueOf(skillCodeValue));
        boolean includeAllResources = resolveIncludeAllResources(input);
        SkillFactoryToolPathResolver.requireMountedSkill(toolContext.getContext(), skillCode);
        Object bizKeyValue = toolContext.getContext().get(SkillFactoryToolPathResolver.CONTEXT_BIZ_KEY);
        String bizKey = bizKeyValue == null ? StringUtils.EMPTY : String.valueOf(bizKeyValue);
        ResolvedSkillPackage skillPackage = mountedSkillResolver.resolveEffectiveOnlineRelease(bizKey, skillCode)
                .orElseThrow(() -> new ToolException("Formal Skill release not found: " + skillCode,
                        ToolException.ErrorCode.FILE_NOT_FOUND));
        registerActivatedRoot(toolContext.getContext(), skillPackage);
        String skillMarkdown = readSkillMarkdown(skillPackage.packageRoot());
        List<String> packageFiles = includeAllResources
                ? SkillFactoryFileTreeReader.listFiles(skillPackage.packageRoot())
                : SkillFactoryFileTreeReader.listFiles(skillPackage.packageRoot(), MAX_SUPPORT_FILES);
        List<String> supportFiles = packageFiles.stream()
                .filter(path -> !StringUtils.equals(path, FILE_SKILL_MARKDOWN))
                .toList();
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("skillCode", skillCode);
        result.put("version", skillPackage.version());
        result.put("skillDirectory", skillPackage.packageRoot().toString());
        result.put("skillMarkdown", skillMarkdown);
        result.put("directoryTree", SkillFactoryFileTreeReader.renderTree(
                skillPackage.packageRoot(), MAX_TREE_DEPTH, MAX_TREE_ENTRIES));
        result.put("supportFiles", supportFiles);
        result.put("fileCount", supportFiles.size() + 1);
        if (includeAllResources) {
            result.put(FIELD_RESOURCES, readAllResources(skillPackage.packageRoot(), supportFiles));
            result.put(FIELD_RESOURCE_COUNT, supportFiles.size());
        }
        result.put("usage", "目录使用 tree；文件使用 read 并传 skillDirectory 下的绝对文件路径；"
                + "Python 脚本使用 python 并传绝对脚本路径。禁止把绝对路径写入 Skill 包文件。");
        log.info("SkillFactory已激活挂载Skill正式包, bizKey={}, skillCode={}, version={}, fileCount={}, "
                        + "includeAllResources={}",
                bizKey, skillCode, skillPackage.version(), supportFiles.size() + 1, includeAllResources);
        return JsonSupport.toJSON(result);
    }

    /** 解析是否一次性加载全部支持资源，避免字符串等非布尔入参被静默接受。 */
    private boolean resolveIncludeAllResources(Map<String, Object> input) {
        Object value = input == null ? null : input.get(FIELD_INCLUDE_ALL_RESOURCES);
        if (value == null) {
            return false;
        }
        if (value instanceof Boolean booleanValue) {
            return booleanValue;
        }
        throw new ToolException(FIELD_INCLUDE_ALL_RESOURCES + " must be boolean",
                ToolException.ErrorCode.INVALID_PARAMS);
    }

    /** 读取正式 Skill 包中的全部支持资源；UTF-8 文本直接返回，二进制资源使用 Base64。 */
    private List<Map<String, Object>> readAllResources(Path packageRoot, List<String> supportFiles) {
        return supportFiles.stream()
                .map(relativePath -> readResource(packageRoot, relativePath))
                .toList();
    }

    private Map<String, Object> readResource(Path packageRoot, String relativePath) {
        Path normalizedRoot = packageRoot.toAbsolutePath().normalize();
        Path resourcePath = normalizedRoot.resolve(relativePath).normalize();
        if (!resourcePath.startsWith(normalizedRoot) || Files.isSymbolicLink(resourcePath)) {
            throw new ToolException("Resource path is not allowed: " + relativePath,
                    ToolException.ErrorCode.PERMISSION_DENIED);
        }
        try {
            byte[] content = Files.readAllBytes(resourcePath);
            Map<String, Object> resource = new LinkedHashMap<>();
            resource.put(FIELD_RESOURCE_PATH, relativePath);
            resource.put(FIELD_RESOURCE_SIZE, content.length);
            putResourceContent(resource, content);
            return resource;
        } catch (IOException e) {
            throw new ToolException("Read Skill resource failed: " + relativePath, e,
                    ToolException.ErrorCode.EXECUTION_ERROR);
        }
    }

    private void putResourceContent(Map<String, Object> resource, byte[] content) {
        try {
            String textContent = StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(content))
                    .toString();
            resource.put(FIELD_RESOURCE_ENCODING, ENCODING_UTF8);
            resource.put(FIELD_RESOURCE_CONTENT, textContent);
        } catch (CharacterCodingException e) {
            resource.put(FIELD_RESOURCE_ENCODING, ENCODING_BASE64);
            resource.put(FIELD_RESOURCE_CONTENT, Base64.getEncoder().encodeToString(content));
        }
    }

    @SuppressWarnings("unchecked")
    private void registerActivatedRoot(Map<String, Object> context, ResolvedSkillPackage skillPackage) {
        Object roots = context.get(SkillFactoryToolPathResolver.CONTEXT_ACTIVATED_SKILL_ROOTS);
        if (!(roots instanceof Map<?, ?>)) {
            throw new ToolException("activatedSkillRoots not exists", ToolException.ErrorCode.PERMISSION_DENIED);
        }
        ((Map<String, Path>) roots).put(skillPackage.skillCode(), skillPackage.packageRoot());
    }

    private String readSkillMarkdown(Path packageRoot) {
        Path skillFile = packageRoot.resolve(FILE_SKILL_MARKDOWN);
        try {
            return Files.readString(skillFile, StandardCharsets.UTF_8);
        } catch (IOException e) {
            throw new ToolException("Read SKILL.md failed", e, ToolException.ErrorCode.EXECUTION_ERROR);
        }
    }
}
