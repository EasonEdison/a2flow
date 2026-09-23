package dev.a2flow.management.model;

/**
 * A2UI Application 查询 Tool 的稳定错误码。
 *
 * <p>错误只描述当前可信环境下 Application 不可用或不可变发布合同损坏，不暴露 Build、发布指针、
 * Catalog、凭证或运行时内部标识。批量查询时每个 appCode 独立返回一个错误码。
 */
public enum A2uiApplicationToolErrorCode {
    A2UI_APPLICATION_RELEASE_NOT_AVAILABLE,
    A2UI_APPLICATION_RELEASE_INVALID
}
