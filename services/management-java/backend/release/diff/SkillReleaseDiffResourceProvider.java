package dev.a2flow.management.release.diff;

import java.util.List;
import java.util.Map;

import dev.a2flow.management.release.ReleaseModels.AssetSnapshot;

/**
 * Skill lifecycle 向共享发布层提供受控文件资源的边界接口。
 *
 * <p>实现归属 skill-workbench-lifecycle：它只能读取当前 `preprod/current` 和目标
 * `online/releases/{version}`，负责路径安全、UTF-8/JSON/BINARY 分类和内容读取，不计算行级 Diff。
 * 共享发布 Adapter 只依赖本接口，不直接访问 workspace 目录或 lifecycle 私有实现。
 */
public interface SkillReleaseDiffResourceProvider {

    /** 读取当前可编辑 `preprod/current` 的真实文件资源。 */
    List<ReleaseDiffResource> currentResources(String skillCode, Map<String, String> params);

    /** 读取目标正式数字版本 `online/releases/{version}` 的真实文件资源。 */
    List<ReleaseDiffResource> versionResources(String skillCode, Integer version,
            AssetSnapshot targetSnapshot, Map<String, String> params);
}
