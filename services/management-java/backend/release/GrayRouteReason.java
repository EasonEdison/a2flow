package dev.a2flow.management.release;

/**
 * 环境资产解析选择 stable 或 candidate 时的确定性原因。
 *
 * <p>该值用于日志、监控和调用方诊断，不允许调用方反向覆盖路由结果。
 */
public enum GrayRouteReason {

    NO_CANDIDATE,
    FULL_PERCENTAGE,
    WHITELIST,
    PERCENTAGE,
    STABLE_BUCKET,
    MISSING_USER_ID
}
