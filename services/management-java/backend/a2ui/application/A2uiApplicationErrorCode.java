package dev.a2flow.management.a2ui.application;

/**
 * A2UI Application 编译阶段稳定错误码。
 *
 * <p>上游 M 端按 code 定位 draft/Build 门禁，下游 Artifact Runtime 不依赖可变中文文案。本枚举只
 * 表达领域失败，不绑定外部 HTTP/SSE 状态，也不为非法 draft 定义 fallback。
 */
public enum A2uiApplicationErrorCode {
    DRAFT_INVALID("A2UI_APPLICATION_DRAFT_INVALID", "Application draft 不完整"),
    PROTOCOL_UNSUPPORTED("A2UI_PROTOCOL_UNSUPPORTED", "协议版本不受支持"),
    CATALOG_SUPPORT_MISSING("A2UI_CATALOG_SUPPORT_MISSING", "Catalog 发布快照不完整"),
    CATALOG_ENVIRONMENT_MISMATCH(
            "A2UI_CATALOG_ENVIRONMENT_MISMATCH", "Build 固定的 Catalog 未在目标环境精确发布"),
    CATALOG_COMPONENT_AMBIGUOUS("A2UI_CATALOG_COMPONENT_AMBIGUOUS", "Catalog 组件类型不唯一"),
    COMPONENT_NOT_AVAILABLE("A2UI_COMPONENT_NOT_AVAILABLE", "组件不在精确 Catalog 快照中"),
    SHOW_INVALID("A2UI_SHOW_INVALID", "ShowTemplate 结构不合法"),
    PARAMS_SCHEMA_INVALID("A2UI_PARAMS_SCHEMA_INVALID", "Application 参数 Schema 结构或约束不合法"),
    PARAMS_SCHEMA_UNSUPPORTED("A2UI_PARAMS_SCHEMA_UNSUPPORTED", "Application 参数 Schema 包含运行时尚未支持的规则"),
    SHOW_INPUT_AUTHORITY_FORBIDDEN("A2UI_SHOW_INPUT_AUTHORITY_FORBIDDEN", "Show 输入暴露执行 authority"),
    ACTION_UNBOUND("A2UI_ACTION_UNBOUND", "Show Action 未绑定业务能力"),
    ACTION_BINDING_ORPHAN("A2UI_ACTION_BINDING_ORPHAN", "ActionBinding 不属于 Show Action"),
    ACTION_BINDING_AMBIGUOUS("A2UI_ACTION_BINDING_AMBIGUOUS", "ActionBinding 存在歧义"),
    ACTION_CODE_RESERVED("A2UI_ACTION_CODE_RESERVED", "ActionCode 已由 Workflow 运行态保留"),
    ACTION_CONTEXT_SCHEMA_MISMATCH("A2UI_ACTION_CONTEXT_SCHEMA_MISMATCH", "Action context 超出 Binding schema"),
    INTERACTIVE_COMPLETION_ACTION_REQUIRED(
            "A2UI_INTERACTIVE_COMPLETION_ACTION_REQUIRED", "交互式 Application 至少需要一个完成 Action"),
    DISPLAY_ONLY_COMPLETION_ACTION_FORBIDDEN(
            "A2UI_DISPLAY_ONLY_COMPLETION_ACTION_FORBIDDEN", "仅展示 Application 不允许完成 Workflow 交互"),
    BUSINESS_SUCCESS_PREDICATE_REQUIRED(
            "A2UI_BUSINESS_SUCCESS_PREDICATE_REQUIRED", "完成 Action 必须配置业务成功判定"),
    BUSINESS_SUCCESS_PREDICATE_INVALID(
            "A2UI_BUSINESS_SUCCESS_PREDICATE_INVALID", "业务成功判定不是受支持的封闭表达式"),
    CAPABILITY_REFERENCE_INVALID(
            "A2UI_CAPABILITY_REFERENCE_INVALID", "CapabilityAction 当前生效能力不存在或不可用"),
    CAPABILITY_SCHEMA_INCOMPATIBLE(
            "A2UI_CAPABILITY_SCHEMA_INCOMPATIBLE", "CapabilityAction 当前 schema 与映射不兼容"),
    BINDING_PARAM_SCHEMA_INCOMPATIBLE(
            "A2UI_BINDING_PARAM_SCHEMA_INCOMPATIBLE", "Application 参数与 Binding 能力输入不兼容"),
    CAPABILITY_LOAD_SIDE_EFFECT_INVALID(
            "A2UI_CAPABILITY_LOAD_SIDE_EFFECT_INVALID", "LoadBinding 只能引用只读能力"),
    RESULT_ADAPTER_INVALID("A2UI_RESULT_ADAPTER_INVALID", "ResultAdapter 配置不合法"),
    BUILD_ID_INVALID("A2UI_BUILD_ID_INVALID", "Build ID 生成失败"),
    SOURCE_STALE("A2UI_APPLICATION_SOURCE_STALE", "Application source 已发生变化"),
    HISTORY_SNAPSHOT_INVALID("A2UI_APPLICATION_HISTORY_SNAPSHOT_INVALID",
            "历史版本快照不完整或资产不匹配，无法恢复编排，请选择其他版本");

    private final String code;
    private final String message;

    A2uiApplicationErrorCode(String code, String message) {
        this.code = code;
        this.message = message;
    }

    public String getCode() {
        return code;
    }

    public String getMessage() {
        return message;
    }
}
