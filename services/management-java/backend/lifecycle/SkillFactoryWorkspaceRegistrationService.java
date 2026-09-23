package dev.a2flow.management.lifecycle;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

import jakarta.annotation.Resource;

import org.springframework.stereotype.Service;

import dev.a2flow.management.access.AssetCreationTransactionService;
import dev.a2flow.management.lifecycle.domain.SkillDraft;
import dev.a2flow.management.lifecycle.domain.SkillWorkspaceFile;
import dev.a2flow.management.storage.db.repository
        .SkillFactoryWorkspaceFileRepository;
import dev.a2flow.management.storage.db.repository
        .SkillFactoryWorkspaceRepository;

import lombok.extern.slf4j.Slf4j;

/**
 * Skill 注册工作区准备与数据库短事务的编排服务。
 *
 * <p>该类先在数据库事务外原子创建工作区并执行调用方提供的初始化动作，再计算文件摘要，最后调用
 * {@link AssetCreationTransactionService} 原子写入 Skill 元数据、所属专员和负责人。数据库或文件准备
 * 失败时只清理本请求成功创建的目录，不处理已有 Skill、ZIP 导入或版本目录。
 */
@Service
@Slf4j
public class SkillFactoryWorkspaceRegistrationService {

    @Resource
    private SkillFactoryWorkspaceRepository workspaceRepository;

    @Resource
    private SkillFactoryWorkspaceFileRepository fileRepository;

    @Resource
    private AssetCreationTransactionService assetCreationTransactionService;

    /**
     * 创建工作区文件身份并在短事务中持久化 Skill 及初始负责人。
     */
    public SkillDraft register(String operator, String workspaceId, String skillCode,
            Path workspace, Map<String, String> createParams, WorkspaceInitializer initializer)
            throws IOException {
        boolean workspaceCreated = false;
        try {
            workspaceRepository.createWorkspace(workspaceId, Collections.emptyList());
            workspaceCreated = true;
            initializer.initialize();
            List<SkillWorkspaceFile> files = fileRepository.files(workspace);
            String fileTreeDigest = fileRepository.digestWorkspace(workspace);
            SkillDraft draft = assetCreationTransactionService.createSkill(
                    operator, workspaceId, workspace, fileTreeDigest, files.size(), createParams);
            log.info("SkillFactory注册工作区编排完成, skillCode:{}, workspaceId:{}, fileCount:{}",
                    skillCode, workspaceId, files.size());
            return draft.setFileTreeDigest(fileTreeDigest).setFiles(files);
        } catch (IOException | RuntimeException e) {
            if (workspaceCreated) {
                cleanup(workspace, skillCode, e);
            }
            throw e;
        }
    }

    private void cleanup(Path workspace, String skillCode, Exception failure) {
        try (java.util.stream.Stream<Path> stream = Files.walk(workspace)) {
            for (Path item : stream.sorted(Comparator.reverseOrder()).collect(Collectors.toList())) {
                Files.deleteIfExists(item);
            }
            log.warn("SkillFactory注册失败后已清理新建工作区目录, skillCode:{}, workspacePath:{}",
                    skillCode, workspace);
        } catch (IOException cleanupError) {
            failure.addSuppressed(cleanupError);
            log.error("SkillFactory注册失败且清理新建工作区目录失败, skillCode:{}, workspacePath:{}",
                    skillCode, workspace, cleanupError);
        }
    }

    /**
     * 工作区创建后的文件态初始化动作。
     */
    @FunctionalInterface
    public interface WorkspaceInitializer {

        /** 执行工作区内部目录和草稿状态初始化。 */
        void initialize() throws IOException;
    }
}
