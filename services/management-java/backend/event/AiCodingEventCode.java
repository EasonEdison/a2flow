package dev.a2flow.management.event;

import lombok.AllArgsConstructor;
import lombok.Getter;

/**
 * SkillFactory AI Coding 事件编码。
 *
 * <p>该枚举定义 AI Coding runtime payload 的业务事件码。它不替代公共传输事件类型，
 * 也不表示模型内容 block，只用于 patch、审批、业务卡片和 observation 等系统产物的结构化
 * payload，避免把 SkillFactory 专属事件散落为裸字符串。
 */
@Getter
@AllArgsConstructor
public enum AiCodingEventCode {

    /**
     * 模型生成了 patch 草稿，等待操作者预览后应用或丢弃。
     */
    PATCH_PROPOSED("PATCH_PROPOSED", "patch草稿已生成"),

    /**
     * patch 已应用到 workspace。
     */
    PATCH_APPLIED("PATCH_APPLIED", "patch已应用"),

    /**
     * patch 已被丢弃。
     */
    PATCH_DISCARDED("PATCH_DISCARDED", "patch已丢弃"),

    /**
     * patch 确认时检测到 workspace 已变化，应用被拒绝。
     */
    PATCH_CONFLICT("PATCH_CONFLICT", "patch确认冲突"),

    /**
     * M 端业务交互卡片。
     */
    A2UI_MESSAGE("A2UI_MESSAGE", "M端业务交互卡片"),

    /**
     * M 端业务动作形成的 observation 已写入。
     */
    AUTHORING_OBSERVATION("AUTHORING_OBSERVATION", "创作态observation已写入"),

    /**
     * 结构化创作草稿的完整快照或增量修改建议已生成。
     */
    AUTHORING_DRAFT_CHANGE("AUTHORING_DRAFT_CHANGE", "创作草稿修改建议已生成"),

    /**
     * 能力草稿静态校验报告已生成。
     */
    CAPABILITY_DRAFT_VALIDATED("CAPABILITY_DRAFT_VALIDATED", "能力草稿静态校验完成"),

    /**
     * workspace 外部变更形成的 observation 已写入。
     */
    WORKSPACE_CHANGED_OBSERVATION("WORKSPACE_CHANGED_OBSERVATION", "workspace变更observation已写入"),

    /**
     * AG-UI-like 执行过程事件。
     */
    AG_UI_EVENT("AG_UI_EVENT", "执行过程事件"),

    /**
     * 动态运行验证任务已启动。
     */
    VALIDATION_TASK_STARTED("VALIDATION_TASK_STARTED", "运行验证任务已启动"),

    /**
     * 动态运行验证报告已生成。
     */
    VALIDATION_REPORT_CREATED("VALIDATION_REPORT_CREATED", "运行验证报告已生成"),

    /**
     * 用户请求主 Agent 根据验证报告修复。
     */
    VALIDATION_REPAIR_REQUESTED("VALIDATION_REPAIR_REQUESTED", "运行验证修复已请求"),

    /**
     * AI Coding 失败。
     */
    FAILED("FAILED", "AI Coding失败");

    private final String code;
    private final String desc;
}
