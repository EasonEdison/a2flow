package dev.a2flow.management.release.diff;

import java.util.List;

/**
 * SkillFactory 共享发布行级 Diff 引擎。
 *
 * <p>上游领域 Adapter 提供 before/after 资源集合；实现负责路径匹配、JSON 规范化、文本行级比较、
 * 二进制元数据和截断边界。该接口不读取领域事实源，也不执行发布门禁。
 */
public interface ReleaseDiffEngine {

    /**
     * 比较两个资源集合并生成统一发布 Diff 文档。
     *
     * @param from 左侧版本标签
     * @param to 右侧版本标签
     * @param beforeResources 左侧资源集合
     * @param afterResources 右侧资源集合
     * @param query 查询范围和展示参数
     */
    ReleaseDiffDocument compare(String from, String to, List<ReleaseDiffResource> beforeResources,
            List<ReleaseDiffResource> afterResources, ReleaseDiffQuery query);
}
