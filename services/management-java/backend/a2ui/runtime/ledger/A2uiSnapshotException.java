package dev.a2flow.management.a2ui.runtime.ledger;

/**
 * A2UI 运行态快照归并异常。
 *
 * <p>该异常只表达协议消息无法安全归并为 canonical snapshot，不负责转换成 HTTP/SSE 错误，
 * 也不触发 CapabilityAction 重试或旧 CARD_CONTAINER 降级。</p>
 */
public class A2uiSnapshotException extends IllegalArgumentException {

    public A2uiSnapshotException(String message) {
        super(message);
    }

    public A2uiSnapshotException(String message, Throwable cause) {
        super(message, cause);
    }
}
