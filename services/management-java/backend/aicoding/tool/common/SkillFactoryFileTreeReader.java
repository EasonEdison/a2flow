package dev.a2flow.management.aicoding.tool.common;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import dev.a2flow.management.agentcore.runtime.tool.ToolException;

/** SkillFactory AI Coding 只读目录结构读取器。 */
public final class SkillFactoryFileTreeReader {

    private SkillFactoryFileTreeReader() {
    }

    /** 返回相对指定根目录的完整排序文件清单。 */
    public static List<String> listFiles(Path root) {
        return listFiles(root, Long.MAX_VALUE);
    }

    /** 返回相对指定根目录的排序文件清单。 */
    public static List<String> listFiles(Path root, int maxFiles) {
        return listFiles(root, (long) maxFiles);
    }

    /** 返回目录结构，内容只包含目录和文件名。 */
    public static String renderTree(Path root, int maxDepth, int maxEntries) {
        try (var paths = Files.walk(root, maxDepth)) {
            List<String> entries = paths.skip(1)
                    .sorted()
                    .limit(maxEntries)
                    .map(path -> renderEntry(root, path))
                    .toList();
            return entries.isEmpty() ? "./" : "./\n" + String.join("\n", entries);
        } catch (IOException e) {
            throw new ToolException("Read directory tree failed: " + root, e,
                    ToolException.ErrorCode.EXECUTION_ERROR);
        }
    }

    private static String renderEntry(Path root, Path path) {
        Path relative = root.relativize(path);
        int depth = Math.max(0, relative.getNameCount() - 1);
        String suffix = Files.isDirectory(path) ? "/" : "";
        return "  ".repeat(depth) + "- " + relative.getFileName() + suffix;
    }

    private static List<String> listFiles(Path root, long maxFiles) {
        try (var paths = Files.walk(root)) {
            return paths.filter(Files::isRegularFile)
                    .map(root::relativize)
                    .map(Path::toString)
                    .sorted()
                    .limit(maxFiles)
                    .toList();
        } catch (IOException e) {
            throw new ToolException("List directory failed: " + root, e,
                    ToolException.ErrorCode.EXECUTION_ERROR);
        }
    }
}
