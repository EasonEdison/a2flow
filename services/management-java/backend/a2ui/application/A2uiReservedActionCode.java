package dev.a2flow.management.a2ui.application;

import java.util.Arrays;

/**
 * Adviser Workflow Engine 代码拥有的 A2UI Action 保留码。
 *
 * <p>上游 Application 保存和发布使用本枚举拒绝作者态占用，下游 Adviser 运行态使用同名协议码
 * 路由到本地 Workflow typed use case。本枚举不读取 M 配置、KConf 或请求 context，也不提供
 * CapabilityAction fallback。
 */
public enum A2uiReservedActionCode {

    WORKFLOW_START,
    WORKFLOW_SUBMIT,
    WORKFLOW_RETRY,
    WORKFLOW_SKIP,
    WORKFLOW_STOP;

    /** 精确判断一个 actionCode 是否属于 Workflow 运行态保留集合。 */
    public static boolean isReserved(String actionCode) {
        return Arrays.stream(values()).anyMatch(value -> value.name().equals(actionCode));
    }
}
