package dev.a2flow.management.model;

/**
 * 组件查询 Tool 的稳定错误码。
 *
 * <p>错误码只描述模型可处理的参数、可信环境、组件身份和发布契约问题，不暴露资产 ID、发布指针、
 * bundle、模板、数据库异常或认证信息。批量查询时每个 componentName 独立返回一个错误码。
 */
public enum ComponentToolErrorCode {
    ARGUMENT_INVALID,
    RELEASE_ENVIRONMENT_REQUIRED,
    RELEASE_ENVIRONMENT_INVALID,
    COMPONENT_NOT_FOUND,
    COMPONENT_DISABLED,
    COMPONENT_RELEASE_NOT_AVAILABLE,
    COMPONENT_RELEASE_INVALID
}
