package dev.a2flow.management.lifecycle;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import jakarta.annotation.Resource;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Service;

import dev.a2flow.management.lifecycle.artifact.SkillPackageArtifactService;
import dev.a2flow.management.lifecycle.artifact.WorkspaceZipArchive;
import dev.a2flow.management.lifecycle.domain.SkillDraft;
import dev.a2flow.management.storage.db.repository.SkillFactoryWorkspaceFileRepository;
import dev.a2flow.management.storage.db.repository.SkillFactoryWorkspaceRepository;

import lombok.extern.slf4j.Slf4j;

/**
 * SkillFactory 工作区 ZIP 下载编排服务。
 *
 * <p>上游统一 method dispatcher 传入已校验的 workspaceId 和 workspace view 参数；本服务只读校验
 * `workspaceId == skillCode`，解析 `preprod/current` 或指定 `online/releases/{version}`，扫描受控文件，
 * 调用 ZIP 产物服务并组装 Base64 页面响应。它不初始化/迁移目录、不保存草稿、不创建 ReleaseArtifact，
 * 也不改变正式发布 ZIP 的 `skillCode/` 顶层目录契约。
 */
@Service
@Slf4j
public class SkillFactoryWorkspaceZipExportService {

    private static final String PARAM_VIEW_MODE = "viewMode";
    private static final String PARAM_VERSION = "version";
    private static final String PARAM_SOURCE_VERSION = "sourceVersion";
    private static final String VIEW_MODE_PREPROD_CURRENT = "PREPROD_CURRENT";
    private static final String VIEW_MODE_ONLINE_RELEASE = "ONLINE_RELEASE";
    private static final String DIR_PREPROD = "preprod";
    private static final String DIR_CURRENT = "current";
    private static final String DIR_ONLINE = "online";
    private static final String DIR_RELEASES = "releases";
    private static final String FIELD_WORKSPACE_ID = "workspaceId";
    private static final String FIELD_SKILL_CODE = "skillCode";
    private static final String FIELD_ZIP_FILE_NAME = "zipFileName";
    private static final String FIELD_ZIP_BASE64 = "zipBase64";
    private static final String FIELD_FILE_COUNT = "fileCount";
    private static final String FIELD_FILE_TREE_DIGEST = "fileTreeDigest";
    private static final String FIELD_VIEW_MODE = "viewMode";
    private static final String FIELD_READONLY = "readonly";
    private static final String FIELD_VERSION = "version";
    private static final String ERROR_SKILL_DRAFT_NOT_FOUND = "skill draft not found";
    private static final String ERROR_WORKSPACE_NOT_FOUND = "workspace does not exist";
    private static final String ERROR_WORKSPACE_IDENTITY_MISMATCH = "workspaceId must equal skillCode";
    private static final String ERROR_RELEASE_VERSION_INVALID = "release version must be positive";
    private static final String ERROR_RELEASE_VERSION_NOT_FOUND = "release version does not exist";
    private static final String EMPTY = "";

    @Resource
    private SkillFactoryWorkspaceRepository workspaceRepository;

    @Resource
    private SkillFactoryWorkspaceFileRepository fileRepository;

    @Resource
    private SkillPackageArtifactService packageArtifactService;

    /**
     * 导出当前选择的 workspace view，并返回页面下载需要的 ZIP 元数据和 Base64 字节。
     */
    public Map<String, Object> export(String workspaceId, Map<String, String> params) throws IOException {
        SkillDraft draft = requireDraft(workspaceId);
        String skillCode = draft.getSkillCode();
        if (!StringUtils.equals(workspaceId, skillCode)) {
            log.warn("SkillFactory工作区ZIP导出失败，工作区身份不一致, workspaceId:{}, skillCode:{}",
                    workspaceId, skillCode);
            throw new IllegalArgumentException(ERROR_WORKSPACE_IDENTITY_MISMATCH);
        }
        WorkspaceExportView workspaceView = resolveView(workspaceId, params, draft.getVersion());
        List<Path> exportFiles = fileRepository.listFiles(workspaceView.path);
        log.info("SkillFactory开始下载工作区ZIP, workspaceId:{}, skillCode:{}, viewMode:{}, version:{}, "
                        + "fileCount:{}",
                workspaceId, skillCode, workspaceView.viewMode, workspaceView.version, exportFiles.size());
        WorkspaceZipArchive.Export export = packageArtifactService.buildWorkspaceExport(
                skillCode, workspaceView.path, exportFiles);
        byte[] zipBytes = export.getZipBytes();
        Map<String, Object> result = new LinkedHashMap<>();
        result.put(FIELD_WORKSPACE_ID, workspaceId);
        result.put(FIELD_SKILL_CODE, skillCode);
        result.put(FIELD_ZIP_FILE_NAME, export.getZipFileName());
        result.put(FIELD_ZIP_BASE64, Base64.getEncoder().encodeToString(zipBytes));
        result.put(FIELD_FILE_COUNT, export.getFileCount());
        result.put(FIELD_FILE_TREE_DIGEST, fileRepository.digestWorkspace(workspaceView.path));
        result.put(FIELD_VIEW_MODE, workspaceView.viewMode);
        result.put(FIELD_READONLY, workspaceView.readonly);
        result.put(FIELD_VERSION, workspaceView.version);
        log.info("SkillFactory工作区ZIP下载数据生成完成, workspaceId:{}, zipFileName:{}, fileCount:{}, bytes:{}",
                workspaceId, export.getZipFileName(), export.getFileCount(), zipBytes.length);
        return result;
    }

    private SkillDraft requireDraft(String workspaceId) {
        SkillDraft draft = workspaceRepository.findDraftByWorkspaceId(workspaceId);
        if (draft == null || StringUtils.isBlank(draft.getSkillCode())) {
            log.warn("SkillFactory工作区ZIP导出失败，Skill草稿不存在, workspaceId:{}", workspaceId);
            throw new IllegalArgumentException(ERROR_SKILL_DRAFT_NOT_FOUND);
        }
        return draft;
    }

    private WorkspaceExportView resolveView(
            String workspaceId, Map<String, String> params, Integer draftVersion) {
        Path identityWorkspace = workspaceRepository.resolveWorkspace(workspaceId).normalize();
        if (!Files.isDirectory(identityWorkspace)) {
            log.warn("SkillFactory工作区ZIP导出失败，身份工作区不存在, workspaceId:{}, workspacePath:{}",
                    workspaceId, identityWorkspace);
            throw new IllegalArgumentException(ERROR_WORKSPACE_NOT_FOUND);
        }
        String viewMode = StringUtils.defaultIfBlank(value(params, PARAM_VIEW_MODE),
                VIEW_MODE_PREPROD_CURRENT);
        if (StringUtils.equals(viewMode, VIEW_MODE_ONLINE_RELEASE)) {
            int version = parseVersion(params);
            Path releaseWorkspace = identityWorkspace.resolve(DIR_ONLINE)
                    .resolve(DIR_RELEASES)
                    .resolve(String.valueOf(version))
                    .normalize();
            if (!releaseWorkspace.startsWith(identityWorkspace) || !Files.isDirectory(releaseWorkspace)) {
                log.warn("SkillFactory工作区ZIP导出失败，正式版本不存在, workspaceId:{}, version:{}, "
                                + "workspacePath:{}",
                        workspaceId, version, releaseWorkspace);
                throw new IllegalArgumentException(ERROR_RELEASE_VERSION_NOT_FOUND);
            }
            return new WorkspaceExportView(
                    releaseWorkspace, VIEW_MODE_ONLINE_RELEASE, version, true);
        }
        Path currentWorkspace = identityWorkspace.resolve(DIR_PREPROD)
                .resolve(DIR_CURRENT)
                .normalize();
        if (!currentWorkspace.startsWith(identityWorkspace) || !Files.isDirectory(currentWorkspace)) {
            log.warn("SkillFactory工作区ZIP导出失败，当前工作区不存在, workspaceId:{}, workspacePath:{}",
                    workspaceId, currentWorkspace);
            throw new IllegalArgumentException(ERROR_WORKSPACE_NOT_FOUND);
        }
        return new WorkspaceExportView(
                currentWorkspace, VIEW_MODE_PREPROD_CURRENT, draftVersion, false);
    }

    private int parseVersion(Map<String, String> params) {
        String value = StringUtils.defaultIfBlank(
                value(params, PARAM_VERSION), value(params, PARAM_SOURCE_VERSION));
        try {
            int version = Integer.parseInt(value);
            if (version > 0) {
                return version;
            }
        } catch (NumberFormatException e) {
            throw new IllegalArgumentException(ERROR_RELEASE_VERSION_INVALID, e);
        }
        throw new IllegalArgumentException(ERROR_RELEASE_VERSION_INVALID);
    }

    private String value(Map<String, String> params, String key) {
        return params == null ? EMPTY : StringUtils.defaultString(params.get(key));
    }

    private static final class WorkspaceExportView {

        private final Path path;
        private final String viewMode;
        private final Integer version;
        private final boolean readonly;

        private WorkspaceExportView(Path path, String viewMode, Integer version, boolean readonly) {
            this.path = path;
            this.viewMode = viewMode;
            this.version = version;
            this.readonly = readonly;
        }
    }
}
