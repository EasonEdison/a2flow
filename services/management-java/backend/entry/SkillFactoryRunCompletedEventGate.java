package dev.a2flow.management.entry;

import java.util.function.Consumer;

import dev.a2flow.management.event.AiCodingStreamEvent;
import dev.a2flow.management.event.AiCodingStreamEventFactory;

/**
 * AI Coding 成功终态闸门。
 *
 * <p>Runtime 必须先持久化聚合后的完整 Assistant turn，再允许 `RUN_COMPLETED` 进入事件历史、运行状态和
 * SSE。失败和取消终态保持即时传递，并使先到的成功终态失效。
 */
final class SkillFactoryRunCompletedEventGate implements Consumer<AiCodingStreamEvent> {

    private final Consumer<AiCodingStreamEvent> downstream;
    private AiCodingStreamEvent deferredRunCompleted;
    private boolean nonSuccessTerminalObserved;

    SkillFactoryRunCompletedEventGate(Consumer<AiCodingStreamEvent> downstream) {
        this.downstream = downstream;
    }

    @Override
    public synchronized void accept(AiCodingStreamEvent event) {
        String eventType = event.getEventType();
        if (AiCodingStreamEventFactory.EVENT_RUN_COMPLETED.equals(eventType)) {
            if (!nonSuccessTerminalObserved && deferredRunCompleted == null) {
                deferredRunCompleted = event;
            }
            return;
        }
        if (AiCodingStreamEventFactory.EVENT_RUN_FAILED.equals(eventType)
                || AiCodingStreamEventFactory.EVENT_RUN_CANCELLED.equals(eventType)) {
            nonSuccessTerminalObserved = true;
            deferredRunCompleted = null;
        }
        downstream.accept(event);
    }

    /**
     * Assistant turn 持久化成功后释放一次成功终态。
     */
    synchronized void releaseRunCompleted() {
        if (nonSuccessTerminalObserved || deferredRunCompleted == null) {
            return;
        }
        AiCodingStreamEvent event = deferredRunCompleted;
        deferredRunCompleted = null;
        downstream.accept(event);
    }
}
