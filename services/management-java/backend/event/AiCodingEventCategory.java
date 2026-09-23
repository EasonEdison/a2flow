package dev.a2flow.management.event;

import lombok.AllArgsConstructor;
import lombok.Getter;

/**
 * SkillFactory AI Coding 事件分类。
 *
 * <p>该枚举用于前端把业务事件分区展示，例如 patch 卡片和 observation 时间线。
 */
@Getter
@AllArgsConstructor
public enum AiCodingEventCategory {

    /**
     * 文件 patch 类事件。
     */
    PATCH("PATCH", "文件变更"),


    /**
     * M 端创作态业务交互事件。
     */
    AUTHORING_UI("AUTHORING_UI", "创作态交互"),

    /**
     * 结构化创作草稿快照、增量和校验结果。
     */
    AUTHORING_DRAFT("AUTHORING_DRAFT", "结构化创作草稿"),

    /**
     * Agent observation 类事件。
     */
    OBSERVATION("OBSERVATION", "模型观测"),

    /**
     * AG-UI-like 执行过程事件。
     */
    EXECUTION_TRACE("EXECUTION_TRACE", "执行过程"),

    /**
     * AI Coding 动态运行验证事件。
     */
    VALIDATION("VALIDATION", "运行验证"),

    /**
     * 失败事件。
     */
    ERROR("ERROR", "失败");

    private final String code;
    private final String desc;
}
