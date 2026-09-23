package dev.a2flow.management.support;

import java.util.UUID;
import org.slf4j.MDC;

/** Use an incoming application MDC trace when present; otherwise allocate a correlation ID. */
public final class TraceIds {
    private TraceIds() { }
    public static String currentOrCreate() {
        String existing = MDC.get("traceId");
        return existing == null || existing.isBlank() ? UUID.randomUUID().toString() : existing;
    }
}
