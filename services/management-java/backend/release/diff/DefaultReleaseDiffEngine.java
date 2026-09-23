package dev.a2flow.management.release.diff;

import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.github.difflib.DiffUtils;
import com.github.difflib.algorithm.myers.MyersDiffWithLinearSpace;
import com.github.difflib.patch.AbstractDelta;
import com.github.difflib.patch.Patch;
import dev.a2flow.management.support.JsonSupport;
import dev.a2flow.management.release.ReleaseDigestUtils;

import lombok.extern.slf4j.Slf4j;

/**
 * SkillFactory 共享发布行级 Diff 引擎默认实现。
 *
 * <p>该实现接收领域层准备好的内存资源，统一完成安全路径校验、文件匹配、JSON key 规范化、
 * 文本行级比较、二进制元数据比较和 hunk 生成。它不读取 workspace、数据库或对象存储，也不判断
 * 发布资格。超过文件、字节或行数限制时会抛出明确错误或在条目上标记 truncated，禁止静默丢内容。
 */
@Service
@Slf4j
public class DefaultReleaseDiffEngine implements ReleaseDiffEngine {

    private static final int DEFAULT_CONTEXT_LINES = 3;
    private static final int MAX_CONTEXT_LINES = 20;
    private static final int MAX_RESOURCE_COUNT = 500;
    private static final int MAX_PATH_LENGTH = 512;
    private static final int MAX_CONTENT_BYTES_PER_SIDE = 2 * 1024 * 1024;
    private static final int MAX_DIFF_LINES_PER_SIDE = 20_000;
    private static final String DEFAULT_LANGUAGE = "text";
    private static final String JSON_LANGUAGE = "json";
    private static final String EMPTY_CONTENT = "";
    private static final String ERROR_RESOURCE_COUNT_EXCEEDED = "发布Diff资源数量超过限制";
    private static final String ERROR_RESOURCE_PATH_REQUIRED = "发布Diff资源路径不能为空";
    private static final String ERROR_RESOURCE_PATH_TOO_LONG = "发布Diff资源路径超过限制";
    private static final String ERROR_RESOURCE_PATH_UNSAFE = "发布Diff资源路径不安全";
    private static final String ERROR_RESOURCE_PATH_DUPLICATED = "发布Diff资源路径重复";
    private static final String ERROR_CONTENT_TYPE_REQUIRED = "发布Diff资源内容类型不能为空";
    private static final String ERROR_BINARY_CONTENT_PRESENT = "二进制发布Diff资源不得携带内容";
    private static final String ERROR_BINARY_DIGEST_REQUIRED = "二进制发布Diff资源摘要不能为空";
    private static final String ERROR_JSON_INVALID = "发布Diff JSON资源解析失败";
    private static final String ERROR_CONTEXT_LINES_INVALID = "发布Diff上下文行数必须在0到20之间";
    private static final String ERROR_ENTRY_NOT_FOUND = "发布Diff条目不存在";
    private static final String ERROR_DIFF_CONTEXT_INCONSISTENT = "发布Diff算法返回的上下文区间不一致";
    private static final String TRUNCATED_CONTENT_BYTES = "文件任一侧内容超过2MB，未生成行级Diff";
    private static final String TRUNCATED_LINE_COUNT = "文件任一侧行数超过20000行，未生成行级Diff";
    private static final String HUNK_HEADER_FORMAT = "@@ -%d,%d +%d,%d @@";

    /**
     * 比较两组领域资源，生成列表或单文件详情。
     *
     * <p>列表请求仍会计算未截断文件的增加/删除统计，但不会携带 hunks；详情请求仅为 entryPath
     * 生成 hunks，避免一次返回所有文件内容。
     */
    @Override
    public ReleaseDiffDocument compare(String from, String to, List<ReleaseDiffResource> beforeResources,
            List<ReleaseDiffResource> afterResources, ReleaseDiffQuery query) {
        ReleaseDiffQuery normalizedQuery = normalizeQuery(query);
        Map<String, NormalizedResource> before = normalizeResources(beforeResources);
        Map<String, NormalizedResource> after = normalizeResources(afterResources);
        log.info("共享发布开始计算行级Diff, from:{}, to:{}, beforeFiles:{}, afterFiles:{}, entryPath:{}",
                from, to, before.size(), after.size(), normalizedQuery.getEntryPath());
        List<ReleaseDiffEntry> allEntries = compareResources(before, after, normalizedQuery);
        ReleaseDiffSummary summary = summary(allEntries);
        List<ReleaseDiffEntry> responseEntries = filterEntries(allEntries, normalizedQuery.getEntryPath());
        log.info("共享发布行级Diff计算完成, from:{}, to:{}, changedFiles:{}, additions:{}, deletions:{}, "
                        + "truncated:{}",
                from, to, summary.getChangedFiles(), summary.getAdditions(), summary.getDeletions(),
                summary.getTruncated());
        return new ReleaseDiffDocument()
                .setFrom(StringUtils.defaultString(from))
                .setTo(StringUtils.defaultString(to))
                .setRequestedEntryPath(normalizedQuery.getEntryPath())
                .setViewMode(normalizedQuery.getViewMode())
                .setSummary(summary)
                .setEntries(responseEntries);
    }

    private ReleaseDiffQuery normalizeQuery(ReleaseDiffQuery query) {
        ReleaseDiffQuery normalized = query == null ? new ReleaseDiffQuery() : query;
        int contextLines = normalized.getContextLines() == null
                ? DEFAULT_CONTEXT_LINES : normalized.getContextLines();
        if (contextLines < 0 || contextLines > MAX_CONTEXT_LINES) {
            throw new IllegalArgumentException(ERROR_CONTEXT_LINES_INVALID);
        }
        normalized.setContextLines(contextLines);
        if (normalized.getViewMode() == null) {
            normalized.setViewMode(ReleaseDiffViewMode.UNIFIED);
        }
        if (StringUtils.isNotBlank(normalized.getEntryPath())) {
            normalized.setEntryPath(validatePath(normalized.getEntryPath()));
        }
        return normalized;
    }

    private Map<String, NormalizedResource> normalizeResources(List<ReleaseDiffResource> resources) {
        List<ReleaseDiffResource> safeResources = resources == null ? List.of() : resources;
        if (safeResources.size() > MAX_RESOURCE_COUNT) {
            throw new IllegalArgumentException(ERROR_RESOURCE_COUNT_EXCEEDED + ": " + safeResources.size());
        }
        Map<String, NormalizedResource> result = new LinkedHashMap<>();
        for (ReleaseDiffResource resource : safeResources) {
            NormalizedResource normalized = normalizeResource(resource);
            if (result.putIfAbsent(normalized.path, normalized) != null) {
                throw new IllegalArgumentException(ERROR_RESOURCE_PATH_DUPLICATED + ": " + normalized.path);
            }
        }
        return result;
    }

    private NormalizedResource normalizeResource(ReleaseDiffResource resource) {
        if (resource == null || StringUtils.isBlank(resource.getPath())) {
            throw new IllegalArgumentException(ERROR_RESOURCE_PATH_REQUIRED);
        }
        String path = validatePath(resource.getPath());
        String oldPath = StringUtils.isBlank(resource.getOldPath())
                ? null : validatePath(resource.getOldPath());
        ReleaseDiffContentType contentType = resource.getContentType();
        if (contentType == null) {
            throw new IllegalArgumentException(ERROR_CONTENT_TYPE_REQUIRED + ": " + path);
        }
        if (contentType == ReleaseDiffContentType.BINARY) {
            if (StringUtils.isNotEmpty(resource.getContent())) {
                throw new IllegalArgumentException(ERROR_BINARY_CONTENT_PRESENT + ": " + path);
            }
            if (StringUtils.isBlank(resource.getDigest())) {
                throw new IllegalArgumentException(ERROR_BINARY_DIGEST_REQUIRED + ": " + path);
            }
            return new NormalizedResource(path, oldPath, contentType,
                    StringUtils.defaultIfBlank(resource.getLanguage(), DEFAULT_LANGUAGE),
                    resource.getDigest(), resource.getSize() == null ? 0L : resource.getSize(), null);
        }
        String content = StringUtils.defaultString(resource.getContent());
        if (contentType == ReleaseDiffContentType.JSON) {
            content = canonicalJson(path, content);
        }
        byte[] contentBytes = content.getBytes(StandardCharsets.UTF_8);
        return new NormalizedResource(path, oldPath, contentType,
                StringUtils.defaultIfBlank(resource.getLanguage(),
                        contentType == ReleaseDiffContentType.JSON ? JSON_LANGUAGE : language(path)),
                StringUtils.defaultIfBlank(resource.getDigest(), ReleaseDigestUtils.sha256(content)),
                resource.getSize() == null ? (long) contentBytes.length : resource.getSize(), content);
    }

    private String validatePath(String rawPath) {
        String path = StringUtils.trim(rawPath).replace('\\', '/');
        if (path.length() > MAX_PATH_LENGTH) {
            throw new IllegalArgumentException(ERROR_RESOURCE_PATH_TOO_LONG + ": " + path.length());
        }
        if (StringUtils.isBlank(path) || path.startsWith("/") || path.endsWith("/")
                || path.contains("//") || path.equals(".") || path.equals("..")) {
            throw new IllegalArgumentException(ERROR_RESOURCE_PATH_UNSAFE + ": " + path);
        }
        for (String segment : path.split("/")) {
            if (segment.isEmpty() || segment.equals(".") || segment.equals("..")) {
                throw new IllegalArgumentException(ERROR_RESOURCE_PATH_UNSAFE + ": " + path);
            }
        }
        return path;
    }

    private String canonicalJson(String path, String content) {
        try {
            JsonNode root = JsonSupport.mapper().readTree(content);
            if (root == null) {
                throw new IllegalArgumentException(ERROR_JSON_INVALID + ": " + path);
            }
            return JsonSupport.mapper().writerWithDefaultPrettyPrinter()
                    .writeValueAsString(sortJson(root));
        } catch (IllegalArgumentException e) {
            throw e;
        } catch (Exception e) {
            log.warn("共享发布JSON资源规范化失败, path:{}", path, e);
            throw new IllegalArgumentException(ERROR_JSON_INVALID + ": " + path, e);
        }
    }

    private JsonNode sortJson(JsonNode node) {
        if (node.isObject()) {
            ObjectNode sorted = JsonSupport.mapper().createObjectNode();
            Map<String, JsonNode> fields = new TreeMap<>();
            Iterator<Map.Entry<String, JsonNode>> iterator = node.fields();
            while (iterator.hasNext()) {
                Map.Entry<String, JsonNode> field = iterator.next();
                fields.put(field.getKey(), sortJson(field.getValue()));
            }
            fields.forEach(sorted::set);
            return sorted;
        }
        if (node.isArray()) {
            ArrayNode sorted = JsonSupport.mapper().createArrayNode();
            node.forEach(child -> sorted.add(sortJson(child)));
            return sorted;
        }
        return node;
    }

    private List<ReleaseDiffEntry> compareResources(Map<String, NormalizedResource> before,
            Map<String, NormalizedResource> after, ReleaseDiffQuery query) {
        List<ResourcePair> pairs = matchResources(before, after);
        List<ReleaseDiffEntry> entries = new ArrayList<>();
        for (ResourcePair pair : pairs) {
            ReleaseDiffEntry entry = comparePair(pair, query);
            if (entry != null) {
                entries.add(entry);
            }
        }
        entries.sort(Comparator.comparing(ReleaseDiffEntry::getPath));
        return entries;
    }

    private List<ResourcePair> matchResources(Map<String, NormalizedResource> before,
            Map<String, NormalizedResource> after) {
        List<ResourcePair> pairs = new ArrayList<>();
        Set<String> matchedBefore = new HashSet<>();
        Set<String> matchedAfter = new HashSet<>();
        for (NormalizedResource afterResource : after.values()) {
            NormalizedResource beforeResource = StringUtils.isBlank(afterResource.oldPath)
                    ? before.get(afterResource.path) : before.get(afterResource.oldPath);
            if (beforeResource != null) {
                pairs.add(new ResourcePair(beforeResource, afterResource));
                matchedBefore.add(beforeResource.path);
                matchedAfter.add(afterResource.path);
            }
        }
        for (NormalizedResource afterResource : after.values()) {
            if (matchedAfter.contains(afterResource.path)) {
                continue;
            }
            NormalizedResource renameSource = before.values().stream()
                    .filter(item -> !matchedBefore.contains(item.path))
                    .filter(item -> StringUtils.equals(item.digest, afterResource.digest))
                    .findFirst()
                    .orElse(null);
            if (renameSource != null) {
                pairs.add(new ResourcePair(renameSource, afterResource));
                matchedBefore.add(renameSource.path);
                matchedAfter.add(afterResource.path);
            }
        }
        before.values().stream()
                .filter(item -> !matchedBefore.contains(item.path))
                .forEach(item -> pairs.add(new ResourcePair(item, null)));
        after.values().stream()
                .filter(item -> !matchedAfter.contains(item.path))
                .forEach(item -> pairs.add(new ResourcePair(null, item)));
        return pairs;
    }

    private ReleaseDiffEntry comparePair(ResourcePair pair, ReleaseDiffQuery query) {
        NormalizedResource before = pair.before;
        NormalizedResource after = pair.after;
        ReleaseDiffChangeType changeType = changeType(before, after);
        if (changeType == ReleaseDiffChangeType.MODIFIED
                && equivalentContent(before, after)) {
            return null;
        }
        ReleaseDiffContentType contentType = contentType(before, after);
        ReleaseDiffEntry entry = new ReleaseDiffEntry()
                .setPath(after == null ? before.path : after.path)
                .setOldPath(before == null || after == null || StringUtils.equals(before.path, after.path)
                        ? null : before.path)
                .setChangeType(changeType)
                .setContentType(contentType)
                .setLanguage(after == null ? before.language : after.language)
                .setBeforeDigest(before == null ? null : before.digest)
                .setAfterDigest(after == null ? null : after.digest)
                .setBeforeSize(before == null ? null : before.size)
                .setAfterSize(after == null ? null : after.size)
                .setAdditions(0)
                .setDeletions(0);
        if (contentType == ReleaseDiffContentType.BINARY) {
            return entry;
        }
        String beforeContent = before == null ? EMPTY_CONTENT : before.content;
        String afterContent = after == null ? EMPTY_CONTENT : after.content;
        List<String> beforeLines = lines(beforeContent);
        List<String> afterLines = lines(afterContent);
        String truncatedReason = truncatedReason(beforeContent, afterContent, beforeLines, afterLines);
        if (truncatedReason != null) {
            entry.setTruncated(true)
                    .setTruncatedReason(truncatedReason);
            setTruncatedLineCounts(entry, changeType, beforeLines.size(), afterLines.size());
            log.warn("共享发布文件Diff被显式截断, path:{}, reason:{}, beforeLines:{}, afterLines:{}",
                    entry.getPath(), truncatedReason, beforeLines.size(), afterLines.size());
            return entry;
        }
        List<ReleaseDiffLine> operations = lineDiff(beforeLines, afterLines);
        entry.setAdditions((int) operations.stream()
                        .filter(line -> line.getType() == ReleaseDiffLineType.ADD).count())
                .setDeletions((int) operations.stream()
                        .filter(line -> line.getType() == ReleaseDiffLineType.DELETE).count());
        if (StringUtils.equals(query.getEntryPath(), entry.getPath())) {
            entry.setHunks(hunks(operations, query.getContextLines()));
        }
        return entry;
    }

    private ReleaseDiffChangeType changeType(NormalizedResource before, NormalizedResource after) {
        if (before == null) {
            return ReleaseDiffChangeType.ADDED;
        }
        if (after == null) {
            return ReleaseDiffChangeType.DELETED;
        }
        if (!StringUtils.equals(before.path, after.path)) {
            return ReleaseDiffChangeType.RENAMED;
        }
        return ReleaseDiffChangeType.MODIFIED;
    }

    private ReleaseDiffContentType contentType(NormalizedResource before, NormalizedResource after) {
        if (before != null && before.contentType == ReleaseDiffContentType.BINARY
                || after != null && after.contentType == ReleaseDiffContentType.BINARY) {
            return ReleaseDiffContentType.BINARY;
        }
        if (before != null && before.contentType == ReleaseDiffContentType.JSON
                || after != null && after.contentType == ReleaseDiffContentType.JSON) {
            return ReleaseDiffContentType.JSON;
        }
        return ReleaseDiffContentType.TEXT;
    }

    private boolean equivalentContent(NormalizedResource before, NormalizedResource after) {
        if (before.contentType == ReleaseDiffContentType.BINARY
                || after.contentType == ReleaseDiffContentType.BINARY) {
            return StringUtils.equals(before.digest, after.digest);
        }
        return StringUtils.equals(before.content, after.content);
    }

    /**
     * 设置被截断条目的行数统计。
     *
     * <p>新增或删除文件的单侧行数无需执行比较即可精确得出；修改和重命名文件如果被截断，
     * 无法得出真实的增删行数，必须返回空值，避免把整份文件行数伪装成变更行数。
     */
    private void setTruncatedLineCounts(ReleaseDiffEntry entry, ReleaseDiffChangeType changeType,
            int beforeLineCount, int afterLineCount) {
        if (changeType == ReleaseDiffChangeType.ADDED) {
            entry.setAdditions(afterLineCount).setDeletions(0);
            return;
        }
        if (changeType == ReleaseDiffChangeType.DELETED) {
            entry.setAdditions(0).setDeletions(beforeLineCount);
            return;
        }
        entry.setAdditions(null).setDeletions(null);
    }

    private String truncatedReason(String beforeContent, String afterContent,
            List<String> beforeLines, List<String> afterLines) {
        int beforeByteCount = beforeContent.getBytes(StandardCharsets.UTF_8).length;
        int afterByteCount = afterContent.getBytes(StandardCharsets.UTF_8).length;
        if (beforeByteCount > MAX_CONTENT_BYTES_PER_SIDE
                || afterByteCount > MAX_CONTENT_BYTES_PER_SIDE) {
            return TRUNCATED_CONTENT_BYTES;
        }
        if (beforeLines.size() > MAX_DIFF_LINES_PER_SIDE
                || afterLines.size() > MAX_DIFF_LINES_PER_SIDE) {
            return TRUNCATED_LINE_COUNT;
        }
        return null;
    }

    private List<String> lines(String content) {
        if (StringUtils.isEmpty(content)) {
            return List.of();
        }
        return List.of(content.split("\\R", -1));
    }

    /**
     * 使用成熟开源库的线性空间 Myers 算法生成完整行操作序列。
     *
     * <p>第三方库只负责计算 delta；本方法把 delta 转换为平台统一的上下文、删除和新增行，
     * 后续 hunk、行号和展示契约仍由共享发布层维护。
     */
    private List<ReleaseDiffLine> lineDiff(List<String> before, List<String> after) {
        Patch<String> patch = DiffUtils.diff(before, after, new MyersDiffWithLinearSpace<>());
        List<AbstractDelta<String>> deltas = new ArrayList<>(patch.getDeltas());
        deltas.sort(Comparator
                .comparingInt((AbstractDelta<String> delta) -> delta.getSource().getPosition())
                .thenComparingInt(delta -> delta.getTarget().getPosition()));
        List<ReleaseDiffLine> result = new ArrayList<>();
        int oldIndex = 0;
        int newIndex = 0;
        int oldLineNumber = 1;
        int newLineNumber = 1;
        for (AbstractDelta<String> delta : deltas) {
            int sourcePosition = delta.getSource().getPosition();
            int targetPosition = delta.getTarget().getPosition();
            if (sourcePosition - oldIndex != targetPosition - newIndex) {
                throw new IllegalStateException(ERROR_DIFF_CONTEXT_INCONSISTENT);
            }
            while (oldIndex < sourcePosition) {
                result.add(line(ReleaseDiffLineType.CONTEXT, oldLineNumber++, newLineNumber++,
                        before.get(oldIndex)));
                oldIndex++;
                newIndex++;
            }
            for (String deletedLine : delta.getSource().getLines()) {
                result.add(line(ReleaseDiffLineType.DELETE, oldLineNumber++, null, deletedLine));
                oldIndex++;
            }
            for (String addedLine : delta.getTarget().getLines()) {
                result.add(line(ReleaseDiffLineType.ADD, null, newLineNumber++, addedLine));
                newIndex++;
            }
        }
        if (before.size() - oldIndex != after.size() - newIndex) {
            throw new IllegalStateException(ERROR_DIFF_CONTEXT_INCONSISTENT);
        }
        while (oldIndex < before.size()) {
            result.add(line(ReleaseDiffLineType.CONTEXT, oldLineNumber++, newLineNumber++,
                    before.get(oldIndex)));
            oldIndex++;
            newIndex++;
        }
        return orderChangedLinesForReview(result);
    }

    /**
     * 按代码审阅习惯把同一连续变更块中的删除行放在新增行之前。
     *
     * <p>线性空间 Myers 对替换可能返回 INSERT 后 DELETE；这里仅调整展示顺序，不改变
     * delta、行号或增删统计，使统一视图与 GitHub 常见的删除后新增顺序一致。
     */
    private List<ReleaseDiffLine> orderChangedLinesForReview(List<ReleaseDiffLine> operations) {
        List<ReleaseDiffLine> result = new ArrayList<>();
        int index = 0;
        while (index < operations.size()) {
            if (operations.get(index).getType() == ReleaseDiffLineType.CONTEXT) {
                result.add(operations.get(index++));
                continue;
            }
            List<ReleaseDiffLine> changedLines = new ArrayList<>();
            while (index < operations.size()
                    && operations.get(index).getType() != ReleaseDiffLineType.CONTEXT) {
                changedLines.add(operations.get(index++));
            }
            changedLines.stream()
                    .filter(item -> item.getType() == ReleaseDiffLineType.DELETE)
                    .forEach(result::add);
            changedLines.stream()
                    .filter(item -> item.getType() == ReleaseDiffLineType.ADD)
                    .forEach(result::add);
        }
        return result;
    }

    private ReleaseDiffLine line(ReleaseDiffLineType type, Integer oldLineNumber,
            Integer newLineNumber, String content) {
        return new ReleaseDiffLine()
                .setType(type)
                .setOldLineNumber(oldLineNumber)
                .setNewLineNumber(newLineNumber)
                .setContent(content);
    }

    private List<ReleaseDiffHunk> hunks(List<ReleaseDiffLine> operations, int contextLines) {
        List<int[]> ranges = new ArrayList<>();
        int index = 0;
        while (index < operations.size()) {
            while (index < operations.size()
                    && operations.get(index).getType() == ReleaseDiffLineType.CONTEXT) {
                index++;
            }
            if (index >= operations.size()) {
                break;
            }
            int start = Math.max(0, index - contextLines);
            int lastChange = index;
            while (index < operations.size()) {
                if (operations.get(index).getType() != ReleaseDiffLineType.CONTEXT) {
                    lastChange = index;
                }
                if (index - lastChange > contextLines) {
                    break;
                }
                index++;
            }
            int end = Math.min(operations.size() - 1, lastChange + contextLines);
            if (!ranges.isEmpty() && start <= ranges.get(ranges.size() - 1)[1] + 1) {
                ranges.get(ranges.size() - 1)[1] = end;
            } else {
                ranges.add(new int[] {start, end});
            }
        }
        List<ReleaseDiffHunk> result = new ArrayList<>();
        for (int[] range : ranges) {
            List<ReleaseDiffLine> hunkLines = new ArrayList<>(
                    operations.subList(range[0], range[1] + 1));
            int oldStart = previousLineCount(operations, range[0], true) + 1;
            int newStart = previousLineCount(operations, range[0], false) + 1;
            int oldLines = lineCount(hunkLines, true);
            int newLines = lineCount(hunkLines, false);
            result.add(new ReleaseDiffHunk()
                    .setOldStart(oldStart)
                    .setOldLines(oldLines)
                    .setNewStart(newStart)
                    .setNewLines(newLines)
                    .setHeader(String.format(HUNK_HEADER_FORMAT, oldStart, oldLines, newStart, newLines))
                    .setLines(hunkLines));
        }
        return result;
    }

    private int previousLineCount(List<ReleaseDiffLine> lines, int endExclusive, boolean oldSide) {
        return lineCount(lines.subList(0, endExclusive), oldSide);
    }

    private int lineCount(List<ReleaseDiffLine> lines, boolean oldSide) {
        return (int) lines.stream()
                .filter(line -> oldSide ? line.getOldLineNumber() != null : line.getNewLineNumber() != null)
                .count();
    }

    private ReleaseDiffSummary summary(List<ReleaseDiffEntry> entries) {
        int additions = entries.stream().mapToInt(entry -> entry.getAdditions() == null ? 0 : entry.getAdditions())
                .sum();
        int deletions = entries.stream().mapToInt(entry -> entry.getDeletions() == null ? 0 : entry.getDeletions())
                .sum();
        List<String> truncatedPaths = entries.stream()
                .filter(entry -> Boolean.TRUE.equals(entry.getTruncated()))
                .map(ReleaseDiffEntry::getPath)
                .toList();
        return new ReleaseDiffSummary()
                .setChangedFiles(entries.size())
                .setAdditions(additions)
                .setDeletions(deletions)
                .setTruncated(!truncatedPaths.isEmpty())
                .setTruncatedReason(truncatedPaths.isEmpty()
                        ? null : "以下文件Diff已截断: " + String.join(", ", truncatedPaths));
    }

    private List<ReleaseDiffEntry> filterEntries(List<ReleaseDiffEntry> entries, String entryPath) {
        if (StringUtils.isBlank(entryPath)) {
            return entries;
        }
        ReleaseDiffEntry matched = entries.stream()
                .filter(entry -> StringUtils.equals(entry.getPath(), entryPath))
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException(ERROR_ENTRY_NOT_FOUND + ": " + entryPath));
        return List.of(matched);
    }

    private String language(String path) {
        int extensionIndex = path.lastIndexOf('.');
        if (extensionIndex < 0 || extensionIndex == path.length() - 1) {
            return DEFAULT_LANGUAGE;
        }
        String extension = StringUtils.lowerCase(path.substring(extensionIndex + 1));
        return switch (extension) {
            case "md", "markdown" -> "markdown";
            case "yaml", "yml" -> "yaml";
            case "js", "jsx" -> "javascript";
            case "ts", "tsx" -> "typescript";
            case "java" -> "java";
            case "py" -> "python";
            case "sh", "bash" -> "shell";
            case "html", "htm" -> "html";
            case "css", "less", "scss" -> extension;
            case "xml" -> "xml";
            default -> DEFAULT_LANGUAGE;
        };
    }

    private static final class NormalizedResource {
        private final String path;
        private final String oldPath;
        private final ReleaseDiffContentType contentType;
        private final String language;
        private final String digest;
        private final long size;
        private final String content;

        private NormalizedResource(String path, String oldPath, ReleaseDiffContentType contentType,
                String language, String digest, long size, String content) {
            this.path = path;
            this.oldPath = oldPath;
            this.contentType = contentType;
            this.language = language;
            this.digest = digest;
            this.size = size;
            this.content = content;
        }
    }

    private static final class ResourcePair {
        private final NormalizedResource before;
        private final NormalizedResource after;

        private ResourcePair(NormalizedResource before, NormalizedResource after) {
            this.before = before;
            this.after = after;
        }
    }
}
