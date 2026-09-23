package dev.a2flow.management.lifecycle.domain;

import lombok.Data;
import lombok.experimental.Accessors;

/**
 * Skill 草稿的轻量展示元数据。
 *
 * <p>上游是 Adviser Intelligent Lab 的 Skill 元数据解析器，下游数据源是 sellerdata 的
 * {@code skill_draft} Repository。本对象只承载稳定 Skill code 和中英文展示名，不携带工作区文件、
 * 发布指针、发布状态或负责人关系，避免 Lab 为展示名称读取重量级工作区详情。
 */
@Data
@Accessors(chain = true)
public class SkillDraftMetadata {

    /** Skill 稳定唯一标识。 */
    private String skillCode;

    /** Skill 中文展示名。 */
    private String skillNameCn;

    /** Skill 英文展示名。 */
    private String skillNameEn;
}
