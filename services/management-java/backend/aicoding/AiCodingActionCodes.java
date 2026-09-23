package dev.a2flow.management.aicoding;

/**
 * AI Coding 控制命令常量。
 *
 * <p>这些命令来自前端 chat 控制面，用于区分普通模型对话和不需要模型重新规划的 patch
 * 确认/丢弃动作。普通组件中心 AI authoring 复用同一条 chat 流式协议，但不再通过顶层 action
 * 进入硬编码流程，避免绕开模型对话链路。
 */
public final class AiCodingActionCodes {

    public static final String CODING_PATCH_CONFIRM = "CODING_PATCH_CONFIRM";
    public static final String CODING_PATCH_DISCARD = "CODING_PATCH_DISCARD";
    public static final String AUTHORING_UI_ACTION = "AUTHORING_UI_ACTION";
    public static final String CODING_VALIDATE = "CODING_VALIDATE";
    public static final String CODING_VALIDATION_REPAIR = "CODING_VALIDATION_REPAIR";

    private AiCodingActionCodes() {
    }
}
