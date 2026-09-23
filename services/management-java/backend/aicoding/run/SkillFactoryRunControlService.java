package dev.a2flow.management.aicoding.run;

import java.util.concurrent.atomic.AtomicBoolean;

/** Runtime control port. Implementations must use real run state and preserve cancellation identity. */
public interface SkillFactoryRunControlService {
    void registerCancellationToken(String sessionId, String invokeId, AtomicBoolean token);
    void unregisterCancellationToken(String sessionId, String invokeId, AtomicBoolean token);
    SkillFactoryRunStatus markRunning(String sessionId, String invokeId);
    void markCancelled(String sessionId, String invokeId);
    void markFailed(String sessionId, String invokeId);
    void markCompleted(String sessionId, String invokeId);
    SkillFactoryRunStatus queryStatus(String sessionId, String invokeId);
    SkillFactoryRunStatus requestCancel(String sessionId, String invokeId);
    boolean isCancellationRequested(String sessionId, String invokeId, AtomicBoolean token);
}
